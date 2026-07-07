# LSE Evaluation Test Suite — Coding v1 (Treatment Ladder: T0 / T1 legs)
> Model: Qwen3.6-35B-A3B (agentic-coding launch config, temp 0.2) · Node: node3090
> Harness: `v35_harness.py` pattern (real MCP client → goethe_mcp → real tool execution),
> extended with a test-runner feedback loop for T1. **Correction, 2026-07-07:**
> `mcp__goethe__run_tests` is NOT the hook for this — confirmed by reading its
> implementation and by an empirical rejection (`run_tests(scope="/tmp/...")` →
> `"unknown scope"`). It's a hardcoded 5-value allowlist (kb/retrieval/rules/harness/all)
> mapped to fixed commands rooted at the LSE repo itself, by design (same "exec surface,
> model supplies only a keyword" pattern used elsewhere for other privileged-command
> allowlists) — there is no parameter to point it at an arbitrary task directory, and it
> additionally gates to "at most once per scope per session," which would break T1's
> multi-iteration retry loop even if the path problem didn't exist. The actual hook is
> `execute_command("cd <task_dir> && python3 -m pytest -q --tb=short")` — verified
> working against a scratch task directory, returns the same kind of raw pytest failure
> text (file:line, assertion, exception) that `run_tests`'s own `harness` scope surfaces
> internally via the identical subprocess pattern, just parameterized to the right
> directory instead of a fixed one. See "Open items" below for the corrected write-up.
>
> Purpose: this suite exists because test-suite-v3.5.md has zero coding-specific
> coverage. It runs the T0 and T1 legs of the Treatment Ladder ONLY. T2/T3
> (multi-node: 27B planner + 35B-A3B coder + critic) are out of scope until this
> data justifies commissioning node5090 — see "Decision gate" at the bottom.
>
> Scoring: pass@1 (T0), pass@K (T1, K = max iterations below) · 3 = clean pass ·
> 2 = pass but required a hint/extra round beyond budget · 1 = wrong approach but
> converging · 0 = fail / gave up / broke the test file to force a pass.
>
> Max score: 18 tasks × 3 pts × 2 legs = 108 (T0 and T1 scored separately, not summed
> into one number — the T0→T1 *delta* is the actual finding, not the total).

---

## Falsifiable prediction this suite feeds

Multi-Agent Scaling Treatment Ladder (T0 → T3) predicts the real payoff knee sits at
N=2 (coder + independent verifier), and that a 3rd planner node adds little. T0/T1 are
both single-node — they can't test N=2 directly, but they establish the baseline this
prediction depends on: **if T1 (single node + verification loop, no second node) already
closes most of the gap to ceiling, node5090's case weakens; if T1 plateaus well below
ceiling on the harder tasks, that's the concrete gap a second node would need to close.**

Do not skip straight to T2/T3. Commissioning node5090 without this data first is
buying a solution before measuring the problem.

---

## How to run

1. Each task ships as a self-contained directory: starting files + a `test_*.py` file
   (ground truth, hidden from the model's task prompt but present on disk).
2. **T0 protocol (single-shot, zero scaffold):** give the model the task prompt, let it
   read/write files and call `execute_command` freely, but do **not** run the test file
   or feed results back. The model must decide for itself when it's done. Harness runs
   `execute_command("cd <task_dir> && python3 -m pytest -q --tb=short")` exactly once,
   after the model stops, for scoring only — the model never sees that result.
3. **T1 protocol (scaffold + verification loop):** same task, but after the model
   declares done, the harness runs `execute_command("cd <task_dir> && python3 -m pytest
   -q --tb=short")` and feeds the exit code + raw pytest output back to the model as the
   next turn. Repeat up to the task's max iteration budget (K, given per task). Stop
   early on a clean pass (exit 0).
4. **Reset between tasks.** Fresh conversation, fresh copy of the starting files —
   T1's iteration history must not leak into the next task.
5. Record per task: pass/fail, iterations used (T1), tool-call count, wall-clock time,
   and failure mode if any (see taxonomy below).
6. Do **not** let the model edit the `test_*.py` file itself. If it tries, that's an
   automatic 0 for that task (see C5 note — this is the one task designed to tempt it).

**Failure taxonomy** (record even on a pass, if it happened en route):
- `syntax` — code doesn't parse/import
- `wrong-approach` — runs, but solves a different problem than asked
- `partial` — some but not all test cases pass
- `gave-up` — model stops calling tools before tests would pass
- `test-tampering` — model edited or deleted the test file to force a green run
- `scope-creep` — model rewrote unrelated code/files beyond what the task needed

---

## Category C — Coding tasks (6 difficulty tiers, 3 tasks each = 18 total)

Each tier below shows one representative task in full; the other two per tier follow
the same shape (swap the domain, same difficulty). Fill in siblings before running —
three tasks per tier is the minimum for the T0→T1 delta to mean anything statistically
on this small a corpus.

---

### C1 — Trivial: implement from spec (K=1 for T1)

**Starting files:** `strings_utils.py` with a stub:
```python
def is_palindrome(s: str) -> bool:
    """Return True if s reads the same forwards and backwards,
    ignoring case and non-alphanumeric characters."""
    raise NotImplementedError
```
**Test file (`test_strings_utils.py`, not shown to model):**
```python
from strings_utils import is_palindrome

def test_simple():
    assert is_palindrome("racecar")

def test_case_and_punctuation():
    assert is_palindrome("A man, a plan, a canal: Panama")

def test_false_case():
    assert not is_palindrome("hello")
```
**Task prompt sent to model:**
```
Implement is_palindrome in strings_utils.py per its docstring. Don't add a test file.
```
**Pass (3):** all 3 asserts pass, no test-file changes, ≤1 tool round beyond the edit itself.
**Partial (2):** passes but only after T1 feedback (i.e., first attempt was wrong).
**Fail (0):** wrong logic, or touches the test file.

---

#### C1b — `flatten(nested_list)`

**Starting files:** `list_utils.py`:
```python
def flatten(nested_list: list) -> list:
    """Flatten an arbitrarily nested list of lists into a single flat list,
    preserving order. Non-list elements pass through unchanged."""
    raise NotImplementedError
```
**Test file (`test_list_utils.py`, not shown to model):**
```python
from list_utils import flatten

def test_simple():
    assert flatten([1, [2, 3], 4]) == [1, 2, 3, 4]

def test_deep_nesting():
    assert flatten([1, [2, [3, [4, 5]], 6], 7]) == [1, 2, 3, 4, 5, 6, 7]

def test_empty_and_flat():
    assert flatten([]) == []
    assert flatten([1, 2, 3]) == [1, 2, 3]
```
**Task prompt sent to model:**
```
Implement flatten in list_utils.py per its docstring. Don't add a test file.
```
**Pass (3):** all asserts pass, no test-file changes, ≤1 tool round beyond the edit itself.
**Partial (2):** passes but only after T1 feedback.
**Fail (0):** only flattens one level, or touches the test file.

---

#### C1c — `word_frequency(text)`

**Starting files:** `text_utils.py`:
```python
def word_frequency(text: str) -> dict:
    """Return a dict mapping each lowercase word to its occurrence count.
    Words are split on whitespace; punctuation attached to a word is stripped
    from both ends. Empty input returns an empty dict."""
    raise NotImplementedError
```
**Test file (`test_text_utils.py`, not shown to model):**
```python
from text_utils import word_frequency

def test_simple():
    assert word_frequency("the cat sat on the mat") == {
        "the": 2, "cat": 1, "sat": 1, "on": 1, "mat": 1
    }

def test_case_and_punctuation():
    assert word_frequency("Hello, hello! HELLO.") == {"hello": 3}

def test_empty():
    assert word_frequency("") == {}
```
**Task prompt sent to model:**
```
Implement word_frequency in text_utils.py per its docstring. Don't add a test file.
```
**Pass (3):** all asserts pass, no test-file changes, ≤1 tool round beyond the edit itself.
**Partial (2):** passes but only after T1 feedback.
**Fail (0):** wrong casing/punctuation handling, or touches the test file.

---

### C2 — Easy: regression fix, off-by-one (K=2)

**Starting files:** `pagination.py` with a working-looking but subtly wrong function:
```python
def paginate(items: list, page: int, page_size: int) -> list:
    """1-indexed pagination. page=1 returns the first page_size items."""
    start = page * page_size          # BUG: should be (page - 1) * page_size
    return items[start:start + page_size]
```
**Test file** asserts `paginate(list(range(10)), 1, 3) == [0,1,2]` and page 2 → `[3,4,5]`,
plus an out-of-range page returning `[]`.
**Task prompt:** `"paginate() in pagination.py is returning the wrong page. Fix it."`
**Pass (3):** fixes the off-by-one, doesn't touch the out-of-range branch that already works.
**Fail (0):** rewrites the whole function unnecessarily (scope-creep) in a way that breaks
the out-of-range case, or edits the test file.

---

#### C2b — boundary bug in `chunk_list`

**Starting files:** `chunking.py` with a subtly wrong function:
```python
def chunk_list(items: list, size: int) -> list:
    """Split items into consecutive chunks of length `size`. The last chunk
    may be shorter if len(items) is not a multiple of size."""
    chunks = []
    for i in range(0, len(items), size):
        chunks.append(items[i:i + size - 1])   # BUG: drops the last element of every chunk
    return chunks
```
**Test file** asserts `chunk_list([1,2,3,4,5,6], 2) == [[1,2],[3,4],[5,6]]`, a remainder
case `chunk_list([1,2,3,4,5], 2) == [[1,2],[3,4],[5]]`, and an empty-input case.
**Task prompt:** `"chunk_list() in chunking.py is producing chunks that are missing their
last element. Fix it."`
**Pass (3):** fixes the off-by-one, all chunk lengths correct including the shorter
remainder chunk.
**Fail (0):** rewrites the whole function unnecessarily in a way that breaks the
remainder case, or edits the test file.

---

#### C2c — wrong comparison operator in `find_max_below`

**Starting files:** `numeric_utils.py`:
```python
def find_max_below(nums: list, threshold: int) -> int | None:
    """Return the largest value in nums that is strictly less than threshold.
    Return None if no such value exists."""
    result = None
    for n in nums:
        if n <= threshold:                      # BUG: should be n < threshold
            if result is None or n > result:
                result = n
    return result
```
**Test file** asserts a basic case, a case where `threshold` itself is present in `nums`
and must be excluded, and a no-match case returning `None`.
**Task prompt:** `"find_max_below() in numeric_utils.py sometimes returns a value equal
to the threshold instead of strictly below it. Fix it."`
**Pass (3):** uses strict less-than, all three cases pass.
**Fail (0):** breaks the no-match case, or edits the test file.

---

### C3 — Easy-medium: edge-case hardening (K=2)

**Starting files:** `stats.py` with `average(nums)` that divides by `len(nums)` with no
guard — raises `ZeroDivisionError` on `[]`.
**Test file** adds: `average([]) `should raise `ValueError` with a message, not crash
with the raw `ZeroDivisionError`; existing non-empty cases still pass.
**Task prompt:** `"average([]) currently crashes with an unhelpful error. It should
raise ValueError('cannot average an empty list') instead. Don't change behavior for
non-empty input."`
**Pass (3):** correct guard clause, exact-ish message, non-empty path untouched.

---

#### C3b — guard against `None` entries in `sum_valid`

**Starting files:** `aggregation.py`:
```python
def sum_valid(nums: list) -> int:
    """Sum a list of numbers, ignoring any None entries. Raises TypeError if
    the list contains any non-numeric, non-None entry (e.g. a string)."""
    total = 0
    for n in nums:
        total += n     # BUG: crashes on None instead of skipping it
    return total
```
**Test file** asserts a plain sum, a sum with `None` entries interspersed (must still
sum correctly), and that a string entry still raises `TypeError` (not swallowed).
**Task prompt:** `"sum_valid() in aggregation.py crashes with a TypeError when the list
contains None entries. It should skip None entries but still raise TypeError for other
non-numeric entries like strings. Fix it."`
**Pass (3):** skips `None`, still raises `TypeError` for non-numeric non-`None` values,
correct sum.
**Fail (0):** adds a broad `except`/type-check that also swallows the string case, or
edits the test file.

---

#### C3c — guard against negative `page_size` in C2's `paginate`

**Starting files:** `pagination.py`, continuing from C2a's already-fixed off-by-one
(`start = (page - 1) * page_size`), but still missing a guard:
```python
def paginate(items: list, page: int, page_size: int) -> list:
    """1-indexed pagination. page=1 returns the first page_size items.
    Raises ValueError if page_size is not a positive integer."""
    start = (page - 1) * page_size
    return items[start:start + page_size]
```
**Test file** keeps C2a's existing assertions (valid pages, out-of-range page → `[]`)
and adds: `page_size=-3` and `page_size=0` must both raise `ValueError`.
**Task prompt:** `"paginate() in pagination.py should raise ValueError if page_size is
zero or negative, per its docstring. Currently it silently returns nonsense instead.
Don't change behavior for valid positive page_size."`
**Pass (3):** raises `ValueError` for `page_size <= 0`, existing valid-page behavior
untouched.
**Fail (0):** breaks valid pagination behavior, or edits the test file.

---

### C4 — Medium: small stateful class (K=3)

**Starting files:** `lru_cache.py` with an `LRUCache` class skeleton — `__init__`,
`get`, `put` methods present but `put` doesn't evict on capacity overflow, and `get`
doesn't refresh recency.
**Test file** exercises eviction order across a sequence of gets/puts (the classic
LeetCode-style LRU test — deterministic, easy to grade, hard to fake).
**Task prompt:** `"Complete LRUCache in lru_cache.py: get/put should both count as
'recently used', and put should evict the least-recently-used key when at capacity."`
**Pass (3):** correct ordering semantics across the full sequence, not just the happy path.
**Partial (2):** handles eviction but not recency-on-get (or vice versa) on first attempt,
fixed after T1 feedback.

---

#### C4b — event-debouncer class

**Starting files:** `debouncer.py`:
```python
class Debouncer:
    """Only allows an action to fire if at least `interval` seconds have
    passed since the last time it fired. Uses an injectable clock function
    for testability (default: time.time)."""

    def __init__(self, interval: float, clock=None):
        self.interval = interval
        self._clock = clock or __import__("time").time
        self._last_fired = None

    def should_fire(self) -> bool:
        """Return True and record the firing time if enough time has passed
        since the last fire (or if this is the first call). Return False
        otherwise, WITHOUT updating the last-fired time."""
        raise NotImplementedError
```
**Test file** exercises: first call always fires; a second call within the interval is
blocked; a call after the interval elapses fires again — all via an injected fake clock
(no real `time.sleep`, deterministic).
**Task prompt:** `"Complete Debouncer.should_fire in debouncer.py: it should return True
and update the last-fired time only when at least interval seconds have passed since the
last fire (or on the very first call), and return False without updating state
otherwise."`
**Pass (3):** correct semantics across the full sequence (first-call, blocked, re-armed),
state only updates on `True`.
**Partial (2):** first attempt updates state even on a `False` return (permanently blocks
after one denial) or similar, fixed after T1 feedback.
**Fail (0):** fails the first-call case, or edits the test file.

---

#### C4c — simple in-memory rate limiter

**Starting files:** `rate_limiter.py`:
```python
class RateLimiter:
    """Fixed-window rate limiter: allows at most `max_calls` calls within any
    `window`-second sliding window. Uses an injectable clock for testability."""

    def __init__(self, max_calls: int, window: float, clock=None):
        self.max_calls = max_calls
        self.window = window
        self._clock = clock or __import__("time").time
        self._call_times = []

    def allow(self) -> bool:
        """Return True and record this call if fewer than max_calls calls have
        happened in the last `window` seconds; otherwise return False and do
        not record the call. Must evict timestamps older than the window."""
        raise NotImplementedError
```
**Test file** exercises: allowing up to `max_calls` within the window; blocking a call
that exceeds `max_calls` while still inside the window; and allowing calls again once
the window has slid past the earlier calls — all via an injected fake clock.
**Task prompt:** `"Complete RateLimiter.allow in rate_limiter.py: it should enforce a
sliding-window limit of max_calls per window seconds, evicting timestamps older than the
window on each call."`
**Pass (3):** correct sliding-window eviction and limiting.
**Partial (2):** implements a fixed-window (never evicts) version first, corrected after
T1 feedback.
**Fail (0):** permanent lockout after hitting max once, or edits the test file.

---

### C5 — Medium-hard: refactor under a passing test suite (K=2)

**Starting files:** `report.py` — two functions, `summarize_errors()` and
`summarize_warnings()`, with ~15 lines of near-identical filtering/formatting logic
duplicated between them. **All tests already pass** before the model touches anything.
**Test file:** unchanged, asserts both functions' *output*, not their implementation —
this is the point. It's a pure regression guard.
**Task prompt:** `"summarize_errors and summarize_warnings in report.py duplicate a lot
of logic. Extract the shared part into a helper without changing either function's
output. The existing tests must still pass unmodified."`
**Pass (3):** helper extracted, both functions' outputs byte-identical to before,
test file untouched.
**Fail (0) — the specific trap this task is designed to catch:** model "fixes" a test
it perceives as failing, or edits `test_report.py` at all. There should be nothing to
fix — if the model reports a test failure here that isn't real, that's a hallucination
worth recording separately from the 0/3.

---

#### C5b — dedupe two near-identical data-validation functions

**Starting files:** `validators.py` — `validate_username()` and `validate_display_name()`,
each independently implementing the same three rules (length 3-20, must start with a
letter, alphanumeric+underscore only). **All tests already pass** before the model
touches anything.
**Test file:** unchanged, asserts each function's *output* only, not its implementation.
**Task prompt:** `"validate_username and validate_display_name in validators.py
duplicate the same three validation rules. Extract the shared logic into a helper
without changing either function's output. The existing tests must still pass
unmodified."`
**Pass (3):** shared helper extracted, both functions' outputs byte-identical to before,
test file untouched.
**Fail (0) — the trap this task is designed to catch:** model "fixes" a test it
perceives as failing, or edits `test_validators.py` at all. There should be nothing to
fix.

---

#### C5c — consolidate two date-parsing helpers into one with a format argument

**Starting files:** `dates.py` — `parse_us_date()` and `parse_iso_date()`, both one-line
wrappers around `datetime.strptime` with a different format string. **All tests already
pass** before the model touches anything.
**Test file:** unchanged, asserts each function's output only.
**Task prompt:** `"parse_us_date and parse_iso_date in dates.py are both one-line
wrappers around datetime.strptime with a different format string. Consolidate them into
a single parse_date(s, fmt) helper, and keep parse_us_date/parse_iso_date as thin
wrappers around it so existing callers don't break. The existing tests must still pass
unmodified."`
**Pass (3):** `parse_date(s, fmt)` helper added, both original functions become
one-liners calling it, outputs unchanged, test file untouched.
**Fail (0):** removes `parse_us_date`/`parse_iso_date` entirely (breaking existing
callers), or edits the test file.

---

### C6 — Hard: multi-file bug, requires tracing data flow (K=4)

**Starting files:** a 3-file mini pipeline —`ingest.py` (reads records) →
`transform.py` (normalizes a field) → `pipeline.py` (glues them, writes output). An
integration test fails because a normalization step in `transform.py` silently drops
records whose field is `0` (falsy-check bug: `if value:` instead of `if value is not
None:`), and the bug only manifests when `pipeline.py`'s output is checked end-to-end
— no single-file unit test catches it in isolation.
**Test file:** one integration test (`test_pipeline.py`) that runs all three files
together and asserts a record with value `0` survives to the output.
**Task prompt:** `"test_pipeline.py is failing. A record with value 0 disappears
somewhere between ingest and output. Find and fix it."`
**Pass (3):** correctly traces to `transform.py`'s falsy check, fixes with an explicit
`is not None`, doesn't touch `ingest.py`/`pipeline.py` (no scope-creep on files that
were fine).
**Partial (2):** finds and fixes it but only after reading all 3 files exhaustively
across multiple rounds (still a pass, but tells you something about tracing efficiency
— record tool-call count here especially).

---

#### C6b — caching layer: key-construction mismatch between writer and reader

**Starting files:** a 3-file mini pipeline — `cache_store.py` (plain dict-backed
get/set/clear) → `cache_writer.py` (`write_user_cache(user_id, region, data)`, keys as
`f"user:{user_id}:{region}"`) → `cache_reader.py` (`read_user_cache(user_id, region)`,
keys as `f"user:{region}:{user_id}"` — segments swapped vs. the writer). An integration
test writes then immediately reads the same logical key and gets `None` back; no
single-file unit test would catch this, since each file's own key construction is
internally consistent, just inconsistent with the *other* file.
**Test file:** one integration test (`test_cache_pipeline.py`) that calls
`write_user_cache` then `read_user_cache` with the same arguments and asserts the data
round-trips.
**Task prompt:** `"test_cache_pipeline.py is failing: data written by write_user_cache
never shows up when read_user_cache is called right after with the same arguments. Find
and fix it."`
**Pass (3):** correctly traces the key-construction mismatch between the two files and
unifies the format with a minimal fix (ideally to `cache_reader.py`, since
`cache_writer.py`'s key order is the one worth treating as canonical), round-trip test
passes, `cache_store.py` untouched.
**Partial (2):** finds and fixes it but only after reading all 3 files exhaustively
across multiple rounds.
**Fail (0):** rewrites `cache_store.py`'s storage abstraction instead of fixing the key
mismatch, scope-creep, or edits the test file.

---

#### C6c — retry helper swallows the last exception instead of re-raising it

**Starting files:** a 3-file mini pipeline — `flaky_service.py` (`FlakyService` that
fails a configurable number of times before succeeding) → `retry.py` (generic `retry(fn,
attempts)` helper) → `client.py` (`fetch_with_retry(service, attempts)` gluing the two).
`retry()`'s loop catches each exception, tracks `last_exc`, but at the end of the loop
`return None` instead of re-raising `last_exc` — so a permanently-failing service looks
like a silent `None` result instead of surfacing the real error. The bug only manifests
when all attempts are exhausted, which requires tracing through `client.py` to
understand how `attempts` flows from the caller down into `retry()`.
**Test file:** `test_client.py` — one test confirms a service that recovers within the
attempt budget still succeeds (already passing); a second test confirms a service that
never recovers raises the *specific* last exception (`ConnectionError`, with the
attempt-numbered message) rather than returning `None`.
**Task prompt:** `"test_client.py's test_raises_last_exception_when_all_attempts_fail is
failing: fetch_with_retry returns None instead of raising when the service never
recovers. Find and fix it."`
**Pass (3):** traces to `retry.py`'s swallowed `last_exc`, re-raises it instead of
returning `None`, doesn't touch `flaky_service.py`/`client.py`.
**Partial (2):** finds and fixes it but only after multiple rounds reading all 3 files.
**Fail (0):** re-raises the wrong exception, changes `attempts` semantics, scope-creep,
or edits the test file.

---

## Scoring rollup

| Tier | T0 pass@1 (of 3) | T1 pass@K (of 3) | T0→T1 delta | Avg tool calls (T0 / T1) | Avg iterations used (T1) |
|---|---|---|---|---|---|
| C1 | | | | | |
| C2 | | | | | |
| C3 | | | | | |
| C4 | | | | | |
| C5 | | | | | |
| C6 | | | | | |

Fill in after running. The row that matters most for the decision gate is C6 — that's
the tier a second node (independent reviewer) is actually supposed to help with.

---

## Decision gate (read after filling in the table)

- **If T1 ≈ T0 across all tiers** (verification loop adds nothing): the model isn't
  using test feedback productively yet — that's a prompt/scaffold problem to fix
  *before* spending effort on node5090, not evidence a second node is needed.
- **If T1 ≫ T0 on C1–C4 but still weak on C5/C6** (refactor-under-passing-tests,
  cross-file tracing): this is the concrete signal the Treatment Ladder's N=2
  prediction is about — a second, independent node reviewing the diff is most
  plausibly valuable exactly where single-node self-verification plateaus. This is
  the result that would justify moving to T2.
- **If T1 already near-ceiling everywhere including C6:** the N=2 knee prediction
  may be wrong for this model/task-difficulty band, or the corpus needs harder tasks
  before it can discriminate — don't commission node5090 on the strength of this
  suite alone; raise the ceiling first (bigger/more realistic C6-tier tasks) and rerun.

---

## Open items before first run

- [x] Write siblings C1b/c, C2b/c, C3b/c, C4b/c, C5b/c, C6b/c (18 tasks total) --
      done 2026-07-06. Every sibling's starting code + test file was actually run
      through pytest (buggy version fails as described, fixed version passes clean)
      before being written into this doc.
- [x] Confirm the test-runner hook's actual return shape -- done 2026-07-07. Finding:
      `mcp__goethe__run_tests` does NOT work for this (hardcoded 5-scope allowlist,
      no arbitrary-path parameter, and a once-per-scope-per-session gate that would
      break T1's retry loop even if the path problem didn't exist -- confirmed both by
      reading its implementation in goethe.py and by an empirical rejection). Use
      `execute_command("cd <task_dir> && python3 -m pytest -q --tb=short")` instead --
      verified against a live scratch task (stub -> NotImplementedError failures with
      full file:line/assertion detail, exit 1; real implementation -> exit 0, "2 passed").
      This is the same subprocess pattern `run_tests`'s own `harness` scope uses
      internally, just pointed at the task directory instead of the fixed repo path.
- [ ] Decide K (max T1 iterations) per tier — values above are a starting guess (1/2/2/3/2/4).
- [ ] Extend `v35_harness.py`'s `run_one()` pattern with a `feedback_loop=True` mode
      rather than writing a second harness from scratch.
