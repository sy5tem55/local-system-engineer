# Session Handover — 2026-06-13 (P27 Cowork)

## State at end of session

### Deployed Versions

| Component | Version | Status |
|---|---|---|
| Tool | **Cogitator v1.7.13** | READY FOR DEPLOY — paste into OWUI Admin → Tools → LSE Cogitator → Save |
| System Prompt | v0.5.15 | ✅ deployed |
| Routing Filter | v1.2.0 | ✅ deployed |
| llama.cpp | b9577 | ✅ deployed |
| Launcher GUI | v1.5 | ✅ deployed |

### Deploy Checklist for v1.7.13

1. Open `tools/cogitator-v1.7.13.py` (4508 lines)
2. Paste into OWUI Admin → Tools → LSE Cogitator → Save
3. OWUI black-formats on save — verify with black-norm sha256:
   ```bash
   python3 -m black --quiet - < tools/cogitator-v1.7.13.py | sha256sum
   # Expected: 866b0b4d656a20753bd2bf18d159389da44f00366678f80804495349c03dc67c
   ```
4. Confirm version in OWUI tool description shows "1.7.13"

### What was done this session (P27)

- **v1.7.12 restored** from OWUI copy-paste backup (`backupfromOWUI1.7.12.py`) + cache-only-on-success fix applied (failed SSH fingerprints were cached, blocking retry with correct key)
- **v1.7.13 shipped** — SSH KB-FIRST RULE in execute_command docstring: `search_kb('{hostname} SSH access')` with NO `topic_filter` before any `ssh` command; never bare ssh without `-i` key
- **KB source fix** — `fix_rutx50_kb_source.py` corrected fabricated `source_url` on "Teltonika RUTX50 SSH Access Guide" to accurate attribution. Verified applied to doc `f3d292b0…`
- **Capital MDs synced** — CURRENT-STATE, README, VALVES, LSE-ARCHITECTURE, ROADMAP all updated to v1.7.13 / current facts. Committed `8cb7d14`

### Commits this session

```
0ce2cd4  fix_rutx50_kb_source.py: correct field name source_url, fix applied
78c16fb  cogitator v1.7.12: restore from OWUI backup + cache-only-on-success fix
[P27]    cogitator v1.7.13: SSH KB-FIRST RULE
8cb7d14  P27: sync capital MDs to Cogitator v1.7.13
```

---

## Pending tasks (carry forward)

### Immediate
- [ ] **Deploy v1.7.13 to OWUI** — file ready; paste + verify black-norm sha256 `866b0b4d…`
- [ ] **Session debrief KB entry** — Write P26/P27 learnings to `/opt/local-se/kb/session-learnings.md` (draft in this handover; confirm + append via `>>`)
- [ ] **System prompt update note** — user confirmed v0.5.15 already references `tool v1.7.13 · LSE Routing filter version: 1.2.0`

### From ROADMAP (open)
- [ ] **node-t3-005 Duplicate Model Cleanup** — do via interactive LSE session, use episode as verifier
- [ ] **ES index-existence probe** in stack health check — `curl -s localhost:9200/lse-kb,lse-errors,lse-rfc-kb,lse-search-cache/_count`
- [ ] **Launcher docker container visibility** — show all running containers + CPU/MEM in GUI ≥v1.078
- [ ] **NoMtp flag commit** — `lse-stack-launch-1.078.ps1` + `lse-profiles.xml` changes not yet committed; re-sign from WSL
- [ ] **16-tool-call limit** — root cause unresolved: check Admin → Models → Qwen3 preset → Advanced → Max Tool Calls
- [ ] **searxng-error-exporter** — Grafana Panel 24 "Failing engines" still shows 0
- [ ] **NVD custom SearXNG engine** — cvedetails blocked, NVD REST API engine pending

---

## Session-learnings KB entry to write (P26/P27)

Append to `/opt/local-se/kb/session-learnings.md` via `>>`:

```
## Session 2026-06-13 — P26/P27: Write tool truncates NTFS; OWUI backup; ES source_url; git locks

### What worked
- OWUI backup recovery: copy-paste tool code from OWUI editor → .txt → rename .py.
  Pure CRLF on Windows clipboard — not a problem. Python normalizes CRLF→LF on write.
  AST.parse() accepts both. Black-norm sha256 is the deploy identity check. Use stdin
  pipe for large files: `python3 -m black --quiet - < file.py | sha256sum`
  (--code flag hits OSError: Argument list too long on files > ~100KB)
- Finding correct ES field names: print sorted(src.keys()) from a live hit before writing
  any update logic — reveals actual schema without guessing

### What failed and why
- **Attempted:** Reconstructing cogitator from P26 chat transcript after Write tool truncation
  **Failed because:** User paste was the last message before context summarization — compressed
  into summary prose, not preserved in JSONL. Largest message in JSONL was 43KB; 213KB paste lost.
  **Fix:** User provided OWUI copy-paste backup (backupfromOWUI1.7.12.py). OWUI stores the
  deployed (black-formatted) version — this is the authoritative source for deployed code.

- **Attempted:** fix_rutx50_kb_source.py first version used src.get("source") with URL-content match
  **Failed because:** KB documents store URL in source_url, not source. Script returned
  "(none)" for all docs — silent wrong-field read.
  **Fix:** src.get("source_url"); use title match for targeting, not URL-content match.

- **Attempted:** Git commit from Cowork sandbox after capital MD updates
  **Failed because:** .git/index.lock and .git/HEAD.lock persisted from a prior crashed session.
  Sandbox (Linux) cannot delete NTFS lock files — rm returns "Operation not permitted".
  **Fix:** From PowerShell on LUCIFER: `Get-ChildItem ".git\*.lock" | Remove-Item -Force`
  Run before every commit attempt when working across Cowork + Windows git.

### Key facts
- Write tool on large NTFS .py files: silently truncates. P26 incident: cogitator-v1.7.12.py
  (4483 lines) truncated by Write tool during reconstruction. Only detectable by post-write
  line count: `python3 -c "print(sum(1 for _ in open(path)))"`. Run after every Write on .py > 100 lines.
- Black-norm sha256 for large files: stdin pipe only.
  `python3 -m black --quiet - < file.py | sha256sum` (works)
  `python3 -m black --code "$(cat large_file.py)"` → OSError: Argument list too long
- OWUI stores black-formatted deployed code; copy-paste from OWUI editor = authoritative backup.
  CRLF→LF normalization is automatic. AST-valid either way.
- ES lse-kb schema fields: content, created_at, doc_id, embedding, quality_score,
  refinement_count, source_path, source_url, tags, title, topic, updated_at, version.
  source_tier and verified_against are dynamic (added via update scripts / index_to_kb).
- SSH behavioral bugs fixed in v1.7.13 docstring:
  (1) bare ssh before KB lookup — model tried ssh root@rutx50 with no key → 30s timeout;
  (2) wrong topic_filter — searched KB with topic_filter=pfsense for RUTX50 SSH query.
  Rule: search_kb('{hostname} SSH access') with NO topic_filter before ANY ssh command.
```

WSL2 append command:
```bash
cat >> /opt/local-se/kb/session-learnings.md << 'DEBRIEF_EOF'
<paste entry above>
DEBRIEF_EOF
tail -30 /opt/local-se/kb/session-learnings.md  # verify
```

---

## Model Parameters — Anti-hallucination Assessment

**Current settings (live from OWUI DB + llama-server flags):**

| Parameter | Value | Assessment |
|---|---|---|
| temperature | 0.6 | ✅ Qwen3 official recommendation — correct |
| top_k | 20 | ✅ Conservative (default 40) — good for factual/tool-call tasks |
| top_p | 0.95 | ✅ Standard — fine combined with top_k=20 |
| min_p | 0 | ✅ Qwen3 model card spec — correct, do not change |
| reasoning-budget | 3072 | ✅ **Biggest anti-hallucination lever** — thinking before answering beats any sampling param |
| ctx-size | 80,000 | ✅ |
| function_calling | native | ✅ Correct for tool-calling |

**Verdict: params are correct — they match Qwen3's official recommendations exactly.**

The primary anti-hallucination levers for LSE are not sampling params but:
1. **reasoning-budget 3072** — model thinks before answering (chain-of-thought in hidden tokens)
2. **Docstring-enforced rules** — KB-FIRST, source-claim verification, CONFIG GROUND-TRUTH, SSH KB-FIRST (v1.7.13)
3. **Code-enforced gates** — budget_gate(), verify_source_claims(), _device_cache

No parameter changes recommended.

---

## KV Cache Tradeoff: Q8/Q8 vs Q4 options

**Current:** `cache_type_k=q8_0, cache_type_v=q8_0` at `ctx-size=80000`

### Memory math (Qwen3-27B architecture)

Qwen3-27B: 64 layers, 8 KV heads (GQA), head_dim=128

| Config | Bytes/token | KV at 80k ctx | KV at 120k | KV at 160k |
|---|---|---|---|---|
| K=Q8 V=Q8 (current) | ~144 KB | ~11 GB | ~16.9 GB | OOM |
| K=Q8 V=Q4 | ~108 KB | ~8.4 GB | ~12.6 GB | OOM |
| K=Q4 V=Q4 | ~72 KB | ~5.6 GB | ~8.4 GB | ~11.2 GB |

RTX 4090 has 24 GB. Q4_K_M weights ≈ 15.2 GB → ~8.8 GB available for KV.

**Current Q8/Q8 at 80k fits within 8.8 GB (barely).** Longer sessions risk OOM.

### Quality tradeoff

- **V cache Q8→Q4**: V participates in value aggregation after softmax — less sensitive to quantization noise than K. Research (KVQuant, KIVI papers) shows < 0.5 perplexity increase. **Practically invisible on sysadmin/tool-call output.**
- **K cache Q8→Q4**: K participates in attention score computation (query·key^T). Quantization noise affects which tokens are attended to. ~1–2% perplexity increase — noticeable in creative writing, acceptable for sysadmin reasoning.
- **K cache Q8→Q2**: Significant quality degradation. Not recommended.

### Recommendations

**Drop V first (lowest risk):**
```bash
# In start-llama-server.sh — change one flag:
--cache-type-v q4_0   # was q8_0
# Saves ~2.6 GB KV at 80k; extends comfortable range to ~120k
```

**Drop both for very long sessions:**
```bash
--cache-type-k q4_0 --cache-type-v q4_0
# KV at 80k: ~5.6 GB, at 160k: ~11.2 GB — still fits 4090
# Quality acceptable for LSE tool-calling and sysadmin reasoning
```

**Decision rule:**
- Sessions under 80k tokens and no OOM → keep Q8/Q8 (current, max quality)
- Arena episodes or long debug sessions that hit compact_context → try K=Q8 V=Q4
- Only need 120k+ context regularly → K=Q4 V=Q4 justified

**For LSE specifically:** The model calls tools (structured JSON), reasons about infrastructure, and follows docstring rules. It is NOT doing literary generation where token-level quality matters at the margin. K=Q4/V=Q4 is safe for the use case if you need the context window.

---

## Infrastructure state at end of P27

- **llama-server LUCIFER**: Qwen3.6-27B-Q4_K_M, port 8080, ctx 80k, K=Q8 V=Q8, reasoning-budget 3072
- **node3090**: llama-server :8080, Qwen3.6-27B, 96k ctx (agent_profile in _NODE_REGISTRY)
- **Elasticsearch**: running in Docker, lse-kb (19 docs), lse-errors, lse-rfc-kb all live
- **RUTX50 KB entry**: `f3d292b0…` — source_url corrected to ground_truth (P27)
- **Git repo**: clean on master, last commit 8cb7d14
