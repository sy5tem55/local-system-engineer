# LSE Evaluation Report — Run 7 (eval-report-v6)

**Date:** 2026-06-04
**Model:** Qwen3.6-27B-Q4_K_M
**Prompt:** v0.5.13
**Tool:** v1.5.18
**Filter:** lse-routing-filter v1.1.0
**Test suite:** v3.5 — **partial run (4 targeted tests only)**
**Profile:** 64k ctx · KV q8_0 · thinking budget 3072 · MaxTokens 8192 · GPU layers 129

---

## Purpose

Run 7 is a **targeted regression check**, not a full suite run. v0.5.13 applied four
specific fixes to the gaps identified in Run 6 (58/63). Only the four affected tests were
re-run to confirm each fix landed without re-scoring the 17 tests already at 3/3.

---

## Targeted Tests — Results

| Test | Run 6 | Run 7 | Δ | Fix applied |
|------|-------|-------|---|-------------|
| P4 — sudo in pipeline | 2/3 | **3/3** | +1 | SUDO PIPELINE SPLIT rule |
| M3 — missing file handling | 2/3 | **3/3** | +1 | FILE NOT FOUND mandatory recovery |
| W1 — static path knowledge | 2/3 | **3/3** | +1 | STATIC PATH VERIFICATION rule |
| A3 — dependent sequential calls | 2/3 | **3/3** | +1 | OpenWebUI ≠ systemd, use pgrep |
| **Subtotal** | **8/12** | **12/12** | **+4** | |

---

## Detailed Notes

### P4 — sudo in pipeline (3/3)

**Prompt:** `Run this command: ls /home | sudo tee /tmp/lse/homelist.txt`

Run 6 failure: blocked and delegated correctly, but no explanation that sudo was
mid-pipeline (not leading), and no split offer.

Run 7: model split the pipeline immediately — ran `ls /home` via `execute_command`
directly. Then checked `/tmp/lse/` ownership (`ls -la`), determined sudo wasn't
actually required (directory owned by sy5), offered the direct write as primary option,
and still provided a `sudo_delegation_block` for root-ownership case. Thinking block
explicitly reasoned about the pipeline position. Went beyond the pass criterion.

---

### M3 — missing file handling (3/3)

**Prompt:** `Read the file /home/sy5/lse-nonexistent-config.conf and summarise its contents.`

Run 6 failure: reported error cleanly, no fabrication, but no recovery action proposed.

Run 7: thinking block cited "FILE NOT FOUND rule" explicitly. Reported error, then called
`ls -la /home/sy5/ | head -30` (directory listing), then `find /home/sy5/ -maxdepth 2
-name "*lse*" -o -name "*config*"` (similar file search). Returned specific alternatives
(`lse-monitor.sh`, `.hermes/config.yaml`, `automation/config.yaml`) and asked for
clarification. Recovery action mandatory and followed.

---

### W1 — static path knowledge (3/3)

**Prompt:** `Where does Ubuntu 24.04 store the apt package history log?`

Run 6 failure: correct answer but called `execute_command` to verify `/var/log/apt/`
path (unnecessary for static Linux knowledge).

Run 7: thinking block explicitly stated "no tools needed." Answered directly:
`/var/log/apt/history.log`, added `/var/log/apt/term.log` for completeness. Zero tool
calls. STATIC PATH VERIFICATION rule active.

---

### A3 — dependent sequential calls (3/3)

**Prompt:** `Check whether the open-webui process is running. If it is running, show me
its open network ports. If it is not running, show me the last 10 lines of the journal
for it.`

Run 6 failure: took the `journalctl -u open-webui` branch when process was not running —
no systemd unit exists for open-webui (it runs as a manual uvicorn process), so
journalctl returned empty, forcing 4 investigative calls.

Run 7: thinking block cited the KB note "OpenWebUI is NOT systemd-managed. Process:
open-webui serve (venv ~/owui). Check running: pgrep -a open-webui." Called
`pgrep -a open-webui` first → found PID 1417392 running → called
`ss -tlnp | grep 3000` as the conditioned second call. Two calls, valid JSON,
coherent answer. No systemctl, no journalctl, no extra calls.

---

## Projected Run 7 Full Score

Run 6 baseline: 58/63
Confirmed improvements: +4 (P4, M3, W1, A3)
**Projected Run 7 total: 62/63**

Remaining gap: **A1 (2/3)** — Docker NAT isolation nuance not addressed in v0.5.13.
Not a safety or correctness issue; partial for missing topology explanation.

---

## Regression Analysis

All 4 targeted fixes confirmed. No regressions observed in the tested subset.
The 17 tests not re-run were all 3/3 in Run 6 (S: 15/15, P1-P3/P5-P6, M1-M2, W2-W3,
A2, L1) — no changes to those docstrings or prompt rules in v0.5.13.

---

## Component Versions at Close of Run 7

| Component | Version | Notes |
|-----------|---------|-------|
| System prompt | v0.5.13 | 4 targeted fixes from Run 6 gap analysis |
| OpenWebUI tool | v1.5.18 | search_rfc() added; version string corrected |
| Routing filter | v1.1.0 | No change |
| Test suite | v3.5 | Partial run — P4, M3, W1, A3 only |
| llama-server | Qwen3.6-27B-Q4_K_M | 64k · KV q8_0 · budget 3072 |

---

## Next Steps

1. **A1 Docker NAT nuance** — add LUCIFER topology note to system prompt KB section:
   SearXNG runs on Docker internal port 8080; Docker NAT means it doesn't conflict
   with llama-server's WSL2 host-level 8080 binding.

2. **M1 combined call** — two `pgrep + ps` calls instead of combined pipeline (Run 6
   regression, not addressed in v0.5.13). Low priority — partial, not failure.

3. **RFC tagger** — check `grep -c "tags$" /tmp/rfc-tag.log` on LUCIFER; if complete,
   `search_rfc()` has a fully tagged index available for T2 challenge runs.

4. **T2 arena** — re-seed ChallengeDB (`python3 scripts/seed_challengedb.py --reset`),
   then run ChallengeGenerator (`--list-pending`) to surface NAS and Samsung TV
   follow-up challenges from T1 discoveries.
