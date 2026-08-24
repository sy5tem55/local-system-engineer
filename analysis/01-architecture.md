# 01 — Architecture Map

All citations resolve against corpus **[A]** at commit `8bfc8d6`. Environment claims are
marked `[verified: …]` or `[operator-provided, unverified]`.

---

## 1. The shape of the system in one paragraph

Goethe is a **single Python class** (`Tools`, 2,396 lines, assembled from five mixins)
whose public methods are auto-discovered and re-published as MCP tools by an 881-line
gateway. Every method is an operation on the operator's homelab — run a command, read a
file, SSH somewhere, query the firewall, wake a GPU node — and every method is wrapped in
guards that can refuse. Around that core sit three things that make it more than a tool
belt: a **trust-scored knowledge base** that demotes itself when its advice fails, a
**planner ledger** in SQLite that survives context resets, and **TRAUM**, a 13,260-line
nightly subsystem that mines the agent's own episode logs into proposed KB changes which
a human then adjudicates one at a time. The protocol that governs the agent's behaviour
is written in the docstrings; some of it is also written in the guards. The distance
between those two sets is the subject of §7 — and of the funding case.

---

## 2. Control flow: MCP client → side effect

```
  llama-server :8080  (Qwen3-class 27B, local)
  llama-ui / LibreChat :3080 / Goethe Console /ui
            │  MCP streamable-HTTP, token-gated
            ▼
  ┌─────────────────────────────────────────────────────────────┐
  │ goethe_mcp.py  :9700                                        │
  │  _TokenGuard ────────────── build_http_app():680            │
  │  register(mcp, inst) ────── :603   auto-discovers public    │
  │                                    methods of `Tools`       │
  │  _ToolSchemaFixer ───────── :326   schema normalisation     │
  │  description[:3072] ─────── :182   _TOOL_DESC_MAX           │
  │  _redact_args / _redact_text :492/:476                      │
  │  _journal() ─────────────── :528   episode JSONL per call   │
  └───────────────┬─────────────────────────────────────────────┘
                  ▼
  ┌─────────────────────────────────────────────────────────────┐
  │ class Tools(KBMixin, NetSecMixin, NodeLifecycleMixin,        │
  │             PlannerMixin, WebMixin)      goethe.py:55        │
  │   Valves(BaseModel) ────────────────────  goethe.py:57–439   │
  │   _validate_command_safety() ───────────  goethe.py:815      │
  │   _snapshot_before_write() ─────────────  goethe.py:1314     │
  └───────────────┬─────────────────────────────────────────────┘
                  ▼ side effects
   shell · SSH (lse-admin key) · Elasticsearch :9200 · Ollama :11434
   SearxNG :8088 · pfSense REST/GraphQL · Vaultwarden :3003
   WoL / poweroff on GPU nodes · llama-server spawn (Gemma planner)
```

`register()` at `goethe_mcp.py:603` is the whole publication mechanism: **adding a public
method to `Tools` ships a new MCP tool.** That is the system's greatest ergonomic
strength and, per `03`, its widest unreviewed surface.

The auto-discovery is why the description cap matters. `goethe_mcp.py:177–182`:

```python
# 3072 is measured, not guessed: it is the smallest value at which no tool's
_TOOL_DESC_MAX = int(os.environ.get("GOETHE_MCP_TOOL_DESC_MAX", "3072"))
```

**Answering §6's open question — which protocol text does the cap actually cut?**
Exactly one tool's docstring exceeds 3072 chars: `planner()` at `goethe_planner.py:1506`,
3,282 chars, losing 210. The lost tail is:

> `O-KB: planner() runs its own search_kb on the task and appends top matches to whatever
> context you pass. You do not need to paste KB content you already found — but pasting
> live probe output is still essential.`

No `MUST`/`MANDATORY`/`NEVER`/`GATE`/`RULE`/`REQUIRED` keyword is lost. **No contract text
is truncated** — and that is guaranteed structurally, not by luck, by
`tests/test_docstring_mcp_truncation.py`, which reads the cap out of `goethe_mcp.py`
rather than hardcoding it (`tests/test_docstring_mcp_truncation.py:26–33`) precisely so
the gate cannot drift from the gateway. The test's own header records why it exists:

> *"Regression test for the v0.4.7 incident: planner's MANDATORY TRIGGER block was
> silently dropped by goethe_mcp.py's description[:1024] truncation, causing the model to
> violate a rule it never saw."* — `tests/test_docstring_mcp_truncation.py:3–5`

This is the single best illustration of the project's engineering culture, and it recurs
throughout §7.

---

## 3. Flow (a) — the planner ledger loop

```
planner(task)                          goethe_planner.py:1506
  ├─ _augment_context_with_kb() ────── :1391  (KB is injected server-side)
  ├─ _call_planner_backend() ───────── :396
  │    ├─ _call_node_planner()  ────── :244   node3090 llama-server :8080
  │    │                                       → Ollama :11434 fallback
  │    ├─ _try_forced_planner_endpoint() :158 PLANNER_FORCE_URL valve
  │    ├─ _spawn_gemma_server() ────── :802   VRAM-gated local GGUF spawn
  │    ├─ _call_chatgpt_planner() ──── :544   ← cloud
  │    └─ _call_claude_planner() ───── :590   ← cloud
  ├─ _parse_planner_envelope() ─────── :1204  strips <think>…</think>
  ├─ _normalize_plan_steps() ───────── :1303  atomised steps, depends_on edges
  └─ writes tasks.db  ──────────────── _tasks_db():861

plan_step_done(task_id, step, evidence)  :1057
  ├─ evidence gate
  ├─ strike the step in the ledger
  └─ returns _plan_step_prompt() ───── :1675  ← the NEXT step, packaged as a
                                               fresh-context prompt

task_checkpoint() :883  ──► tasks.db ──►  task_resume() :984
```

The design decision worth naming to an investor is at the bottom: **there is no
websocket, no agent-to-agent protocol, no shared memory.** The planner and the executing
agent communicate exclusively through a SQLite ledger, and each step is re-packaged as a
self-contained prompt. CURRENT-STATE.md:90 records the rationale verbatim: *"No websocket
by design — SQLite ledger is the planner↔agent channel."* That is what makes a context
reset a non-event: the ledger is the process, the context is scratch.

**Sovereignty caveat — material to moat #4.** `_read_codex_oauth_token()` at
`goethe_planner.py:476` and `_read_claude_oauth_token()` at `:504` are real, wired
backends. The core loop runs local, but the planner cascade *can* route to a cloud model.
The claim "no cloud LLM in the core loop; planner backends optional" is accurate and
should be stated exactly that carefully — `02` scores it on that basis.

---

## 4. Flow (b) — KB search → index → demotion → quarantine → recovery

```
search_kb(query)                         goethe_kb.py:166
  ├─ _embed() :112   Ollama, 1024-dim, LRU 256, 5000-char input cap
  │                  timeout (3s connect, 8s read) → keyword-only fallback
  ├─ hybrid 0.7·knn + 0.3·BM25, min_score default 4.0
  ├─ volatility TTL → [EXPIRED] tag + rerank demotion
  ├─ [STALE] banner for quarantined docs
  ├─ [TIME] / [DREAM] banners, once per session (_consume_time_banner :462)
  └─ adaptive body budget  _BODY_BUDGET=14000 / _BODY_CAP_TOP_MIN=4000  :77–79

index_to_kb(...)                         goethe_kb.py:435
  ├─ TrustPolicy.ceiling(source_tier) ── :41
  └─ TrustPolicy.apply_origin(...) ───── :502   ← ASYMMETRIC TRUST, in code

record_outcome(doc_id, success, evidence)  :845
  ├─ success ────► streak reset, updated_at bumped (TTL clock resets)  :931–934
  ├─ failure + len(evidence) >= 20 ──► q = max(0.2, q − 0.15)          :935–936
  │                                    q <= 0.2 ► stale=True, QUARANTINE :941–947
  └─ failure + no evidence ──► counted, NOT demoted                    :950–955

kb_verify(doc_id, observed)  :1055     observed < 20 chars → rejected  :1132
mentor_demote(doc_id, q, reason) :1172  human-authorised kill switch
mentor_correct(...) :968                tier-gated raise, clears quarantine
```

### 4.1 The trust model, stated precisely

**Source-tier ceilings** — `goethe_kb.py:33–38`:
```python
TIER_CEILING = {
    "ground_truth": 1.0,
    "primary":      0.8,
    "secondary":    0.6,
    "inferred":     0.4,
}
```

**Asymmetric trust is code-enforced**, not exhorted — `goethe_kb.py:60–68`:
```python
if origin == "web" and tier == "ground_truth":
    tier = "primary"
    ceiling = min(ceiling, cls.TIER_CEILING["primary"])
    warn = (" | ORIGIN DOWNGRADE: origin=web cannot carry "
            "source_tier=ground_truth (asymmetric trust rule) …")
```
and it is wired into the write path at `goethe_kb.py:502`. Origins are
`("web", "human", "local-probe", "dream")` (`:48`), and `"dream"` is stamped only by the
apply path — the agent cannot claim it (`:46–47`, `:459`).

This closes a finding the project itself raised and left open. CURRENT-STATE.md:14 records
that the 2026-07-13 threat model *"found origin=web/human/local-probe tagging
UNIMPLEMENTED in live index_to_kb — laundering protection is a blunt ceiling"*. **It is
implemented now.** Worth saying out loud to a diligence reader who finds the old note.

### 4.2 The asymmetry that gives the KB its character

The demotion path is where this system differs from every RAG stack:

| direction | requires |
|---|---|
| **lower** a doc's quality | ≥20 chars of real tool output (`:935`) — *evidence* |
| **raise** a doc's quality | a tier-gated write via `index_to_kb`/`mentor_correct` — *authority* |
| **quarantine** | automatic at the 0.2 floor, `stale=True` (`:941`) |
| **un-quarantine** | only a tier-gated raise clears it (`:925–927`) |
| **kill outright** | `mentor_demote` — human words only (`:1172`) |

Evidence demotes; only authority promotes. A failing document decays on its own and
cannot climb back without a human or a higher-tier source. **The knowledge base is
designed to forget.**

### 4.3 Where it is thinner than it looks

The evidence gate is a **length check and nothing more** — `goethe_kb.py:935`:
```python
elif len(evidence) >= 20:
```
Twenty characters of any string passes. There is no check that the evidence came from a
tool call, no correlation with the episode journal, no structural validation. The gate
raises the *cost* of laundering a claim from zero to trivial; it does not make it hard.
The same is true at `:1132` (`kb_verify`) and at `dream_apply.py:384`
(`check_evidence_thin(args, min_len=20)`). Carried to `03` as an epistemics P1 — and it
is the most interesting thing on the roadmap, because binding evidence to the episode
journal is both tractable and genuinely novel.

---

## 5. Flow (c) — node wake → query → drift check → shutdown

```
wake_node(node)              goethe_node.py:145
  ├─ ping first (skip WoL if already up)
  ├─ search_kb("<node> wake procedure") before the magic packet
  └─ surfaces KB notes on every return path

query_node_agent(node, …)    :289
check_node_agent_drift(node) :387   ← the ONE drift detector that exists
start_node_agent(node, force):456
stop_node_agent(node)        :598
shutdown_node(node, confirmed=False)  :642
        └─ confirmed=False returns a prompt the model must surface to the user;
           confirmed=True executes.  Two-step gate, in code.
```

`check_node_agent_drift` is worth dwelling on: **the codebase already contains a drift
detector.** It compares a remote node agent against expectation. What it does *not* cover
is the drift class that actually bit this project — prompt-template version vs code
version (§0.6.3 of the ingestion audit). The §6 detector is therefore not a new concept
for this codebase; it is an existing concept applied to the one surface it was never
pointed at. That materially lowers the cost and the risk of the M0 milestone.

`shutdown_node`'s two-step confirmation is a good template for what "code-enforced" means
here: the refusal is a *return value the model must relay*, not an exception. The gate
works by making the unsafe path require an explicit second call.

---

## 6. Flow (d) — the dream cycle (TRAUM)

TRAUM is the project's most novel component and the largest thing in the tree: **8 files,
13,260 LOC, 44% of all `tools/` code**. Four of those files are absent from §1A's
manifest (`traum_controller.py` 1,653; `traum_eval_registry.py` 1,550;
`episode_index.py` 459; `traum_eval.py` 119).

```
  every MCP tool call
        │  goethe_mcp.py:528  _journal()
        ▼
  /opt/local-se/episodes/<day>/*.jsonl        [verified: 37 MB, 701 files]
        │  redacted at write; day-dir cap 500 MB; _SENSITIVE_TOOLS blanket-redacted
        ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │ dream_runner.py (5,135 LOC)   systemd goethe-dream.timer 03:30   │
  │   guards: lockfile · 30-min active-session guard · per-run LLM   │
  │           budget · 45-min wall clock · structural                │
  │           "no-dream-of-dreams" assert                            │
  │                                                                  │
  │   pass 1  dedup                 mechanical                       │
  │   pass 2  stale-contradiction   mechanical                       │
  │   pass 3  error-cluster         over lse-errors                  │
  │   pass 4  patterns              agent_commands.log mining,       │
  │                                 redact_log_text() at parse time  │
  │   pass 5  insights              LLM, verbatim-evidence enforced  │
  │   pass 6  digest                dream_digest.py, ≤30 lines       │
  │                                                                  │
  │   null-result discipline: every pass emits looked/corpus_size/   │
  │   thresholds so "nothing there" ≠ "didn't look"                  │
  │   crash discipline: FAILED banner, crashes.jsonl, record_error   │
  │                     provenance=dream-infra, 3-night escalation   │
  └───────────────┬──────────────────────────────────────────────────┘
                  ▼ proposals-<pass>.jsonl  +  traum-state.db
  ┌──────────────────────────────────────────────────────────────────┐
  │ dream_apply.py (1,629 LOC) — validate, then ASK                  │
  │   validate_proposal_for_apply()  :499  calls eleven checks:      │
  │     check_quarantine            :305   check_noop           :365 │
  │     check_ground_truth          :318   check_evidence_thin  :384 │
  │     check_provenance_format     :325   check_prompt_rule_target :395│
  │     check_quality_raise         :336   check_skill_collision_raise :416│
  │     check_target_cas            :352   check_kb_fact_collision_raise :459│
  │                                        check_procedure_step_count :487│
  │   render_group() :557  →  ask_yes_no() :657  →  input()          │
  │   apply_group(tools, group, dry_run) :780                        │
  └──────────────────────────────────────────────────────────────────┘
                  ▼ only on "y"
        KB mutation via the SAME public Tools methods the agent uses
```

### 6.1 "It proposes; it never applies" — verified, with one asterisk

The human gate is literally a blocking `input()` — `dream_apply.py:657–662`:
```python
def ask_yes_no(prompt: str) -> bool:
    try:
        answer = input(f"{prompt} > ").strip().lower()
    except EOFError:
        answer = ""
    return answer in ("y", "yes")
```
`EOFError → ""` → falsy. **Fail-closed under automation**: pipe nothing to it and every
proposal is rejected. That is the correct default and it is worth showing to a reviewer.

The asterisk: `dream_apply.py:199–200`
```python
def _dream_auto_apply_default() -> str:
    return os.environ.get("GOETHE_DREAM_AUTO_APPLY", "")
```
An env var can whitelist proposal types for automatic application. It is **empty by
default**, and the decision to keep it empty is recorded with evidence (CURRENT-STATE.md:14,
"4.8: `DREAM_AUTO_APPLY` stays empty; nightly cadence retained"). So the precise claim
is: *the agent never applies its own proposals under the shipped configuration, and the
capability to change that is a single environment variable.* Say it that way. A technical
partner will find the variable, and finding it after you have claimed "never" is worse
than being told.

`check_target_cas` (`:352`) deserves a name-check: proposals carry a compare-and-swap
against the document they were derived from, so a proposal generated overnight cannot
apply to a document the operator changed in the morning. That is a real distributed-systems
instinct in a homelab project.

### 6.2 State machine

`traum_state.py:37–52`:
```python
RUN_STATES     = {"QUEUED","RUNNING","SUCCEEDED","DEGRADED","FAILED","BLOCKED","CANCELLED"}
ATTEMPT_STATES = {"QUEUED","RUNNING","SUCCEEDED","NULL","BLOCKED","FAILED","CANCELLED"}
ATTEMPT_TERMINAL_STATES = ATTEMPT_STATES - {"QUEUED","RUNNING"}
CONSUMABLE_OUTCOMES = {"SUCCEEDED","NULL"}
```

§1A's attempt-state list is exactly right. The semantics that matter:

- **`NULL` ≠ `FAILED`.** `NULL` means the pass ran correctly and found nothing.
  `CONSUMABLE_OUTCOMES = {"SUCCEEDED","NULL"}` — a null result is a *completed* attempt.
  Without this distinction "the dream found nothing" and "the dream broke" are the same
  row, and the operator learns to ignore both.
- **`BLOCKED` ≠ `FAILED`.** Blocked is a refused precondition (lock held, session active
  within 30 min, budget spent) — the run was *prevented*, not attempted. It is
  terminal-but-retryable.
- `DEGRADED` exists for runs but not attempts: a run can partially succeed; an attempt
  cannot.

Seven proposal types — `dream_runner.py:1671`:
```python
KNOWN_PROPOSAL_TYPES = {"dedup","reverify","demote","skill-candidate","kb-fact","prompt-rule","diagnosis"}
```

### 6.3 TRAUM's honesty record

Two things a diligence reader will find, and both should be led with rather than buried:

1. **The A/B evaluation of dreaming lost, and the loss was recorded as the result.**
   CURRENT-STATE.md:14: *"4.5/4.6: A/B eval designed pre-registered, then RUN — **verdict
   LOSS (A=53/60, B=51/60), recorded as-is**"*, with root cause analysed as
   methodological (n=1, ~15-min divergence window, unpinned sampling) in
   `eval/eval-report-traum-1.md` §6–7, and a `record_error` filed. A pre-registered
   experiment on the founder's favourite subsystem, run, lost, and published. That is
   rarer than the subsystem.
2. **A live plaintext credential was found by the patterns pass**, in a `--dry-run`, and
   the run was deliberately not persisted. The fix (`redact_log_text()` at parse time)
   shipped before Thread 4 proceeded. Same source.

---

## 7. Enforcement vs. persuasion

This is the table that decides both the moat and the risk. Method: for each named
protocol rule, locate the enforcement. `[CODE]` = a guard function returns a refusal or
mutates the input. `[PROMPT]` = the rule exists only as docstring/system-prompt text.

### 7.1 Code-enforced

| rule | mechanism | citation |
|---|---|---|
| Hard command denylist | `_BLOCKED_COMMANDS` substring + `_BLOCKED_COMMAND_NAMES` token match | `goethe.py:376`, `:404`, `:826–841` |
| Protected credential reads | `_BLOCKED_READ_PATHS = ("/etc/shadow","/etc/gshadow")` | `goethe.py:417`, `:846–850` |
| Privileged-token detection | `_priv_token_hits()` + chained-command variant | `goethe.py:569`, `:951–974` |
| Read/write path allowlists | `_is_allowed_read` / `_is_allowed_write` | `goethe.py:460`, `:617` |
| Protected write filenames (rc files, SSH keys) | `_BLOCKED_WRITE_FILENAMES` | `goethe.py:597`, `:625–633` |
| Heredoc-body evasion | `_strip_heredoc_bodies` + `_normalize_for_scan` before scanning | `goethe.py:735`, `:759` |
| Pre-write recovery snapshot | git blob under `refs/lse-snapshots/`, fs fallback; **caller MUST refuse if both fail** | `goethe.py:1314–1373` |
| PKILL self-match | unbracketed `pkill -f` over `ssh_run` blocked | `goethe_netsec.py:114–125` |
| Active-download clobber | `pgrep` probe refuses a second download | `goethe_web.py:150–175` |
| Web anti-spiral budget | rolling window, `BUDGET EXHAUSTED` refusal | `goethe_web.py:95–140` |
| Year stripping (CHRONOS) | years removed server-side from queries | `goethe_web.py:448`, docstring `:230–232` |
| `[TIME]`/`[DREAM]` banner | server-injected, once-per-session flag | `goethe_web.py:462`; `goethe.py:1656`, `:1679` |
| Asymmetric trust | web can never mint `ground_truth` | `goethe_kb.py:60–68`, wired `:502` |
| Tier ceilings | single `TrustPolicy` source of truth | `goethe_kb.py:33–44` |
| Evidence-gated demotion | `len(evidence) >= 20` | `goethe_kb.py:935` |
| Ground-truth evidence floor | `>= 50` chars | `goethe_kb.py:1559` |
| `kb_verify` thin-observation reject | `len(observed) < 20` | `goethe_kb.py:1132` |
| Quarantine at floor | `q <= 0.2 → stale=True` | `goethe_kb.py:941–947` |
| Shutdown confirmation | two-step `confirmed` gate | `goethe_node.py:642` |
| Sudo grant lifecycle | grants DB, sudoers generation, one-time consumption | `goethe_perms.py:195`, `:221`, `:252`, `:445` |
| Secret redaction on egress | `_SENSITIVE_TOOLS` blanket-redact + `_SECRET_FIELD_RE` convention | `goethe_mcp.py:349`, `:493`, `:556` |
| Dream human gate | blocking `input()`, EOF→reject | `dream_apply.py:657` |
| Dream proposal validation | eleven independent checks incl. CAS | `dream_apply.py:499` |
| Protocol text survives MCP truncation | test reads the cap from the gateway | `tests/test_docstring_mcp_truncation.py:26–38` |

### 7.2 Prompt-only

| rule | where it lives | what happens if ignored |
|---|---|---|
| **KB-FIRST** ("ALWAYS call search_kb before search_web") | `goethe_web.py:209–216` docstring | **Nothing.** `search_web` has no code path that checks whether `search_kb` ran. |
| REQUIRED SEQUENCE steps 1–5 for `search_web` | `goethe_web.py:219–231` | nothing |
| "Do not call search_web more than once for the same topic" | `goethe_web.py:232` | nothing (the budget gate limits volume, not repetition) |
| CONFIG GROUND-TRUTH RULE | `execute_command` docstring | nothing |
| RESOURCE-AVAILABILITY RULE (ping before SSH/API) | `execute_command` docstring | nothing |
| VENDOR-BEHAVIOR GROUND-TRUTH RULE (waterfall before patching) | `execute_command` docstring | nothing |
| RELEASE ASSET RULE (`get_github_release` before pinning) | `execute_command` docstring | nothing |
| DOWNLOAD PROGRESS RULE (call `monitor_download`) | `execute_command` docstring | **partially enforced** — `_active_download_guard` catches the clobber case only |
| KB-FIRST before first `ssh_run` to a new host | `goethe_netsec.py:83` | nothing |
| SSH-complexity guidance (use `ssh_script` for chains) | `goethe_netsec.py` docstrings | actionable hint, not refusal |
| CONTEXT HANDOFF at >70% | `plan_step_done` docstring | nothing |
| "hand-written plan or tracking files are a protocol violation" | system prompt + planner docstring | **nothing — and it failed in production** |

### 7.3 The pattern that makes this table interesting

The project **migrates rules from the right column to the left when they fail**, and it
says so in the code. `goethe_web.py:155–162`:

> *"Code-level enforcement: the LSE has repeatedly re-issued download commands (curl / hf
> download) instead of calling monitor_download() to check progress, restarting the
> transfer and producing partial/corrupt files — **docstrings did not hold**."*

`goethe.py:1323`:
> *"Enforcement in code, not docstring (sudo-blocker lineage)."*

`goethe_web.py:233` even annotates the boundary inside a single docstring:
> *"TIME DISCIPLINE (v0.3.1 — **ENFORCED IN CODE, not prose**; CHRONOS-4 retired the old
> YEAR-INJECTION and 30d/7d staleness rules from this docstring)"*

So: this is not a system that confuses instructions with controls. It knows the
difference, annotates it, and has a demonstrated one-way ratchet from persuasion to
enforcement, driven by production incidents. **That ratchet — not any individual guard —
is the thing worth funding.** `02` scores it accordingly.

And the counter-evidence is equally clear. `/opt/local-se/active-task.md` is a
hand-written tracking file, forbidden by the protocol, **live on the canonical host for
44 days** (mtime 2026-07-04, observed 2026-08-17) `[verified: ls -la]`, cross-referencing
a real ledger task id — the operator ran the compliant and the forbidden mechanism side
by side. Every rule in §7.2 is one bad day away from that.

### 7.4 The guards are not theoretical

`[verified: /opt/local-se/agent_commands.log, 117,022 lines]`
```
  11939 CMD              6644 PRIV-BLOCKED
  11704 DONE             2323 HARD-BLOCKED
                         1370 WRITE-BLOCKED
                          364 READ-BLOCKED
```
**10,701 refusals against 11,939 executed commands.** The left column of §7.1 fires
roughly as often as commands succeed. This is the system's best evidence and it exists
only as an ungoverned log file on one machine.

---

## 8. The hardened gateway launcher (`start-goethe-safe`)

§4 asks me to document this as a security strength. It is one — and its location is a P0.

**What it does** `[verified: /proc/1354430/cmdline]`. A `setsid --fork --wait` wrapper
around an inline Python supervisor that, before and during every write to its log sink:

- re-`lstat`s the log path and `fstat`s its own descriptor, and **raises
  `RuntimeError("launch log identity changed")`** unless `(st_dev, st_ino)` still match,
  the file is still a regular file, `st_uid == os.getuid()`, and the mode is still
  exactly `0o600`. That is a symlink/replacement attack check on every write.
- caps the active log at `16 * 1024 * 1024` bytes and wraps in place with the marker
  `[start-goethe-safe] active log reached 16 MiB and was wrapped`.
- degrades loudly rather than silently: `mark_degraded()` emits
  `[start-goethe-safe] LOG SINK DEGRADED; OUTPUT WILL BE DISCARDED: <detail>`.
- sanitises every detail string through `safe_detail()` — strips `\t\r\n`, ASCII-encodes
  with `backslashreplace`, truncates to 512 — so nothing can inject log lines.
- refuses to start unless `expected_host in ("127.0.0.1","0.0.0.0")` and a command exists.
- coordinates start-up through `.state` / `.gate` / `commit-*.gate` files under
  `/tmp/goethe-gui-runtime-<uid>/` keyed by a launch nonce and a UUID.

This is careful, adversarially-minded code. **It is not in any of the analysed repos.** It
lives at
`/mnt/c/Goethe3.0/.deploy-staging/Goethe.App-20260801-safe-03/win-x64/Scripts/start-goethe-safe.sh`,
one of ten parallel staging directories, and the `goethe_mcp.py` beside it is a third
divergent copy carrying **no `__version__` at all**:

```
fccf09a3…  /mnt/c/…/Scripts/goethe_mcp.py     ← the one actually serving :9700
9ca2c554…  tools/goethe_mcp.py                ← __version__ = "1.13.0"
7c66e09c…  lse/mcp/goethe_mcp.py              ← un-remoted repo
```

The security strength and the provenance P0 are the same artifact. `05`/M0 must pull it
into VCS before anything else is touched.

---

## 9. State stores

| store | path / index | written by | if lost | governance |
|---|---|---|---|---|
| `tasks.db` | valve `TASKS_DB` | `goethe_planner.py:861`, `task_checkpoint`, `plan_step_done` | **all in-flight plans and step ledgers** — the planner↔agent channel | `.gitignore`d; no backup found |
| `agent_commands.log` | `/opt/local-se/agent_commands.log` | `self._log()`, 8 modules, 139 sites | the entire safety-enforcement record (117k lines / 7.4 MB) | `*.log` gitignored; read-only input to TRAUM pass 4 |
| `lse-kb` | ES :9200 | `index_to_kb`, `mentor_correct`, `record_outcome`, dream apply | the accumulated operational knowledge | **282 docs on A, 45 on B**; no snapshot repo configured |
| `lse-errors` | ES :9200 | `record_error` | diagnosis records (interpretation + anti_response) | **82 on A, 1 on B** |
| `lse-skills` | ES :9200 | `skill_record`, `skill_outcome` | learned procedures | 30 on A, 5 on B |
| `lse-rfc-kb` | ES :9200 | RFC authority ingest | 628 docs | **A-only; in no manifest** |
| `lse-web-idx` | ES :9200 (node3090) | unknown | **45,415 docs** | **B-only; in no manifest, doc, or `.gitignore`** |
| `episodes/` | `/opt/local-se/episodes` | `goethe_mcp.py:528 _journal()` | TRAUM's entire input corpus | 37 MB / 701 files on A; day-dir cap 500 MB |
| `traum-state.db` | dream dir | `traum_state.py` | run/attempt/proposal history and the CAS anchors | `.gitignore`d |
| `challenges.db` | LSE Challenge Arena | arena tooling | benchmark history | referenced README:61 |
| grants DB | `goethe_perms.py:57 _db()` | `grant`, `revoke`, `resolve_request`, `_audit` | **every sudo grant and its audit trail** | separate audit table, not in `agent_commands.log` |
| `.search_budget.json` | beside `TASKS_DB` | `_budget_gate` | the anti-spiral window | ephemeral by design |

**Not one of these has a backup policy in the repo.** `docs/07-operations-runbook.md`
exists and §10 covers dreaming operations, but no scheduled dump of ES, no SQLite backup,
no episode archival rotation is defined in tracked code. The KB is the moat; the moat has
no snapshot. That is M0 scope.

### 9.1 What the 6× KB divergence actually means

The brief asks what it means that the two instances' KBs diverge 6×. Sharpened by the
counts in `00`:

| index | A | B | ratio |
|---|---|---|---|
| `lse-kb` | 282 | 45 | 6.3× |
| `lse-skills` | 30 | 5 | 6× |
| `lse-errors` | 82 | **1** | **82×** |

The two instances run **byte-identical code** (15/15, §0.3) against **wildly different
memory**. So the honest reading is:

- **For the sovereignty claim, this is good.** It proves the KB is genuinely per-instance
  local state and not a shared service — the product is separable from any one machine.
- **For the product claim, it is the central risk.** Behaviour is a function of code *and*
  KB, and only the code is under version control. Two instances of "Goethe v0.4.9" will
  answer the same question differently and there is no artifact that describes the
  difference. `lse-errors` at 1 doc means node3090's `check_error_kb` is effectively a
  no-op: the instance cannot recognise a failure it has seen before.
- **It makes "which instance did you demo?" an unanswerable question**, which is exactly
  the question a technical partner asks second.

The KB is not versioned, not schema-versioned, not snapshotted, and not diffable. Until
it is, the KB is the least reproducible and most valuable thing in the system. `05`
sequences the unification decision on that basis.
