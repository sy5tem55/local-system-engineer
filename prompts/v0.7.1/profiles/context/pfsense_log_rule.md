# PFSENSE LOG RULE

JIT CONTEXT FILE — v0.7.0 (extracted verbatim from v0.6.3 canonical, 2026-09-19, task 1bfb3e45).
Not part of the always-on BASE prompt. Read this file first when: the user asks about pfSense firewall/DHCP/system logs, blocked IPs, or 'what is the firewall seeing'.

---

PFSENSE LOG RULE
────────────────
NEVER call raw pfSense firewall log endpoints. Always use the gateway:
  ❌ pfsense_query("/api/v2/status/logs/firewall")  — returns 10,000+ tokens, floods context
  ✅ execute_command("bash /opt/local-se/pfsense-gateway-tools.sh summary 24 10")
  ✅ execute_command("bash /opt/local-se/pfsense-gateway-tools.sh tail 20 block")
  ✅ execute_command("bash /opt/local-se/pfsense-gateway-tools.sh search '<IP>'")
  ✅ execute_command("bash /opt/local-se/pfsense-gateway-tools.sh events")
Gateway auto-starts on first call. No manual setup required.
Token cost: ~200 tokens vs 10,000+ raw (98% savings).
Exemption: non-log endpoints are fine — DHCP leases, DNS config, system version, firewall rules.
Full reference: search_kb("pfSense gateway") → doc_id 471b028dc810773d
