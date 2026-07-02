# pfSense REST API v2 — Firewall Rule Operations (Complete Reference)

**Source:** pfrest.org + pfSense-pkg-RESTAPI source + live Swagger at https://pfsense.home.arpa/api/v2/documentation
**Topic:** pfsense
**Quality:** 0.95 (ground-truth verified on live API 2026-06-27)
**Last updated:** 2026-06-27
**API Version:** pfSense-pkg-RESTAPI v2.8.0+ (schema migration from v2.7.x)
**Breaking changes from v2.7.x:** `interface`→array+uppercase, `src`→`source`, `dst`→`destination`, `dstport`→`destination_port`

---

## Endpoints

| Method | Endpoint | Action |
|--------|----------|--------|
| GET    | /api/v2/firewall/rules | List all rules |
| GET    | /api/v2/firewall/rule?id=N | Get one rule by index |
| POST   | /api/v2/firewall/rule | Create one rule |
| PATCH  | /api/v2/firewall/rule?id=N | Update one rule |
| DELETE | /api/v2/firewall/rule | Delete one rule — body: `{"id": N}` |
| PUT    | /api/v2/firewall/rules | Replace ALL rules (destructive) |

---

## Full Rule Payload Schema (POST/PATCH)

> **v2.8.0+ schema** — tested live 2026-06-27. Do NOT use v2.7.x field names (`src`/`dst`/`dstport`).

```json
{
  "type":               "pass|block|reject",
  "interface":          ["LAN"]|["WAN"]|["OPT1"]|["OPT2"],
  "ipprotocol":         "inet|inet6|inet46",
  "protocol":           "tcp|udp|tcp/udp|icmp|any",
  "source":             "any|<ip>|<cidr>|<alias>",
  "source_port":        "any|<port>|<port-range>",
  "destination":        "any|<ip>|<cidr>|<alias>",
  "destination_port":   "any|<port>|<port-range>",
  "gateway":            "",
  "descr":              "Human-readable label",
  "disabled":           false,
  "log":                false,
  "quick":              true,
  "statetype":          "keep state|sloppy state|synproxy state|none",
  "direction":          "any|in|out",
  "floating":           false,
  "apply":              true
}
```

**Required fields:** `type`, `interface`, `ipprotocol`
**Default when omitted:** `source=any`, `destination=any`, `source_port=any`, `destination_port=any`, `protocol=any`, `disabled=false`, `log=false`, `quick=true`

**Critical field rules:**
- `interface` is an **array** of **UPPERCASE** strings: `["OPT1"]`, `["LAN"]`
- `source` and `destination` are **flat strings** (not nested objects)
- Port fields are `source_port` / `destination_port` (NOT `srcport` / `dstport`)

---

## placement=N Semantics

- **0-indexed**: `placement=0` inserts at the TOP (first rule evaluated)
- `placement=1` inserts at position 1 (second rule)
- Omitting `placement` appends at the BOTTOM (last rule, evaluated last)
- **Scope is per-interface**: placement 0 on `lan` means first LAN rule, not first global rule
- **pfSense evaluates rules top-to-bottom, first match wins** (`quick=true` enforces this)

To insert BEFORE a known rule at index N: use `placement=N`
To insert AFTER a known rule at index N: use `placement=N+1`

---

## Finding a Rule's ID (for PATCH/DELETE)

Rule IDs are positional indices (0-based) within the interface rule list.

```bash
# List all rules with their IDs
curl -H "X-API-Key: <key>" https://pfsense.home.arpa/api/v2/firewall/rules | \
  python3 -c "import sys,json; rules=json.load(sys.stdin)['data']; \
  [print(f'id={i} iface={r[\"interface\"]} type={r[\"type\"]} descr={r.get(\"descr\",\"\")}') \
  for i,r in enumerate(rules)]"
```

Or filter by description:
```bash
GET /api/v2/firewall/rules?descr__contains=Meross
```

Or filter by interface:
```bash
GET /api/v2/firewall/rules?interface=lan
```

---

## Apply Timing

**Two ways to apply changes:**

1. **Inline apply** (recommended): add `apply=true` to POST/PATCH payload
   - Rule is written AND firewall is reloaded in one call
   - May be slower (waits for pf reload)

2. **Deferred apply**: omit `apply` or set `apply=false`, then call:
   ```
   POST /api/v2/firewall/apply
   ```
   - Useful when making multiple rule changes — batch them, apply once at end
   - Rules are staged but not active until apply is called

**Check pending changes:**
```
GET /api/v2/firewall/apply
```
Returns `{"data": {"applied": true}}` if no pending changes.

---

## Bulk Rule Operations

```bash
# Replace ALL rules on ALL interfaces (destructive — replaces everything)
PUT /api/v2/firewall/rules
Body: [{"type":"pass","interface":["LAN"],...}, ...]

# This is a full replacement — not an append.
# Use with dry_run=true first to validate:
PUT /api/v2/firewall/rules?dry_run=true
```

**Safer bulk pattern:** fetch all → modify list in Python → PUT back

---

## Rule Validation Errors

Common error shapes:
```json
{"code": 400, "status": "bad request", "message": "...", "data": null}
```

| Error | Cause |
|-------|-------|
| `invalid interface` | Interface name not found or wrong case (use `"LAN"` not `"lan"` — must be uppercase in array) |
| `invalid protocol` | Protocol not in allowed set |
| `invalid ip format` | source/destination not a valid IP, CIDR, or alias |
| `invalid port` | Port not numeric or not a defined alias |
| `placement out of range` | placement > number of existing rules on that interface |

Always use `dry_run=true` on first attempt for new rule shapes.

---

## Rule Ordering Guarantees

- Rules are evaluated **per interface, top to bottom**
- **`quick=true`** (default): first match stops evaluation — order is critical
- `quick=false`: pfSense continues evaluating all rules (rare, for logging)
- Floating rules (`floating=true`) are evaluated BEFORE interface-specific rules
- After `apply=true`, rule order in pfSense UI matches the API order

**Safe insert-before pattern:**
```python
# 1. Get current rules
rules = GET /api/v2/firewall/rules?interface=lan
# 2. Find target rule index
idx = next(i for i,r in enumerate(rules) if r['descr'] == 'My Target Rule')
# 3. Insert before it
POST /api/v2/firewall/rule body={"placement": idx, "apply": true, ...}
```

---

## Interface Name Reference

| Display Name | API Value (in array) |
|-------------|---------------------|
| LAN | `"LAN"` |
| WAN | `"WAN"` |
| OPT1 | `"OPT1"` |
| OPT2 | `"OPT2"` |
| WLAN | `"WLAN"` |
| IoT | `"IoT"` |
| WireGuard | `"TUN_WG0"` |
| VLAN interface | e.g. `"igc0_vlan10"` |

**Rules:** Values are **UPPERCASE** and passed as **array**: `["OPT1"]`.
**Verified valid set:** `[WAN, LAN, TUN_WG0, OPT2, WLAN, OPT1, IoT, WANPHY, WireGuard, Tailscale, enc0, openvpn, any]`
Get all interface names: `GET /api/v2/interfaces`

---

## Minimal Working Examples

**Block a specific IP on LAN:**
```bash
curl -sk -X POST -H "X-API-Key: <key>" -H "Content-Type: application/json" \
  https://pfsense.home.arpa/api/v2/firewall/rule \
  -d '{"type":"block","interface":["LAN"],"ipprotocol":"inet","source":"192.168.1.50","destination":"any","descr":"Block IoT device","apply":true}'
```

**Block outbound port 1883 (MQTT) from IoT device:**
```bash
curl -sk -X POST -H "X-API-Key: <key>" -H "Content-Type: application/json" \
  https://pfsense.home.arpa/api/v2/firewall/rule \
  -d '{"type":"block","interface":["LAN"],"ipprotocol":"inet","protocol":"tcp","source":"192.168.1.16","destination":"any","destination_port":"1883","descr":"Block Meross MQTT","log":true,"apply":true}'
```

**Allow UDP 1900 (SSDP) on OPT1:**
```bash
curl -sk -X POST -H "X-API-Key: <key>" -H "Content-Type: application/json" \
  https://pfsense.home.arpa/api/v2/firewall/rule \
  -d '{"type":"pass","interface":["OPT1"],"ipprotocol":"inet","protocol":"udp","source":"192.168.5.0/24","destination":"239.255.255.250","destination_port":"1900","descr":"SSDP discovery","apply":true}'
```

**Delete a rule by ID:**
```bash
curl -sk -X DELETE -H "X-API-Key: <key>" -H "Content-Type: application/json" \
  https://pfsense.home.arpa/api/v2/firewall/rule \
  -d '{"id":34}'
```

**Validate without writing:**
```bash
# Add dry_run=true to query string
curl -sk -X POST "https://pfsense.home.arpa/api/v2/firewall/rule?dry_run=true" \
  -H "X-API-Key: <key>" -H "Content-Type: application/json" \
  -d '{"type":"block","interface":["LAN"],...}'
```
