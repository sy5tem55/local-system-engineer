# 04 — Fundability Gap

## What "fundable" means here

Two audiences, one bar. A **seed VC** asks *"can a team I don't know run this, and is the
hard part hard?"* A **research grant reviewer** asks *"is the claim novel, and is the
evidence reproducible by someone else?"* Both reduce to the same test:

> **A competent stranger, given only the repository URL and a laptop, can reach a running
> instance and reproduce every claim you make — without you in the room.**

Every criterion below is written so that it passes or fails on a **command someone else
can run** or an **artifact they can open**. No criterion is scored on my impression.

Scoring: each criterion 0–100, weighted. **Anything below 80 maps to a milestone in `05`.**

---

## Definition of Fundable — the acceptance criteria

### A. Code integrity (weight 12)

| # | criterion | test |
|---|---|---|
| A1 | CI runs on every push | `gh api repos/:owner/:repo/actions/workflows` returns ≥1 workflow; badge green on `master` |
| A2 | Lint gate | CI job `lint` runs `ruff check .` and fails the build |
| A3 | Test gate with coverage floor | CI job `test` runs pytest; `--cov-fail-under=70` |
| A4 | Type gate | `mypy tools/` or `pyright` in CI, non-strict, ratcheting |
| A5 | Release tags | `git tag -l` non-empty; every tag has a CHANGELOG section |

### B. Provenance (weight 20 — P0-critical)

| # | criterion | test |
|---|---|---|
| B1 | One canonical repo, declared | `PROVENANCE.md` at root naming repo + branch + deployed artifact |
| B2 | One-line "where is the code" | `head -1 PROVENANCE.md` answers it |
| B3 | Every tree accounted for | `PROVENANCE.md` lists `lse/`, `Goethe3.0`, node3090, each with status ∈ {canonical, vendored, frozen-evidence, retired} |
| B4 | Fresh clone → running instance on clean hardware | `scripts/bootstrap.sh` on a blank VM ends with `curl -s localhost:9700/health` returning 200 |
| B5 | The deployed gateway is a tracked artifact | `sha256sum $(readlink -f <running gateway>)` matches a file in the repo; asserted by a test |
| B6 | Corpus B retired or re-synced with a manifest | either B carries a `git clone` of the remote, or `EVIDENCE-MANIFEST.md` freezes it with hashes |
| B7 | Corpus hash manifest | `scripts/corpus_manifest.py --verify` exits 0 |
| B8 | Dependencies declared and pinned | `pyproject.toml` `[project].dependencies` + lockfile; `pip install -e .` succeeds offline-ish |

### C. Documentation (weight 10)

| # | criterion | test |
|---|---|---|
| C1 | README states what it is, for whom, in the first screen | read it |
| C2 | README version block is correct | matches `tools/goethe.py:3`; asserted in CI |
| C3 | Quickstart that works | a stranger follows it to a running instance |
| C4 | Architecture doc current | `LSE-ARCHITECTURE.md` matches the shipped module layout |
| C5 | CHANGELOG usable | sectioned by release tag |
| C6 | `docs/` has an index | `docs/README.md` exists |

### D. Security (weight 14)

| # | criterion | test |
|---|---|---|
| D1 | Threat model doc, current | `docs/threat-model-kb.md` with no findings marked open-but-actually-fixed |
| D2 | Secret handling documented, one path | `docs/security.md` names one resolution order |
| D3 | No secrets in any tracked or logged artifact | `gitleaks detect` clean; `grep` over a redacted log sample clean |
| D4 | Egress redaction tested | contract tests over `redact.py` + `_SENSITIVE_TOOLS` |
| D5 | External review sign-off | a named reviewer's written pass |
| D6 | Command execution has a non-shell path | allowlisted argv mode exists and is the default for common operations |

### E. Evaluation (weight 16)

| # | criterion | test |
|---|---|---|
| E1 | Suite size adequate to the claims | behavioural + contract, both in-repo |
| E2 | Regression baseline stored | `eval/baselines/<version>.json` committed |
| E3 | Pass rate over time visible | CI publishes; trend readable |
| E4 | Contract tests run in CI (not skipped) | the 98 ES-dependent tests execute |
| E5 | The moat claim has an efficacy result | a TRAUM eval that is not n=1 |

### F. Demo-ability (weight 10)

| # | criterion | test |
|---|---|---|
| F1 | 10-minute reproducible demo script | `scripts/demo.sh` on clean hardware |
| F2 | Demo shows the moat, not the tool list | it must show a proposal → human gate → KB change |
| F3 | Demo needs no homelab | works against seeded fixtures |

### G. Metrics (weight 8)

| # | criterion | test |
|---|---|---|
| G1 | Audit log queryable | a command producing the refusal taxonomy |
| G2 | Episode corpus documented | size, schema, retention |
| G3 | KB health visible | doc count, quality distribution, quarantine count, staleness |
| G4 | A headline number a partner can repeat | e.g. "10,701 refusals / 11,939 commands" |

### H. IP (weight 5)

| # | criterion | test |
|---|---|---|
| H1 | LICENSE present and appropriate | Apache-2.0 ✅ |
| H2 | Clean provenance — no third-party code of unclear origin | `.backups/openwebui-tool-v1.6.1.py.bak` reviewed |
| H3 | Contributor story | single author, documented |

### I. Narrative (weight 5)

| # | criterion | test |
|---|---|---|
| I1 | One-pager exists | `09-onepager.md` |
| I2 | It leads with the moat, not the feature list | read it |
| I3 | Claims are precise where the code is conditional | e.g. "never auto-applies" → "not under the shipped configuration" |

---

## Score: Goethe today — **41 / 100**

| group | wt | score | weighted | gap → milestone |
|---|---|---|---|---|
| A. Code integrity | 12 | **25** | 3.0 | M0, M1 |
| B. Provenance | 20 | **15** | 3.0 | **M0** |
| C. Documentation | 10 | **45** | 4.5 | M1, M6 |
| D. Security | 14 | **50** | 7.0 | M3 |
| E. Evaluation | 16 | **48** | 7.7 | M4 |
| F. Demo-ability | 10 | **10** | 1.0 | M5 |
| G. Metrics | 8 | **35** | 2.8 | M5 |
| H. IP | 5 | **85** | 4.3 | — |
| I. Narrative | 5 | **0** | 0.0 | M6 |
| | **100** | | **41.3** | |

**Every group except H is below 80. All eight map to milestones.**

---

## Itemised justification

### A. Code integrity — 25/100

| # | score | evidence |
|---|---|---|
| A1 CI | **0** | `ls: cannot access '.github/workflows': No such file or directory`. `.github/` exists, holds only Copilot instructions. |
| A2 Lint | **30** | `pyproject.toml` configures ruff for `BLE, E9, F` — three rule families, no type/complexity/security/import rules. Nothing runs it. Partial credit: a `RUFF-TRIAGE-2026-07-31.md` exists, so it has been run by hand. |
| A3 Tests + floor | **55** | The suite is real: 37 files, 14,625 LOC, **925 collected, 818 passing from a fresh clone in 10.28s**. No coverage measurement, no floor, nothing gated. This is the highest-value under-claimed asset in the repo. |
| A4 Types | **0** | Annotations are used throughout; no checker configured. |
| A5 Tags | **0** | `git tag -l` → empty. 224 KB of CHANGELOG maps to no tag. |

**The gap is not work; it is wiring.** A1+A3 together are ~1 day and move this group from
25 to ~75.

### B. Provenance — 15/100 · **the binding constraint**

| # | score | evidence |
|---|---|---|
| B1 canonical repo declared | **20** | The GitHub remote exists and works. Nothing declares it canonical, and HEAD is on `codex/fix-sudo-grants-live`, not `master`, with no statement of which branch is authoritative. |
| B2 one-line answer | **0** | Four answers (`03` P0-3). |
| B3 every tree accounted for | **0** | `lse/` is an un-remoted repo; `Goethe3.0` has two further remotes; node3090 has no VCS. None documented. |
| B4 fresh clone → running | **25** | Clone + checkout + 4 `pip install`s → **818 tests pass**. That is real credit. But there is no bootstrap script, no dependency manifest, and 4 tests fail on a hardcoded Windows path (`tools/node_facts.py:405`). You reach a *tested* tree, not a *running instance*. |
| B5 deployed artifact tracked | **0** | The live gateway `fccf09a3…` is in no repo and carries no `__version__`. |
| B6 corpus B status | **10** | B is a working rsync mirror (15/15 sha-identical) — better than the brief believed — but has no VCS, no manifest, and holds the only copy of the T0/T1 eval suite and a 45,415-doc index. |
| B7 corpus manifest | **20** | `eval/SHA256SUMS` exists for 5 artifacts. Nothing repo-wide. |
| B8 dependencies | **0** | No manifest of any kind; `goethe.py:6` pins `elasticsearch==8.19.3` in a docstring while units run 9.4.1 against ES 9.4.3. |

**This group alone is 20% of the score and sits at 15.** It is also the cheapest to fix.

### C. Documentation — 45/100

| # | score | evidence |
|---|---|---|
| C1 README opening | **60** | Two competing H1s (`README.md:1` "Your AI Sysadmin That Actually Works", `:23` "Local System Engineer (LSE)"). Content is substantive — stack, versions, security model, TRAUM, layout. |
| C2 version block correct | **0** | `README.md:50` v0.2.5 vs `:191` v0.4.0-a vs code v0.4.9. **Self-contradictory.** |
| C3 quickstart | **20** | No install section a stranger can follow; no dependency list to install. |
| C4 architecture doc | **60** | `LSE-ARCHITECTURE.md` (23.8 KB) exists and is well-structured; predates the mixin extraction in places. |
| C5 CHANGELOG | **30** | 224 KB, chronological, maps to no tag. Rich but unusable for diligence. |
| C6 docs index | **20** | 80+ files including a threat model, a runbook, an operator manual and 14 dated SPECs — **genuinely good material that nobody will find**. No index. |

The documentation problem is not absence. It is that ~400 KB of real documentation is
undiscoverable and self-contradictory about the one fact a reader checks first.

### D. Security — 50/100

| # | score | evidence |
|---|---|---|
| D1 threat model | **65** | `docs/threat-model-kb.md` exists, Shostack ×4, with 22 cited test node-id groups re-verified. **Stale in the reader's favour's opposite direction**: it records origin tagging as UNIMPLEMENTED; it is implemented (`goethe_kb.py:502`). A reviewer will believe the gap is open. |
| D2 secret path documented | **35** | Three different resolution orders across three files (`03` P1-14), two different secrets paths. `VALVES.md:13` honestly documents `/proc/<pid>/environ` exposure — which I confirmed live by reading the gateway's full argv with no privileges. |
| D3 no secrets in artifacts | **40** | `.gitignore` is disciplined (`*.log`, `*.jsonl`, `token*.json`, `*.env`, `tokens.md`). But a **live plaintext password was found in `agent_commands.log`** by the project's own dream pass, and rotation was left *"on the operator"*. Unverified whether it happened. |
| D4 egress redaction tested | **75** | `redact.py` 517 LOC, `RedactingFormatter`, `_SENSITIVE_TOOLS` blanket-redaction (`goethe_mcp.py:349,493,556`), `_SECRET_FIELD_RE` by naming convention. Tested via contract suite. Genuinely strong. |
| D5 external review | **0** | None. |
| D6 non-shell execution path | **35** | `assert_state` (`goethe.py:1980`) proves the pattern — read-only argv allowlist, no shell. But `execute_command` is `subprocess.run(command, shell=True)` (`goethe.py:1220`) behind a denylist. |

The unusual thing here: **the enforcement is better than the documentation of it.** 10,701
logged refusals is stronger evidence than most funded security products can produce, and
it is invisible.

### E. Evaluation — 48/100

| # | score | evidence |
|---|---|---|
| E1 suite size | **70** | 925 contract tests (14,625 LOC) + a v3.5/v4 behavioural suite + `eval_goethe_rules.py` (453 LOC). **But the T0/T1 behavioural harness is not in the repo** — it lives only on node3090, and the two suites are disjoint. |
| E2 baseline stored | **20** | `eval/SHA256SUMS` and a frozen gold set (`retrieval-gold-v1.jsonl`) exist; **v2 gold sets exist only on the live host**. No pass-rate baseline per release. |
| E3 pass rate over time | **15** | Point-in-time prose reports (`eval-report-v9.md`, `eval-report-traum-1.md`). No trend. Self-reported number (420) is 2× below actual (818). |
| E4 contract tests run in CI | **0** | 98 tests skip on `Elasticsearch not reachable on 127.0.0.1:9200`. **The KB trust lifecycle — the moat — is unverified by construction in any automated run.** |
| E5 efficacy result for the moat | **55** | A pre-registered A/B was designed, run, and **lost** (A=53/60, B=51/60), published as a loss with methodological root cause. As *science conduct* this scores very high; as *efficacy evidence* it is n=1 with a ~15-minute divergence window and no true pre-dreaming snapshot (no ES snapshot repo was configured). |

E5 is the criterion that decides a research grant. The honesty is an asset; the result is
not yet evidence.

### F. Demo-ability — 10/100

| # | score | evidence |
|---|---|---|
| F1 demo script | **0** | None. |
| F2 demo shows the moat | **0** | — |
| F3 no homelab required | **30** | Partial credit only because 818 tests run with no infrastructure — the seams for fixture-based demoing exist. |

**This is the lowest group and the one that most directly costs money in a meeting.** The
system's best moment — a dream proposal rendered, a human answering `n`, the KB refusing
to change — is currently unreachable without an operator, a GPU and 14 months of episodes.

### G. Metrics — 35/100

| # | score | evidence |
|---|---|---|
| G1 audit log queryable | **40** | 117,022 lines with a real tag taxonomy — `CMD`, `DONE`, `PRIV-BLOCKED`, `HARD-BLOCKED`, `WRITE-BLOCKED`, `READ-BLOCKED`, `SEARCH-KB`, `INDEX-KB`, `SUDO-DELEGATE` — parseable with `grep`. No tool, no schema doc, no aggregate. TRAUM's patterns pass reads it, so a parser exists internally. |
| G2 episode corpus documented | **45** | 37 MB / 701 files, redacted at write, day-dir cap 500 MB, `_SENSITIVE_TOOLS` blanket-redacted. Schema lives in `goethe_mcp.py:528` and nowhere else. |
| G3 KB health visible | **30** | The fields exist (`quality_score`, `consecutive_failures`, `stale`, `updated_at`, `embed_model_version`) and `search_kb` surfaces trust counts and `[STALE]`/`[EXPIRED]` banners. No dashboard, no aggregate view. **Two indices (`lse-rfc-kb` 628, `lse-web-idx` 45,415) are in no manifest at all.** |
| G4 headline number | **25** | The number exists and is excellent — **10,701 refusals against 11,939 commands** — and I had to compute it. Nobody on the team has ever quoted it. |

### H. IP — 85/100

| # | score | evidence |
|---|---|---|
| H1 LICENSE | **100** | Apache-2.0, full text, 11 KB. Correct choice for a project wanting adoption plus patent protection. |
| H2 clean provenance | **60** | `.backups/openwebui-tool-v1.6.1.py.bak` (130 KB) is the OpenWebUI-era ancestor; the lineage from an OpenWebUI tool to a standalone MCP server should be stated explicitly rather than left for a reviewer to infer from a backup filename. |
| H3 contributor story | **90** | Single author, `AGENTS.md` present, history coherent. |

### I. Narrative — 0/100

No one-pager, no deck, no positioning document. `README.md:1` is the closest thing and it
leads with "Your AI Sysadmin That Actually Works" — a category claim in the most contested
category (`02` §5, score 4/10) rather than the memory claim (`02` §6, score 9/10). The
project is currently positioned on its weakest moat.

---

## The shape of the gap

```
   H  IP            ████████████████████░  85
   D  Security      ████████████░░░░░░░░░  50
   E  Evaluation    ███████████░░░░░░░░░░  48
   C  Docs          ██████████░░░░░░░░░░░  45
   G  Metrics       ████████░░░░░░░░░░░░░  35
   A  Code integ.   ██████░░░░░░░░░░░░░░░  25
   B  Provenance    ███░░░░░░░░░░░░░░░░░░  15   ← 20% of the weight
   F  Demo          ██░░░░░░░░░░░░░░░░░░░  10
   I  Narrative     ░░░░░░░░░░░░░░░░░░░░░   0
```

**The distinctive feature of this gap is that almost none of it is engineering.**

The hard, expensive, genuinely-novel work is *done*: a 13,260-line memory-consolidation
subsystem with a human gate that the 2026 literature says nobody else has shipped; 925
contract tests; a code-enforced trust lifecycle; a threat model; 14 months of operational
evidence. What is missing is **the layer that lets someone else see it** — CI, a
provenance statement, a dependency manifest, a demo, a number, a paragraph.

Rough effort split of the 59 missing points:

| kind of work | points recoverable | effort |
|---|---|---|
| wiring & declaration (CI, PROVENANCE, deps, tags, index, README) | **~26** | ~1.5 weeks |
| packaging & surfacing (demo, metrics tool, one-pager) | **~15** | ~2 weeks |
| genuine engineering (evidence provenance, argv path, ES-in-CI, TRAUM efficacy eval) | **~18** | ~6–8 weeks |

**A fundable score of 80+ is roughly a quarter of focused work, and the first 26 points
are a fortnight.** That is the plan in `05`.

---

## Target trajectory

| after | score | what a reviewer can now do |
|---|---|---|
| **today** | **41** | read code, form a good impression, fail to verify anything |
| **M0** | **58** | clone, bootstrap, run, and know which tree is real |
| **M1** | **66** | trust the docs, see green CI, cite a version |
| **M2** | **71** | trust that drift cannot silently recur |
| **M3** | **78** | trust the evidence gates and the secret handling |
| **M4** | **85** | see a pass-rate trend and an efficacy result — **fundable** |
| **M5** | **91** | watch a 10-minute demo and quote a metric |
| **M6** | **94** | read one page and understand the moat |

The threshold crossing is **M4**. M5 and M6 raise the valuation, not the fundability.
