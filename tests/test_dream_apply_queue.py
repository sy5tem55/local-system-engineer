"""
Unit tests for the TRAUM-AUTO morning queue (Thread 4, Prompt 4.4 —
tools/dream_apply.py's `--queue` mode): gather_queue, group_queue_by_type,
render_queue, cmd_queue, and the parse_args/main() wiring that lets --queue
run without ever touching goethe.py/Tools/ES.

Covers, entirely offline (no live Elasticsearch, no Tools instantiation,
synthetic tmp_path-scoped day-dirs only):
  - gather_queue() returns pending proposals oldest-day-dir-first, tagged
    with date/age_days.
  - proposals whose day-dir is older than --stale-days are auto-expired:
    excluded from `pending`, appended (once) to that day-dir's expired.jsonl
    with a reason, and NOT re-expired (duplicated) on a second call.
  - proposals already resolved via applied.jsonl or rejected.jsonl are
    excluded from both pending and expired (never touched at all).
  - a malformed-but-regex-matching day-dir name (e.g. 2026-13-40, which
    dream_digest._DAY_DIR_RE accepts but date.fromisoformat() cannot parse)
    fails closed: age_days=0, never auto-expired.
  - group_queue_by_type buckets preserve each type's oldest-first order,
    and bucket order itself follows "oldest overall pending item's type
    leads".
  - render_queue produces a readable per-type listing including date, age,
    call, pair_id (when present), and a truncated `why`.
  - cmd_queue: empty-queue message on stderr when nothing is pending;
    listing on stdout + summary/expiry notices on stderr otherwise.
  - main(): --queue works with NO --proposals given (no longer required);
    without --queue, a missing --proposals raises SystemExit; --queue never
    calls load_tools_class (proven by monkeypatching it to explode).

Run: python3 -m pytest tests/test_dream_apply_queue.py -q
"""

import json
import sys
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import dream_apply as da  # noqa: E402
import dream_digest as dd  # noqa: E402


# --- fixtures / helpers ------------------------------------------------------

def _write_jsonl(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wt", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def _proposal(ptype="kb-fact", call="index_to_kb", why="why text", **extra) -> dict:
    p = {"type": ptype, "call": call, "args": {"doc_id": "d1"}, "why": why}
    p.update(extra)
    return p


TODAY = date(2026, 7, 12)  # matches the session's own current date


# --- gather_queue: basic pending / ordering ----------------------------------

class TestGatherQueueBasic:
    def test_empty_dream_dir_returns_nothing(self, tmp_path):
        pending, expired = da.gather_queue(str(tmp_path / "nope"), TODAY)
        assert pending == []
        assert expired == []

    def test_day_dir_with_no_proposals_file_is_skipped(self, tmp_path):
        (tmp_path / "2026-07-10").mkdir()
        pending, expired = da.gather_queue(str(tmp_path), TODAY)
        assert pending == expired == []

    def test_single_fresh_day_dir_all_pending(self, tmp_path):
        _write_jsonl(tmp_path / "2026-07-10" / "proposals.jsonl",
                     [_proposal(why="a"), _proposal(why="b")])
        pending, expired = da.gather_queue(str(tmp_path), TODAY, stale_days=14)
        assert expired == []
        assert len(pending) == 2
        assert all(e["date"] == "2026-07-10" and e["age_days"] == 2 for e in pending)

    def test_pending_is_oldest_day_dir_first(self, tmp_path):
        _write_jsonl(tmp_path / "2026-07-01" / "proposals.jsonl", [_proposal(why="oldest")])
        _write_jsonl(tmp_path / "2026-07-10" / "proposals.jsonl", [_proposal(why="newest")])
        pending, _ = da.gather_queue(str(tmp_path), TODAY, stale_days=14)
        assert [e["date"] for e in pending] == ["2026-07-01", "2026-07-10"]


# --- gather_queue: staleness auto-expiry -------------------------------------

class TestGatherQueueExpiry:
    def test_proposal_older_than_stale_days_is_expired_not_pending(self, tmp_path):
        _write_jsonl(tmp_path / "2026-06-10" / "proposals.jsonl", [_proposal(why="ancient")])
        pending, expired = da.gather_queue(str(tmp_path), TODAY, stale_days=14)
        assert pending == []
        assert len(expired) == 1
        assert expired[0]["age_days"] == 32
        assert "stale" in expired[0]["reason"]
        assert "re-dream will re-propose" in expired[0]["reason"]

    def test_proposal_exactly_at_boundary_is_not_expired(self, tmp_path):
        # 2026-06-28 -> age_days == 14 exactly; rule is "> stale_days", so
        # exactly-14 must still be pending (14 is the last SAFE day).
        _write_jsonl(tmp_path / "2026-06-28" / "proposals.jsonl", [_proposal(why="boundary")])
        pending, expired = da.gather_queue(str(tmp_path), TODAY, stale_days=14)
        assert expired == []
        assert len(pending) == 1
        assert pending[0]["age_days"] == 14

    def test_proposal_one_day_past_boundary_is_expired(self, tmp_path):
        _write_jsonl(tmp_path / "2026-06-27" / "proposals.jsonl", [_proposal(why="past boundary")])
        pending, expired = da.gather_queue(str(tmp_path), TODAY, stale_days=14)
        assert pending == []
        assert len(expired) == 1
        assert expired[0]["age_days"] == 15

    def test_expiry_writes_expired_jsonl_with_full_fields(self, tmp_path):
        _write_jsonl(tmp_path / "2026-06-01" / "proposals.jsonl", [_proposal(why="x")])
        da.gather_queue(str(tmp_path), TODAY, stale_days=14)
        rows = dd.load_jsonl(str(tmp_path / "2026-06-01" / "expired.jsonl"))
        assert len(rows) == 1
        row = rows[0]
        assert row["proposal"]["why"] == "x"
        assert "expired_at" in row and row["expired_at"]
        assert row["age_days"] == 41

    def test_expiry_is_unconditional_not_gated_by_a_dry_run_flag(self, tmp_path):
        """gather_queue has no dry_run parameter at all -- expiry always
        writes, same precedent as rejected.jsonl in the single-run flow."""
        import inspect
        sig = inspect.signature(da.gather_queue)
        assert "dry_run" not in sig.parameters

    def test_second_call_does_not_re_expire_or_duplicate(self, tmp_path):
        _write_jsonl(tmp_path / "2026-06-01" / "proposals.jsonl", [_proposal(why="x")])
        pending1, expired1 = da.gather_queue(str(tmp_path), TODAY, stale_days=14)
        assert len(expired1) == 1
        pending2, expired2 = da.gather_queue(str(tmp_path), TODAY, stale_days=14)
        assert pending2 == []
        assert expired2 == [], "already-expired proposal must not be re-expired on a later call"
        rows = dd.load_jsonl(str(tmp_path / "2026-06-01" / "expired.jsonl"))
        assert len(rows) == 1, "expired.jsonl must not accumulate duplicate entries"


# --- gather_queue: resolved-state exclusion (applied/rejected/expired) ------

class TestGatherQueueResolvedExclusion:
    def test_already_applied_proposal_excluded_from_pending(self, tmp_path):
        p = _proposal(why="already handled")
        _write_jsonl(tmp_path / "2026-07-10" / "proposals.jsonl", [p])
        _write_jsonl(tmp_path / "2026-07-10" / "applied.jsonl",
                     [{"proposal": p, "result": "ok", "applied_at": "x", "dry_run": False}])
        pending, expired = da.gather_queue(str(tmp_path), TODAY, stale_days=14)
        assert pending == expired == []

    def test_already_rejected_proposal_excluded_from_pending(self, tmp_path):
        p = _proposal(why="declined")
        _write_jsonl(tmp_path / "2026-07-10" / "proposals.jsonl", [p])
        _write_jsonl(tmp_path / "2026-07-10" / "rejected.jsonl",
                     [{"proposal": p, "reason": "human declined", "rejected_at": "x"}])
        pending, expired = da.gather_queue(str(tmp_path), TODAY, stale_days=14)
        assert pending == expired == []

    def test_resolved_proposal_older_than_stale_days_is_not_re_expired(self, tmp_path):
        """An old, already-applied proposal must not show up in `expired`
        either -- it's resolved, not stale-and-unreviewed."""
        p = _proposal(why="old but applied")
        _write_jsonl(tmp_path / "2026-06-01" / "proposals.jsonl", [p])
        _write_jsonl(tmp_path / "2026-06-01" / "applied.jsonl",
                     [{"proposal": p, "result": "ok", "applied_at": "x", "dry_run": False}])
        pending, expired = da.gather_queue(str(tmp_path), TODAY, stale_days=14)
        assert pending == []
        assert expired == []

    def test_one_resolved_one_pending_in_same_day_dir(self, tmp_path):
        p_applied = _proposal(why="handled", call="index_to_kb")
        p_pending = _proposal(why="still open", call="skill_record", ptype="skill-candidate")
        _write_jsonl(tmp_path / "2026-07-10" / "proposals.jsonl", [p_applied, p_pending])
        _write_jsonl(tmp_path / "2026-07-10" / "applied.jsonl",
                     [{"proposal": p_applied, "result": "ok", "applied_at": "x", "dry_run": False}])
        pending, _ = da.gather_queue(str(tmp_path), TODAY, stale_days=14)
        assert len(pending) == 1
        assert pending[0]["proposal"]["why"] == "still open"


# --- gather_queue: defensive malformed day-dir name -------------------------

class TestGatherQueueMalformedDayDir:
    def test_regex_matching_but_unparseable_date_fails_closed_never_expires(self, tmp_path):
        # dd._DAY_DIR_RE is r"^\d{4}-\d{2}-\d{2}$" -- matches month=13, day=40
        # even though date.fromisoformat() cannot parse it.
        _write_jsonl(tmp_path / "2026-13-40" / "proposals.jsonl", [_proposal(why="weird dir")])
        pending, expired = da.gather_queue(str(tmp_path), TODAY, stale_days=14)
        assert expired == [], "a day-dir whose date can't be parsed must never auto-expire"
        assert len(pending) == 1
        assert pending[0]["age_days"] == 0


# --- group_queue_by_type ------------------------------------------------------

class TestGroupQueueByType:
    def test_groups_preserve_oldest_first_order_within_type(self, tmp_path):
        pending = [
            {"date": "2026-07-01", "age_days": 11, "proposal": _proposal(ptype="kb-fact", why="a")},
            {"date": "2026-07-05", "age_days": 7, "proposal": _proposal(ptype="kb-fact", why="b")},
        ]
        buckets = da.group_queue_by_type(pending)
        assert list(buckets.keys()) == ["kb-fact"]
        assert [e["proposal"]["why"] for e in buckets["kb-fact"]] == ["a", "b"]

    def test_bucket_order_follows_oldest_overall_item_first(self, tmp_path):
        # dedup's oldest item (day 1) precedes kb-fact's oldest item (day 2)
        # in the input stream -> dedup bucket must lead.
        pending = [
            {"date": "2026-07-01", "age_days": 11, "proposal": _proposal(ptype="dedup", why="d1")},
            {"date": "2026-07-02", "age_days": 10, "proposal": _proposal(ptype="kb-fact", why="k1")},
            {"date": "2026-07-03", "age_days": 9, "proposal": _proposal(ptype="dedup", why="d2")},
        ]
        buckets = da.group_queue_by_type(pending)
        assert list(buckets.keys()) == ["dedup", "kb-fact"]
        assert len(buckets["dedup"]) == 2
        assert len(buckets["kb-fact"]) == 1

    def test_missing_type_field_buckets_as_unknown(self, tmp_path):
        pending = [{"date": "2026-07-01", "age_days": 1, "proposal": {"call": "x", "why": "y"}}]
        buckets = da.group_queue_by_type(pending)
        assert list(buckets.keys()) == ["unknown"]


# --- render_queue --------------------------------------------------------------

class TestRenderQueue:
    def test_renders_date_age_call_and_why(self):
        pending = [{"date": "2026-07-01", "age_days": 11,
                    "proposal": _proposal(ptype="kb-fact", call="index_to_kb", why="a short reason")}]
        buckets = da.group_queue_by_type(pending)
        text = da.render_queue(buckets, TODAY)
        assert "kb-fact" in text
        assert "2026-07-01" in text
        assert "11d old" in text
        assert "index_to_kb" in text
        assert "a short reason" in text

    def test_renders_pair_id_when_present(self):
        pending = [{"date": "2026-07-01", "age_days": 5,
                    "proposal": _proposal(ptype="dedup", call="mentor_correct", why="x",
                                           pair_id="pair-42")}]
        buckets = da.group_queue_by_type(pending)
        text = da.render_queue(buckets, TODAY)
        assert "pair_id=pair-42" in text

    def test_long_why_is_truncated(self):
        long_why = "x" * 300
        pending = [{"date": "2026-07-01", "age_days": 5,
                    "proposal": _proposal(why=long_why)}]
        buckets = da.group_queue_by_type(pending)
        text = da.render_queue(buckets, TODAY)
        assert long_why not in text
        assert "…" in text

    def test_header_includes_total_count_and_date(self):
        pending = [{"date": "2026-07-01", "age_days": 5, "proposal": _proposal(why="a")}]
        buckets = da.group_queue_by_type(pending)
        text = da.render_queue(buckets, TODAY)
        first_line = text.splitlines()[0]
        assert "1 pending" in first_line
        assert TODAY.isoformat() in first_line


# --- cmd_queue (stdout/stderr integration) --------------------------------

class _Args:
    def __init__(self, dream_dir, stale_days=14):
        self.dream_dir = dream_dir
        self.stale_days = stale_days


class TestCmdQueue:
    def test_empty_queue_message_on_stderr(self, tmp_path, capsys):
        da.cmd_queue(_Args(str(tmp_path)))
        out = capsys.readouterr()
        assert out.out == ""
        assert "queue is empty" in out.err

    def test_pending_listing_goes_to_stdout(self, tmp_path, capsys):
        _write_jsonl(tmp_path / "2026-07-10" / "proposals.jsonl", [_proposal(why="visible")])
        da.cmd_queue(_Args(str(tmp_path)))
        out = capsys.readouterr()
        assert "visible" in out.out
        assert "pending across" in out.err

    def test_expiry_notice_reported_on_stderr(self, tmp_path, capsys):
        _write_jsonl(tmp_path / "2026-06-01" / "proposals.jsonl", [_proposal(why="old")])
        da.cmd_queue(_Args(str(tmp_path)))
        out = capsys.readouterr()
        assert "auto-expired" in out.err
        assert "2026-06-01" in out.err


# --- main()/parse_args wiring ----------------------------------------------

class TestMainQueueWiring:
    def test_queue_flag_does_not_require_proposals(self):
        args = da.parse_args(["--queue"])
        assert args.queue is True
        assert args.proposals is None

    def test_stale_days_default_matches_constant(self):
        args = da.parse_args(["--queue"])
        assert args.stale_days == da.DREAM_QUEUE_STALE_DAYS == 14

    def test_missing_proposals_without_queue_raises(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit):
            da.main([])

    def test_queue_mode_never_loads_tools_class(self, tmp_path, monkeypatch):
        """The whole point of --queue being read-only w.r.t. ES: main() must
        route to cmd_queue() and return WITHOUT ever calling
        load_tools_class -- proven by making it explode if called."""
        def boom(*a, **k):
            raise AssertionError("load_tools_class must not be called in --queue mode")
        monkeypatch.setattr(da, "load_tools_class", boom)
        da.main(["--queue", "--dream-dir", str(tmp_path)])  # must not raise

    def test_queue_mode_end_to_end_through_main(self, tmp_path, monkeypatch, capsys):
        _write_jsonl(tmp_path / "2026-07-11" / "proposals.jsonl",
                     [_proposal(why="through main()")])
        monkeypatch.setattr(da, "load_tools_class",
                             lambda *a, **k: (_ for _ in ()).throw(AssertionError("no Tools")))
        da.main(["--queue", "--dream-dir", str(tmp_path)])
        out = capsys.readouterr()
        assert "through main()" in out.out
