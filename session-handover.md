# Session Handover — 2026-06-13 (P27 Cowork)

## State at end of session

### Deployed Versions

| Component | Version | Status |
|---|---|---|
| Tool | **Cogitator v1.7.14** | READY FOR DEPLOY — paste into OWUI Admin → Tools → LSE Cogitator → Save |
| System Prompt | v0.5.15 | ✅ deployed |
| Routing Filter | v1.2.0 | ✅ deployed |
| llama.cpp | b9577 | ✅ deployed |
| Launcher GUI | v1.5 | ✅ deployed |

### Deploy Checklist for v1.7.14

1. Open `tools/cogitator-v1.7.14.py` (4515 lines)
2. Paste into OWUI Admin → Tools → LSE Cogitator → Save
3. OWUI black-formats on save — verify with black-norm sha256:
   ```bash
   python3 -m black --quiet - < tools/cogitator-v1.7.14.py | sha256sum
   # Expected: 435c319aae260a8616b4eeb14751fa747b2ad919d785db33685e461e5009d2c8
   ```
4. Confirm version in OWUI tool description shows "1.7.14"
5. Kill socat on node3090: `ssh lse-admin@node3090.home.arpa "sudo kill 8485"`
6. Verify: `ss -tlnp | grep -E '8642|8643'` → port 8642 up, 8643 gone

### What was done this session (P27)

- **v1.7.12 restored** from OWUI copy-paste backup (`backupfromOWUI1.7.12.py`) + cache-only-on-success fix applied (failed SSH fingerprints were cached, blocking retry with correct key)
- **v1.7.13 shipped** — SSH KB-FIRST RULE in execute_command docstring: `search_kb('{hostname} SSH access')` with NO `topic_filter` before any `ssh` command; never bare ssh without `-i` key
- **KB source fix** — `fix_rutx50_kb_source.py` corrected fabricated `source_url` on "Teltonika RUTX50 SSH Access Guide" to accurate attribution. Verified applied to doc `f3d292b0…`
- **Capital MDs synced** — CURRENT-STATE, README, VALVES, LSE-ARCHITECTURE, ROADMAP all updated to v1.7.13 / current facts. Committed `8cb7d14`
- **Hermes connectivity verified** — gateway confirmed `0.0.0.0:8642` (not loopback-only). socat PID 8485 redundant. HERMES_API_URL default :8643→:8642 fixed in source (v1.7.14) so future deploys don't need valve UI override.
- **v1.7.14 built** — HERMES_API_URL valve default :8643→:8642 + docstring updates. ast OK, black-norm `435c319a…`, 4515 lines (+7). Pending: OWUI deploy + kill socat PID 8485.
- **Hermes bidirectional gap documented** — ROADMAP v1.7.0-b: LSE pull-only, no Hermes push path yet. Three design options recorded.

### Commits this session

```
0ce2cd4  fix_rutx50_kb_source.py: correct field name source_url, fix applied
78c16fb  cogitator v1.7.12: restore from OWUI backup + cache-only-on-success fix
[P27]    cogitator v1.7.13: SSH KB-FIRST RULE
8cb7d14  P27: sync capital MDs to Cogitator v1.7.13
0211ac1  P27: Hermes bidirectional comms gap documented (ROADMAP v1.7.0-b)
[P27]    cogitator v1.7.14: HERMES direct connect :8643→:8642
[P27]    P27: capital MDs + registries updated to v1.7.14
fe18996  P27: session-handover updated (superseded — see below)
```

---

## Pending tasks (carry forward)

### Immediate
- [x] **Deploy v1.7.14 to OWUI** ✅ (P27) — black-norm sha verified `435c319a…`
- [x] **Kill socat** ✅ (P27) — hermes-socat disabled (`systemctl is-enabled hermes-socat` → disabled), port 8643 no longer listening
- [x] **Deploy v1.7.13 to OWUI** ✅ (P27) — superseded by v1.7.14
- [ ] **Session debrief KB entry** — Write P26/P27 learnings to `/opt/local-se/kb/session-learnings.md` (draft below; confirm + append via `>>`)
- [ ] **System prompt update note** — user confirmed v0.5.15 already references `tool v1.7.13 · LSE Routing filter version: 1.2.0`

### From ROADMAP (open)
- [ ] **node-t3-005 Duplicate Model Cleanup** — do via interactive LSE session, use episode as verifier
- [ ] **ES index-existence probe** in stack health check — `curl -s localhost:9200/lse-kb,lse-errors,lse-rfc-kb,lse-search-cache/_count`
- [ ] **Launcher docker container visibility** — show all running containers + CPU/MEM in GUI >=v1.078
- [ ] **NoMtp flag commit** — `lse-stack-launch-1.078.ps1` + `lse-profiles.xml` changes not yet committed; re-sign from WSL
- [ ] **16-tool-call limit** — root cause unresolved: check Admin → Models → Qwen3 preset → Advanced → Max Tool Calls
- [ ] **searxng-error-exporter** — Grafana Panel 24 "Failing engines" still shows 0
- [ ] **NVD custom SearXNG engine** — cvedetails blocked, NVD REST API engine pending
- [ ] **Hermes → LSE push channel (v1.7.0-b)** — currently one-directional: LSE can call Hermes but Hermes cannot initiate. Three design options in ROADMAP: OWUI API inject / hermes-gateway webhook / polling `check_hermes_inbox()`. Needs design decision before implementation.

---

## Session-learnings KB entry to write (P26/P27)

Run on LUCIFER WSL2 to append to `/opt/local-se/kb/session-learnings.md`:

```bash
cat >> /opt/local-se/kb/session-learnings.md << 'DEBRIEF_EOF'

## Session 2026-06-13 - P26/P27: USE BASH for .py on NTFS; OWUI backup; ES source_url; git locks; K cache

### What worked
- OWUI backup recovery: copy-paste tool code from OWUI editor to txt then rename .py.
  Pure CRLF on Windows clipboard -- not a problem. Python normalizes CRLF to LF on write.
  Black-norm sha256 is the deploy identity: python3 -m black --quiet - < file.py | sha256sum
  (--code flag hits OSError: Argument list too long on files > ~100KB)
- Finding correct ES field names: print sorted(src.keys()) from a live hit before writing
  any update logic

### What failed and why
- **Attempted:** Reconstructing cogitator from P26 transcript after truncation
  **Failed because:** User paste was last message before context summarization, compressed
  into summary prose, not preserved in JSONL. Largest JSONL message was 43KB; 213KB paste lost.
  **Fix:** OWUI copy-paste backup is the authoritative source for deployed code.

- **Attempted:** fix_rutx50_kb_source.py used src.get("source") with URL-content match
  **Failed because:** KB documents store URL in source_url, not source. Returned "(none)"
  for all docs -- silent wrong-field read.
  **Fix:** src.get("source_url"); target by title match, not URL-content match.

- **Attempted:** Git commit from Cowork sandbox
  **Failed because:** .git/index.lock and HEAD.lock persisted from crashed session.
  Sandbox cannot delete NTFS lock files -- rm returns "Operation not permitted".
  **Fix:** PowerShell: Get-ChildItem ".git\*.lock" | Remove-Item -Force before every commit.

- **Attempted:** Bash splice on session-handover.md via sandbox mount
  **Failed because:** Sandbox /sessions/.../mnt/ showed stale truncated view (109 lines)
  of a 204-line committed file. Bash splice wrote truncated version back, losing 95 lines.
  **Fix:** For .md files use Read/Write/Edit file tools (not bash -- bash mount can be stale).
  For .py files: ALWAYS use bash (Write/Edit silently truncate .py on NTFS). No exceptions.

### Key facts
- LARGE .py FILES ON NTFS: USE BASH. NOT Write/Edit tools. ALWAYS.
  Splice: python3 -c "with open(p) as f: s=f.read(); s=s.replace(old,new,1); open(p,'w').write(s)"
  Verify: python3 -c "print(sum(1 for _ in open(p)))" + python3 -c "import ast; ast.parse(open(p).read())"
- For .md files: use Read/Write/Edit file tools. Bash mount can show stale/truncated NTFS state.
- ES lse-kb field is source_url (not source). Full schema: content, created_at, doc_id,
  embedding, quality_score, refinement_count, source_path, source_url, tags, title, topic,
  updated_at, version. source_tier and verified_against are dynamic fields.
- KV cache: K must stay Q8_0 -- lowering K breaks this model. V is the only safe knob:
  --cache-type-v q4_0 saves ~2.6 GB at 80k context, extends comfortable range to ~120k.
- SSH v1.7.13: search_kb('{hostname} SSH access') with NO topic_filter before any ssh command.
DEBRIEF_EOF
tail -40 /opt/local-se/kb/session-learnings.md
```

---

## Model Parameters — Anti-hallucination Assessment

**Current settings (live from OWUI DB + llama-server flags):**

| Parameter | Value | Assessment |
|---|---|---|
| temperature | 0.6 | Qwen3 official recommendation -- correct |
| top_k | 20 | Conservative (default 40) -- good for factual/tool-call tasks |
| top_p | 0.95 | Standard -- fine combined with top_k=20 |
| min_p | 0 | Qwen3 model card spec -- correct, do not change |
| reasoning-budget | 3072 | Biggest anti-hallucination lever -- thinking beats sampling params |
| ctx-size | 80,000 | OK |
| function_calling | native | Correct for tool-calling |

**Verdict: params are correct -- match Qwen3 official recommendations exactly.**

Primary anti-hallucination levers (not sampling params):
1. reasoning-budget 3072 -- chain-of-thought in hidden tokens before answering
2. Docstring-enforced rules -- KB-FIRST, source-claim verification, CONFIG GROUND-TRUTH, SSH KB-FIRST (v1.7.13)
3. Code-enforced gates -- budget_gate(), verify_source_claims(), _device_cache

No parameter changes recommended.

---

## KV Cache: Only V is a lever

**Current:** cache_type_k=q8_0, cache_type_v=q8_0 at ctx-size=80000

**K cache: DO NOT TOUCH. K below Q8_0 breaks the model on this architecture.**

V cache is safe to lower. V participates in value aggregation after softmax (less sensitive
than K which drives attention scores). Only valid change is V to Q4_0.

### Memory (Qwen3-27B: 64 layers, 8 KV heads GQA, head_dim=128)

| Config | KV at 80k | KV at 120k |
|---|---|---|
| K=Q8 V=Q8 (current) | ~11 GB | ~16.9 GB |
| K=Q8 V=Q4 | ~8.4 GB | ~12.6 GB |

RTX 4090 24 GB total. Q4_K_M weights ~15.2 GB -- ~8.8 GB available for KV.

### The only valid change

```bash
# /opt/local-se/scripts/start-llama-server.sh:
--cache-type-v q4_0   # was q8_0 -- K stays q8_0 always
# Saves ~2.6 GB at 80k; extends comfortable range to ~120k
```

Decision: no OOM under 80k -- keep Q8/Q8. Long sessions hitting compact_context -- K=Q8 V=Q4.
K is not a lever. V is the only knob.

---

## Infrastructure state at end of P27

- **llama-server LUCIFER**: Qwen3.6-27B-Q4_K_M, port 8080, ctx 80k, K=Q8 V=Q8, reasoning-budget 3072
- **node3090**: llama-server :8080, Qwen3.6-27B, 96k ctx (agent_profile in _NODE_REGISTRY); Hermes gateway :8642 (0.0.0.0); socat PID 8485 still running but redundant — kill before next Hermes test
- **Elasticsearch**: running in Docker, lse-kb (19 docs), lse-errors, lse-rfc-kb all live
- **RUTX50 KB entry**: f3d292b0 -- source_url corrected to ground_truth (P27)
- **Git repo**: clean on master — `934e391` (cogitator v1.7.14) + `566c6f8` (capital MDs)
