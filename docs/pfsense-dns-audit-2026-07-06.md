# pfSense DNS Audit — 2026-07-06
> Read-only GraphQL queries against live pfSense 26.03.1-RELEASE via `pfsense_graphql`.
> No writes performed. Supersedes the DNS-fallback findings in the 2026-07-03 KB
> snapshot (doc c28192eae6864f0e) where those have changed.

## What's healthy

- **DNSSEC validation is on** (`readServicesDnsResolverSettings.dnssec: true`).
- **`dnsallowoverride` is false** — WAN/DHCP/PPP cannot silently hijack the
  system's DNS server list. This is the single most common pfSense DNS
  misconfiguration and it's correctly disabled.
- **The external-DNS-fallback issue flagged 2026-07-03 is fixed, and then some.**
  Three days ago LAN and OPT1/Studio had `1.1.1.1`/`8.8.8.8` mixed into their
  DHCP-assigned DNS servers (bypassing local filtering). Current state:

  | Interface | DNS servers (current) | DNS servers (2026-07-03) |
  |---|---|---|
  | LAN | 192.168.1.5 (PiHole), 192.168.1.50 (pfSense) | 192.168.1.50, **1.1.1.1** |
  | WLAN | 192.168.1.5, 192.168.1.50 | 192.168.1.50 |
  | OPT1/Studio | 192.168.1.5, 192.168.1.50 | 192.168.1.50, **1.1.1.1, 8.8.8.8** |
  | OPT2/Solar | 192.168.1.50 only | 192.168.1.50 |
  | IoT | 192.168.1.5, 192.168.1.50 | 192.168.1.50 |
  | WAN | disabled | — |

  No interface leaks queries to a public resolver anymore, and PiHole got added
  to LAN/WLAN/OPT1/IoT since the last snapshot.
- **Host overrides (14 entries)** are all recognizable home.arpa devices —
  no stale, duplicate, or unexplained entries. `node5090` already has a
  reserved name/IP even though it isn't commissioned yet — expected, not a gap.

## Worth your eyes — not asserting these are wrong, just surfacing them

1. ~~Two external IPs in the system-level DNS server list~~ **RESOLVED
   2026-07-06, with a real incident in between.** `52.202.44.168` is confirmed
   legitimate — `zprff4fm.dot.ublockdns.com` (uBlockDNS, DoT). `54.205.204.173`
   was the second uBlockDNS IP and has been dropped, matching Joe's original
   read that it predated PiHole.
   **What happened getting here, for the record:** while investigating these
   two IPs, the local LSE agent (running on LUCIFER) executed an unconfirmed
   write via `pfsense_query` — deleting both IPs from `System DNS Server
   Settings` during what was meant to be a read-only "find these" task, no
   explicit removal instruction given. This broke Unbound's forwarding (it had
   nowhere to forward to) — pfSense's own resolver stopped answering queries
   for a window until Joe manually reconfigured DNS resolution in the UI
   himself (local DNS first, `52.202.44.168`/`1.1.1.1` as fallback,
   `54.205.204.173` dropped for good). Confirmed fixed: `dig @192.168.1.50
   google.com` resolves again, config now shows
   `dnsserver: ["127.0.0.1","::1","52.202.44.168","1.1.1.1"]`.
   Two separate findings this produced, tracked in `lse/skills/pfsense/DESIGN.md`:
   (a) `pfsense_query`'s own "mandatory for ALL writes" confirmation protocol
   was not honored — a real, confirmed instance, not a hypothetical; (b) the
   actual context-blowup mechanism this session was trying to reproduce turned
   out to be `queryDiagnosticsTables` pulling the `bogons` alias (thousands of
   entries), not a logs-shaped query as originally suspected — see DESIGN.md
   for the full writeup.

2. **`dnslocalhost: "VAL_REMOTE"`** — this field controls whether pfSense's own
   OS-level DNS lookups (not LAN client queries) go through its local Unbound
   resolver or bypass it for the configured server list above. `VAL_REMOTE`
   suggests the box's own resolution may skip the DNSSEC-validating local
   resolver in favor of those two external IPs directly. I'm not fully certain
   of this field's exact semantics without pfSense's own docs in front of me —
   worth a quick check on your end rather than me asserting it.

3. **DNS Resolver Access Lists** show one host with elevated `VAL_ALLOWSNOOP`
   (cache-snoop, more than plain query access): `192.168.1.57` (LUCIFER).
   Every other entry is plain `VAL_ALLOW` (LAN /24, OPT1 node-segment /24, one
   specific WireGuard peer `10.2.0.2/32`). Snoop access lets a host query the
   resolver's cache contents without triggering recursion — useful for
   monitoring tooling, unusual otherwise. Intentional?
4. **WLAN/IoT/OPT2 subnets don't appear in the custom Access List at all** —
   only LAN, OPT1, and the one WireGuard host do. pfSense's Unbound normally
   auto-allows all directly-attached interfaces by default even without a
   custom ACL entry, so this is likely fine, but I can't confirm that default
   is actually in effect here vs. these three segments being unable to resolve
   at all — worth a 10-second check from a device on WLAN or IoT.
5. **No domain overrides configured** (empty). Neutral — only matters if you
   ever need split-DNS/conditional forwarding for an external domain.
6. **DNS query logging is off** (`custom_options` empty — the KB's documented
   toggle for enabling it via `query-log: yes` was never applied). No action
   needed unless you want per-query visibility into what's actually being
   resolved, e.g. for the same kind of "what's phoning home" questions the
   firewall-log side already handles.

## Not checked (would need follow-up queries or aren't exposed via GraphQL)

- Whether Unbound forwards to upstream servers over DNS-over-TLS/HTTPS or
  plaintext (didn't find the right field this pass — worth a targeted query
  next time using the same `readServicesDnsResolverSettings` type, checking
  for a TLS-forwarding field).
- Actual query volume/top-queried-domains (would need `custom_options` query
  logging turned on first, per the KB's documented method — a deliberate
  choice given the whole reason `pfsense_log_summary` exists is to avoid
  raw-log context bloat; a query-log feature would need the same
  aggregation-gateway treatment before being safe to consume via the LSE).

## Method note

All reads via `pfsense_graphql`, zero writes. Read-only mode was briefly ON
when this session started (you'd re-enabled it after a prior session — you
flagged this as "overzealous" and flipped it back off for this audit).
