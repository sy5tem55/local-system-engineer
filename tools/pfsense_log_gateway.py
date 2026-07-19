#!/usr/bin/env python3
"""
pfSense Log Gateway — Lightweight aggregation proxy for LSE.

Sits between pfSense REST API and the LSE (Qwen 27B).
Reduces raw log context consumption by 90-99% through:
  - Server-side filtering (pattern matching before LSE sees data)
  - Aggregation (N identical entries → 1 summary line)
  - Cursor-based incremental fetching (only deltas)
  - Ollama summarizer integration (semantic rolling summaries)
  - Structured metrics (no logs needed for 70% of queries)
  - Hard response size cap (MAX_RESPONSE_BYTES) — prevents context overflow

Usage:
  python3 pfsense_log_gateway.py [--port 9191] [--pf-url https://pfsense.home.arpa]

Endpoints:
  GET /compact?hours=24            — Dense audit summary (<4KB, use for full reports)
  GET /summary?hours=24&top=10     — Structured firewall summary
  GET /tail?lines=50&pattern=BLOCK — Last N lines matching pattern
  GET /events?since=TIMESTAMP      — Incremental delta since last fetch
  GET /metrics                     — System metrics (no logs)
  GET /health                      — Gateway health check
  POST /summarize                  — Ollama 3B delta summarization
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip install requests", file=sys.stderr)
    sys.exit(1)

# ── Configuration ──────────────────────────────────────────────────────────────

DEFAULT_PORT = 9191
DEFAULT_PFSENSE_URL = "https://pfsense.home.arpa"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "qwen2.5:3b"

STATE_DIR = Path("/opt/local-se/tmp")
CURSOR_FILE = STATE_DIR / "log-cursor.json"
SUMMARY_STATE_FILE = STATE_DIR / "rolling-summary.json"
GATEWAY_LOG = Path("/opt/local-se/logs/gateway.log")

# Hard cap on JSON response size — prevents context overflow if aggregation
# produces unexpectedly large output. ~32KB ≈ ~8k tokens, well within 96k ctx.
MAX_RESPONSE_BYTES = 32_000

# pfSense log format patterns (flexible for different pfSense versions)
LOG_PATTERNS = {
    "block": re.compile(
        r"(?P<timestamp>\S+\s+\S+\s+\S+)\s+"
        r"(?P<action>block|pass|match)\s+"
        r"(?P<dir>\<|\>)\s+"
        r"(?P<iface>\w+)\s+"
        r"(?P<proto>\w+)\s+"
        r"(?P<src>[\d.]+)\s+"
        r"(?P<src_port>\d+)\s+"
        r"(?P<dst>[\d.]+)\s+"
        r"(?P<dst_port>\d+)",
        re.IGNORECASE,
    ),
    "generic": re.compile(
        r"(?P<timestamp>\S+\s+\S+\s+\S+)\s+(?P<message>.+)"
    ),
}


# ── pfSense REST API Client ───────────────────────────────────────────────────

class PfSenseClient:
    """Thin wrapper around pfSense REST API v2."""

    def __init__(self, base_url: str, api_key: str | None = None, ca_cert: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("PFSENSE_API_KEY", "")
        self.ca_cert = ca_cert or "/opt/local-se/cert/pfsense-webgui-ca.crt"

        self.session = requests.Session()
        if self.api_key:
            self.session.headers["X-API-Key"] = self.api_key

    def _verify_ssl(self) -> bool | str:
        if self.ca_cert and Path(self.ca_cert).exists():
            return self.ca_cert
        return False

    def get(self, endpoint: str, params: dict | None = None) -> dict | list:
        url = f"{self.base_url}{endpoint}"
        try:
            resp = self.session.get(
                url, params=params, verify=self._verify_ssl(), timeout=30,
            )
            if resp.status_code == 401:
                return {"error": "pfSense auth failed — check API key", "status": 401}
            if resp.status_code == 403:
                return {"error": "pfSense forbidden — insufficient permissions", "status": 403}
            if resp.status_code >= 500:
                return {"error": f"pfSense server error {resp.status_code}", "status": resp.status_code}
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.SSLError:
            if self._verify_ssl():
                resp = self.session.get(url, params=params, verify=False, timeout=30)
                if resp.status_code == 401:
                    return {"error": "pfSense auth failed — check API key", "status": 401}
                resp.raise_for_status()
                return resp.json()
            raise
        except requests.exceptions.Timeout:
            return {"error": "pfSense API timeout (30s)", "status": "timeout"}
        except requests.exceptions.ConnectionError:
            return {"error": "pfSense unreachable — check network/DNS", "status": "unreachable"}
        except requests.exceptions.HTTPError as e:
            return {"error": f"pfSense HTTP error: {e}", "status": "http_error"}

    def get_firewall_logs(self, hours: int = 24, limit: int = 5000) -> list[dict]:
        data = self.get("/api/v2/status/logs/firewall")
        if isinstance(data, dict) and "error" in data and "data" not in data:
            return [{"error": data["error"], "_source": "gateway"}]
        if isinstance(data, dict) and "data" in data:
            logs = data["data"]
        elif isinstance(data, list):
            logs = data
        else:
            logs = []

        if hours and logs:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            filtered = []
            for entry in logs:
                entry_time = self._parse_log_time(entry)
                if entry_time and entry_time >= cutoff:
                    filtered.append(entry)
                if len(filtered) >= limit:
                    break
            logs = filtered

        return logs[:limit]

    def get_system_info(self) -> dict:
        return self.get("/api/v2/system/info")

    def get_interface_stats(self) -> dict:
        return self.get("/api/v2/status/interface")

    def get_dhcp_leases(self) -> list:
        data = self.get("/api/v2/dhcp/server/lease")
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        return data if isinstance(data, list) else []

    def _parse_log_time(self, entry: dict) -> datetime | None:
        for key in ("time", "timestamp", "datetime"):
            if key in entry:
                try:
                    val = entry[key]
                    if isinstance(val, (int, float)):
                        return datetime.fromtimestamp(val, tz=timezone.utc)
                    return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    continue
        if "text" in entry:
            ts_match = re.match(r"(\w+\s+\d+\s+\d+:\d+:\d+)", str(entry["text"]))
            if ts_match:
                try:
                    import calendar
                    parts = ts_match.group(1).split()
                    month_str = parts[0]
                    month = list(calendar.month_abbr).index(month_str.title())
                    day = int(parts[1])
                    h, m, s = map(int, parts[2].split(":"))
                    now = datetime.now(timezone.utc)
                    return now.replace(month=month, day=day, hour=h, minute=m,
                                       second=s, microsecond=0, tzinfo=timezone.utc)
                except (ValueError, AttributeError, IndexError):
                    pass
        return None


# ── Log Parser & Aggregator ───────────────────────────────────────────────────

class LogAggregator:

    def __init__(self):
        self.block_counter = Counter()
        self.port_counter = Counter()
        self.iface_stats = defaultdict(lambda: {"pass": 0, "block": 0})
        self.hourly_counts = Counter()

    def parse_entries(self, logs: list[dict]) -> list[dict]:
        parsed = []
        for entry in logs:
            if isinstance(entry, dict):
                parsed_entry = self._parse_dict_entry(entry)
            elif isinstance(entry, str):
                parsed_entry = self._parse_text_entry(entry)
            else:
                continue
            if parsed_entry:
                parsed.append(parsed_entry)
        return parsed

    def _parse_dict_entry(self, entry: dict) -> dict | None:
        if "text" in entry and "id" in entry:
            parsed = self._parse_filterlog_csv(entry["text"])
            if parsed:
                return parsed
            return self._parse_text_entry(entry["text"])

        action = entry.get("action", entry.get("act", "")).lower()
        if not action:
            msg = entry.get("message", entry.get("filter", ""))
            if msg:
                m = LOG_PATTERNS["block"].search(str(msg))
                if m:
                    return m.groupdict()

        if not action:
            return None
        return {
            "timestamp": entry.get("time", entry.get("timestamp", "")),
            "action": action,
            "interface": entry.get("interface", entry.get("iface", "")),
            "protocol": entry.get("protocol", entry.get("proto", "")),
            "source": entry.get("source", entry.get("src", "")),
            "source_port": entry.get("source_port", entry.get("sport", "")),
            "destination": entry.get("destination", entry.get("dst", "")),
            "destination_port": entry.get("destination_port", entry.get("dport", "")),
            "reason": entry.get("reason", entry.get("rule", "")),
            "raw": entry,
        }

    def _parse_text_entry(self, text: str) -> dict | None:
        m = LOG_PATTERNS["block"].search(text)
        if m:
            return m.groupdict()
        m = LOG_PATTERNS["generic"].search(text)
        if m:
            return m.groupdict()
        return None

    def _parse_filterlog_csv(self, text: str) -> dict | None:
        """Parse pfSense filterlog CSV format.

        pfSense emits two formats depending on IP version:

        IPv4 fields (0-indexed):
          [0]rule [1]sub_rule [2]anchor [3]tracker [4]interface [5]reason
          [6]action [7]direction [8]ip_version=4 [9]tos [10]ecn [11]ttl
          [12]id [13]offset [14]flags [15]proto_num [16]proto_name [17]length
          [18]src_ip [19]dst_ip [20]src_port [21]dst_port [22]data_len

        IPv6 fields (0-indexed):
          [0]rule [1]sub_rule [2]anchor [3]tracker [4]interface [5]reason
          [6]action [7]direction [8]ip_version=6 [9]class [10]flow_label
          [11]hop_limit [12]proto_name [13]proto_num [14]length
          [15]src_ip [16]dst_ip [17]src_port [18]dst_port [19]data_len
        """
        ts_match = re.match(
            r"(?P<timestamp>\w+\s+\d+\s+\d+:\d+:\d+)\s+"
            r"(?P<hostname>\S+)\s+filterlog\[\d+\]:\s*(?P<csv>.*)",
            text,
        )
        if not ts_match:
            return None

        csv_data = ts_match.group("csv").strip()
        fields = csv_data.split(",")
        if len(fields) < 15:
            return None

        try:
            action    = fields[6] if len(fields) > 6 else ""
            iface     = fields[4] if len(fields) > 4 else ""
            reason    = fields[5] if len(fields) > 5 else ""
            direction = fields[7] if len(fields) > 7 else ""
            ipver     = fields[8] if len(fields) > 8 else "4"

            if ipver == "6":
                # IPv6: proto at [12], src at [15], dst at [16], ports at [17][18]
                proto    = fields[12] if len(fields) > 12 else ""
                src_ip   = fields[15] if len(fields) > 15 else ""
                dst_ip   = fields[16] if len(fields) > 16 else ""
                src_port = fields[17] if len(fields) > 17 else ""
                dst_port = fields[18] if len(fields) > 18 else ""
            else:
                # IPv4: proto at [16], src at [18], dst at [19], ports at [20][21]
                proto    = fields[16] if len(fields) > 16 else ""
                src_ip   = fields[18] if len(fields) > 18 else ""
                dst_ip   = fields[19] if len(fields) > 19 else ""
                src_port = fields[20] if len(fields) > 20 else ""
                dst_port = fields[21] if len(fields) > 21 else ""

            # Sanity-check source: must look like an IP, not a label like RTALERT
            if src_ip and not re.match(r'^[\d.a-fA-F:]+$', src_ip):
                return None

            return {
                "timestamp":        ts_match.group("timestamp"),
                "action":           action.lower(),
                "interface":        iface,
                "protocol":         proto,
                "ip_version":       ipver,
                "source":           src_ip,
                "source_port":      src_port,
                "destination":      dst_ip,
                "destination_port": dst_port,
                "reason":           reason,
                "direction":        direction,
                "raw":              text,
            }
        except IndexError:
            return None

    def aggregate(self, parsed_logs: list[dict]) -> dict:
        self.reset()
        for entry in parsed_logs:
            action = entry.get("action", "").lower()
            src = entry.get("source", "unknown")
            dst_port = entry.get("destination_port", entry.get("dst_port", ""))
            proto = entry.get("protocol", entry.get("proto", ""))
            iface = entry.get("interface", entry.get("iface", ""))

            if action == "block":
                self.block_counter[src] += 1
                self.port_counter[(dst_port, proto)] += 1
                self.iface_stats[iface]["block"] += 1
            elif action == "pass":
                self.iface_stats[iface]["pass"] += 1

            ts = entry.get("timestamp", "")
            if ts:
                try:
                    if isinstance(ts, str) and len(ts) >= 13:
                        hour = ts[:13]
                        self.hourly_counts[hour] += 1
                except (ValueError, TypeError):
                    pass

        return {
            "total_entries": len(parsed_logs),
            "total_blocks": sum(self.block_counter.values()),
            "total_pass": sum(s["pass"] for s in self.iface_stats.values()),
            "top_blocked_ips": [
                {"ip": ip, "count": count}
                for ip, count in self.block_counter.most_common(20)
            ],
            "top_blocked_ports": [
                {"port": port, "protocol": proto, "count": count}
                for (port, proto), count in self.port_counter.most_common(20)
            ],
            "interface_stats": dict(self.iface_stats),
            "hourly_distribution": dict(self.hourly_counts.most_common(24)),
        }

    def filter_entries(
        self,
        parsed_logs: list[dict],
        pattern: str | None = None,
        action: str | None = None,
        source: str | None = None,
        interface: str | None = None,
        since: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        filtered = parsed_logs

        if action:
            filtered = [e for e in filtered if e.get("action", "").lower() == action.lower()]
        if source:
            filtered = [e for e in filtered if source in e.get("source", "")]
        if interface:
            filtered = [e for e in filtered if interface.lower() in e.get("interface", "").lower()]
        if pattern:
            pat = re.compile(pattern, re.IGNORECASE)
            filtered = [e for e in filtered if pat.search(json.dumps(e, default=str))]
        if since:
            filtered = [e for e in filtered if str(e.get("timestamp", "")) >= since]

        result = []
        for e in filtered[:limit]:
            result.append({
                "timestamp": e.get("timestamp", ""),
                "action": e.get("action", ""),
                "interface": e.get("interface", ""),
                "protocol": e.get("protocol", ""),
                "source": e.get("source", ""),
                "destination": e.get("destination", ""),
                "destination_port": e.get("destination_port", ""),
            })
        return result

    def deduplicate(self, parsed_logs: list[dict]) -> list[dict]:
        """Group identical consecutive entries into counts."""
        if not parsed_logs:
            return []

        result = []
        current_sig = None
        current_entry = None
        count = 0

        for entry in parsed_logs:
            sig = self._entry_signature(entry)
            if sig == current_sig:
                count += 1
            else:
                # Flush previous group
                if current_entry is not None:
                    result.append({
                        **{k: current_entry.get(k, "") for k in (
                            "timestamp", "action", "interface",
                            "protocol", "source", "destination", "destination_port")},
                        "duplicate_count": count,
                    })
                current_sig = sig
                current_entry = entry
                count = 1

        # Flush last group
        if current_entry is not None:
            result.append({
                **{k: current_entry.get(k, "") for k in (
                    "timestamp", "action", "interface",
                    "protocol", "source", "destination", "destination_port")},
                "duplicate_count": count,
            })

        return result

    def _entry_signature(self, entry: dict) -> str:
        key = (f"{entry.get('action','')}-{entry.get('source','')}"
               f"-{entry.get('destination','')}-{entry.get('destination_port','')}")
        return hashlib.md5(key.encode()).hexdigest()[:8]

    def reset(self):
        self.block_counter = Counter()
        self.port_counter = Counter()
        self.iface_stats = defaultdict(lambda: {"pass": 0, "block": 0})
        self.hourly_counts = Counter()


# ── Cursor State Manager ──────────────────────────────────────────────────────

class CursorManager:

    def __init__(self, cursor_file: Path = CURSOR_FILE):
        self.cursor_file = cursor_file
        self.cursor = self._load()

    def _load(self) -> dict:
        if self.cursor_file.exists():
            try:
                with open(self.cursor_file) as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except (json.JSONDecodeError, IOError):
                # Corrupted — auto-recover with fresh cursor
                pass
        return {"last_timestamp": None, "last_entry_id": None, "last_count": 0}

    def save(self):
        self.cursor_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cursor_file, "w") as f:
            json.dump(self.cursor, f, indent=2)

    def update(self, logs: list[dict]):
        if logs:
            last = logs[-1]
            self.cursor["last_timestamp"] = last.get("time", last.get("timestamp"))
            self.cursor["last_entry_id"] = last.get("id", last.get("uniqueid"))
            self.cursor["last_count"] = len(logs)
            self.save()

    def get_since(self) -> str | None:
        return self.cursor.get("last_timestamp")

    def reset(self):
        self.cursor = {"last_timestamp": None, "last_entry_id": None, "last_count": 0}
        self.save()


# ── Ollama Summarizer ─────────────────────────────────────────────────────────

class Summarizer:

    def __init__(self, ollama_url: str = DEFAULT_OLLAMA_URL, model: str = DEFAULT_OLLAMA_MODEL):
        self.ollama_url = ollama_url
        self.model = model
        self.rolling_summary = self._load_summary()

    def _load_summary(self) -> dict:
        if SUMMARY_STATE_FILE.exists():
            try:
                with open(SUMMARY_STATE_FILE) as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except (json.JSONDecodeError, IOError):
                pass
        return {"summary": "", "last_update": None, "event_count": 0}

    def _save_summary(self):
        SUMMARY_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SUMMARY_STATE_FILE, "w") as f:
            json.dump(self.rolling_summary, f, indent=2)

    def summarize_delta(self, new_events: list[dict]) -> str:
        if not new_events:
            return self.rolling_summary.get("summary", "No events.")

        event_lines = []
        for evt in new_events[:50]:
            action = evt.get("action", "?")
            src = evt.get("source", "?")
            dst = evt.get("destination", "?")
            dport = evt.get("destination_port", "?")
            event_lines.append(f"  {action}: {src} -> {dst}:{dport}")

        events_text = "\n".join(event_lines)
        prompt = f"""You are a network operations summarizer. Maintain a rolling summary of firewall activity.

Current Summary:
{self.rolling_summary.get('summary', 'No prior activity.')}

New Events (last batch):
{events_text}

Provide an updated rolling summary. Keep it concise (max 100 words).
Track: threat patterns, notable IPs, service disruptions, traffic anomalies.
Format as bullet points."""

        try:
            resp = requests.post(
                f"{self.ollama_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False,
                      "options": {"num_ctx": 2048, "temperature": 0.1}},
                timeout=30,
            )
            resp.raise_for_status()
            new_summary = resp.json().get("response", "").strip()
            self.rolling_summary["summary"] = new_summary
            self.rolling_summary["last_update"] = datetime.now(timezone.utc).isoformat()
            self.rolling_summary["event_count"] += len(new_events)
            self._save_summary()
            return new_summary
        except requests.exceptions.ConnectionError:
            return "[Ollama unreachable — raw aggregation only]"
        except (requests.exceptions.Timeout, requests.exceptions.RequestException):
            return "[Ollama timeout — raw aggregation only]"

    def get_summary(self) -> str:
        return self.rolling_summary.get("summary", "No summary yet.")

    def reset(self):
        self.rolling_summary = {"summary": "", "last_update": None, "event_count": 0}
        self._save_summary()


# ── Metrics Collector ─────────────────────────────────────────────────────────

class MetricsCollector:

    def __init__(self, client: PfSenseClient):
        self.client = client

    def collect(self) -> dict:
        metrics = {"timestamp": datetime.now(timezone.utc).isoformat()}

        try:
            info = self.client.get_system_info()
            if isinstance(info, dict):
                d = info.get("data", info)
                metrics["version"] = d.get("version", "unknown")
                metrics["uptime"] = d.get("uptime", "unknown")
                metrics["platform"] = d.get("platform", "unknown")
        except Exception:
            metrics["system_info"] = "unavailable"

        try:
            interfaces = self.client.get_interface_stats()
            if isinstance(interfaces, dict) and "data" in interfaces:
                metrics["interfaces"] = self._parse_interfaces(interfaces["data"])
            elif isinstance(interfaces, list):
                metrics["interfaces"] = self._parse_interfaces(interfaces)
        except Exception:
            metrics["interfaces"] = "unavailable"

        try:
            leases = self.client.get_dhcp_leases()
            if isinstance(leases, list):
                active = [l for l in leases if l.get("active", True)]
                metrics["dhcp_lease_count"] = len(active)
                metrics["top_leases"] = [
                    {"ip": l.get("ipaddr", ""), "hostname": l.get("hostname", ""),
                     "mac": l.get("mac", "")}
                    for l in active[:10]
                ]
        except Exception:
            pass

        return metrics

    def _parse_interfaces(self, interfaces: list) -> list[dict]:
        result = []
        for iface in interfaces:
            if isinstance(iface, dict):
                name = iface.get("name", iface.get("if", "unknown"))
                result.append({
                    "name": name,
                    "bytes_in": iface.get("bytes_in", 0),
                    "bytes_out": iface.get("bytes_out", 0),
                    "packets_in": iface.get("packets_in", 0),
                    "packets_out": iface.get("packets_out", 0),
                    "status": iface.get("status", "unknown"),
                })
        return result


# ── HTTP Server ───────────────────────────────────────────────────────────────

class GatewayHandler(BaseHTTPRequestHandler):

    client: PfSenseClient | None = None
    aggregator: LogAggregator = LogAggregator()
    cursor: CursorManager = CursorManager()
    summarizer: Summarizer | None = None
    metrics: MetricsCollector | None = None

    def log_message(self, format, *args):
        try:
            with open(GATEWAY_LOG, "a") as f:
                f.write(f"{datetime.now().isoformat()} {format % args}\n")
        except IOError:
            pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = dict(urllib.parse.parse_qsl(parsed.query))

        # Per-request API key: LSE retrieves from Vaultwarden and passes as ?api_key=
        # Creates a request-scoped client — key is never stored between requests.
        req_api_key = params.pop("api_key", None) or self.headers.get("X-Pfsense-Api-Key")
        if req_api_key:
            base = GatewayHandler.client.base_url if GatewayHandler.client else DEFAULT_PFSENSE_URL
            ca = GatewayHandler.client.ca_cert if GatewayHandler.client else None
            self.client = PfSenseClient(base_url=base, api_key=req_api_key, ca_cert=ca)

        try:
            if path == "/health":
                self._json_response({"status": "ok", "uptime": time.time()})
            elif path == "/compact":
                self._handle_compact(params)
            elif path == "/summary":
                self._handle_summary(params)
            elif path == "/tail":
                self._handle_tail(params)
            elif path == "/events":
                self._handle_events(params)
            elif path == "/metrics":
                self._handle_metrics(params)
            elif path == "/rolling-summary":
                self._handle_rolling_summary()
            elif path == "/search":
                self._handle_search(params)
            elif path == "/test-fetch":
                logs = self.client.get_firewall_logs(hours=2, limit=3)
                self._json_response({
                    "raw_count": len(logs),
                    "first": str(logs[0])[:200] if logs else "empty",
                })
            elif path == "/reset-cursor":
                self._handle_reset_cursor()
            else:
                self._json_response({"error": "Not found", "available": [
                    "/health", "/compact", "/summary", "/tail", "/events",
                    "/metrics", "/rolling-summary", "/search", "/reset-cursor",
                ]}, 404)
        except Exception as e:
            self._json_response({"error": f"Handler error: {e}"}, 500)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            if parsed.path == "/summarize":
                self._handle_summarize()
            else:
                self._json_response({"error": "Not found"}, 404)
        except Exception as e:
            self._json_response({"error": f"Handler error: {e}"}, 500)

    def _handle_compact(self, params: dict):
        """GET /compact?hours=24
        Dense audit-ready summary in a single response <4KB.
        Use this for full pfSense audit reports — not /summary.
        """
        hours = int(params.get("hours", 24))

        # Firewall log stats
        logs = self.client.get_firewall_logs(hours=hours, limit=5000)
        parsed = self.aggregator.parse_entries(logs)
        agg = self.aggregator.aggregate(parsed)

        # System info (non-log)
        sys_info = self.client.get("/api/v2/system/info")
        pf_version = "unknown"
        pf_uptime = "unknown"
        if isinstance(sys_info, dict):
            d = sys_info.get("data", sys_info)
            # version may be a nested dict {"version": "2.7.x", "base": "..."}
            v = d.get("version", "unknown")
            pf_version = v.get("version", str(v)) if isinstance(v, dict) else str(v)
            pf_uptime = d.get("uptime", "unknown")

        # DHCP
        dhcp_data = self.client.get("/api/v2/dhcp/server/lease")
        dhcp_count = 0
        if isinstance(dhcp_data, dict) and "data" in dhcp_data:
            dhcp_count = len(dhcp_data["data"])

        # Recent blocks (last 10, deduped)
        recent_blocks = self.aggregator.filter_entries(
            parsed, action="block", limit=30
        )
        recent_deduped = self.aggregator.deduplicate(recent_blocks)[:10]

        compact = {
            "type": "compact_audit",
            "generated": datetime.now(timezone.utc).isoformat(),
            "window_hours": hours,
            "note": (
                "pfSense only logs blocked/rejected packets by default. "
                "Zero pass_count is normal — pass rules are not logged unless "
                "explicitly enabled per-rule in pfSense → Firewall → Rules."
            ),
            "pfsense": {
                "version": pf_version,
                "uptime": pf_uptime,
                "dhcp_active_leases": dhcp_count,
            },
            "firewall": {
                "total_entries_parsed": agg["total_entries"],
                "total_blocks": agg["total_blocks"],
                "total_pass": agg["total_pass"],
                "top_blocked_ips": agg["top_blocked_ips"][:10],
                "top_blocked_ports": agg["top_blocked_ports"][:10],
                "interface_stats": agg["interface_stats"],
            },
            "recent_block_sample": recent_deduped,
        }

        self.cursor.update(logs)
        self._json_response(compact)

    def _handle_summary(self, params: dict):
        hours = int(params.get("hours", 24))
        top_n = int(params.get("top", params.get("top_n", 10)))

        logs = self.client.get_firewall_logs(hours=hours, limit=5000)
        parsed = self.aggregator.parse_entries(logs)
        summary = self.aggregator.aggregate(parsed)

        summary["top_blocked_ips"] = summary["top_blocked_ips"][:top_n]
        summary["top_blocked_ports"] = summary["top_blocked_ports"][:top_n]

        self.cursor.update(logs)
        self._json_response({
            "type": "firewall_summary",
            "hours": hours,
            "data": summary,
        })

    def _handle_tail(self, params: dict):
        lines = int(params.get("lines", 20))
        pattern = params.get("pattern")
        action = params.get("action")
        source = params.get("source")
        interface = params.get("interface")

        logs = self.client.get_firewall_logs(hours=2, limit=2000)
        parsed = self.aggregator.parse_entries(logs)

        filtered = self.aggregator.filter_entries(
            parsed, pattern=pattern, action=action, source=source,
            interface=interface, limit=lines * 3,
        )
        deduped = self.aggregator.deduplicate(filtered)

        self._json_response({
            "type": "log_tail",
            "requested_lines": lines,
            "returned": len(deduped[:lines]),
            "filters": {k: v for k, v in params.items() if v},
            "entries": deduped[:lines],
        })

    def _handle_events(self, params: dict):
        since = params.get("since", self.cursor.get_since())

        logs = self.client.get_firewall_logs(hours=1, limit=2000)
        parsed = self.aggregator.parse_entries(logs)

        filtered = self.aggregator.filter_entries(
            parsed, since=since, limit=500
        ) if since else self.aggregator.filter_entries(parsed, limit=200)

        deduped = self.aggregator.deduplicate(filtered)
        self.cursor.update(logs)

        self._json_response({
            "type": "incremental_events",
            "since": since,
            "new_entries": len(deduped),
            "cursor_timestamp": self.cursor.get_since(),
            "events": deduped,
        })

    def _handle_metrics(self, params: dict):
        sys_info = self.client.get("/api/v2/system/info")
        pf_version = "unknown"
        pf_uptime = "unknown"
        if isinstance(sys_info, dict):
            d = sys_info.get("data", sys_info)
            # version may be a nested dict {"version": "2.7.x", "base": "..."}
            v = d.get("version", "unknown")
            pf_version = v.get("version", str(v)) if isinstance(v, dict) else str(v)
            pf_uptime = d.get("uptime", "unknown")

        dhcp_data = self.client.get("/api/v2/dhcp/server/lease")
        dhcp_count = 0
        if isinstance(dhcp_data, dict) and "data" in dhcp_data:
            dhcp_count = len(dhcp_data["data"])

        data = self.metrics.collect() if self.metrics else {}
        data.update({
            "pfsense_version": pf_version,
            "pfsense_uptime": pf_uptime,
            "dhcp_lease_count": dhcp_count,
        })

        self._json_response({"type": "system_metrics", "data": data})

    def _handle_rolling_summary(self):
        if self.summarizer:
            self._json_response({
                "type": "rolling_summary",
                "summary": self.summarizer.get_summary(),
                "last_update": self.summarizer.rolling_summary.get("last_update"),
                "total_events_processed": self.summarizer.rolling_summary.get("event_count", 0),
            })
        else:
            self._json_response({"error": "summarizer not initialized"})

    def _handle_search(self, params: dict):
        query = params.get("q", params.get("query", "")).lower()
        limit = int(params.get("limit", 50))

        logs = self.client.get_firewall_logs(hours=24, limit=5000)
        parsed = self.aggregator.parse_entries(logs)

        results = []
        for entry in parsed:
            searchable = " ".join(str(entry.get(k, "")) for k in (
                "action", "source", "destination", "destination_port",
                "protocol", "interface", "reason",
            )).lower()
            if query and query in searchable:
                results.append(entry)
                if len(results) >= limit * 3:
                    break

        deduped = self.aggregator.deduplicate(results)
        self._json_response({
            "type": "search_results",
            "query": query,
            "total_matches": len(results),
            "returned": len(deduped[:limit]),
            "entries": deduped[:limit],
        })

    def _handle_summarize(self):
        if not self.summarizer:
            self._json_response({"error": "summarizer not initialized"})
            return

        logs = self.client.get_firewall_logs(hours=1, limit=500)
        parsed = self.aggregator.parse_entries(logs)

        since = self.cursor.get_since()
        delta = (self.aggregator.filter_entries(parsed, since=since, limit=200)
                 if since else parsed[:200])

        result = self.summarizer.summarize_delta(delta)
        self.cursor.update(logs)

        self._json_response({
            "type": "summarize_result",
            "events_processed": len(delta),
            "summary": result,
        })

    def _handle_reset_cursor(self):
        self.cursor.reset()
        if self.summarizer:
            self.summarizer.reset()
        self._json_response({"status": "cursor reset", "rolling_summary": "reset"})

    def _json_response(self, data: dict, status: int = 200):
        """Send JSON response with hard size cap to prevent context overflow."""
        body = json.dumps(data, indent=2, default=str).encode()

        # Hard cap: truncate if over MAX_RESPONSE_BYTES
        if len(body) > MAX_RESPONSE_BYTES:
            truncated = {
                "warning": f"Response truncated from {len(body)} to {MAX_RESPONSE_BYTES} bytes",
                "hint": "Use /compact for audit reports, or narrow filters (hours, top_n, lines)",
            }
            # For dict responses, preserve top-level scalar fields + warning
            if isinstance(data, dict):
                truncated.update({
                    k: v for k, v in data.items()
                    if not isinstance(v, (list, dict))
                })
            body = json.dumps(truncated, indent=2, default=str).encode()

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="pfSense Log Gateway")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--pf-url", default=DEFAULT_PFSENSE_URL)
    parser.add_argument("--pf-api-key", default=None, help="pfSense API key (prefer env PFSENSE_API_KEY)")
    parser.add_argument("--ca-cert", default="/opt/local-se/cert/pfsense-webgui-ca.crt")
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument("--ollama-model", default=DEFAULT_OLLAMA_MODEL)
    parser.add_argument("--disable-ollama", action="store_true")
    args = parser.parse_args()

    # Ensure all required directories exist at startup
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    Path("/opt/local-se/logs").mkdir(parents=True, exist_ok=True)
    Path("/tmp/lse").mkdir(parents=True, exist_ok=True)  # tmpfs — recreate after reboot

    client = PfSenseClient(
        base_url=args.pf_url,
        api_key=args.pf_api_key,
        ca_cert=args.ca_cert,
    )
    aggregator = LogAggregator()
    cursor = CursorManager()
    metrics = MetricsCollector(client)

    summarizer = None
    if not args.disable_ollama:
        try:
            resp = requests.get(f"{args.ollama_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                summarizer = Summarizer(ollama_url=args.ollama_url, model=args.ollama_model)
                print(f"  Ollama connected: {args.ollama_url} (model: {args.ollama_model})")
            else:
                print(f"  Ollama unreachable at {args.ollama_url} — summarizer disabled")
        except requests.exceptions.ConnectionError:
            print(f"  Ollama unreachable at {args.ollama_url} — summarizer disabled")

    GatewayHandler.client = client
    GatewayHandler.aggregator = aggregator
    GatewayHandler.cursor = cursor
    GatewayHandler.summarizer = summarizer
    GatewayHandler.metrics = metrics

    print(f"pfSense Log Gateway starting on port {args.port}")
    print(f"  pfSense: {args.pf_url}")
    print(f"  Max response size: {MAX_RESPONSE_BYTES:,} bytes")
    print(f"  Endpoints:")
    print(f"    GET  /compact?hours=24    — Dense audit summary (<4KB) ← use for reports")
    print(f"    GET  /summary?hours=24    — Structured firewall summary")
    print(f"    GET  /tail?lines=50       — Recent logs (filtered)")
    print(f"    GET  /events              — Incremental delta")
    print(f"    GET  /metrics             — System metrics (no logs)")
    print(f"    POST /summarize           — Trigger delta summarization")
    print(f"    GET  /reset-cursor        — Reset all state")

    server = HTTPServer(("0.0.0.0", args.port), GatewayHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
