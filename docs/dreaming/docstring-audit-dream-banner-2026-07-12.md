# lse-docstring-optimizer audit — [DREAM]-banner-adjacent docstrings (Prompt 3.9)

> TRAUM Thread 3, Prompt 3.9's own named task: "Run the lse-docstring-optimizer
> discipline over the [DREAM]-banner-adjacent docstring changes in goethe.py."
> Scope: everything Prompt 3.5 (v0.4.0-a) touched — `Tools._dream_banner()`,
> the TRAUM addition to `Tools._consume_time_banner()`, the `DREAM_DIGEST_PATH`
> Valve field, and (audited as the real model-facing surface, see note below)
> the rendered `[DREAM]` banner line itself.

## Scope note, read first

The lse-docstring-optimizer skill is calibrated for **tool function
docstrings the model reads to decide how to call an LSE tool** (the
`execute_command`/`write_file`/`sudo_delegation_block` class — see the
skill's own "internal-data functions are N/A for STOP PROTOCOL" carve-out).
None of the three Python-level artifacts Prompt 3.5 added are that:

- `_dream_banner()` and `_consume_time_banner()` are **private** methods
  (leading underscore) — never exposed to the model as a callable tool,
  never appear in its tool schema. Their docstrings are maintainer-facing.
- `DREAM_DIGEST_PATH` is an OpenWebUI **Valve** — admin-facing config UI
  text, not part of the model's context window.

The audit below therefore scores all three Python docstrings mostly **N/A**
per the skill's own proportionality rule, and — because the skill's real
purpose is catching *model*-compliance gaps — additionally audits the one
artifact from this feature that the model actually reads at runtime: the
rendered `[DREAM] digest=... | pending-gate=N | read <path> for details`
line itself, injected into `search_kb`'s first return of the session. That
second audit surfaces a real, non-hypothetical finding (below).

---

## Audit 1 — `Tools._dream_banner()` docstring

| Dimension | Score | Notes |
|---|---|---|
| 1. Section headers | N/A | Short, single-purpose (13 lines, one behavioral rule: "degrade to \"\" rather than raise"). Proportionality rule: don't add headers to fill the table. |
| 2. Compliance language | PASS | "degrades to \"\" rather than raising" is unambiguous; matches the actual code (try/except, `return ""`). |
| 3. GOOD/BAD examples | N/A | No model-facing ambiguity to disambiguate — this is an internal helper, not a tool the model chooses how to call. |
| 4. Stop protocol | N/A | Internal-data function (returns a string consumed by another Python method, not a user-facing delegation block). |
| 5. Failure prohibitions | PASS | Explicitly enumerates every failure mode it must swallow: "Missing valve, missing/unreadable file, or a digest whose header we can't parse." |
| 6. Output format | PASS | `line[: self._DREAM_DIGEST_MAX_CHARS]` — the 200-char cap is both stated in the docstring's sibling constant name and enforced in code one line later; no drift risk. |
| 7. Trigger gate | N/A | Not model-invoked; called unconditionally from `_consume_time_banner()`. |
| 8. Verification | N/A | Read-only, no write. |

**Verdict: well-formed for its actual audience.** No changes recommended.

---

## Audit 2 — `Tools._consume_time_banner()` (TRAUM addition)

| Dimension | Score | Notes |
|---|---|---|
| 1. Section headers | N/A | 5-line addition to an existing method's docstring, one behavioral rule ("also appends... on this same first-call gate"). |
| 2. Compliance language | PASS | Declarative, matches code exactly. |
| 3. GOOD/BAD examples | N/A | No ambiguity — one gate, one append. |
| 4. Stop protocol | N/A | Internal. |
| 5. Failure prohibitions | WARN | States what it does ("also appends... on this same first-call gate") but never explicitly prohibits the failure mode a future editor is most likely to introduce: adding a SEPARATE once-per-session gate for `[DREAM]` instead of reusing `_time_banner_emitted`. A second gate would silently duplicate or desync the two banners on a later edit. |
| 6. Output format | PASS | `banner + "\n\n"` — exact, matches the pre-existing `[TIME]`-only return shape one line above it. |
| 7. Trigger gate | PASS | "Return the `[TIME]` banner exactly once per session" is an explicit, testable trigger — confirmed by `TestChronosTimeBanner.test_consume_is_once_per_session` and the new `TestDreamBanner.test_appended_to_time_banner_on_first_search_kb_only` (Prompt 3.9). |
| 8. Verification | N/A | Read-only. |

**Fix applied (docstring-only, matches the skill's "explicit prohibition" pattern from dimension 5):** add one sentence naming the failure mode a future edit is most likely to introduce.

```python
def _consume_time_banner(self) -> str:
    """Return the [TIME] banner exactly once per session (server-side
    enforcement — compliance must not depend on the model reading
    docstrings). TRAUM Thread 3 (v0.4.0-a): also appends the [DREAM]
    banner (Prompt 3.5) on this same first-call gate — one server-side
    injection point covers both time-anchoring and dream-digest
    awareness before the session's first real search_kb result.
    Do NOT add a second, separate once-per-session flag for [DREAM] —
    reusing _time_banner_emitted is what guarantees the two banners can
    never desync (one firing without the other)."""
```

*(Applied to `tools/goethe.py`'s `_consume_time_banner()` docstring in this
pass — verbatim as shown above, confirmed present at `tools/goethe.py:3546`.
This is docstring-only: no behavioral change, no format risk, so it was safe
to land immediately rather than deferring — see "Disposition" below, which
covers only the *behavioral* Audit 4 finding that was deliberately NOT
implemented as a code change this pass.)*

---

## Audit 3 — `DREAM_DIGEST_PATH` Valve description

| Dimension | Score | Notes |
|---|---|---|
| 1–8 | N/A (all) | Admin-facing config UI text, not model context. The skill's rubric doesn't map here at all — no finding to make. |

**Verdict:** out of scope for this skill; no change.

---

## Audit 4 — the rendered `[DREAM]` banner line (the real model-facing surface)

`[DREAM] digest=<date> | pending-gate=<N> | read <path> for details`,
injected ahead of `search_kb`'s first result each session (via
`_consume_time_banner()`).

| Dimension | Score | Notes |
|---|---|---|
| 1. Section headers | N/A | One line by design (200-char hard cap, Prompt 3.5). |
| 2. Compliance language | **FAIL** | Purely informational — states THAT a digest and pending items exist, never says what the model should DO about it. Zero directive language of any kind. |
| 3. GOOD/BAD examples | N/A | Too short a surface for examples; the missing directive (dimension 2) is the actual gap, not an ambiguous existing one. |
| 4. Stop protocol | N/A | Not a delegation block the user must act on. |
| 5. Failure prohibitions | **FAIL** | No prohibition against the model treating `pending-gate=N` (N>0) as an invitation to go read the digest file and act on it unprompted — e.g. summarizing or "helpfully" suggesting the operator approve pending proposals. DESIGN.md §2 invariant 2 ("dreams propose; gates apply... only after a human confirms") is a *system* invariant enforced in `dream_apply.py`'s confirm-gate, but nothing tells the MODEL not to short-circuit that human review by narrating/pushing on it unasked. |
| 6. Output format | PASS | Exact, quoted format (`f"[DREAM] digest={...} | pending-gate={...} | read {path} for details"`), hard-capped at 200 chars — both stated and enforced. |
| 7. Trigger gate | **FAIL** | No stated condition for when the model should mention this to the user, read the digest file, or stay silent. Same failure class as the LSE history table's "Trigger gate (too broad)" row (`get_context_status` called on turn 1) — here the risk is the *reverse* direction: an under-specified trigger inviting proactive, unrequested action on a human-gated system. |
| 8. Verification | N/A | Read-only banner, no write. |

**Critical findings:**
- **[FAIL] Compliance language / Failure prohibitions:** the banner surfaces a pending-review count with no accompanying instruction, in a system whose own core invariant (DESIGN.md §2) is that dream proposals are human-gated. The gap is exactly the LSE eval history's "passive language → model treats rule as advisory" pattern, just in a more subtle form: there's no rule stated at all for the model to be passive *about*.
- **[FAIL] Trigger gate:** nothing tells the model whether "mention pending-gate=3 to the user" is expected, optional, or forbidden. Left as-is, behavior is model-dependent and untested.

## Disposition — why no *behavioral* code was changed in this pass

The fix for Audit 4's findings is a **behavioral instruction**, and this
codebase's own architecture is explicit that behavioral instructions live
in the system prompt (`prompts/node4090-v*.md`, merged from
`prompts/learned-rules.md`), never in `goethe.py` — the exact separation
Prompt 3.6 built `append_learned_rule()` to enforce ("NEVER direct edits to
the canonical node4090 prompt"; plan §3.6). Adding a directive to the
banner *line itself* was considered and rejected: the banner is already
within a few characters of its 200-char hard cap in real digests (the
Prompt 3.9 test fixture's un-capped line was 283 chars before truncation),
so appending a behavioral clause there risks silently truncating the
`read <path> for details` pointer instead.

The Audit 2 fix (a one-sentence docstring prohibition, no behavior change,
no format risk) is the one exception: it WAS applied directly to
`tools/goethe.py` in this pass, since a maintainer-facing docstring edit
carries none of the format/truncation risk that blocked Audit 4's fix, and
doesn't touch anything Prompt 3.9's new `TestDreamBanner` suite asserts on
(that suite pins the rendered banner string and cap, not this method's
docstring text).

**Recommendation for a future prompt (not this one):** propose a
`prompt-rule` via the dream `insights` pass itself — e.g. "Never
proactively read or act on the [DREAM] digest file; only discuss it if the
operator asks" — landing in `prompts/learned-rules.md`'s `## Pending`
section through the existing, human-gated `append_learned_rule` path
(Prompt 3.6), for the operator to merge into the next `node4090` version
bump. This is the mechanism this exact class of finding was built for.
