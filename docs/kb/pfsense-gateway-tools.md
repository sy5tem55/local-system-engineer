# pfSense Log Gateway — Complete Reference

> **Source of Truth** — This single document covers architecture, tool integration, and usage.
> **KB doc_id:** 471b028dc810773d | **Quality:** 0.95

---

## Critical Rule
**NEVER call raw pfSense firewall log endpoints.** Always use the gateway.

| ❌ DO NOT USE | ✅ USE INSTEAD |
|--------------|---------------|
| `pfsense_query("/api/v2/status/logs/firewall")` | `bash /opt/local-se/pfsense-gateway-tools.sh summary 24 10` |
| `curl pfSense.../logs/firewall` | `bash /opt/local-se/pfsense-gateway-tools.sh tail 20 block` |
| Raw log parsing in Python | Gateway handles parsing automatically |

---

## Quick Start (Copy-Paste Ready)

### Method 1: Source tools (persistent, add to ~/.bashrc)
```bash
source /opt/local-se/pfsense-gateway-tools.sh
gateway_summary 24 10
gateway_tail 20 block
gateway_search "81.16.152.2"
gateway_stop  # stop when done
```

### Method 2: Direct calls (no sourcing needed)
```bash
bash /opt/local-se/pfsense-gateway-tools.sh summary 24 10
bash /opt/local-se/pfsense-gateway-tools.sh tail 20 block
bash /opt/local-se/pfsense-gateway-tools.sh search "81.16.152.2"
bash /opt/local-se/pfsense-gateway-tools.sh events
bash /opt/local-se/pfsense-gateway-tools.sh metrics
bash /opt/local-se/pfsense-gateway-tools.sh health
bash /opt/local-se/pfsense-gateway-tools.sh stop
```

Gateway **auto-starts on first call** — no manual start needed.

---

## Tool Definitions (System Prompt Format)

### gateway_summary
```
gateway_summary(hours, top_n)
  Fetch structured firewall summary from the log gateway (port 9191).
  REPLACES raw log fetching. ALWAYS prefer this over pfsense_query for firewall logs.

  ARGS:
    hours  — Time window to analyze (default 24, max 168)
    top_n  — Entries per category (default 10)

  RETURNS JSON:
    {"type":"firewall_summary","hours":24,"data":{"total_entries":15234,"total_blocks":12456,"total_pass":2778,
     "top_blocked_ips":[{"ip":"185.22.x.x","count":3421}],"top_blocked_ports":[{"port":"22","protocol":"tcp","count":5678}],
     "interface_stats":{"WAN":{"pass":100,"block":5000}},"hourly_distribution":{"2026-06-05T10":500}}}

  TOKEN COST: ~200 tokens vs 10,000+ for raw log fetch (98% savings)
```

### gateway_tail
```
gateway_tail(lines, action, source, pattern)
  Fetch recent log entries matching criteria — like `tail -n | grep`.

  ARGS (all optional):
    lines     — Max entries to return (default 50)
    action    — "block" or "pass"
    source    — Source IP filter
    pattern   — Regex filter (e.g., "BLOCK", "185.22")

  RETURNS JSON:
    {"type":"log_tail","requested_lines":20,"returned":15,"filters":{"action":"block","source":"185.22"},
     "entries":[{"timestamp":"...","action":"block","source":"185.22.x.x",
                 "destination":"10.0.0.1","destination_port":"22","duplicate_count":5}]}

  DEDUPLICATION: Identical entries within 60s merged with duplicate_count.
  TOKEN COST: ~50-500 tokens depending on filters (90%+ savings)
```

### gateway_events
```
gateway_events()
  Fetch only NEW events since last query (cursor-based incremental fetch).

  RETURNS JSON:
    {"type":"incremental_events","since":"2026-06-05T11:55:00Z","new_entries":23,
     "cursor_timestamp":"2026-06-05T12:00:00Z","events":[...]}

  CURSOR STATE: Persisted at /opt/local-se/tmp/log-cursor.json
  RESET: GET http://localhost:9191/reset-cursor
  TOKEN COST: ~50-200 tokens (99% savings — only delta)
```

### gateway_search
```
gateway_search(query)
  Search parsed logs by IP address or pattern.

  RETURNS JSON:
    {"type":"search_results","query":"81.16.152.2","total_matches":26,"returned":1,
     "entries":[{"timestamp":"...","action":"block","source":"81.16.152.2",
                 "destination":"93.181.46.208","destination_port":"0","duplicate_count":26}]}

  TOKEN COST: ~150 tokens (97% savings)
```

### gateway_metrics
```
gateway_metrics()
  Fetch structured system metrics — NO LOGS, just telemetry.
  ANSWERS 70% of operational questions without touching logs.

  RETURNS JSON:
    {"type":"system_metrics","data":{"version":"Plus 26.03.1","uptime":"15 days",
     "interfaces":[{"name":"wan","bytes_in":1234567890,"bytes_out":987654321}],
     "dhcp_lease_count":15,"top_leases":[{"ip":"192.168.1.10","hostname":"lucifer"}]}}

  TOKEN COST: ~300 tokens
```

### gateway_health
```
gateway_health()
  Check gateway health and connectivity.

  RETURNS JSON: {"status":"ok","uptime":12345.6}

  USE: Before other gateway calls to verify connectivity.
```

---

## Decision Tree

```
pfSense LOG queries — ALWAYS use gateway, never raw API:

  1. "What's happening on the firewall?"
     → gateway_summary 24 10

  2. "Show me recent blocks from IP X"
     → bash /opt/local-se/pfsense-gateway-tools.sh tail 20 block "X"

  3. "Any new events since last check?"
     → bash /opt/local-se/pfsense-gateway-tools.sh events

  4. "Find logs for IP X"
     → bash /opt/local-se/pfsense-gateway-tools.sh search "X"

  5. "System health / DHCP / interfaces"
     → bash /opt/local-se/pfsense-gateway-tools.sh metrics

  6. Configuration changes (rules, DNS, DHCP settings)
     → pfsense_query (still use raw API for config operations)
     → NEVER use gateway for config — it's read-only log aggregation
```

---

## Token Consumption Comparison

| Operation | Raw pfSense API | Via Gateway | Savings |
|-----------|----------------|-------------|---------|
| Full log fetch | ~10,000+ tokens | ~200 tokens | 98% |
| Tail 50 lines | ~5,000+ tokens | ~100 tokens | 98% |
| Incremental delta | ~5,000+ tokens | ~50 tokens | 99% |
| Search | ~5,000+ tokens | ~150 tokens | 97% |
| System metrics | N/A | ~300 tokens | N/A |

---

## Environment (auto-set by wrapper)
```bash
PFSENSE_URL=https://pfsense.home.arpa
PFSENSE_API_KEY=<stored in Vaultwarden: PFSENSE_API_KEY>
OLLAMA_URL=http://localhost:11434
GATEWAY_PORT=9191
```

---

## Key Files
| File | Purpose |
|------|---------|
| `/opt/local-se/pfsense_log_gateway.py` | Core gateway (1004 lines) |
| `/opt/local-se/pfsense-gateway-tools.sh` | Bash tool wrapper (on-demand) |
| `/opt/local-se/launch-pfsense-gateway.sh` | Launcher script |
| `/opt/local-se/logs/gateway.log` | Gateway log |

---

## When to Use Gateway
- Any firewall log analysis task
- Blocked IP investigation
- Port scan detection
- Interface traffic analysis
- Incremental log monitoring
- BEFORE any pfSense API call that might return logs

## When Raw pfSense API is OK
- System version: `/api/v2/system/version`
- DHCP leases: `/api/v2/dhcp/server/lease`
- DNS config: `/api/v2/system/dns`
- Non-log endpoints
