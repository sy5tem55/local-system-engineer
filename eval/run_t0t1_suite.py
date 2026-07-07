#!/usr/bin/env python3
"""
Batch runner for the T0/T1 coding eval suite
(eval/test-suite-coding-t0t1-v1.md). Runs on node3090 (localhost model +
localhost goethe_mcp). Materializes all 18 tasks into fresh scratch
directories, runs the T0 leg (single-shot, no feedback) then the T1 leg
(verification loop up to the tier's K) for each, and writes results to
JSON incrementally so the run is resumable if interrupted.
"""
import json
import os
import shutil
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from t1_feedback_loop import run_t0_task, run_t1_task
from t1_mcp_harness import make_propose_fn

SCRATCH_ROOT = "/tmp/lse/t0t1-eval"
LLAMA_BASE_URL = "http://localhost:8080/v1"
MCP_URL = "http://localhost:9700/mcp"
MCP_TOKEN = "266ce5843de4fd3ad04dffefae8f17db"

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS_PATH = os.path.join(HERE, "t0t1_suite_results.json")
LOG_PATH = os.path.join(HERE, "t0t1_suite_run.log")


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")


# ---------------------------------------------------------------------------
# Task corpus (mirrors eval/test-suite-coding-t0t1-v1.md exactly; the 8 tasks
# that doc only describes in prose -- C3a, C4a, C5a, C5b, C5c, C6a, C6b, C6c
# -- are constructed here to match those descriptions precisely and were
# pytest-verified locally before this run: buggy/duplicated starting state
# reproduces the described symptom, hand-written fix passes clean.)
# ---------------------------------------------------------------------------

TASKS = []

# --- C1: trivial implement-from-spec, K=1 ----------------------------------

TASKS.append({
    "id": "C1a", "tier": "C1", "k": 1,
    "prompt": "Implement is_palindrome in strings_utils.py per its docstring. Don't add a test file.",
    "files": {"strings_utils.py": '''def is_palindrome(s: str) -> bool:
    """Return True if s reads the same forwards and backwards,
    ignoring case and non-alphanumeric characters."""
    raise NotImplementedError
'''},
    "test_files": {"test_strings_utils.py": '''from strings_utils import is_palindrome

def test_simple():
    assert is_palindrome("racecar")

def test_case_and_punctuation():
    assert is_palindrome("A man, a plan, a canal: Panama")

def test_false_case():
    assert not is_palindrome("hello")
'''},
})

TASKS.append({
    "id": "C1b", "tier": "C1", "k": 1,
    "prompt": "Implement flatten in list_utils.py per its docstring. Don't add a test file.",
    "files": {"list_utils.py": '''def flatten(nested_list: list) -> list:
    """Flatten an arbitrarily nested list of lists into a single flat list,
    preserving order. Non-list elements pass through unchanged."""
    raise NotImplementedError
'''},
    "test_files": {"test_list_utils.py": '''from list_utils import flatten

def test_simple():
    assert flatten([1, [2, 3], 4]) == [1, 2, 3, 4]

def test_deep_nesting():
    assert flatten([1, [2, [3, [4, 5]], 6], 7]) == [1, 2, 3, 4, 5, 6, 7]

def test_empty_and_flat():
    assert flatten([]) == []
    assert flatten([1, 2, 3]) == [1, 2, 3]
'''},
})

TASKS.append({
    "id": "C1c", "tier": "C1", "k": 1,
    "prompt": "Implement word_frequency in text_utils.py per its docstring. Don't add a test file.",
    "files": {"text_utils.py": '''def word_frequency(text: str) -> dict:
    """Return a dict mapping each lowercase word to its occurrence count.
    Words are split on whitespace; punctuation attached to a word is stripped
    from both ends. Empty input returns an empty dict."""
    raise NotImplementedError
'''},
    "test_files": {"test_text_utils.py": '''from text_utils import word_frequency

def test_simple():
    assert word_frequency("the cat sat on the mat") == {
        "the": 2, "cat": 1, "sat": 1, "on": 1, "mat": 1
    }

def test_case_and_punctuation():
    assert word_frequency("Hello, hello! HELLO.") == {"hello": 3}

def test_empty():
    assert word_frequency("") == {}
'''},
})

# --- C2: off-by-one regression fix, K=2 -------------------------------------

TASKS.append({
    "id": "C2a", "tier": "C2", "k": 2,
    "prompt": "paginate() in pagination.py is returning the wrong page. Fix it.",
    "files": {"pagination.py": '''def paginate(items: list, page: int, page_size: int) -> list:
    """1-indexed pagination. page=1 returns the first page_size items."""
    start = page * page_size          # BUG: should be (page - 1) * page_size
    return items[start:start + page_size]
'''},
    "test_files": {"test_pagination.py": '''from pagination import paginate

def test_first_page():
    assert paginate(list(range(10)), 1, 3) == [0, 1, 2]

def test_second_page():
    assert paginate(list(range(10)), 2, 3) == [3, 4, 5]

def test_out_of_range_page():
    assert paginate(list(range(10)), 100, 3) == []
'''},
})

TASKS.append({
    "id": "C2b", "tier": "C2", "k": 2,
    "prompt": "chunk_list() in chunking.py is producing chunks that are missing their last element. Fix it.",
    "files": {"chunking.py": '''def chunk_list(items: list, size: int) -> list:
    """Split items into consecutive chunks of length `size`. The last chunk
    may be shorter if len(items) is not a multiple of size."""
    chunks = []
    for i in range(0, len(items), size):
        chunks.append(items[i:i + size - 1])  # BUG: drops the last element of every chunk
    return chunks
'''},
    "test_files": {"test_chunking.py": '''from chunking import chunk_list

def test_even_chunks():
    assert chunk_list([1, 2, 3, 4, 5, 6], 2) == [[1, 2], [3, 4], [5, 6]]

def test_remainder_chunk():
    assert chunk_list([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]

def test_empty():
    assert chunk_list([], 2) == []
'''},
})

TASKS.append({
    "id": "C2c", "tier": "C2", "k": 2,
    "prompt": "find_max_below() in numeric_utils.py sometimes returns a value equal to the threshold instead of strictly below it. Fix it.",
    "files": {"numeric_utils.py": '''def find_max_below(nums: list, threshold: int):
    """Return the largest value in nums that is strictly less than threshold.
    Return None if no such value exists."""
    result = None
    for n in nums:
        if n <= threshold:                     # BUG: should be n < threshold
            if result is None or n > result:
                result = n
    return result
'''},
    "test_files": {"test_numeric_utils.py": '''from numeric_utils import find_max_below

def test_basic():
    assert find_max_below([1, 5, 9, 3], 6) == 5

def test_threshold_present_excluded():
    assert find_max_below([1, 5, 6, 3], 6) == 5

def test_no_match():
    assert find_max_below([10, 20, 30], 5) is None
'''},
})

# --- C3: edge-case hardening, K=2 ------------------------------------------

TASKS.append({
    "id": "C3a", "tier": "C3", "k": 2,
    "prompt": "average([]) currently crashes with an unhelpful error. It should raise ValueError('cannot average an empty list') instead. Don't change behavior for non-empty input.",
    "files": {"stats.py": '''def average(nums: list) -> float:
    """Return the arithmetic mean of nums."""
    return sum(nums) / len(nums)
'''},
    "test_files": {"test_stats.py": '''import pytest
from stats import average

def test_simple():
    assert average([1, 2, 3]) == 2
    assert average([10]) == 10

def test_empty_raises_value_error():
    with pytest.raises(ValueError):
        average([])
'''},
})

TASKS.append({
    "id": "C3b", "tier": "C3", "k": 2,
    "prompt": "sum_valid() in aggregation.py crashes with a TypeError when the list contains None entries. It should skip None entries but still raise TypeError for other non-numeric entries like strings. Fix it.",
    "files": {"aggregation.py": '''def sum_valid(nums: list) -> int:
    """Sum a list of numbers, ignoring any None entries. Raises TypeError if
    the list contains any non-numeric, non-None entry (e.g. a string)."""
    total = 0
    for n in nums:
        total += n     # BUG: crashes on None instead of skipping it
    return total
'''},
    "test_files": {"test_aggregation.py": '''import pytest
from aggregation import sum_valid

def test_plain_sum():
    assert sum_valid([1, 2, 3]) == 6

def test_skips_none():
    assert sum_valid([1, None, 2, None, 3]) == 6

def test_raises_on_string():
    with pytest.raises(TypeError):
        sum_valid([1, "oops", 2])
'''},
})

TASKS.append({
    "id": "C3c", "tier": "C3", "k": 2,
    "prompt": "paginate() in pagination.py should raise ValueError if page_size is zero or negative, per its docstring. Currently it silently returns nonsense instead. Don't change behavior for valid positive page_size.",
    "files": {"pagination.py": '''def paginate(items: list, page: int, page_size: int) -> list:
    """1-indexed pagination. page=1 returns the first page_size items.
    Raises ValueError if page_size is not a positive integer."""
    start = (page - 1) * page_size
    return items[start:start + page_size]
'''},
    "test_files": {"test_pagination.py": '''import pytest
from pagination import paginate

def test_first_page():
    assert paginate(list(range(10)), 1, 3) == [0, 1, 2]

def test_second_page():
    assert paginate(list(range(10)), 2, 3) == [3, 4, 5]

def test_out_of_range_page():
    assert paginate(list(range(10)), 100, 3) == []

def test_negative_page_size_raises():
    with pytest.raises(ValueError):
        paginate(list(range(10)), 1, -3)

def test_zero_page_size_raises():
    with pytest.raises(ValueError):
        paginate(list(range(10)), 1, 0)
'''},
})

# --- C4: small stateful class, K=3 ------------------------------------------

TASKS.append({
    "id": "C4a", "tier": "C4", "k": 3,
    "prompt": "Complete LRUCache in lru_cache.py: get/put should both count as 'recently used', and put should evict the least-recently-used key when at capacity.",
    "files": {"lru_cache.py": '''class LRUCache:
    """Least-recently-used cache with a fixed capacity."""

    def __init__(self, capacity: int):
        self.capacity = capacity
        self._data = {}
        self._order = []  # oldest at [0], most-recently-used at [-1]

    def get(self, key):
        """Return the value for key, or None if not present. A successful
        get counts as a use and should refresh the key's recency."""
        if key not in self._data:
            return None
        return self._data[key]  # BUG: doesn't refresh recency

    def put(self, key, value) -> None:
        """Insert or update key/value. A put counts as a use. Evict the
        least-recently-used key if inserting a new key would exceed
        capacity."""
        self._data[key] = value  # BUG: doesn't track recency or evict
        if key not in self._order:
            self._order.append(key)
'''},
    "test_files": {"test_lru_cache.py": '''from lru_cache import LRUCache

def test_eviction_order():
    c = LRUCache(2)
    c.put(1, 1)
    c.put(2, 2)
    assert c.get(1) == 1       # 1 becomes MRU
    c.put(3, 3)                # capacity hit: evicts 2 (LRU)
    assert c.get(2) is None
    c.put(4, 4)                # evicts 1 (LRU, since 3 is more recent)
    assert c.get(1) is None
    assert c.get(3) == 3
    assert c.get(4) == 4

def test_update_existing_key_refreshes_recency():
    c = LRUCache(2)
    c.put(1, 1)
    c.put(2, 2)
    c.put(1, 10)   # update existing key, 1 becomes MRU
    c.put(3, 3)    # evicts 2, not 1
    assert c.get(2) is None
    assert c.get(1) == 10
    assert c.get(3) == 3
'''},
})

TASKS.append({
    "id": "C4b", "tier": "C4", "k": 3,
    "prompt": "Complete Debouncer.should_fire in debouncer.py: it should return True and update the last-fired time only when at least interval seconds have passed since the last fire (or on the very first call), and return False without updating state otherwise.",
    "files": {"debouncer.py": '''class Debouncer:
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
'''},
    "test_files": {"test_debouncer.py": '''from debouncer import Debouncer

def make_clock(times):
    it = iter(times)
    return lambda: next(it)

def test_first_call_always_fires():
    d = Debouncer(interval=10, clock=make_clock([0]))
    assert d.should_fire() is True

def test_second_call_within_interval_blocked():
    d = Debouncer(interval=10, clock=make_clock([0, 5]))
    assert d.should_fire() is True
    assert d.should_fire() is False

def test_call_after_interval_fires_again():
    d = Debouncer(interval=10, clock=make_clock([0, 5, 11]))
    assert d.should_fire() is True
    assert d.should_fire() is False
    assert d.should_fire() is True
'''},
})

TASKS.append({
    "id": "C4c", "tier": "C4", "k": 3,
    "prompt": "Complete RateLimiter.allow in rate_limiter.py: it should enforce a sliding-window limit of max_calls per window seconds, evicting timestamps older than the window on each call.",
    "files": {"rate_limiter.py": '''class RateLimiter:
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
'''},
    "test_files": {"test_rate_limiter.py": '''from rate_limiter import RateLimiter

def make_clock(times):
    it = iter(times)
    return lambda: next(it)

def test_allows_up_to_max():
    r = RateLimiter(max_calls=2, window=10, clock=make_clock([0, 1]))
    assert r.allow() is True
    assert r.allow() is True

def test_blocks_over_max_within_window():
    r = RateLimiter(max_calls=2, window=10, clock=make_clock([0, 1, 2]))
    assert r.allow() is True
    assert r.allow() is True
    assert r.allow() is False

def test_allows_again_after_window_slides():
    r = RateLimiter(max_calls=2, window=10, clock=make_clock([0, 1, 12]))
    assert r.allow() is True
    assert r.allow() is True
    assert r.allow() is True
'''},
})

# --- C5: refactor under a passing test suite, K=2 ---------------------------

TASKS.append({
    "id": "C5a", "tier": "C5", "k": 2,
    "prompt": "summarize_errors and summarize_warnings in report.py duplicate a lot of logic. Extract the shared part into a helper without changing either function's output. The existing tests must still pass unmodified.",
    "files": {"report.py": '''def summarize_errors(records: list) -> str:
    """Return a formatted summary of error-level records."""
    filtered = [r for r in records if r.get("level") == "error"]
    lines = [f"[{r['level'].upper()}] {r['code']}: {r['message']}" for r in filtered]
    if not filtered:
        return "0 error(s)."
    return f"{len(filtered)} error(s):\\n" + "\\n".join(lines)


def summarize_warnings(records: list) -> str:
    """Return a formatted summary of warning-level records."""
    filtered = [r for r in records if r.get("level") == "warning"]
    lines = [f"[{r['level'].upper()}] {r['code']}: {r['message']}" for r in filtered]
    if not filtered:
        return "0 warning(s)."
    return f"{len(filtered)} warning(s):\\n" + "\\n".join(lines)
'''},
    "test_files": {"test_report.py": '''from report import summarize_errors, summarize_warnings

RECORDS = [
    {"level": "error", "code": "E1", "message": "boom"},
    {"level": "warning", "code": "W1", "message": "careful"},
    {"level": "error", "code": "E2", "message": "bang"},
    {"level": "info", "code": "I1", "message": "fyi"},
]

def test_summarize_errors():
    assert summarize_errors(RECORDS) == "2 error(s):\\n[ERROR] E1: boom\\n[ERROR] E2: bang"

def test_summarize_warnings():
    assert summarize_warnings(RECORDS) == "1 warning(s):\\n[WARNING] W1: careful"

def test_empty():
    assert summarize_errors([]) == "0 error(s)."
    assert summarize_warnings([]) == "0 warning(s)."
'''},
})

TASKS.append({
    "id": "C5b", "tier": "C5", "k": 2,
    "prompt": "validate_username and validate_display_name in validators.py duplicate the same three validation rules. Extract the shared logic into a helper without changing either function's output. The existing tests must still pass unmodified.",
    "files": {"validators.py": '''def validate_username(s: str) -> bool:
    """Return True if s is 3-20 chars, starts with a letter, and contains
    only letters, digits, and underscores."""
    if not (3 <= len(s) <= 20):
        return False
    if not s[0].isalpha():
        return False
    return all(c.isalnum() or c == "_" for c in s)


def validate_display_name(s: str) -> bool:
    """Return True if s is 3-20 chars, starts with a letter, and contains
    only letters, digits, and underscores."""
    if not (3 <= len(s) <= 20):
        return False
    if not s[0].isalpha():
        return False
    return all(c.isalnum() or c == "_" for c in s)
'''},
    "test_files": {"test_validators.py": '''from validators import validate_username, validate_display_name

def test_valid():
    assert validate_username("abc_123")
    assert validate_display_name("abc_123")

def test_too_short():
    assert not validate_username("ab")
    assert not validate_display_name("ab")

def test_starts_with_digit():
    assert not validate_username("1abc")
    assert not validate_display_name("1abc")

def test_bad_char():
    assert not validate_username("abc-123")
    assert not validate_display_name("abc-123")
'''},
})

TASKS.append({
    "id": "C5c", "tier": "C5", "k": 2,
    "prompt": "parse_us_date and parse_iso_date in dates.py are both one-line wrappers around datetime.strptime with a different format string. Consolidate them into a single parse_date(s, fmt) helper, and keep parse_us_date/parse_iso_date as thin wrappers around it so existing callers don't break. The existing tests must still pass unmodified.",
    "files": {"dates.py": '''from datetime import datetime


def parse_us_date(s: str) -> datetime:
    """Parse a US-format date string 'MM/DD/YYYY'."""
    return datetime.strptime(s, "%m/%d/%Y")


def parse_iso_date(s: str) -> datetime:
    """Parse an ISO-format date string 'YYYY-MM-DD'."""
    return datetime.strptime(s, "%Y-%m-%d")
'''},
    "test_files": {"test_dates.py": '''from datetime import datetime
from dates import parse_us_date, parse_iso_date

def test_parse_us_date():
    assert parse_us_date("07/08/2026") == datetime(2026, 7, 8)

def test_parse_iso_date():
    assert parse_iso_date("2026-07-08") == datetime(2026, 7, 8)
'''},
})

# --- C6: multi-file bug, requires tracing data flow, K=4 --------------------

TASKS.append({
    "id": "C6a", "tier": "C6", "k": 4,
    "prompt": "test_pipeline.py is failing. A record with value 0 disappears somewhere between ingest and output. Find and fix it.",
    "files": {
        "ingest.py": '''def read_records(raw: list) -> list:
    """Pass through a list of raw record dicts unchanged."""
    return list(raw)
''',
        "transform.py": '''def normalize(records: list) -> list:
    """Normalize records: drop any record whose 'value' field is missing
    (None). Records with a present value (including 0) must survive."""
    out = []
    for r in records:
        value = r.get("value")
        if value:   # BUG: falsy check drops value == 0; should be `is not None`
            out.append(r)
    return out
''',
        "pipeline.py": '''from ingest import read_records
from transform import normalize


def run_pipeline(raw: list) -> list:
    """Read then normalize records, returning the final output list."""
    records = read_records(raw)
    return normalize(records)
''',
    },
    "test_files": {"test_pipeline.py": '''from pipeline import run_pipeline

def test_zero_value_survives():
    raw = [
        {"id": 1, "value": 0},
        {"id": 2, "value": 5},
        {"id": 3, "value": None},
    ]
    out = run_pipeline(raw)
    ids = [r["id"] for r in out]
    assert 1 in ids
    assert 2 in ids
    assert 3 not in ids
'''},
})

TASKS.append({
    "id": "C6b", "tier": "C6", "k": 4,
    "prompt": "test_cache_pipeline.py is failing: data written by write_user_cache never shows up when read_user_cache is called right after with the same arguments. Find and fix it.",
    "files": {
        "cache_store.py": '''_STORE = {}


def cache_set(key: str, value) -> None:
    _STORE[key] = value


def cache_get(key: str):
    return _STORE.get(key)


def cache_clear() -> None:
    _STORE.clear()
''',
        "cache_writer.py": '''from cache_store import cache_set


def write_user_cache(user_id: str, region: str, data) -> None:
    """Write data to the cache under a key combining user_id and region."""
    key = f"user:{user_id}:{region}"
    cache_set(key, data)
''',
        "cache_reader.py": '''from cache_store import cache_get


def read_user_cache(user_id: str, region: str):
    """Read data from the cache under a key combining user_id and region."""
    key = f"user:{region}:{user_id}"   # BUG: segments swapped vs. the writer
    return cache_get(key)
''',
    },
    "test_files": {"test_cache_pipeline.py": '''from cache_store import cache_clear
from cache_writer import write_user_cache
from cache_reader import read_user_cache

def test_roundtrip():
    cache_clear()
    write_user_cache("u1", "us-east", {"name": "Joe"})
    assert read_user_cache("u1", "us-east") == {"name": "Joe"}
'''},
})

TASKS.append({
    "id": "C6c", "tier": "C6", "k": 4,
    "prompt": "test_client.py's test_raises_last_exception_when_all_attempts_fail is failing: fetch_with_retry returns None instead of raising the underlying exception when every retry attempt fails. Find and fix it.",
    "files": {
        "flaky_service.py": '''class FlakyService:
    """A service that fails `fail_count` times before succeeding."""

    def __init__(self, fail_count: int):
        self.fail_count = fail_count
        self.calls = 0

    def call(self):
        self.calls += 1
        if self.calls <= self.fail_count:
            raise ConnectionError(f"attempt {self.calls} failed")
        return "ok"
''',
        "retry.py": '''def retry(fn, attempts: int):
    """Call fn() up to `attempts` times, returning its result on the first
    success. If every attempt fails, re-raise the last exception."""
    last_exc = None
    for _ in range(attempts):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
    return None  # BUG: should re-raise last_exc instead of swallowing it
''',
        "client.py": '''from retry import retry


def fetch_with_retry(service, attempts: int):
    """Fetch from service, retrying up to `attempts` times."""
    return retry(lambda: service.call(), attempts)
''',
    },
    "test_files": {"test_client.py": '''import pytest
from flaky_service import FlakyService
from client import fetch_with_retry

def test_recovers_within_budget():
    service = FlakyService(fail_count=2)
    result = fetch_with_retry(service, attempts=3)
    assert result == "ok"

def test_raises_last_exception_when_all_attempts_fail():
    service = FlakyService(fail_count=5)
    with pytest.raises(ConnectionError, match="attempt 3 failed"):
        fetch_with_retry(service, attempts=3)
'''},
})

assert len(TASKS) == 18, f"expected 18 tasks, got {len(TASKS)}"
assert len({t['id'] for t in TASKS}) == 18, "duplicate task ids"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def materialize(task, leg):
    task_dir = os.path.join(SCRATCH_ROOT, f"{task['id']}-{leg}")
    if os.path.exists(task_dir):
        shutil.rmtree(task_dir)
    os.makedirs(task_dir)
    for fname, content in task["files"].items():
        with open(os.path.join(task_dir, fname), "w") as f:
            f.write(content)
    for fname, content in task["test_files"].items():
        with open(os.path.join(task_dir, fname), "w") as f:
            f.write(content)
    return task_dir


def run_task(task, propose_fn, results):
    tid, tier, k = task["id"], task["tier"], task["k"]

    log(f"=== {tid} (tier {tier}, K={k}) : T0 leg ===")
    t0_dir = materialize(task, "t0")
    t0_start = time.time()
    t0_outcome = None
    try:
        t0_outcome = run_t0_task(t0_dir, task["prompt"], propose_fn)
        log(f"{tid} T0: passed={t0_outcome.passed} elapsed={time.time()-t0_start:.1f}s")
    except Exception as e:
        log(f"{tid} T0: EXCEPTION {e}\n{traceback.format_exc()}")
    t0_elapsed = time.time() - t0_start

    log(f"=== {tid} (tier {tier}, K={k}) : T1 leg ===")
    t1_dir = materialize(task, "t1")
    t1_start = time.time()
    t1_outcome = None
    try:
        t1_outcome = run_t1_task(t1_dir, task["prompt"], propose_fn, max_iterations=k)
        log(f"{tid} T1: passed={t1_outcome.passed} iterations_used={t1_outcome.iterations_used} elapsed={time.time()-t1_start:.1f}s")
    except Exception as e:
        log(f"{tid} T1: EXCEPTION {e}\n{traceback.format_exc()}")
    t1_elapsed = time.time() - t1_start

    result = {
        "id": tid, "tier": tier, "k": k,
        "t0": {
            "passed": t0_outcome.passed if t0_outcome else None,
            "elapsed_s": round(t0_elapsed, 1),
            "final_test_output": t0_outcome.test_output if t0_outcome else None,
            "error": None if t0_outcome else "exception, see log",
        },
        "t1": {
            "passed": t1_outcome.passed if t1_outcome else None,
            "iterations_used": t1_outcome.iterations_used if t1_outcome else None,
            "hit_budget": t1_outcome.hit_budget if t1_outcome else None,
            "elapsed_s": round(t1_elapsed, 1),
            "final_test_output": t1_outcome.final_test_output if t1_outcome else None,
            "error": None if t1_outcome else "exception, see log",
        },
    }
    results.append(result)
    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)
    return result


def main():
    os.makedirs(SCRATCH_ROOT, exist_ok=True)
    results = []
    if os.path.exists(RESULTS_PATH):
        with open(RESULTS_PATH) as f:
            results = json.load(f)
    done_ids = {r["id"] for r in results}
    log(f"Starting suite run. {len(done_ids)}/18 tasks already done, skipping those.")

    log("Building shared propose_fn (lists tools once, reused across all tasks)...")
    propose_fn = make_propose_fn(LLAMA_BASE_URL, MCP_URL, MCP_TOKEN)
    log("propose_fn ready.")

    for task in TASKS:
        if task["id"] in done_ids:
            log(f"Skipping {task['id']} (already done)")
            continue
        run_task(task, propose_fn, results)

    log("Suite complete. Results written to " + RESULTS_PATH)


if __name__ == "__main__":
    main()
