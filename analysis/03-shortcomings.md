# 03 — Shortcomings Audit

Scope: **corpus A (canonical)**. `[B]` findings serve the drift analysis. `[env]` findings
cite command output.

Severity: **P0 = kills funding** (a diligence reader stops here) · **P1 = blocks it**
(must be closed before a term sheet) · **P2 = weakens it** (visible, arguable).

Categories: VCS/provenance · correctness · security · scalability · product · docs · eval ·
ops · epistemics.

**32 findings: 6 P0, 14 P1, 12 P2.**

---

## P0 — kills funding

### P0-1 · The deployment tree is a git repository with no remote
**Category:** VCS/provenance · **[A]**

`.gitignore` (verbatim):
```
# lse/ is an EMBEDDED GIT REPO of its own (the lse product tree) — ignored
# here wholesale; its content (incl. the goethe-dream unit templates) is
# committed inside lse/.git, not this repo.
lse/
```
```
$ git -C lse rev-parse HEAD   → 3ad9f2e37991b3352958734a3db9b864e3d0aaba
$ git -C lse remote -v        → (empty — NO REMOTE)
$ ls lse/  → CHANGELOG.md README.md VERSION.md bin docs exporters installer
             lib mcp owui services skills tasks.db
```
`[verified: goethe__execute_command]`

3,473 LOC containing the installer, the systemd unit templates, the skills trees, a
second gateway and a live `tasks.db` — with no push target, on one disk. Its entire
history dies with node4090's SSD. §1A lists `lse/` as part of corpus A; it is not in
corpus A.

**Fix:** `git remote add origin` + push, or vendor it into the canonical repo as a
subtree. Decide which; do it in M0 before anything else.

---

### P0-2 · The gateway serving production is in neither repository
**Category:** VCS/provenance, security · **[A][env]**

```
$ ps → bash /mnt/c/Goethe3.0/.deploy-staging/Goethe.App-20260801-safe-03/win-x64/Scripts/start-goethe-safe.sh --bind-host 127.0.0.1
$ tr '\0' '\n' < /proc/1354430/cmdline
/home/sy5/owui/bin/python3
/mnt/c/Goethe3.0/.deploy-staging/Goethe.App-20260801-safe-03/win-x64/Scripts/goethe_mcp.py
--goethe /home/sy5/projects/local-system-engineer/tools/goethe.py …
```

Three divergent copies of the gateway exist and **the one serving traffic is the least
governed**:
```
fccf09a359c28e4c…  /mnt/c/…/Scripts/goethe_mcp.py   ← LIVE.  no __version__ at all
9ca2c55402aca8c…  tools/goethe_mcp.py               ← __version__ = "1.13.0"
7c66e09c0939ffd…  lse/mcp/goethe_mcp.py             ← un-remoted repo
```
`/mnt/c/Goethe3.0` is a fourth repo with two more remotes
(`github → Goethe_GUI.git`, `goethe-app → Goethe.App.git`) and **ten parallel staging
directories** (`-safe-03`, `-safe-04`, `-safe-05`, `-3.16-fix`, `-preserved-20260810`,
`-pr-worktree`, `-c7-snapshot`, …).

The hardened `start-goethe-safe` launcher — genuinely good security code (log-sink
dev/ino/uid/mode identity checks, uid-pinned 16 MiB wrapping, degraded-mode markers,
`safe_detail()` log-injection sanitising, `expected_host` allowlist) — is in none of the
repos either. **The security strength and the provenance failure are the same file.**

**Fix:** pin the deployed gateway into the canonical repo, replace the staging-dir launch
with a versioned artifact, delete the nine stale staging dirs. Add
`tests/test_gateway_pin.py`-style assertion that the running gateway's sha matches a
tracked file. (That test file *already exists* — extend it.)

---

### P0-3 · "Where is the code" has four answers
**Category:** VCS/provenance · **[A][B]**

| # | location | VCS | remote |
|---|---|---|---|
| 1 | `~/projects/local-system-engineer` | git | `sy5tem55/local-system-engineer.git` |
| 2 | `~/projects/local-system-engineer/lse/` | git | **none** |
| 3 | `/mnt/c/Goethe3.0/…/Goethe.App-20260801-safe-03/` | git | `Goethe_GUI.git` + `Goethe.App.git` |
| 4 | `node3090:/home/lse-admin/projects/local-system-engineer` | **none** | rsync target |

Compounding it: HEAD is on `codex/fix-sudo-grants-live`, not `master`, and **nothing in
the repo declares which branch is authoritative** — `README.md`, `AGENTS.md` and
`CURRENT-STATE.md` are all silent. **7 of 10 local branches have no remote counterpart**,
including all three `refactor/*` branches and `traum-incoming`.

**Fix:** a `PROVENANCE.md` at repo root naming the canonical repo, the canonical branch,
the deployed artifact and the status of every other tree; enforce with a CI check.

---

### P0-4 · No CI, with 925 tests sitting green
**Category:** ops · **[A]**
```
$ ls -la .github/workflows
ls: cannot access '.github/workflows': No such file or directory
$ find .github -type f
.github/copilot-instructions.md
.github/instructions/{lse-tools,node-ops}.instructions.md
.github/prompts/{lse-docstring-audit,lse-stack-health}.prompt.md
.github/skills/{lse-docstring-audit,lse-stack-health}/SKILL.md
```
`.github/` exists and is used **only for Copilot instructions**. A ruff config exists
(`pyproject.toml`). 818 tests pass from a fresh clone. **Nothing runs on push.**

This is the cheapest P0 in the document — the work is already done, it simply is not
gated. It is also the single most damaging omission, because a reviewer reads "no CI" as
"nothing is verified" and never discovers the 925 tests.

**Fix:** `.github/workflows/ci.yml` — ruff + pytest + the drift detector (P0-6). M0.

---

### P0-5 · No dependency manifest of any kind
**Category:** ops, correctness · **[A]**
```
$ ls requirements*.txt setup.py setup.cfg Pipfile poetry.lock uv.lock
(all: No such file or directory)
$ cat pyproject.toml
[tool.ruff]                      ← the ENTIRE file
line-length = 120
target-version = "py313"
[tool.ruff.lint]
select = ["BLE","E9","F"]
```
No `[project]`, no `[build-system]`, no pins. Required third-party imports:
`elasticsearch, requests, pydantic, mcp, starlette, uvicorn, numpy, rich, pytest, PIL,
pdfminer, pypdf, torch, trimesh`.

The project already knows — CURRENT-STATE.md:14: *"no requirements.txt pins the client
anywhere; drift risk stands"*, alongside a recorded live mismatch (tracked systemd units
run `/usr/bin/python3` with ES client 9.4.1 against live ES 9.4.3, while the owui venv
carries 8.19.3). Meanwhile `goethe.py:6` declares `requirements: elasticsearch==8.19.3`
in a docstring — a **fourth** version of the same answer.

Also: `target-version = "py313"` matches no verified environment (tests verified green on
3.11; the gateway runs `/usr/bin/python3`).

**Fix:** `[project]` table with pinned deps + a lockfile; delete the docstring pin.

---

### P0-6 · Prompt-vs-code version drift, per-instance, with no detector
**Category:** correctness, ops · **[A][A-vs-B]**

| instance | prompt template | claims mcp | claims Goethe | actual code |
|---|---|---|---|---|
| node3090 | `prompts/node3090-v0.3.0.md:37` | v1.11.2 | v0.4.4 | **v1.13.0 / v0.4.9** |
| node4090 | `prompts/v0.6.2.md:12` | v1.12.0 | v0.4.4 | **v1.13.0 / v0.4.9** |

The two prompts **disagree with each other** about **byte-identical code** (15/15 files
sha-identical, `00` §0.3). Drift is per-instance.

Corpus-wide there are **19 distinct version tuples** for two artifacts, not the five the
brief expected. `README.md` contradicts *itself*: v0.2.5 at line 50, v0.4.0-a at line 191.
Two files both titled `v0.5.18` claim different gateway versions.

**This is a known, ticketed, unclosed defect class.** `kb/session-learnings.md:762`:
> *"Three different version strings currently coexist for 'Goethe' … none of these were
> reconciled this session, flagged in eval-report-v7.md instead"*

and `ROADMAP.md:52` carries an open **P0-1** to fix it — now seven minor versions stale.
A docs pass has been tried and has failed repeatedly. **Only a gate will hold.**

#### The detector — exact wiring

`.github/workflows/ci.yml`, job `drift`:

```yaml
  drift:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python3 scripts/check_version_drift.py --strict
```

`scripts/check_version_drift.py` — three extractors, one comparison, exit 1 on mismatch:

1. **Code (authoritative).**
   - `tools/goethe.py` → `^title:\s*LSE Goethe v(?P<v>\d+\.\d+\.\d+)` and
     `^version:\s*(?P<v>\d+\.\d+\.\d+)` (assert these two agree with each other).
   - `tools/goethe_mcp.py` → `^__version__\s*=\s*"(?P<v>[^"]+)"`.
2. **Prompt templates.** Every `prompts/*.md` and `tools/system-prompt-*.md`:
   `^Version:\s+\S+\s+\((?P<parts>.*)\)$` and `^>\s*Requires:\s*(?P<parts>.*)$`, parsing
   `goethe_mcp v<x>` and `Goethe v<y>`. **Only files named in `prompts/DEPLOYED.toml`
   are checked** — a two-key manifest mapping instance → template
   (`node4090 = "v0.6.2.md"`, `node3090 = "node3090-v0.3.0.md"`), because the other 42
   files are deliberate history and must not fail the build.
3. **Docs.** `README.md`, `CURRENT-STATE.md`, `ROADMAP.md`, `VALVES.md`, `VERSION.md`,
   `skills/**/SKILL.md` → same two regexes.

Failure modes, each with its own exit message:
- any deployed prompt template disagrees with code → **fail**
- two deployed templates disagree with each other → **fail** (this is the per-instance class)
- any doc disagrees with code → **fail**
- the two `goethe.py` self-declarations disagree → **fail**
- `prompts/DEPLOYED.toml` names a file that does not exist → **fail**

Plus a **live extension** run by the Qwen tracker rather than by CI (`07` §5): for each
instance, `ssh <host> sha256sum <deployed prompt>` compared against the tracked template's
hash, so a hand-edited prompt on a live box is also caught. CI cannot see the live boxes;
the tracker can.

**Why this is cheap:** the prompt templates are already *in the repo* (44 of them), and
`goethe_node.py:387 check_node_agent_drift` proves the team already builds drift
detectors. This is an existing pattern pointed at the one surface it was never pointed at.

---

## P1 — blocks funding

### P1-1 · `execute_command` is a denylist in front of `shell=True`
**Category:** security · **[A]**

`goethe.py:1220–1222`:
```python
result = subprocess.run(
    command,
    shell=True,
```
Everything protecting that call is `_validate_command_safety()` (`goethe.py:815`)
correctly parsing arbitrary shell *before* `sh -c` sees it — via `_BLOCKED_COMMANDS`
substring matching (`:376`), `_BLOCKED_COMMAND_NAMES` token matching (`:404`),
`_priv_token_hits()` (`:569`), `_normalize_for_scan()` (`:735`) and
`_strip_heredoc_bodies()` (`:759`).

The engineering is careful and the guards fire 10,701 times in the live log. But
denylist-before-shell is a **structurally losing position**: it must anticipate every
encoding of every forbidden operation, while the attacker needs one. `echo <base64> |
base64 -d | sh`, `$'\x73udo'`, `${IFS}`, variable indirection, and any interpreter
invocation route around substring matching. `goethe.py:739` shows the team already knows —
D5-FIX (2026-07-31) exists precisely because `_BLOCKED_COMMANDS` being "a
literal-substring list" caused a miss.

**Context that keeps this at P1, not P0:** the threat model is the operator's own model
misbehaving, not an adversary with prompt injection. But the agent *does* ingest untrusted
web content (`fetch_url`, `search_reddit`, browser-rendered scraping), so an
injection→execution path exists on paper.

**Fix:** for the common paths, add an allowlisted argv mode (`assert_state` already proves
the pattern — read-only argv allowlist, no shell, `goethe.py:1980`) and reserve
`shell=True` for an explicitly-flagged escape hatch that logs at a distinct level. Not a
rewrite; a second door.

---

### P1-2 · Evidence gates are length checks
**Category:** epistemics · **[A]**
```python
elif len(evidence) >= 20:                 # goethe_kb.py:935
if len(observed) < 20:                    # goethe_kb.py:1132
def check_evidence_thin(args, min_len=20) # dream_apply.py:384
```
Twenty characters of any string passes. No check that the evidence came from a tool call.
The system's headline property — "code-enforced evidence" — is enforced by `len()`.

**Fix, and it is the best item in the plan:** every tool call is already journaled with
its verbatim result to `/opt/local-se/episodes` (`goethe_mcp.py:528`). Require the
evidence string to be a substring of a result the current session actually received. That
converts a length check into a **provenance proof**, using infrastructure that exists, and
it is a feature a memory *library* structurally cannot copy because it requires owning the
execution surface. ~1 week. See `05`/M3.

---

### P1-3 · KB-FIRST — the system's most-cited rule — is prompt-only
**Category:** epistemics · **[A]**

`goethe_web.py:209–216` (docstring):
> *"KB-FIRST RULE — mandatory, no exceptions: ALWAYS call search_kb() before calling this
> function. … Skipping search_kb() before search_web() is a protocol violation."*
> *"GATE: Only call this when search_kb() has been called first and returned a miss."*

`search_web` contains **no code path that checks whether `search_kb` ran**. The word
"GATE" appears; no gate exists. Same for the "REQUIRED SEQUENCE" steps 1–5 (`:219–231`)
and "Do not call search_web more than once for the same topic" (`:232`).

**Fix:** a per-session flag set by `search_kb` and checked by `search_web`, returning a
refusal that names the missing call. The `_budget_gate` (`goethe_web.py:95`) already
demonstrates exactly this shape of session-scoped code gate in the same file.

---

### P1-4 · Prompt-only rules decay — observed in production, 44 days
**Category:** epistemics, product · **[A][env]**
```
-rw-r--r-- 1 sy5 sy5 1700 Jul  4 16:05 /opt/local-se/active-task.md

# Active Task: Pi-hole Audit + SSD Partitioning
## Task C: Pi-hole State of the Art Audit — IN PROGRESS (task bb705f42)
- [x] Research: Exa + Reddit via Camoufox — KB indexed (19b48a6038e6f535)
- [ ] Backup Pi-hole config — BLOCKED, user did not confirm
```
A hand-written tracking file the protocol explicitly forbids, live for 44 days on the
canonical host — and it **cross-references a real ledger task id** (`bb705f42`), i.e. the
compliant mechanism and the forbidden one ran side by side.

This is not a footnote. It is the empirical proof that everything in the prompt-only
column of `01` §7.2 is one busy day from failing, and it happened to the person who wrote
the rule.

**Fix:** `planner()` refuses to start a task while an unregistered `*task*.md` exists in
`/opt/local-se/`, naming the file. Ten lines. It converts the project's most embarrassing
artifact into a demo of the ratchet.

---

### P1-5 · The behavioural eval suite is not in the canonical repo
**Category:** eval, VCS/provenance · **[A][B]**
```
$ find . -name 'run_t0t1_suite*' -o -name 't1_feedback_loop*' -o -name 't1_mcp_harness*'
(empty = ABSENT from canonical repo)
```
It exists only on node3090:
```
f 30207 2026-07-08 …/eval/run_t0t1_suite.py
f  7690 2026-07-08 …/eval/t1_feedback_loop.py
f  8085 2026-07-08 …/eval/t1_mcp_harness.py
f 11562 2026-07-08 …/eval/t0t1_suite_results.json
```
`.gitignore` ignores `eval/*` as a class with 14 named carve-outs; the T0/T1 suite is not
among them. The two hosts' eval suites are **disjoint**, not sub/superset. Two newer gold
sets (`retrieval-gold-v2.jsonl`, `retrieval-gold-v2-candidates.jsonl`) also exist only on
the live host, in no repo.

The behavioural evidence a grant reviewer would ask for lives, unversioned, on the machine
the brief calls "not the project".

**Fix:** carve-out and commit the T0/T1 suite and the v2 gold sets; make the two suites
one suite.

---

### P1-6 · No backup policy for any state store
**Category:** ops · **[A][env]**

Not one of `tasks.db`, `traum-state.db`, `challenges.db`, the grants DB,
`agent_commands.log` (117,022 lines / 7.4 MB), `episodes/` (37 MB / 701 files) or the six
Elasticsearch indices has a scheduled backup defined in tracked code. The project records
the consequence itself: `eval/eval-report-traum-1.md` per CURRENT-STATE.md:14 —
*"no true pre-dreaming ES snapshot existed (no snapshot repo configured)"* — which
**invalidated the control arm of the flagship A/B experiment.** Absent backups have
already cost this project its most important result.

**Fix:** ES snapshot repository + nightly SQLite `.backup` + episode archival rotation, in
`lse/services/`, with a restore drill in the runbook. M0.

---

### P1-7 · The audit log does not cover the highest-risk surface
**Category:** security, ops · **[A]**

`self._log()` call sites per module:
```
goethe_planner.py 37   goethe.py 28   goethe_kb.py 23   goethe_web.py 22
goethe_node.py 16      pfsense_tools 6   net_discovery_tools 4   goethe_netsec.py 3
```
**`goethe_netsec.py` — `ssh_run`, `ssh_script`, `nmap_summary`, the highest-privilege
remote execution path — has three log sites**, and 279 SSH lines appear in 117k. The TRAUM
subsystem writes to this log not at all; `goethe_perms.py` uses a separate `_audit()`
table (`:70`), so sudo grants and command execution are in different, uncorrelated stores.

**Fix:** log every SSH invocation with host, user, and redacted command; unify or
cross-reference the perms audit table.

---

### P1-8 · Library code hardcodes a Windows host path
**Category:** correctness, scalability · **[A]**
```
FileNotFoundError: [Errno 2] No such file or directory:
  '/mnt/c/Goethe3.0/ACTUAL-Qwen3.6-27B-UD-Q4_K_XL.gguf.md'
  at tools/node_facts.py:405
```
`[verified: pytest from fresh clone]` — 4 of the 9 fresh-clone failures. A library module
reaches into the Windows C: drive of one specific machine. The codebase cannot run
unmodified on any other host.

**Fix:** valve or env var with a documented default; skip cleanly when absent.

---

### P1-9 · Nine tests fail and 98 skip on a clean machine
**Category:** eval, ops · **[A]**
```
9 failed, 818 passed, 98 skipped in 10.28s
```
All 98 skips: `Elasticsearch not reachable on 127.0.0.1:9200`. Failures beyond P1-8:
`test_prove_it.py` ×3 (needs live ES/SSH — `ASSERT FAIL ❌ — /"status"/ NOT found in
output (exit 7)`); `test_goethe_perms.py` ×1 (asserts the wrong skip-reason branch under
`/tmp`); `test_cycle_completes.py` ×1.

818/925 green from a stranger's clone is a *strong* number. But "red on a clean checkout"
is what a reviewer sees first, and 98 silently-skipped KB-contract tests mean the trust
lifecycle — the moat — is **unverified in CI by construction**.

**Fix:** ES in a CI service container so the 98 run; mark the genuinely
environment-coupled ones `@pytest.mark.integration` and exclude by default.

---

### P1-10 · Two live data stores exist in no manifest, doc, or ignore file
**Category:** ops, epistemics · **[env][A][B]**
```
node4090: lse-rfc-kb    628 docs      (A-only)
node3090: lse-web-idx 45,415 docs      (B-only)
```
`lse-web-idx` is **by far the largest data store in the system** — 45,415 documents — and
appears in no manifest, no doc, no `.gitignore`, and no backup. Nobody can say what is in
it, who wrote it, or whether it contains secrets.

**Fix:** inventory every index; document or drop each; extend the corpus hash manifest to
cover data stores, not just code.

---

### P1-11 · `lse-errors`: 82 docs vs 1 — one instance has no error memory
**Category:** epistemics · **[A-vs-B][env]**

`check_error_kb` and TRAUM's error-cluster pass both read `lse-errors`. On node3090 it
holds **one document**. That instance is structurally incapable of recognising a failure
it has already diagnosed, while running byte-identical code that claims it can.

**Fix:** part of the KB unification decision (`05` M4).

---

### P1-12 · Single-operator coupling is total
**Category:** product, scalability · **[A]**

Every human-in-the-loop mechanism assumes exactly one human at one terminal:
- `dream_apply.ask_yes_no()` (`:657`) is `input()` on stdin — one person, one TTY, no
  audit of *who* approved, no delegation, no queue, no async.
- `mentor_correct`/`mentor_demote` (`goethe_kb.py:968`, `:1172`) take a reason string with
  no identity field. The KB records *that* a human authorised a change, never *which*.
- `sudo_delegation_block` produces a block for a human to run; grants land in a single
  local DB (`goethe_perms.py:57`) with no notion of requester vs approver.

**At two operators this breaks immediately**: no approval attribution, no
separation of duties, concurrent `dream_apply` runs race on `traum-state.db`. Every
enterprise buyer asks "who approved that?" in the first meeting, and today there is no
field to answer from.

**Fix:** an `actor` field on every gate (approve/demote/grant), sourced from an env or
token identity; move the dream gate behind the existing Console UI so approvals are
attributable and asynchronous. This is also the natural first *product* surface.

---

### P1-13 · A 2,396-line core and a 1,669-line UI, with lint that checks almost nothing
**Category:** correctness, product · **[A]**

`goethe.py` is 2,396 lines with `Valves` spanning `:57–439` (383 lines of configuration in
a class body). `goethe_ui.py` is 1,669. `dream_runner.py` is **5,135**. Ruff is configured
for `BLE`, `E9`, `F` only (`pyproject.toml`) — blind-except, syntax errors, pyflakes. **No
type checking anywhere** despite type annotations throughout; no complexity, naming,
import, security or docstring rules.

Mitigating: the mixin extraction (PH5-1/PH5-2, `goethe_kb.py:3–15`) shows decomposition is
already underway and was done *verbatim, with a contract suite pinning behaviour* — the
right way. Three `refactor/bumpy-road-*` branches exist, unpushed.

**Fix:** add `mypy`/`pyright` in non-strict mode to CI and ratchet; continue the mixin
extraction on `dream_runner.py`.

---

### P1-14 · Secret handling has three resolution orders and one plaintext-in-env pattern
**Category:** security · **[A]**

Order 1 (`tools/start-goethe.sh:29`): `source ~/.lse/secrets` → process env.
Order 2 (`tools/write-debrief-2026-06-08.sh:24`): *"env PFSENSE_API_KEY →
/opt/local-se/.lse/secrets → valve fallback"* — a **different path** (`/opt/local-se/.lse/`
vs `~/.lse/`).
Order 3 (`vaultwarden_tools_v1.3.0.py:10`): `BW_PASSWORD` env, set in `~/.lse/secrets`.

`VALVES.md:13` states the exposure plainly:
> *"The process environment is visible to anyone with access to LUCIFER's process table
> (`/proc/<pid>/environ`) — treat it the same as OpenWebUI valves were treated."*

I confirmed this is live: I read the gateway's full argv out of `/proc/1354430/cmdline`
with no privileges beyond the agent's own tool.

The **egress** redaction is genuinely good — `_SENSITIVE_TOOLS` blanket-redacts results
(`goethe_mcp.py:349`, `:493`, `:556`), `_SECRET_FIELD_RE` catches `*_KEY|TOKEN|SECRET|
PASSWORD` valves by convention rather than by list, `redact.py` is 517 lines with a
`RedactingFormatter`. The weakness is **at rest and in the process table**, not on the
wire. And CURRENT-STATE.md:14 records a live plaintext password having been found in
`agent_commands.log` via an `sshpass -p` command — with credential rotation *"still on the
operator"*, i.e. possibly still unrotated.

**Fix:** confirm that credential was rotated (do this today); move all secrets to
Vaultwarden with short-lived handles; document one resolution order and delete the others.

---

## P2 — weakens funding

### P2-1 · README contradicts itself about the product version
`README.md:50` → Goethe **v0.2.5**; `README.md:191` → Goethe **v0.4.0-a**; code → v0.4.9.
The first thing a reader opens is internally inconsistent and seven minor versions stale.
**Fix:** generate the version block from code at build time.

### P2-2 · The tool count is wrong everywhere
Actual public methods on `Tools`: **44** (goethe 8 + kb 13 + web 10 + node 6 + netsec 3 +
planner 4). Docs variously claim 45, 37 and "45 tools"
(`skills/lse-eval-runner/SKILL.md:40`, CURRENT-STATE.md:86, ROADMAP.md:163).
**Fix:** assert the count in CI.

### P2-3 · Self-reported test count is 2× too low
CURRENT-STATE.md:14: *"Full suite: 420 passed"*. Actual: **818 passed / 925 collected**.
The project undersells its own strongest asset.
**Fix:** CI publishes the number.

### P2-4 · An open P0 in ROADMAP.md is itself stale
`ROADMAP.md:52`: *"[ ] **P0-1** — Update CURRENT-STATE.md + VERSION.md to Goethe v0.2.9 /
goethe_mcp v1.9.3"*. The target versions are seven minor releases old. The backlog has
drifted from the code it tracks — the same failure the drift detector addresses.

### P2-5 · `CHANGELOG.md` is 224 KB and unreadable
No release sectioning that maps to a tag; unusable for diligence.
**Fix:** `Keep a Changelog` format, cut releases, tag them. **The repo has no tags at all.**

### P2-6 · Dead artifacts
`[A]` `tools/goethe_mcp.py.bak.2026-08-11`, `tools/voicebox-tts-proxy.py` — untracked but
git-adjacent, low risk.
`[B]` `goethe.py.bkp.20260630_144333` (266 KB), `goethe.py.new` (24 KB) — on a host with
**no VCS**, so these are unrecoverable-if-lost *and* a live confusion risk for anyone
looking at that machine. P1 for B's status as a live host; P2 for corpus A.
`.backups/` holds **24,941 LOC** of historical `goethe-v0.2.1/0.2.2/0.3.8.py` — the reason
naive LOC counts overstate the codebase by 55%.

### P2-7 · The engagement's own LOC figure is inflated
§1A's "~75,621 LOC across 131 files" counts backups and the un-remoted `lse/` tree. Honest
number: **53,793 LOC across 113 tracked files**. Quoting the larger figure to an investor
invites the correction to come from them.

### P2-8 · Port 3002 is double-booked
`localhost:3002` appears 9 times in `tools/` meaning Firecrawl on node3090 and Grafana on
node4090 depending on file. Nine hardcoded literals, no config layer, 20+ hardcoded
host:port pairs total.
**Fix:** a services config module.

### P2-9 · `docs/` is 80+ files with no index
Real assets are in there — `threat-model-kb.md`, `07-operations-runbook.md`,
`TRAUM-OPERATOR-MANUAL.md`, 14 dated SPECs — and no reader will find them.
**Fix:** `docs/README.md` index; promote the threat model and runbook into the top-level
README.

### P2-10 · No regression baseline for the eval suites
`eval/SHA256SUMS` exists (good), but there is no stored pass-rate history, no
per-release baseline, no trend. `eval-report-v9.md` and `eval-report-traum-1.md` are
point-in-time prose. A grant reviewer asks "pass rate over time" and there is no answer.
**Fix:** commit a `eval/baselines/<version>.json` per release; CI diffs it.

### P2-11 · TRAUM has an N of 1
The most novel component — 13,260 LOC, 44% of `tools/` — runs on exactly one machine, is
absent from node3090, and has never executed anywhere else. Its dependencies on that
host's paths are untested elsewhere.
**Fix:** make TRAUM runnable in CI against a disposable ES; that is also the efficacy-eval
prerequisite.

### P2-12 · `GOETHE_DREAM_AUTO_APPLY` weakens the headline claim if found first
`dream_apply.py:199`. Empty by default, decision documented with evidence. But "the agent
never applies its own proposals" is stated unconditionally in the brief and would be
found. State it as "never under the shipped configuration; auto-apply is an env var we
have deliberately left empty, and here is the decision record." Precision costs nothing
and buys the room.

---

## Findings the brief expected that I could not substantiate

Recording these so the next reader does not re-litigate them:

1. **"Corpus B frozen 2026-07-08 while A commits on 2026-08-15"** — **falsified**.
   `tools/` on node3090 has mtime 2026-08-15 and all 15 shared core files are
   byte-identical to A@pin. Root mtime does not reflect subdirectory changes. B is an
   automated rsync mirror, and the sync is documented (CURRENT-STATE.md:12). The
   provenance P0s are real, but *this* was not one of them.
2. **"MCP description truncation cuts protocol text"** — **not substantiated, and the
   opposite is true**. Exactly one docstring exceeds 3072 chars (`planner()`, losing 210),
   and the lost tail contains no contract keyword. `tests/test_docstring_mcp_truncation.py`
   structurally prevents the class, reading the cap out of the gateway so the gate cannot
   drift. This is a *strength*, and it was found by an incident (v0.4.7) and fixed
   properly.
3. **"origin tagging unimplemented / laundering protection is a blunt ceiling"** — was
   true when the threat model was written (2026-07-13, per CURRENT-STATE.md:14); **it is
   implemented now** at `goethe_kb.py:502`. Anyone reading the old note will believe the
   gap is open. Update the threat model.
4. **Circular import `goethe_netsec → goethe`** — **not real**. `goethe_netsec.py:16` is a
   comment reading *"import goethe.py — import direction is one-way, goethe.py imports
   this file."* The dependency graph is acyclic.

---

## Where the P0s cluster

Five of six P0s are **one problem**: nobody can say what the system is, where it lives, or
how to get a running copy. Not code quality — the code is better than the brief suggests.
818 green tests, a real threat model, a genuinely novel subsystem, 10,701 logged refusals,
and a published losing experiment sit behind a provenance story that a diligence reader
will not get past in the first hour.

That is good news for the milestone plan: **M0 is not a rewrite. It is a week of
canonicalisation that moves the fundability score more than any feature could.**
