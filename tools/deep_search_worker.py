#!/usr/bin/env python3
"""deep_search_worker.py — detached deep-search run worker (contract v0.3).

Spawned by the goethe_ui POST /deepSearch/topics/{id}/passes route as a
detached (setsid) process so it survives gateway restarts.

Usage:
  deep_search_worker.py <run_id> <topic_id> <question> <instructions>
      <max_steps> <max_sources> <state_dir>

Single writer for (all under <state_dir>):
  runs/<run_id>/state.json    live runner state — the UI poll target
  runs/<run_id>/trace.jsonl   append-only state_trace mirror (1 line/transition)
  runs/<run_id>/result.json   terminal: full DeepSearchResult dict
  runs/<run_id>/report.md     terminal: cited markdown report
  runs/<run_id>/extraction.json  Phase-1 stub (separate extraction call is
                               Phase 2, decision 1) — written as []
  topics/<topic_id>.json      run start: status -> researching; terminal:
                               append pass, merge sources, recompute
                               convergence, status -> done|converged
                               (ONE atomic rewrite each)

Model/tool plumbing mirrors the in-process deep_search MCP tool exactly:
_DSAdapterClient (goethe_deep_search.py) translates the core's token +
ChatML-completions calls onto the Strata chat-completions API and the
tool posts onto websearch-lb's MCP streamable-HTTP dialect.

Env (all optional, defaults in parens):
  DEEP_SEARCH_MODEL_URL      (http://node3090.home.arpa:8080)
  DEEP_SEARCH_MODEL_NAME     (qwen3.8-flash-next-unsloth-ud-iq4_xs)
  DEEP_SEARCH_SEARCH_URL     (http://127.0.0.1:9703)
  DEEP_SEARCH_READ_URL       (http://127.0.0.1:9703)
  DEEP_SEARCH_MODEL_API_KEY  (falls back to GOETHE_PLANNER_FORCE_API_KEY)
  DEEP_SEARCH_LB_TOKEN       ("")
  DEEP_SEARCH_LOG_DIR        (core audit log dir; set by the spawner)

Contract rules honoured here:
  * state.json heartbeat refreshed on every state transition AND at least
    every 10 s (background thread).
  * Readers (routes/UI) never rewrite state.json; orphan detection
    (heartbeat stale > 60 s or pid dead) is display-side only.
  * The model API key is never written to any run/topic file.
"""

import asyncio
import datetime
import json
import os
import signal
import sys
import threading
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import deep_search_core as core  # noqa: E402
from goethe_deep_search import _DSAdapterClient  # noqa: E402


def _now():
    return datetime.datetime.now(
        datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, default=str)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _env(name, default):
    value = os.environ.get(name, "")
    return value if value else default


def _state_name(x):
    """State enum -> bare name. str-Enum str() yields "State.PLANNING"
    (verified on py3.12); json.dumps yields the bare value. Normalize."""
    n = getattr(x, "name", None)
    if n:
        return str(n)
    s = str(x)
    return s.split(".", 1)[1] if "." in s else s


class RunState:
    """Owned state.json view with a lock; one writer only (this process)."""

    def __init__(self, rdir, run_id, topic_id, max_steps, limit_s):
        self.rdir = rdir
        self.path = os.path.join(rdir, "state.json")
        self.lock = threading.Lock()
        self.t0 = time.monotonic()
        self.trace = []
        self.doc = {
            "run_id": run_id, "topic_id": topic_id, "status": "QUEUED",
            "state": "PLANNING",
            "step": {"i": 0, "n": max_steps},
            "trace_tail": [],
            "budgets": {"steps_used": 0, "sources_used": 0,
                        "elapsed_s": 0, "limit_s": limit_s},
            "heartbeat_ts": _now(), "started_at": _now(),
            "pid": os.getpid(),
        }
        self._write()

    def _elapsed(self):
        return int(time.monotonic() - self.t0)

    def _write(self):
        """Caller must hold self.lock."""
        self.doc["heartbeat_ts"] = _now()
        self.doc["budgets"]["elapsed_s"] = self._elapsed()
        _atomic_write_json(self.path, self.doc)

    def set_status(self, status):
        with self.lock:
            self.doc["status"] = status
            self._write()

    def transition(self, state_name, note):
        """on_progress callback: live state + trace update (contract:
        heartbeat refresh on every transition)."""
        name = _state_name(state_name)
        entry = {"state": name,
                 "t_offset_s": round(time.monotonic() - self.t0, 3),
                 "note": str(note)[:400]}
        with self.lock:
            self.doc["state"] = name
            if name in ("SEARCHING", "READING"):
                self.doc["step"]["i"] = min(
                    self.doc["step"]["i"] + 1, self.doc["step"]["n"])
                # rev4: keep the live budget gauge in sync — the UI's
                # "N steps" previously read 0 until the terminal write.
                self.doc["budgets"]["steps_used"] = self.doc["step"]["i"]
            self.trace.append(entry)
            self.doc["trace_tail"] = self.trace[-12:]
            self._write()

    def set_terminal(self, status, state_name, steps_used, sources_used,
                     error=None):
        with self.lock:
            self.doc["status"] = status
            self.doc["state"] = str(state_name)
            self.doc["step"]["i"] = steps_used
            self.doc["budgets"]["steps_used"] = steps_used
            self.doc["budgets"]["sources_used"] = sources_used
            self.doc["trace_tail"] = self.trace[-12:]
            if error is not None:
                self.doc["error"] = error
            self._write()

    def heartbeat_loop(self, stop):
        while not stop.is_set():
            if stop.wait(10):
                break
            with self.lock:
                self._write()


def _write_trace_jsonl(rdir, state_trace):
    with open(os.path.join(rdir, "trace.jsonl"), "w", encoding="utf-8") as f:
        for entry in state_trace:
            f.write(json.dumps(entry, ensure_ascii=False, default=str))
            f.write("\n")


def _result_dict(result):
    """Mirror the mixin's return dict exactly (contract §3 result.json)."""
    return {"status": result.status, "report": result.report,
            "sources": result.sources, "plan": result.plan,
            "state_trace": result.state_trace,
            "budgets_used": result.budgets_used,
            "error": None if result.error is None else result.error}


def _touch_topic_status(state_dir, tid, status):
    """Run-start topic status flip. The worker is the single writer of
    topic files after creation (docstring contract), so the 'researching'
    flip is owned here, not in the gateway route. Best-effort: a failure
    must not abort the run — the terminal update re-asserts status."""
    ts = _now()
    tpath = os.path.join(state_dir, "topics", tid + ".json")
    try:
        dossier = _read_json(tpath)
    except (OSError, ValueError):
        return
    dossier["status"] = status
    dossier["updated_at"] = ts
    _atomic_write_json(tpath, dossier)
    try:
        index = _read_json(os.path.join(state_dir, "topics.json"))
    except (OSError, ValueError):
        return
    changed = False
    for entry in index:
        if isinstance(entry, dict) and entry.get("id") == tid:
            entry["status"] = status
            entry["updated_at"] = ts
            changed = True
    if changed:
        _atomic_write_json(os.path.join(state_dir, "topics.json"), index)


def _update_topic(state_dir, tid, run_id, question, started_at, ok,
                  report, state_trace, result_sources, error):
    """Terminal topic update: append pass, merge sources, recompute
    convergence, flip status — ONE atomic dossier rewrite + index
    refresh. Status (spec: researching | done | converged |
    handed_off | archived): 'researching' is reserved for ACTIVE runs,
    so a terminal pass never leaves the topic looking live."""
    finished_at = _now()
    tpath = os.path.join(state_dir, "topics", tid + ".json")
    dossier = _read_json(tpath)

    steps_used = sum(
        1 for e in state_trace
        if _state_name(e.get("state", "")) in ("SEARCHING", "READING"))
    fetched = sum(1 for s in result_sources if s.get("fetched"))

    pass_entry = {
        "run_id": run_id, "status": "DONE" if ok else "FAILED",
        "question": question, "started_at": started_at,
        "finished_at": finished_at,
        "steps_used": steps_used, "sources_fetched": fetched,
        "report_chars": len(report or ""),
        "error": None if ok else error,
    }
    dossier.setdefault("passes", []).append(pass_entry)

    sources = dossier.setdefault("sources", [])
    seen = {s.get("url") for s in sources if isinstance(s, dict)}
    highest = 0
    for s in sources:
        sid = str(s.get("id", "")) if isinstance(s, dict) else ""
        if sid.startswith("s-"):
            try:
                highest = max(highest, int(sid[2:]))
            except ValueError:
                pass
    for src in result_sources or []:
        url = src.get("url") if isinstance(src, dict) else None
        if not url or url in seen:
            continue
        highest += 1
        seen.add(url)
        sources.append({
            "id": "s-%03d" % highest, "url": url,
            "title": src.get("title", ""),
            "snippet": (src.get("snippet", "") or "")[:1000],
            "pass": run_id, "fetched": bool(src.get("fetched")),
            "quality_tier": "unverified", "fetched_via": "websearch-lb",
            "citation_count": 0,
        })

    budget = dossier.setdefault(
        "budget", {"steps": 0, "sources_fetched": 0, "passes": 0})
    budget["steps"] = budget.get("steps", 0) + steps_used
    budget["sources_fetched"] = (budget.get("sources_fetched", 0) + fetched)
    budget["passes"] = budget.get("passes", 0) + 1

    conv = dossier.setdefault("convergence", {
        "open_questions": 0, "contradictions": 0, "stable_passes": 0,
        "kb_covered": False, "sufficient": False})
    conv["stable_passes"] = sum(
        1 for p in dossier["passes"] if p.get("status") == "DONE")
    conv["kb_covered"] = False
    conv["sufficient"] = conv["stable_passes"] >= 2
    if conv["sufficient"]:
        topic_status = "converged"
    elif ok:
        topic_status = "done"
    else:
        # pass failed — no usable result; topic stays open for a retry
        topic_status = "researching"
    dossier["status"] = topic_status
    dossier["updated_at"] = finished_at
    _atomic_write_json(tpath, dossier)

    ipath = os.path.join(state_dir, "topics.json")
    index = _read_json(ipath)
    for entry in index:
        if isinstance(entry, dict) and entry.get("id") == tid:
            entry["status"] = topic_status
            entry["updated_at"] = finished_at
    _atomic_write_json(ipath, index)
    return steps_used, fetched


def main(argv):
    if len(argv) != 7:
        sys.stderr.write(
            "usage: deep_search_worker.py <run_id> <topic_id> <question> "
            "<instructions> <max_steps> <max_sources> <state_dir>\n")
        return 2
    run_id, topic_id, question, instructions, max_steps_s, max_sources_s, \
        state_dir = argv
    try:
        max_steps = int(max_steps_s)
        max_sources = int(max_sources_s)
    except ValueError:
        sys.stderr.write("max_steps/max_sources must be ints\n")
        return 2

    rdir = os.path.join(state_dir, "runs", run_id)
    os.makedirs(os.path.join(rdir, "worker.audit"), exist_ok=True)

    model_url = _env("DEEP_SEARCH_MODEL_URL",
                     "http://node3090.home.arpa:8080")
    model_name = _env("DEEP_SEARCH_MODEL_NAME",
                      "qwen3.8-flash-next-unsloth-ud-iq4_xs")
    search_url = _env("DEEP_SEARCH_SEARCH_URL", "http://127.0.0.1:9703")
    read_url = _env("DEEP_SEARCH_READ_URL", "http://127.0.0.1:9703")
    key = _env("DEEP_SEARCH_MODEL_API_KEY",
               _env("GOETHE_PLANNER_FORCE_API_KEY", ""))
    lb_token = _env("DEEP_SEARCH_LB_TOKEN", "")
    log_dir = os.environ.get("DEEP_SEARCH_LOG_DIR", "")

    core.configure(proxy_url=model_url, model=model_name)
    if log_dir:
        core.set_log_dir(log_dir)

    budgets = core.Budgets(maxSteps=max(1, max_steps),
                           maxSources=max(1, max_sources))
    rs = RunState(rdir, run_id, topic_id, budgets.maxSteps,
                  budgets.totalBudgetSeconds)

    def _term(signum, _frame):
        try:
            rs.set_terminal("FAILED", "FAILED",
                            rs.doc["budgets"]["steps_used"],
                            rs.doc["budgets"]["sources_used"],
                            {"class": "WorkerTerminated",
                             "message": "signal %d" % signum,
                             "state_at_failure": rs.doc.get("state")})
        finally:
            os._exit(128 + signum)

    signal.signal(signal.SIGTERM, _term)
    signal.signal(signal.SIGINT, _term)
    rs.set_status("RUNNING")
    try:
        _touch_topic_status(state_dir, topic_id, "researching")
    except Exception:
        pass  # best-effort; terminal update re-asserts topic status

    stop = threading.Event()
    hb = threading.Thread(target=rs.heartbeat_loop, args=(stop,),
                          daemon=True)
    hb.start()

    ok = False
    result = None
    error = None
    report = ""
    state_trace = []
    result_sources = []
    client = None
    try:
        if not key:
            error = {"class": "ConfigurationError",
                     "message": "DEEP_SEARCH_MODEL_API_KEY / "
                                "GOETHE_PLANNER_FORCE_API_KEY empty",
                     "state_at_failure": "PLANNING"}
        else:
            client = _DSAdapterClient(
                model_base=model_url, lb_search=search_url,
                lb_read=read_url, model_key=key, lb_token=lb_token)
            try:
                coro = core.deep_search(
                    question, instructions, budgets=budgets,
                    search_endpoint=search_url, read_endpoint=read_url,
                    on_progress=rs.transition, client=client)
                result = asyncio.run(coro)
            except Exception as exc:
                error = {"class": type(exc).__name__,
                         "message": str(exc)[:400],
                         "state_at_failure": "UNKNOWN"}
                state_trace = list(rs.trace)
    finally:
        stop.set()
        hb.join(timeout=5)
        if client is not None:
            client.close()

    # ---- terminal writes (contract §5: state.json + result.json +
    # report.md + extraction.json, then ONE atomic topic rewrite) ----
    if result is not None:
        ok = result.status == "DONE"
        report = result.report or ""
        state_trace = result.state_trace
        result_sources = result.sources
        if error is None and result.error is not None:
            error = result.error
        out = _result_dict(result)
    else:
        out = {"status": "FAILED", "report": "", "sources": [],
               "plan": [], "state_trace": state_trace,
               "budgets_used": {}, "error": error}

    steps_used = sum(
        1 for e in state_trace
        if _state_name(e.get("state", "")) in ("SEARCHING", "READING"))
    sources_used = sum(
        1 for s in result_sources if s.get("fetched")) if result_sources \
        else 0

    _write_trace_jsonl(rdir, state_trace)
    _atomic_write_json(os.path.join(rdir, "result.json"), out)
    with open(os.path.join(rdir, "report.md"), "w", encoding="utf-8") as f:
        if ok:
            f.write(report + "\n")
        else:
            f.write("# Deep Search Run FAILED\n\n")
            f.write("- run_id: %s\n" % run_id)
            f.write("- error class: %s\n"
                    % (error or {}).get("class", "Unknown"))
            f.write("- message: %s\n"
                    % (error or {}).get("message", ""))
    _atomic_write_json(os.path.join(rdir, "extraction.json"), [])
    rs.set_terminal("DONE" if ok else "FAILED",
                    (_state_name(state_trace[-1].get("state", ""))
                     if state_trace else "FAILED"),
                    steps_used, sources_used,
                    None if ok else error)
    try:
        _update_topic(state_dir, topic_id, run_id, question,
                      rs.doc["started_at"], ok, report, state_trace,
                      result_sources, None if ok else error)
    except Exception as exc:
        # Topic merge failure must not mask the run result — record it in
        # the run state so the operator sees the partial-write situation.
        with rs.lock:
            rs.doc["topic_update_error"] = "%s: %s" % (
                type(exc).__name__, str(exc)[:200])
            rs._write()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
