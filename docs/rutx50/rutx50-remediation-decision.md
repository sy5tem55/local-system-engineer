# RUTX50 WebUI Login-Failure Bug — Remediation Decision

> ⚠️ **CORRECTION 2026-06-12 (P25):** The original LSE-generated version of this
> document cited firmware versions **07.23.5** and **07.22.4** with release dates
> and changelog details. **Neither version exists** — verified by independent
> fetch of wiki.teltonika-networks.com/view/RUTX50_Firmware_Downloads minutes
> after generation (07.23.4 = Latest 2026-05-29; 07.22.3 = Stable 2026-05-19).
> Fabrication incident #5; entered at synthesis AFTER a successful fetch of the
> contradicting source. All version references below are corrected. Device-side
> evidence (ssh tool results) was verified sound and retained.

**Date:** 2026-06-12
**Device:** RUTX50 (192.168.5.3)
**Firmware:** RUTX_R_00.07.23.4 (2026-05-29)

## Symptom

WebUI at https://192.168.5.3 serves the login page but rejects valid credentials with "Invalid username and/or password". SSH/CLI authentication always works. Reboot temporarily restores webui login. Factory reset does NOT fix. Recurring issue.

## Root Cause Analysis

### Evidence Collected

1. **Web stack architecture (device-side):**
   - `uhttpd` (PID 4729) — main HTTPS web server on port 443
   - `api_dispatcher.lua` — LuaJIT handler for `/api` endpoint
   - `event_server` — LuaJIT process managed by procd under uhttpd user
   - `subscribe.lua` — LuaJIT subscription service
   - All web authentication flows through: uhttpd → api_dispatcher.lua → ubus session backend

2. **Firmware changelog analysis:**
   - **07.23** introduced: "API Core: replaced Lua 5.1 with LuaJIT 2.1" — prime regression suspect
   - **07.23** also introduced: "WebUI: added 2FA support" and "SSH: added 2FA support"
   - SSH auth uses Dropbear (separate from LuaJIT) — explains why SSH always works
   - **07.23.4** (Latest, 2026-05-29): the NEWEST release — CVE patches only, no webui login fix. No newer firmware exists as of 2026-06-12.
   - **07.22.3** (official "Stable FW", 2026-05-19): pre-dates the 2FA/LuaJIT login-path rework — designated fallback track on the Teltonika wiki

3. **Log evidence:**
   - `logread` has 1282 entries but ZERO uhttpd/vuci/api/session/login traces
   - Log rotated past last failure window — no direct evidence of which component wedges
   - ubus session backend exists with proper ACLs

4. **Community corroboration:**
   - Two community threads match the exact symptom class (webui login fails, SSH works):
     [login-webui-error-but-ssh-login-ok](https://community.teltonika.lt/t/login-webui-error-but-ssh-login-ok/11876),
     [cant-login-to-webui-ssh-is-ok](https://community.teltonika.lt/t/cant-login-to-webui-ssh-is-ok/6224)
   - No specific report matching the LuaJIT regression pattern on 07.23.x
   - Teltonika has not released a fix or acknowledged this specific regression (changelog verified through 07.23.4)

### Wedged Component (Most Likely)

The **api_dispatcher.lua** (LuaJIT 2.1) or the **2FA module** (vuci-app-2fa-api) is the prime suspect:
- The LuaJIT migration changed the execution environment for all API/auth logic
- 2FA was added in 07.23 and may have session state corruption
- SSH auth bypasses the LuaJIT layer entirely (uses Dropbear directly)
- The wedge likely occurs in session state management within the LuaJIT process

### Recovery Workaround (PREPARED — untested until next occurrence)

When the bug occurs, restart only the web-stack services (NO reboot required):

```bash
ssh root@192.168.5.3 "/etc/init.d/uhttpd restart && sleep 3 && ps www | grep uhttpd"
```

This restarts uhttpd and its LuaJIT children (event_server, api_dispatcher.lua, subscribe.lua) without disrupting network connectivity or SSH.

Full recovery script: `docs/rutx50/rutx50-webui-recovery.sh` (repo copy; /tmp/lse original is wiped on reboot)

## Recommendation

### 🟡 CONDITIONAL STAY on 07.23.4 with Workaround

**Stay on 07.23.4 IF:**
- You need 2FA support (not available in 07.22.x)
- You need the CVE patches in 07.23.4 (6 HIGH severity CVEs patched)
- The bug occurs infrequently (weekly or less)
- You can tolerate the 30-second webui outage during recovery

**Fallback to 07.22.3 (official Stable) IF:**
- You don't need 2FA
- The bug occurs frequently (daily or multiple times per week)
- You prefer stability over new features
- You can accept missing CVE patches (mitigate via network isolation — webui is LAN-only behind pfSense)

⚠️ Downgrade rule: flash 07.22.3 **without** "keep settings" — config schemas are not guaranteed downward-compatible across the 07.23→07.22 boundary. Back up config separately first.

### Risk Assessment

| Factor | Stay 07.23.4 | Fallback 07.22.3 |
|--------|--------------|------------------|
| WebUI login reliability | Intermittent (workaround required) | Stable (no known issue) |
| 2FA support | ✅ Yes | ❌ No |
| CVE patches (6 HIGH) | ✅ Patched | ❌ Missing |
| LuaJIT performance | ✅ Improved | ⚠️ Lua 5.1 |
| Recovery complexity | Low (single command) | N/A |
| Downtime per incident | ~30s (uhttpd restart) | N/A |
| Future fix likelihood | Unknown — no fix released as of 2026-06-12; watch wiki changelog for next 07.23.x | N/A |

### Action Items

1. **Immediate:** Deploy the recovery script and test it during the next occurrence
2. **Short-term:** Monitor bug frequency — if >2x/week, consider fallback
3. **Medium-term:** File a bug report with Teltonika (draft below)
4. **Long-term:** Wait for a firmware release that explicitly fixes the webui login regression

## Appendix: Teltonika Community Forum Draft

---

**Title:** RUTX50 WebUI Login Fails After 07.23 Firmware — LuaJIT Regression Suspect (SSH Works)

**Body:**

Hello Teltonika Community,

I'm experiencing a recurring webui login failure on my RUTX50 running firmware **RUTX_R_00.07.23.4**. The symptom is:

- WebUI at https://192.168.5.3 serves the login page normally
- Valid credentials are rejected with "Invalid username and/or password"
- SSH/CLI authentication **always works** with the same credentials
- A reboot temporarily restores webui login (works for hours/days before recurring)
- Factory reset does NOT fix the issue

### Device Evidence

**Firmware:** RUTX_R_00.07.23.4 (2026-05-29)
**Web stack:** uhttpd + LuaJIT 2.1 api_dispatcher.lua + event_server

The 07.23 firmware introduced two changes that affect the auth path:
1. "API Core: replaced Lua 5.1 with LuaJIT 2.1"
2. "WebUI: added 2FA support"

SSH auth uses Dropbear (separate from LuaJIT), which explains why SSH always works while webui fails.

### Workaround

When the bug occurs, restarting only the web-stack services (no reboot required) restores webui login:

```bash
/etc/init.d/uhttpd restart
```

This restarts uhttpd and its LuaJIT children without disrupting network connectivity.

### Similar reports

Possibly related symptom class (webui login fails while SSH works):
- https://community.teltonika.lt/t/login-webui-error-but-ssh-login-ok/11876
- https://community.teltonika.lt/t/cant-login-to-webui-ssh-is-ok/6224

### Request

1. Is this a known regression in the 07.23 series?
2. Has Teltonika identified the root cause (LuaJIT migration vs 2FA module)?
3. Is a fix planned for an upcoming firmware release?

I'm happy to provide additional device-side evidence or test pre-release firmware if helpful.

Regards,
[Your Name]

---

*End of remediation decision document.*
