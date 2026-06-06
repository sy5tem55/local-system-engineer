# Log Summariser Design — v1.5.17
> Added: 2026-06-04
> Context: LSE Challenge Arena — pfSense log + nmap context explosion problem

---

## Problem

pfSense firewall logs and nmap output are too large for direct injection into the
model context. In a challenge episode:

- `GET /api/v2/status/logs/firewall` → 50–200 KB of raw log lines (thousands of entries)
- `nmap -sV --top-ports 1000 192.168.1.0/24 192.168.5.0/24` → ~5000 lines of text

The LSE tool's `MAX_OUTPUT_CHARS = 4000` truncation cuts these mid-entry, producing
a useless partial dump. The model cannot reason over truncated raw logs and the
context window fills regardless.

---

## Solution: Tool-level summarisers (Option B)

Two new functions added to `openwebui-tool-v1.5.17.py`. The model calls these
instead of `pfsense_query('/api/v2/status/logs/firewall')` or
`execute_command('nmap ...')`. Both docstrings explicitly forbid the raw-data
alternatives.

### Architecture — two tiers

```
Raw data source (pfSense API / nmap XML)
        │
        ▼ Tier 1 — Programmatic extraction (Python, deterministic, always runs)
        │   pfsense_log_summary: top blocked IPs, top blocked ports,
        │                        pass/block ratio per interface
        │   nmap_summary:        per-host open ports + service strings,
        │                        unexpected port cross-reference
        │
        ▼ Tier 2 — Ollama narrative (optional, non-blocking)
        │   Model: llama3.2:3b on OLLAMA_URL (same endpoint as RAG embeddings)
        │   Input: compact Tier 1 summary (~300 chars) — never raw logs
        │   Output: 2–3 bullet anomaly narrative (~200 chars)
        │   Skipped silently if Ollama unreachable or model not pulled
        │
        ▼ LSE model sees only compact JSON (~600–900 chars total)
```

Tier 1 alone satisfies all T1 challenge assertions (counts, IP lists, ratios).
Tier 2 handles narrative-only assertions ("flag anomalous behaviour").

---

## pfsense_log_summary

```python
pfsense_log_summary(hours=24, top_n=10, api_key="") -> str
```

**Returns JSON:**
```json
{
  "log_count": 4821,
  "window_hours": 24,
  "top_blocked_ips": [
    {"ip": "1.2.3.4", "count": 847},
    ...
  ],
  "top_blocked_ports": [
    {"port": 443, "protocol": "tcp", "count": 1203},
    ...
  ],
  "interface_ratios": {
    "WAN": {"pass_count": 12, "block_count": 4809, "block_ratio": 0.9975},
    "LAN": {"pass_count": 3201, "block_count": 21, "block_ratio": 0.0065}
  },
  "anomalies": "• 192.168.1.90 generated 847 DHCP requests (Samsung TV DHCP hammer)\n• ..."
}
```

**API field mapping** — pfSense REST API v2 log entries vary by firmware version.
The function handles both old-style (`act`, `src`, `dstport`, `proto`, `interface`)
and new-style (`action`, `src_ip`, `dst_port`, `protocol`, `iface`) field names.

---

## nmap_summary

```python
nmap_summary(targets="192.168.1.0/24", top_ports=1000, known_services="") -> str
```

Runs: `nmap -sV --top-ports N -oX - --open <targets>`

**Returns JSON:**
```json
{
  "scan_results": {
    "192.168.1.50": {
      "ports": [22, 80, 443, 514],
      "services": {"22": "ssh OpenSSH 9.6", "443": "https"}
    }
  },
  "unexpected_ports": [
    {"ip": "192.168.1.90", "port": 8008, "service": "http Golang net/http"}
  ],
  "host_count": 7,
  "scan_time_s": 42.3,
  "command": "nmap -sV --top-ports=1000 -oX - --open 192.168.1.0/24 192.168.5.0/24"
}
```

`known_services` is a JSON string `{"ip": [port, ...]}`. Any open port not listed
for its host is added to `unexpected_ports`. Pass `""` to skip baseline check.

---

## Ollama model requirement

`pfsense_log_summary` uses `llama3.2:3b` for anomaly narrative. Pull on LUCIFER:

```bash
ollama pull llama3.2:3b
```

This is ~2 GB. The model runs CPU-only (same as `nomic-embed-text`). If not
pulled, `pfsense_log_summary` still returns a complete summary — `anomalies`
field will be `""`.

---

## Challenge assertion mapping

| Challenge | Assertions | Tool to use |
|---|---|---|
| pf-t1-003 Firewall Log Baseline | log_count ≥ 100, top_blocked_ips ≥ 5, block_ratio > 0 | `pfsense_log_summary()` |
| net-t1-009 Open Port Audit | scan_results has 192.168.1.50, port 8123 found, unexpected_findings | `nmap_summary()` |
| net-t1-010 Inter-Subnet Traffic | interface bytes_in/out, top_talkers ≥ 1 | `pfsense_query('/api/v2/status/interface')` + `pfsense_log_summary()` |

---

## Deploy note

Upload `tools/openwebui-tool-v1.5.17.py` to OpenWebUI Admin → Tools.
SHA-256: `f30c1e97493aa6f58fe3498df94c15784d747a5e1e04a209a405251e5211c973`

After deploy, verify both functions appear in the tool list in a new chat session.
