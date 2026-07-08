"""
LSE net-discovery tools
version: 1.0.0
On-demand LAN discovery via the net-discovery/ orchestrator (discovery_engine.py
+ snapshot.json + SQLite), packaged as a goethe_mcp `--also` skill.

Wraps, does not modify, the existing net-discovery/ standalone system (found
dormant during packaging -- no live service, snapshot.json a month stale).
Full design writeup, including why this stays single-run/read-only and what's
deliberately deferred to v2: lse/skills/net-discovery/DESIGN.md.
"""
import json
import os
import subprocess
import sys
import time
from pydantic import BaseModel, Field


class Tools:

    class Valves(BaseModel):
        NET_DISCOVERY_DIR: str = Field(
            default="/home/sy5/projects/local-system-engineer/net-discovery",
            description="Absolute path to the net-discovery/ directory containing "
            "discovery_engine.py, config.json, and snapshot.json.",
        )
        PFSENSE_API_KEY: str = Field(
            default="",
            description="pfSense REST API key, injected into the discovery_engine.py "
            "subprocess environment for probe_dhcp.py (which reads it via "
            "os.environ and raises EnvironmentError if unset -- it does not fall "
            "back to any config value). Same key used by the pfsense skill's "
            "PFSENSE_API_KEY valve; duplicated here because this module is loaded "
            "standalone via --also and has no reference to that Tools instance.",
        )
        SCAN_TIMEOUT_S: int = Field(
            default=90,
            description="Max seconds to wait for a discovery_engine.py single-run "
            "scan before giving up. The last real run's own meta.duration_s was "
            "26.28s for a full 4-probe pass; 90s gives real margin without "
            "hanging indefinitely if a probe stalls.",
        )
        LOG_FILE: str = Field(
            default="/opt/local-se/agent_commands.log",
            description="Path to the persistent agent command audit log. Shared "
            "log file with goethe.py's own Valves so NETDISC-* log lines "
            "interleave with the rest of the audit trail.",
        )

    def __init__(self):
        self.valves = self.Valves()

    def _log(self, entry: str) -> None:
        """Append a timestamped line to the audit log (best-effort). Same
        pattern as the pfsense/vault skills' _log -- duplicated here because
        this module is loaded standalone via --also and has no reference to
        goethe.py's own Tools instance."""
        from datetime import datetime  # noqa: PLC0415

        try:
            log_path = self.valves.LOG_FILE
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(log_path, "a") as f:
                f.write(f"[{ts}] {entry}\n")
        except Exception:
            pass

    def _snapshot_path(self) -> str:
        return os.path.join(self.valves.NET_DISCOVERY_DIR, "snapshot.json")

    def _load_snapshot(self):
        path = self._snapshot_path()
        if not os.path.isfile(path):
            return None
        with open(path) as f:
            return json.load(f)

    def _format_meta_summary(self, snapshot: dict, extra_note: str = "") -> str:
        meta = snapshot.get("meta", {})
        lines = [
            f"generated_at: {snapshot.get('generated_at', 'unknown')}",
            f"devices: {meta.get('device_count', '?')} total, "
            f"{meta.get('up_count', '?')} up, {meta.get('down_count', '?')} down",
            f"probes_run: {meta.get('probes_run', [])}",
        ]
        if meta.get("probes_failed"):
            lines.append(f"probes_failed: {meta['probes_failed']}")
        if meta.get("duration_s") is not None:
            lines.append(f"scan_duration_s: {meta['duration_s']}")
        if extra_note:
            lines.append(extra_note)
        return "\n".join(lines)

    def net_discovery_scan(self) -> str:
        """
        Trigger ONE discovery_engine.py pass (DHCP leases + ICMP sweep, plus
        WiFi/mDNS if those probes are available) and return a compact summary.
        Refreshes snapshot.json and the SQLite device history on disk.

        This is the only net_discovery_* tool that touches the network. It
        always runs a single pass -- never `--loop` -- a chat tool must not be
        able to silently start a long-running background process. Typical
        runtime is well under a minute; capped by valves.SCAN_TIMEOUT_S.

        Returns a compact text summary (device counts, probes run/failed,
        scan duration) -- NEVER the raw snapshot, which runs 60KB+ for a
        ~100-device LAN and would blow out context. Use net_discovery_device()
        to look up specific devices after scanning.
        """
        net_dir = self.valves.NET_DISCOVERY_DIR
        engine = os.path.join(net_dir, "discovery_engine.py")
        if not os.path.isfile(engine):
            return f"ERROR: discovery_engine.py not found at {engine}"

        env = os.environ.copy()
        api_key = self.valves.PFSENSE_API_KEY.strip()
        if api_key:
            # probe_dhcp.py reads this specific env var name via os.environ.get()
            # -- see config.json's gateway "api_key_env" field.
            env["PFSENSE_API_KEY"] = api_key
        else:
            self._log("NETDISC-WARN: PFSENSE_API_KEY valve is empty -- probe_dhcp will fail")

        start = time.time()
        try:
            result = subprocess.run(
                [sys.executable, "discovery_engine.py"],
                cwd=net_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=self.valves.SCAN_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            self._log(f"NETDISC-TIMEOUT: scan exceeded {self.valves.SCAN_TIMEOUT_S}s")
            return f"ERROR: scan timed out after {self.valves.SCAN_TIMEOUT_S}s"
        elapsed = time.time() - start

        snapshot = self._load_snapshot()
        if snapshot is None:
            tail = (result.stdout[-1500:] + result.stderr[-1500:]).strip()
            self._log(
                f"NETDISC-FAIL: scan produced no snapshot.json (exit {result.returncode})"
            )
            return (
                f"ERROR: scan finished (exit {result.returncode}, {elapsed:.1f}s) but "
                f"no snapshot.json was produced. Tail of output:\n{tail}"
            )

        self._log(f"NETDISC-SCAN: exit={result.returncode} elapsed={elapsed:.1f}s")
        note = f"subprocess_exit: {result.returncode}"
        if result.returncode != 0:
            note += f" (non-zero -- check stderr tail: {result.stderr[-500:]})"
        return self._format_meta_summary(snapshot, extra_note=note)

    def net_discovery_snapshot(self, max_age_warn_s: int = 3600) -> str:
        """
        Return the last known network snapshot WITHOUT triggering a new scan --
        fast, no network traffic. Use this for "what do we already know" queries;
        use net_discovery_scan() when you need current data.

        Explicitly flags staleness if the snapshot is older than max_age_warn_s
        (default 1 hour) -- this system was found with a snapshot a full month
        old and nothing surfacing that fact anywhere, so don't repeat that
        silently here.

        Args:
            max_age_warn_s: age threshold in seconds above which a staleness
                warning is added to the summary. Default 3600 (1 hour).
        """
        snapshot = self._load_snapshot()
        if snapshot is None:
            return (
                f"ERROR: no snapshot.json at {self._snapshot_path()}. "
                "Run net_discovery_scan() first."
            )

        note = ""
        generated_at = snapshot.get("generated_at")
        if generated_at:
            try:
                from datetime import datetime, timezone  # noqa: PLC0415

                gen_dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
                age_s = (datetime.now(timezone.utc) - gen_dt).total_seconds()
                if age_s > max_age_warn_s:
                    note = (
                        f"STALENESS WARNING: this snapshot is {age_s/3600:.1f} hours old "
                        f"(threshold: {max_age_warn_s/3600:.1f}h). Call net_discovery_scan() "
                        "for current data."
                    )
            except Exception:
                pass

        return self._format_meta_summary(snapshot, extra_note=note)

    def net_discovery_device(self, query: str, limit: int = 20) -> str:
        """
        Look up devices in the last snapshot by substring match against IP,
        MAC, hostname, or vendor (case-insensitive). Returns full metadata
        for matches only -- never the full device list, which runs 100+
        entries on this LAN.

        Reads the last snapshot as-is; does not trigger a scan. Call
        net_discovery_scan() first if you need current data before looking
        a device up.

        Args:
            query: substring to match against ip/mac/hostname/vendor.
            limit: max number of matches to return (default 20), to bound
                response size if the query is too broad.
        """
        if not query or not query.strip():
            return "ERROR: query must be a non-empty string."

        snapshot = self._load_snapshot()
        if snapshot is None:
            return (
                f"ERROR: no snapshot.json at {self._snapshot_path()}. "
                "Run net_discovery_scan() first."
            )

        q = query.strip().lower()
        matches = []
        for dev in snapshot.get("devices", []):
            haystack = " ".join(
                str(dev.get(f, "") or "") for f in ("ip", "mac", "hostname", "vendor")
            ).lower()
            if q in haystack:
                matches.append(dev)
            if len(matches) >= limit:
                break

        if not matches:
            return (
                f"No devices matched '{query}' (searched "
                f"{len(snapshot.get('devices', []))} devices in the last snapshot)."
            )

        header = (
            f"{len(matches)} match(es) for '{query}' "
            f"(snapshot generated_at: {snapshot.get('generated_at', 'unknown')}):"
        )
        return header + "\n\n" + json.dumps(matches, indent=2)
