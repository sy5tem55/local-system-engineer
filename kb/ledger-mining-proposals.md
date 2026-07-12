# Ledger Mining — Skill Learning Proposals (Prompt 3.3)

Source: `/opt/local-se/tasks.db` (`task_blocks`, 81 rows), cross-referenced against the `lse-skills` index. Nothing below has been written to skills or KB — everything is a proposal for review.

## Methodology note (read first)

The schema doesn't carry what the prompt assumed. `steps_json` (structured, `packaged_prompt` per step) exists on only 17 of 81 tasks, and every step's `status` is either `done` or `pending` — there's no `failed` state, and no case of the same step number holding two different `packaged_prompt` values as a revise-then-succeed pair. (One task, `a6568fe4`, has duplicate step numbers, but inspection showed it's the planner re-numbering after a scope change, not a revision of the same step.)

So "fail → revise → succeed" and "revise cycles" had to be reconstructed from the free-text `done_steps`/`findings` narrative fields instead of a structured diff. That's weaker evidence than the prompt implies exists — flagging this rather than forcing a fit. Below, each item cites its source task_id so you can pull the raw record and judge for yourself.

## 1. Fail → succeed patterns (skill-candidate / planner-contract notes)

**Docker port reservation not pre-checked (task `a6568fe4`, step 5).**
Couchbase container failed to start on port 18096 — Docker had it reserved — before succeeding on 28096. Planner-contract candidate: packaged prompts that hardcode a container port should include a pre-check (`ss -tlnp` or `docker ps --format` for the target port) rather than discovering the conflict at container-start time.

**DNSSEC + custom Unbound options crash the resolver (task `2ae2f45e`, done, checkpoints=15).**
Findings state plainly: "Custom options (query-log, verbosity) crash Unbound when DNSSEC enabled on pfSense 26.03.1 Plus — DO NOT combine." This reads as a crash-and-recover within the task. Proposed KB fact (topic: `pfsense-unbound`): don't combine `custom_options` edits with DNSSEC-enable in the same change; sequence them with a health check between.

**Unverified API-path assumption (task `episteme-fix`, done).**
Explicit correction in the ledger: "checkpoint's claim about /api/... paths was wrong — legacy paths (/search, /graph/{id}, etc.) are the correct ones in Episteme 0.3.9." Planner-contract candidate: for any REST integration, verify the actual path via a live `curl`/OpenAPI check before packaging a prompt that assumes a `/api/` convention.

**llama.cpp reasoning-budget sentinel collision (task `node-t3-002`, open).**
"CORRECTED CANONICAL: --reasoning-budget changed from 16000 to -1" — root cause was `-1` ("unlimited") colliding with the "not provided" sentinel in `server-common.cpp`, causing premature "Reasoning Cancelled." Good KB fact for the llama.cpp/Qwen3.6 flag set; also worth checking whether this correction ever reached the `rebuild-llama-cpp-on-node3090` skill's canonical launch flags.

**Camofox browser upgrade fixed two live bugs (task `d45a919e`, done).**
v135.0.1 → v150.0.2 + PR #5651 fixed a `[object Promise]` display bug and a viewport CDP protocol error. No existing skill covers Camofox repair — see new-skill-candidate list below.

## 2. Task classes with repeated difficulty (proxy for ">2 revise cycles")

No single task_id shows >2 structured revisions, so I used two proxies: (a) the same underlying goal re-attempted across separate task_ids, and (b) `checkpoints` count as a rough resume/iteration signal.

**`cs` CLI v1.0.33 license bypass — attempted 3 times, still unresolved.**
Task_ids `70be4402` (checkpoints=8), `ac817c89` (checkpoints=1), `d2725cd0` (checkpoints=1), all status `open`. Across all three: license-check flow fully mapped (GraalVM native-image, `codescene.license.online` Clojure namespace, JWT key lookup), an MCP-side bypass exists in `cli.rs` but the CLI still exits 401/returns empty stdout. Proposed KB fact (topic: `codescene-cli-patch`): document the mapped validation flow and the current blocker, and recommend against further blind reverse-engineering attempts — either pursue the official trial-token path or treat as a known dead end pending a different approach.

**Episteme MCP malfunction — attempted 3 times across different symptoms.**
`a6d0a534` (checkpoints=4, schema-init bug), `episteme-fix` (checkpoints=3, API path mismatch), `episteme-fixes-20260708` (checkpoints=4, `/search` hang on embedding model resolution). Proposed KB fact (topic: `episteme-mcp`): consolidate the three known-issue classes into one reference so the next Episteme problem starts from "which of these three" instead of re-diagnosing architecture from scratch.

**Single highest-friction task: `a6568fe4` (CodeSmriti/Couchbase init), checkpoints=20, still open.**
Highest checkpoint count in the whole ledger. Couchbase container reaches "healthy" but cluster services never fully initialize — `setupServices` endpoint fails, SDK auth fails, user seeding and ingestion both deferred. Worth a standalone KB fact under `codesmriti` documenting that "container healthy" is not sufficient evidence the stack is usable.

## 3. skill_outcome backfill proposals (ground-truth evidence found, not yet reported)

These are ready to run via `skill_outcome(...)` — proposing, not executing:

1. **`sre/start-full-stack-services-on-node3090`** — currently `uses=20, ok=4, fail=0` (16 uses with no recorded outcome). Task `7e99b33b` ("Full startup sequence for node3090", done) verifies all 7 services with concrete ground truth (llama-server PID + `/health` OK on :8080, Goethe MCP PID + 35 tools on :9700, Camoufox healthy, Firecrawl 6 containers up). Propose: `success=True, source_tier=ground_truth, evidence="task 7e99b33b: llama-server PID 5462 health OK :8080; Goethe MCP PID 7385 port 9700 35 tools; Camoufox healthy; Firecrawl 6 containers up"`.

2. **`linux-sysadmin/rebuild-llama-cpp-on-node3090-with-cuda-13-3-gcc-14-rtx-3090`** — currently `ok=0/fail=0` despite 7-8 recorded uses. Task `a7f3c921` (done) diagnosed a CUDA 12/13 runtime mismatch, rebuilt with the documented flags, and verified inference stability for 10+ minutes. Propose: `success=True, source_tier=ground_truth, evidence="task a7f3c921: rebuilt with CUDAToolkit_ROOT=/usr/local/cuda-13.3, arch=86; verified inference + stability 10+ min post-deploy"`.

3. **`Local System Engineer/launch-codesmriti-stack-on-demand-backend-on-node3090-mcp-ga`** — task `a6568fe4` (open) shows a genuine failure not currently in the skill's failure-mode list: Couchbase container reports healthy but `setupServices` REST call fails and SDK auth fails, blocking user seeding and ingestion. Propose: `success=False, source_tier=ground_truth, evidence="task a6568fe4: container healthy but setupServices endpoint failed, SDK auth fails, buckets exist but cluster services not initialized — user seeding and ingestion both deferred"`. Recommend also adding this as a named failure mode on the skill itself.

## 4. New skill-candidates (no existing match found via skill_search)

- **Fix CodeSmriti FTS/vector search returning empty results** (task `codesmriti-fts-fix`, done, checkpoints=4). Root causes: FTS index mapped to `code_kosha.*` nested paths but documents store fields at root level; API embedding model defaulted to `localhost:11434` instead of `host.docker.internal:11434` inside the container. Concrete, verified, reusable procedure — worth recording as a skill in its own right, distinct from the existing launch/teardown skill.
- **Repair Camofox browser (display + viewport bugs) via version upgrade** (task `d45a919e`, done, checkpoints=2). v135.0.1 → v150.0.2-alpha.26 + PR #5651, verified end-to-end (health, tab creation, snapshot).

## Suggested next step

If this looks right, tell me which of the skill_outcome calls in section 3 to actually run, and whether to record the section 4 candidates as new skills and the section 1/2 items as KB facts. I'd rather you sign off per-item than have me batch-write on your behalf.
