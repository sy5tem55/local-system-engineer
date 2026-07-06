"""
LSE pfSense Tools
version: 1.0.0
GraphQL reads, REST writes, and firewall-log summaries against pfSense
(pfSense-pkg-RESTAPI / pfrest.org package) via the goethe_mcp `--also` mechanism.

Extracted from tools/goethe.py (Phase 2 skill extraction, 2026-07-06) — byte-identical
port of pfsense_graphql, pfsense_query, pfsense_log_summary, _pfsense_verify, and
_pfsense_cap_response, following the same shape as the completed vault extraction
(tools/vaultwarden_tools_v1.3.0.py / lse/skills/vault/tools.py).

Same session also added (2026-07-06, post-incident hardening, present in this port):
  - _pfsense_cap_response: universal ~32KB response-size cap across all three
    pfsense_* tools (confirmed fix for the queryDiagnosticsTables/bogons context
    blowup — 2,966,261 tokens against a 131,072 token window).
  - pfsense_query's confirmed=bool gate: writes require explicit confirmation
    (confirmed fix for the unconfirmed pfSense System DNS write that broke Unbound).
  - Code-level log-endpoint guards in pfsense_query (endpoint path) and
    pfsense_graphql (GraphQL type shape) — docstring-only prohibition was not a
    reliable backstop; see the LOG-ENDPOINT GUARD comments inline below.

kb/ in this same skill directory holds the bundled schema reference (firewall rule
payload schema, REST API reference, GraphQL type naming convention) so `search_kb`
does not have to succeed for this skill to be usable standalone.

Full incident + design writeup: lse/skills/pfsense/DESIGN.md.
"""

import os
from pydantic import BaseModel, Field


class Tools:

    class Valves(BaseModel):
        PFSENSE_URL: str = Field(
            default="https://pfsense.home.arpa",
            description="Base URL of the pfSense REST API (pfrest.org package, Plus 26.03). "
            "Not a secret — safe to store in valve.",
        )
        PFSENSE_API_KEY: str = Field(
            default="",
            description="pfSense REST API key (read-only). Acceptable blast radius: exposes "
            "network topology and firewall rules but cannot modify anything. "
            "Alternatively retrieve from Vaultwarden at runtime via vault_unlock() "
            "+ get_vault_secret() and pass as api_key parameter to pfsense_query(). "
            "WRITE ACCESS PROTOCOL: key is read-only by default. If pfSense write "
            "access is temporarily enabled (T3+ challenges), rotate this key "
            "immediately after and re-enable Read Only in pfSense UI.",
        )
        PFSENSE_CA_CERT: str = Field(
            default="/opt/local-se/cert/pfsense-webgui-ca.crt",
            description="Path to the exported pfSense WebGUI CA certificate for TLS verification. "
            "Export from pfSense: System → Cert Manager → CAs → Export CA. "
            "When set and the file exists, pfsense_query uses verify=<path>. "
            "When empty or file missing, falls back to verify=False (logged warning). "
            "Cert at default path: CN=pfsense-webgui-ca, valid until Apr 2036.",
        )
        LOG_FILE: str = Field(
            default="/opt/local-se/agent_commands.log",
            description="Path to the persistent agent command audit log. Shared log file "
            "with goethe.py's own Valves so PFSENSE-* log lines interleave with the rest "
            "of the audit trail.",
        )

    def __init__(self):
        self.valves = self.Valves()

    def _log(self, entry: str) -> None:
        """Append a timestamped line to the audit log (best-effort). Byte-identical
        to goethe.py's _log — duplicated here because this module is loaded
        standalone via `--also` and has no reference to the goethe Tools instance.
        """
        from datetime import datetime  # noqa: PLC0415

        try:
            log_path = self.valves.LOG_FILE
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(log_path, "a") as f:
                f.write(f"[{ts}] {entry}\n")
        except Exception:
            pass

    def _pfsense_verify(self):
        """Return verify param for pfSense requests: CA cert path or False."""
        import os as _os  # noqa: PLC0415

        cert = self.valves.PFSENSE_CA_CERT.strip()
        if cert and _os.path.isfile(cert):
            return cert
        if cert:
            self._log(
                f"PFSENSE-SSL-WARN: cert not found at {cert}, falling back to verify=False"
            )
        return False

    def _pfsense_cap_response(self, text: str, max_bytes: int = 32000) -> str:
        """Truncate an outbound pfSense response if it exceeds max_bytes.

        Defense-in-depth backstop, applied uniformly across all pfsense_*
        tools. Some pfSense GraphQL/REST responses have no pagination or size
        limit -- e.g. queryDiagnosticsTables returning built-in alias tables
        like 'bogons' (several thousand entries) inline. Confirmed incident
        2026-07-06: an unbounded response reached 2,966,261 tokens against a
        131,072 token context window, killing the session mid-response.
        A content-based check on the query string can't enumerate every large
        built-in collection type in advance -- this caps the RESPONSE instead,
        which catches all of them regardless of which field/table caused it.
        """
        encoded = text.encode("utf-8", errors="ignore")
        if len(encoded) <= max_bytes:
            return text
        truncated = encoded[:max_bytes].decode("utf-8", errors="ignore")
        self._log(
            f"PFSENSE-SIZE-CAP: response truncated from {len(encoded)} to {max_bytes} bytes"
        )
        return (
            truncated
            + f"\n\n...[TRUNCATED: full response was {len(encoded)} bytes, exceeds "
            f"the {max_bytes}-byte pfSense response cap. This usually means the query "
            "touched a large built-in collection (e.g. a diagnostics table like "
            "'bogons', or an unfiltered list type) -- not a firewall log. Narrow the "
            "query with more specific field selections or a filter argument if the "
            "type supports one; use pfsense_log_summary specifically for log data.]"
        )

    def pfsense_graphql(
        self,
        query: str,
        variables: dict = None,
        api_key: str = "",
    ) -> str:
        """
        Execute a GraphQL query or mutation against pfSense (pfrest.org package).
        Endpoint: POST https://pfsense.home.arpa/api/v2/graphql

        ── TOOL ROUTING — READ THIS FIRST ────────────────────────────────────────
        Three tools, three responsibilities. Use exactly the right one:

          pfsense_graphql    ← YOU ARE HERE — ALL reads and audits
          pfsense_query      ← writes only (POST/PATCH/PUT/DELETE)
          pfsense_log_summary← firewall logs only

        GATE — use pfsense_graphql for:
          • Any question about current pfSense state or configuration
          • Firewall rules audit, DHCP leases, ARP table, routing, interfaces
          • System status, version, uptime, CPU/memory
          • Security audit, device inventory, connection map
          • Anything that reads data without changing it

        DO NOT use pfsense_query for reads — GraphQL is always preferred for reads.
        DO NOT use pfsense_log_summary for config/state — it only reads firewall logs.
        ──────────────────────────────────────────────────────────────────────────

        AUTHENTICATION:
          vault_unlock() → get_vault_secret("pfsense-api-key") → pass as api_key.

        SCHEMA INTROSPECTION PROHIBITION:
          NEVER query __schema, __type, or any introspection field.
          The full GraphQL schema is enormous — introspection returns megabytes
          and will overflow the context window exactly like the log endpoint.
          BAD:  pfsense_graphql('{ __schema { ... } }')   ← context bomb
          BAD:  pfsense_graphql('{ __type(name:"FirewallRule") { fields { name } } }')
          If you are unsure of field names, use the common queries listed below.
          For placement/ordering parameters, see pfsense_query docstring — they are
          Common Control Parameters, not GraphQL fields.

        COMMON QUERIES (field names are case-sensitive — verify with KB if unsure):
          search_kb("pfsense GraphQL fields", topic_filter="pfsense") for the full schema.

          # System info
          { SystemVersion { version } }

          # All firewall rules
          { FirewallRule { id type interface src dst srcport dstport protocol descr enabled log } }

          # Active DHCP leases (LAN device map)
          { DHCPServerLease { ip mac hostname start end } }

          # ARP table
          { ARPTable { ip mac interface hostname } }

          # Interface stats
          { NetworkInterface { name descr status mac ipaddr } }

          # Routing gateways
          { RoutingGateway { name interface gateway monitor } }

          # Multi-resource in one call (preferred — reduces tool calls)
          {
            SystemVersion { version }
            DHCPServerLease { ip mac hostname }
            FirewallRule { type interface src dst descr enabled }
          }

        LOG ENDPOINT PROHIBITION:
          NEVER query firewall logs via GraphQL or pfsense_query.
          Use pfsense_log_summary(mode="compact") for all log analysis.

        Args:
            query:     GraphQL query string (without wrapping braces if simple field list,
                       or full `query { ... }` / `mutation { ... }` syntax).
            variables: Optional variables dict for parameterised queries.
            api_key:   pfSense API key from Vaultwarden.
        """
        import requests as _req
        import json as _json
        import re as _re  # noqa: PLC0415

        key = api_key.strip() or self.valves.PFSENSE_API_KEY.strip()
        if not key:
            return (
                "ERROR: No pfSense API key. "
                "Call vault_unlock() → get_vault_secret('pfsense-api-key') → pass as api_key."
            )

        # Wrap bare field list in query { } if not already wrapped
        q = query.strip()
        if not q.startswith(("{", "query", "mutation", "subscription")):
            q = f"{{ {q} }}"

        # LOG-ENDPOINT GUARD (code-level, item 1 -- 2026-07-06 post-incident hardening):
        # Docstring-only "NEVER query firewall logs via GraphQL" was not a reliable
        # backstop. Reject any query whose selection set expands a log-shaped type
        # (e.g. FirewallLog, StatusLogsFirewall) -- matched as an identifier containing
        # "log"/"logs" immediately followed by a sub-selection "{". This does NOT match
        # the legitimate scalar `log` field on FirewallRule (e.g. "... log }") since a
        # scalar leaf has no following "{".
        if _re.search(r"(?i)[a-z_]*logs?[a-z_]*\s*\{", q):
            return (
                "ERROR: pfsense_graphql rejected -- query touches a log-shaped GraphQL "
                "type (e.g. FirewallLog / StatusLogsFirewall). Raw log types can return "
                "megabytes of data and overflow the context window. Use "
                "pfsense_log_summary(mode=\"compact\") for all log analysis instead."
            )

        url = self.valves.PFSENSE_URL.rstrip("/") + "/api/v2/graphql"
        self._log(f"PFSENSE-GRAPHQL: {q[:120]}")
        try:
            resp = _req.post(
                url,
                headers={"X-API-Key": key, "Content-Type": "application/json"},
                json={"query": q, **({"variables": variables} if variables else {})},
                verify=self._pfsense_verify(),
                timeout=20,
            )
            try:
                data = resp.json()
                if "errors" in data:
                    return self._pfsense_cap_response(
                        f"GraphQL errors: {_json.dumps(data['errors'], indent=2)}"
                    )
                return self._pfsense_cap_response(
                    _json.dumps(data.get("data", data), indent=2)
                )
            except Exception:
                return f"[HTTP {resp.status_code}] {resp.text[:3000]}"
        except _req.exceptions.ConnectionError as e:
            return (
                f"ERROR: Cannot reach pfSense at {self.valves.PFSENSE_URL}. Detail: {e}"
            )
        except _req.exceptions.Timeout:
            return f"ERROR: pfSense GraphQL timed out after 20s."
        except Exception as e:
            return f"ERROR: pfsense_graphql failed: {e}"

    def pfsense_query(
        self,
        endpoint: str,
        method: str = "POST",
        payload: dict = None,
        api_key: str = "",
        confirmed: bool = False,
    ) -> str:
        """
        Write to the pfSense REST API v2 (POST, PATCH, PUT, DELETE only).
        Base URL: https://pfsense.home.arpa

        CONFIRMATION GATE — mandatory, code-enforced, applies to writes only:
          This function refuses to execute unless confirmed=True is passed
          explicitly. Reads (pfsense_graphql, pfsense_log_summary) are NOT
          affected by this gate -- only this function, and only real writes.
          Before calling with confirmed=True: show the user the exact
          endpoint, method, and payload you are about to send, and wait for
          an explicit yes. Confirmed 2026-07-06 incident: a write was executed
          during a read-only investigatory task with no explicit instruction
          to write and no confirmation -- this parameter exists so that gap
          cannot happen silently again.
          EXEMPT from this gate: any endpoint containing dry_run=true. A
          dry_run call validates the payload against pfSense without
          persisting anything (see Common Control Parameters below) -- it is
          not a write, so it does not require confirmation. Use it freely to
          preview a change before asking the user to confirm the real write.

        ── TOOL ROUTING — READ THIS FIRST ────────────────────────────────────────
        Three tools, three responsibilities. Use exactly the right one:

          pfsense_graphql    ← ALL reads and audits (use this first)
          pfsense_query      ← YOU ARE HERE — writes only
          pfsense_log_summary← firewall logs only

        GATE — use pfsense_query ONLY for:
          • POST   — create a firewall rule, alias, route, etc.
          • PATCH  — update an existing object by ID
          • PUT    — replace all objects (bulk write)
          • DELETE — remove an object

        DO NOT use pfsense_query for GET/read operations.
        Use pfsense_graphql for all reads — it is always preferred for reads.
        ──────────────────────────────────────────────────────────────────────────

        KB-FIRST RULE — mandatory before constructing any payload:
          Before calling this function, call:
            search_kb("pfsense REST API firewall rules", topic_filter="pfsense")
          The KB contains the full POST/PATCH payload schema, required fields,
          valid field values, validation error shapes, and placement semantics.
          Guessing field names or required fields from training data is a protocol
          violation — the API will reject the call with a 400 error.

          GOOD: search_kb("pfsense REST API firewall rules", topic_filter="pfsense")
                → inspect schema → pfsense_query("/api/v2/firewall/rule", "POST", payload)
          BAD:  pfsense_query("/api/v2/firewall/rule", "POST", {"type":"pass",...})
                ← payload constructed without KB read — wrong field names / missing
                   required fields → 400 error → retry loop

        LOG ENDPOINT PROHIBITION — mandatory, no exceptions:
          NEVER call /api/v2/status/logs/firewall via this function.
          Use pfsense_log_summary() for all log analysis.

        WRITE ACCESS PROTOCOL — mandatory before any write:
          1. Disable Read Only: pfSense UI → System → REST API → Read Only: off
          2. Perform the write operation
          3. Verify the result with pfsense_graphql
          4. Re-enable Read Only before ending the session
          5. Log the change in CHANGELOG: timestamp + what changed
          Leaving Read Only disabled at session end is a protocol violation.

        ORDERED RULE DEPLOYMENT — placement parameter:
          Rules are evaluated top-to-bottom per interface, first match wins.
          placement=N inserts the rule at index N (0-indexed). Existing rules
          at N and below are shifted down by one.
          placement=0   → top of the list (evaluated first)
          placement=N   → before the rule currently at index N
          omit placement → appended at the bottom (evaluated last)

          CORRECT PATTERN — always read position first, then write:
            Step 1: find the target index
              rules = pfsense_graphql('{ FirewallRule { id type interface descr } }')
              # Inspect output to find e.g. deny-all at index 19
            Step 2: insert before it
              pfsense_query(
                endpoint="/api/v2/firewall/rule",
                method="POST",
                payload={
                  "type": "pass", "interface": ["LAN"],
                  "ipprotocol": "inet", "protocol": "tcp",
                  "source": "192.168.1.16", "destination": "any",
                  "destination_port": "443",
                  "descr": "Allow Meross HTTPS",
                  "placement": 19,   ← inserts before the deny-all
                  "apply": True,
                },
                api_key=key
              )

          FIELD NAMES — v2.8.0+ schema (breaking change from v2.7.x, verified live
          2026-06-27; full reference in this skill's kb/firewall-rules-api.md):
            interface   → ARRAY of UPPERCASE strings, e.g. ["LAN"], NOT "lan"
            source      → flat string (was "src")
            destination → flat string (was "dst")
            destination_port → flat string (was "dstport")
          Guessing the old v2.7.x names (src/dst/dstport, lowercase bare interface)
          produces a 400 error. Required fields: type, interface, ipprotocol.

          DO NOT introspect the GraphQL mutation schema to find placement —
          placement is a Common Control Parameter, not endpoint-specific.
          DO NOT guess the position — always read first with pfsense_graphql.

        COMMON WRITE ENDPOINTS:
          POST   /api/v2/firewall/rule          — create firewall rule
          PATCH  /api/v2/firewall/rule?id=N     — update rule at index N
          DELETE /api/v2/firewall/rule?id=N     — delete rule at index N
          PUT    /api/v2/firewall/rules          — replace all rules (destructive)
          POST   /api/v2/firewall/apply          — apply pending firewall changes
          POST   /api/v2/firewall/alias          — create alias
          PATCH  /api/v2/firewall/alias?id=N     — update alias

        ALIAS CREATE — payload NOT live-verified (unlike the rule schema above);
        confirmed only as a read-side shape from pfrest.org's own docs. Always
        pass dry_run=true first and read the validation error if this is wrong:
              pfsense_query(
                endpoint="/api/v2/firewall/alias?dry_run=true",
                method="POST",
                payload={
                  "name": "iot_devices", "type": "host",
                  "address": ["192.168.1.16"], "detail": ["Meross plug"],
                  "descr": "IoT devices alias",
                },
                api_key=key
              )

        SSL: Uses /opt/local-se/cert/pfsense-webgui-ca.crt (falls back to verify=False).

        Args:
            endpoint:  API path, e.g. "/api/v2/firewall/rule"
            method:    POST | PATCH | PUT | DELETE (no GET — use pfsense_graphql instead)
            payload:   Dict for request body.
            api_key:   pfSense API key from Vaultwarden.
            confirmed: Must be True for any real (non-dry_run) write. Defaults to
                       False so an omitted/forgotten argument fails safe. Show the
                       user the exact call first, get an explicit yes, then retry
                       with confirmed=True.
        """
        import re as _re  # noqa: PLC0415
        import requests  # noqa: PLC0415
        import json as _json  # noqa: PLC0415

        key = api_key.strip() or self.valves.PFSENSE_API_KEY.strip()
        if not key:
            return (
                "ERROR: No pfSense API key. Set PFSENSE_API_KEY valve or retrieve from "
                "Vaultwarden: vault_unlock() → get_vault_secret('pfsense-api-key') → "
                "pass result as api_key parameter."
            )

        method = method.upper()
        if method == "GET":
            return (
                "ERROR: pfsense_query is for writes only. "
                "Use pfsense_graphql() for all read operations."
            )

        # LOG-ENDPOINT GUARD (code-level, item 1 -- 2026-07-06 post-incident hardening):
        # Docstring-only "NEVER call /api/v2/status/logs/firewall" was not a reliable
        # backstop. Hard-reject any endpoint with a /log or /logs path segment.
        if _re.search(r"(?i)/logs?(/|\?|$)", endpoint):
            return (
                "ERROR: pfsense_query rejected -- endpoint touches a log path "
                f"({endpoint!r}). Log data can return megabytes and overflow the "
                "context window. Use pfsense_log_summary(mode=\"compact\") for all "
                "log analysis instead."
            )

        is_dry_run = bool(_re.search(r"dry_run=true", endpoint, _re.IGNORECASE))
        if not confirmed and not is_dry_run:
            self._log(
                f"PFSENSE-WRITE-BLOCKED: unconfirmed {method} {endpoint} "
                f"(confirmed=False, dry_run={is_dry_run})"
            )
            return (
                "ERROR: This write requires explicit user confirmation first. "
                f"Proposed call: {method} {endpoint} payload={payload}. "
                "Show the user this exact endpoint, method, and payload, wait for "
                "an explicit yes, then call pfsense_query again with confirmed=True. "
                "To validate the payload without writing anything, add dry_run=true "
                "to the endpoint instead -- that does not require confirmation."
            )

        url = self.valves.PFSENSE_URL.rstrip("/") + "/" + endpoint.lstrip("/")
        self._log(f"PFSENSE-WRITE: {method} {url} confirmed={confirmed} dry_run={is_dry_run}")

        try:
            resp = requests.request(
                method=method,
                url=url,
                headers={
                    "X-API-Key": key,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=payload if payload else None,
                verify=self._pfsense_verify(),
                timeout=15,
            )
            try:
                return self._pfsense_cap_response(_json.dumps(resp.json(), indent=2))
            except Exception:
                return f"[HTTP {resp.status_code}] {resp.text[:2000]}"
        except requests.exceptions.ConnectionError as e:
            return (
                f"ERROR: Cannot reach pfSense at {self.valves.PFSENSE_URL}. Detail: {e}"
            )
        except requests.exceptions.Timeout:
            return f"ERROR: pfSense API timed out after 15s ({url})."
        except Exception as e:
            return f"ERROR querying pfSense API: {e}"

    def pfsense_log_summary(
        self,
        hours: int = 24,
        top_n: int = 10,
        mode: str = "compact",
        api_key: str = "",
    ) -> str:
        """
        Return a compact pfSense firewall log summary via the local log gateway.

        ── TOOL ROUTING — READ THIS FIRST ────────────────────────────────────────
        Three tools, three responsibilities. Use exactly the right one:

          pfsense_graphql    ← ALL reads and audits (config, rules, leases, ARP)
          pfsense_query      ← writes only (POST/PATCH/PUT/DELETE)
          pfsense_log_summary← YOU ARE HERE — firewall logs only

        GATE — use this function ONLY for:
          - "pfSense audit report" / "stability report" / "security report"
          - "firewall log analysis" / "what's being blocked" / "traffic patterns"
          - "is device X phoning home?" / "outbound connections from IP"
          - Any question about blocked IPs, blocked ports, or packet-level activity
          DO NOT use this for reading config, rules, leases, or system state.
          Use pfsense_graphql for config/state questions.
        ──────────────────────────────────────────────────────────────────────────

        LOG ACCESS PROHIBITION — mandatory, no exceptions:
          NEVER call pfsense_query('/api/v2/status/logs/firewall') for log analysis.
          That endpoint returns raw data (up to 2.7M tokens) which overflows the
          96k context window and terminates the session mid-response.
          NEVER call pfsense_query() or pfsense_graphql with any /logs/ endpoint.

          GOOD: pfsense_log_summary(hours=24, mode="compact")   ← gateway returns <4KB
          BAD:  pfsense_query('/api/v2/status/logs/firewall')    ← 2.7M tokens, session dies
          BAD:  pfsense_graphql('{ FirewallLog { ... } }')       ← same overflow risk

        HOW IT WORKS:
          Calls the local log gateway (http://localhost:9191) which pre-aggregates
          pfSense logs server-side before returning structured JSON.
          The gateway response is always under 32KB regardless of log volume.
          If the gateway is not running it is started automatically.

        MODE SELECTION:
          mode="compact"  (default) — dense audit summary, use for full reports (<4KB)
          mode="summary"            — structured stats only, faster for single questions

        RETURNED FIELDS (compact mode):
          pfsense.version, pfsense.uptime, pfsense.dhcp_active_leases
          firewall.total_entries_parsed, firewall.total_blocks, firewall.total_pass
          firewall.top_blocked_ips[{ip, count}]
          firewall.top_blocked_ports[{port, protocol, count}]
          firewall.interface_stats
          recent_block_sample

        PRE-CALL REQUIREMENT — mandatory, no exceptions:
          Before calling this function, retrieve the pfSense API key from Vaultwarden:
            vault_unlock() → get_vault_secret("pfsense-api-key") → pass here as api_key
          Calling without api_key when the gateway is not running will fail.
          If the gateway is already running from this session, api_key can be omitted.

        Args:
            hours:   Time window in hours (default 24).
            top_n:   Top N IPs/ports in summary mode (default 10, max 20).
            mode:    "compact" for audit reports, "summary" for quick stats.
            api_key: pfSense API key from Vaultwarden. Required to start the gateway.
        """
        import json as _json
        import subprocess

        GATEWAY_URL = "http://localhost:9191"
        GATEWAY_SCRIPT = "/opt/local-se/pfsense-gateway-tools.sh"

        def _ensure_gateway():
            """Start the gateway if not running.

            Key resolution order:
              1. api_key parameter (retrieved from Vaultwarden by LSE)
              2. PFSENSE_API_KEY env var (fallback if already set in environment)
            If none found, gateway starts keyless — pass api_key on each request.
            """
            import requests as _req
            import time as _time

            # Already running?
            try:
                r = _req.get(f"{GATEWAY_URL}/health", timeout=3)
                if r.status_code == 200:
                    return True, None
            except Exception:
                pass

            # Key comes from the api_key parameter — retrieved from Vaultwarden by LSE.
            # No secrets files. No valves. LSE calls vault_unlock() → get_vault_secret()
            # → passes result here. Fallback to PFSENSE_API_KEY env if already set.
            pf_key = api_key.strip() or os.environ.get("PFSENSE_API_KEY", "").strip()
            if not pf_key:
                # Gateway can start without key; key passed per-request via ?api_key=
                pf_key = ""

            # Start gateway with key in environment
            env = os.environ.copy()
            env["PFSENSE_API_KEY"] = pf_key
            try:
                subprocess.Popen(
                    ["bash", GATEWAY_SCRIPT, "restart"],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                _time.sleep(3)
                r = _req.get(f"{GATEWAY_URL}/health", timeout=5)
                if r.status_code == 200:
                    return True, None
                return (
                    False,
                    f"ERROR: Gateway started but /health returned {r.status_code}. Check /opt/local-se/logs/gateway.log",
                )
            except Exception as e:
                return False, f"ERROR: Could not start gateway: {e}"

        ok, err = _ensure_gateway()
        if not ok:
            return err or (
                "ERROR: pfSense log gateway not running and could not be started. "
                f"Run manually: bash {GATEWAY_SCRIPT} restart"
            )

        try:
            import requests as _req

            endpoint = "/compact" if mode == "compact" else "/summary"
            params = {"hours": hours}
            if mode == "summary":
                params["top"] = min(top_n, 20)
            # Forward the API key per-request — gateway uses it for pfSense calls
            # without storing it between requests (KISS: key comes from Vaultwarden each time)
            if api_key.strip():
                params["api_key"] = api_key.strip()

            r = _req.get(f"{GATEWAY_URL}{endpoint}", params=params, timeout=30)
            r.raise_for_status()
            data = r.json()

            self._log(
                f"PFSENSE-LOG-SUMMARY: gateway={mode} hours={hours} "
                f"blocks={data.get('firewall', {}).get('total_blocks', '?')}"
            )
            return self._pfsense_cap_response(_json.dumps(data, indent=2))

        except Exception as e:
            return f"ERROR: pfsense_log_summary — gateway call failed: {e}"

