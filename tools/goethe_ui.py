#!/usr/bin/env python3
"""
goethe_ui.py — Goethe Console: gateway-served dashboard + token-gated JSON APIs.
==============================================================================
version: 0.3.0

Surfaces Goethe's two differentiators — the empirical KB trust lifecycle and
the TRAUM dreaming workstream — on a web UI served by the goethe_mcp gateway
itself. No new process, no new port, no new dependencies: everything here is
Python stdlib (urllib for ES, sqlite3 for the ledger, plain file reads for
dreams/episodes). This is deliberate — CURRENT-STATE.md documents live
ES-client version drift (9.4.1 / 8.19.3 / server 9.4.3); raw HTTP JSON against
ES has no client library to drift.

ROUTES (mounted by goethe_mcp.build_http_app, v1.12.0+)
  GET  /ui                → dashboard HTML (goethe_dashboard.html, same dir).
                            No token: static page, contains no data.
  GET  /api/ui/overview   → gateway/stack health summary          (token-gated)
  GET  /api/ui/kb         → KB trust: aggs + worst/newest docs    (token-gated)
  GET  /api/ui/dream      → TRAUM digest + day-dir proposal map   (token-gated)
  GET  /api/ui/ledger     → tasks.db task blocks + step progress  (token-gated)
  POST /api/ui/ledger/delete {task_id} → archive + delete a task  (token-gated)
  GET  /api/ui/episodes   → 7-day episode call stats by exit_class(token-gated)
  GET  /api/ui/perms      → goethe_perms pending requests + grants(token-gated)
  GET  /api/ui/backends   → planner backend config status (read-only,      (token-gated)
                            no live calls to paid backends — see backend_status())
  POST /api/ui/perms/approve  {id, once?} → approve a pending request
                            (once=false, default: persistent "always" grant;
                             once=true: single-use, auto-revokes after one match)
  POST /api/ui/perms/deny     {id}        → deny a pending request ("no")
  POST /api/ui/perms/delete   {id}        → delete an unapprovable request
  POST /api/ui/perms/delete-invalid {}    → delete all unapprovable requests
  POST /api/ui/perms/revoke   {id}        → revoke an active grant
  POST /api/ui/perms/grant  {kind,pattern} → create a proactive grant
                            (read/write only; sudo stays CLI-only because it
                            needs root to regenerate the sudoers file)

Every GET /api/ui/* endpoint is READ-ONLY by construction: ES access is a POST
to _search only, sqlite opens with mode=ro, and dream/episode access is
os.scandir + open-for-read. The permission actions and task-ledger deletion are
the deliberate, token-gated write exceptions. Permission actions were added
2026-07-20
so the yes/no/always approval flow (previously CLI-only via `goethe-perm`,
and before that not reachable at all — see session-learnings.md 2026-07-20)
is visible and actionable from the Console instead of requiring a terminal.
The exception is intentionally as narrow as possible:
  - It can only touch rows in goethe_perms' own `requests`/`grants` SQLite
    tables (resolve a pending request, delete an unapprovable pending request,
    or revoke one existing grant) —
    see goethe_perms.py for the actual SQL. It cannot run commands or touch
    ES/dreams/episodes.
  - Task deletion accepts one exact task_id, snapshots the complete row into
    tasks.db's task_blocks_deleted archive, and then deletes only that row from
    task_blocks in the same SQLite transaction. It cannot select a database
    path or execute arbitrary SQL.
  - It NEVER writes /etc/sudoers.d/goethe-grants. Approving a 'sudo' kind
    request first passes goethe_perms' exact-command safety validation, then
    only creates a DB row; making that grant take effect at the OS level
    still requires the human to run
    `goethe-perm sync-sudoers` themselves in a terminal. The Console
    surfaces this reminder in the UI rather than doing it for you.
  - Gated by the same bearer token as every other /api/ui/* route — no new
    trust boundary, just a new capability behind the existing one.
Nothing else in this module can mutate state. Both write surfaces use the same
bearer token normalisation as goethe_mcp._TokenGuard ("Bearer <t>" or raw
"<t>").

CONFIG (env, mirrors the GOETHE_* valve-override convention)
  GOETHE_ES_URL          default http://127.0.0.1:9200
  GOETHE_TASKS_DB        default /opt/local-se/tasks.db
  GOETHE_DREAM_DIR       default /opt/local-se/dreams
  GOETHE_EPISODE_DIR     default /opt/local-se/episodes
  GOETHE_UI              set to "off" to disable the router entirely

FAIL-SAFE CONTRACT (same rule as episode journaling): a UI failure must never
affect the MCP surface. Every handler catches everything and answers JSON with
an "error" field; unknown paths pass through untouched to the wrapped app.
"""

import asyncio
import datetime
import json
import os
import re
import sqlite3
import sys
import time
import urllib.request

__version__ = "0.3.0"
# 0.1.1 — kb_stats 400 fix: terms aggs on source_tier/volatility/origin must
#          target the .keyword subfield — live lse-kb-1024 maps them as text
#          (the trust-migration keyword mapping didn't survive the 1024-dim
#          reindex). Found live 2026-07-19, first Console deploy.
# 0.2.0 — Permissions panel: GET /api/ui/perms (pending + grants) and the
#          three POST /api/ui/perms/* actions (approve/deny/revoke). See the
#          module docstring's ROUTES section for the deliberate, narrow
#          exception this carves out of the read-only contract.
# 0.2.2 — Invalid legacy sudo requests can be permanently deleted one at a
#          time or in one bulk cleanup. Server-side guards protect approvable
#          requests and active grants from the delete path.
# 0.3.0 — Ledger returns every task block. Exact-ID Console deletion archives
#          the full row transactionally before removing it from the live table.

# goethe_perms.py lives next to this file but this module is loaded via
# importlib.util.spec_from_file_location (not a normal package import — see
# goethe_mcp.py), so its own directory isn't guaranteed to be on sys.path
# yet. Same pattern goethe.py._perms_mod() uses. Import failure degrades to
# an "error" field in the JSON, same fail-safe contract as the ES/sqlite/
# file-read panels below — a broken goethe_perms.py must not take the whole
# Console down.
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import goethe_perms as _perms
except Exception:
    _perms = None

_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MAX_EPISODE_LINES_PER_DAY = 20000   # token-bomb lesson: cap reads at the source
_MAX_DIGEST_BYTES = 64 * 1024
_ES_TIMEOUT = 6


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default) or default


def _es_url() -> str:
    return _env("GOETHE_ES_URL", "http://127.0.0.1:9200").rstrip("/")


def _tasks_db_path() -> str:
    return _env("GOETHE_TASKS_DB", "/opt/local-se/tasks.db")


def _dream_dir() -> str:
    return _env("GOETHE_DREAM_DIR", "/opt/local-se/dreams")


def _episode_dir() -> str:
    return os.environ.get("GOETHE_EPISODE_DIR", "/opt/local-se/episodes")


def _es_search(index: str, body: dict) -> dict:
    """POST body to {ES}/{index}/_search. Read-only by construction."""
    req = urllib.request.Request(
        f"{_es_url()}/{index}/_search",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=_ES_TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


# --------------------------------------------------------------------------
# Panel data builders (sync; run via asyncio.to_thread from the router)
# --------------------------------------------------------------------------

def kb_stats() -> dict:
    """KB trust lifecycle: quality histogram, tier/volatility/origin breakdown,
    quarantine + decay counts, worst 10 docs, 10 most recent updates."""
    aggs_body = {
        "size": 0,
        "aggs": {
            "quality": {"histogram": {"field": "quality_score", "interval": 0.1,
                                      "extended_bounds": {"min": 0, "max": 1}}},
            # LIVE-MAPPING NOTE (2026-07-19): on the real index (alias lse-kb →
            # lse-kb-1024) source_tier/volatility/origin are TEXT with .keyword
            # subfields — NOT raw keyword as rag/08-kb-trust-migration.py
            # implies (the 1024-dim reindex re-derived the mapping). A terms
            # agg on the bare text field is a 400; always agg on .keyword.
            "tiers": {"terms": {"field": "source_tier.keyword", "size": 10,
                                "missing": "(untagged)"}},
            "volatility": {"terms": {"field": "volatility.keyword", "size": 5,
                                     "missing": "(untagged)"}},
            "origins": {"terms": {"field": "origin.keyword", "size": 8,
                                  "missing": "(untagged)"}},
            "quarantined": {"filter": {"term": {"stale": True}}},
            "decaying": {"filter": {"range": {"consecutive_failures": {"gte": 1}}}},
            "avg_quality": {"avg": {"field": "quality_score"}},
        },
    }
    doc_fields = ["doc_id", "title", "topic", "quality_score", "source_tier",
                  "volatility", "consecutive_failures", "stale", "updated_at",
                  "origin", "verified_against"]
    worst_body = {"size": 10, "_source": doc_fields,
                  "sort": [{"quality_score": "asc"}],
                  "query": {"match_all": {}}}
    recent_body = {"size": 10, "_source": doc_fields,
                   "sort": [{"updated_at": {"order": "desc",
                                            "unmapped_type": "date"}}],
                   "query": {"match_all": {}}}

    aggs = _es_search("lse-kb", aggs_body)
    worst = _es_search("lse-kb", worst_body)
    recent = _es_search("lse-kb", recent_body)

    def _docs(resp):
        out = []
        for h in resp.get("hits", {}).get("hits", []):
            d = h.get("_source", {})
            d["doc_id"] = d.get("doc_id") or h.get("_id")
            out.append(d)
        return out

    a = aggs.get("aggregations", {})
    total = aggs.get("hits", {}).get("total", {})
    total = total.get("value", 0) if isinstance(total, dict) else total
    return {
        "total": total,
        "avg_quality": (a.get("avg_quality") or {}).get("value"),
        "quarantined": (a.get("quarantined") or {}).get("doc_count", 0),
        "decaying": (a.get("decaying") or {}).get("doc_count", 0),
        "quality_histogram": [
            {"bucket": b["key"], "count": b["doc_count"]}
            for b in (a.get("quality") or {}).get("buckets", [])
        ],
        "tiers": [{"key": b["key"], "count": b["doc_count"]}
                  for b in (a.get("tiers") or {}).get("buckets", [])],
        "volatility": [{"key": b["key"], "count": b["doc_count"]}
                       for b in (a.get("volatility") or {}).get("buckets", [])],
        "origins": [{"key": b["key"], "count": b["doc_count"]}
                    for b in (a.get("origins") or {}).get("buckets", [])],
        "worst": _docs(worst),
        "recent": _docs(recent),
    }


def dream_stats() -> dict:
    """TRAUM: latest digest verbatim + a per-day map of proposal/crash/null
    counts from the day-dirs. Proposal JSONL schemas vary by pass — counts are
    line-based with a best-effort status breakdown, never a hard parse."""
    droot = _dream_dir()
    out = {"digest": None, "digest_mtime": None, "days": [],
           "dream_dir": droot}

    digest_path = os.path.join(droot, "latest-digest.md")
    try:
        st = os.stat(digest_path)
        with open(digest_path, encoding="utf-8", errors="replace") as f:
            out["digest"] = f.read(_MAX_DIGEST_BYTES)
        out["digest_mtime"] = datetime.datetime.fromtimestamp(
            st.st_mtime).isoformat(timespec="seconds")
    except OSError:
        pass  # no digest yet — the UI shows an empty state

    days = []
    try:
        entries = [e for e in os.scandir(droot)
                   if e.is_dir() and _DAY_RE.match(e.name)]
    except OSError:
        entries = []
    for e in sorted(entries, key=lambda x: x.name, reverse=True)[:14]:
        day = {"date": e.name, "passes": [], "proposals": 0,
               "status_counts": {}, "crashes": 0, "null_results": 0,
               "failed_banner": False}
        try:
            for f in os.scandir(e.path):
                if not f.is_file():
                    continue
                name = f.name
                if name.startswith("proposals") and name.endswith(".jsonl"):
                    m = re.match(r"proposals-?(.*)\.jsonl", name)
                    pass_name = (m.group(1) or "legacy") if m else "legacy"
                    n = 0
                    try:
                        with open(f.path, encoding="utf-8",
                                  errors="replace") as fh:
                            for line in fh:
                                line = line.strip()
                                if not line:
                                    continue
                                n += 1
                                try:
                                    status = str(json.loads(line).get(
                                        "status", "unknown"))
                                except (json.JSONDecodeError, AttributeError):
                                    status = "unknown"
                                day["status_counts"][status] = \
                                    day["status_counts"].get(status, 0) + 1
                    except OSError:
                        continue
                    day["proposals"] += n
                    day["passes"].append({"pass": pass_name, "proposals": n})
                elif name == "crashes.jsonl":
                    try:
                        with open(f.path, encoding="utf-8",
                                  errors="replace") as fh:
                            day["crashes"] = sum(1 for ln in fh if ln.strip())
                    except OSError:
                        pass
                elif name == "null-results.jsonl":
                    try:
                        with open(f.path, encoding="utf-8",
                                  errors="replace") as fh:
                            day["null_results"] = sum(
                                1 for ln in fh if ln.strip())
                    except OSError:
                        pass
                elif name.startswith("report") and name.endswith(".md"):
                    try:
                        with open(f.path, encoding="utf-8",
                                  errors="replace") as fh:
                            head = fh.read(2048)
                        if "FAILED" in head:
                            day["failed_banner"] = True
                    except OSError:
                        pass
        except OSError:
            pass
        days.append(day)
    out["days"] = days
    return out


def ledger_stats() -> dict:
    """tasks.db task blocks with parsed step progress. Opens read-only."""
    path = _tasks_db_path()
    out = {"tasks": [], "counts": {}, "db": path}
    if not os.path.isfile(path):
        return out
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(task_blocks)")]
        has_steps = "steps_json" in cols
        has_backend = "backend" in cols  # goethe.py v1.13.0 migration
        extra_cols = (", steps_json" if has_steps else "") + (", backend" if has_backend else "")
        sel = "task_id, goal, status, checkpoints, created_at, updated_at" + extra_cols
        rows = conn.execute(
            f"SELECT {sel} FROM task_blocks "
            "ORDER BY updated_at DESC").fetchall()
        steps_idx = 6 if has_steps else None
        backend_idx = 6 + (1 if has_steps else 0) if has_backend else None
        for r in rows:
            task = {"task_id": r[0], "goal": r[1], "status": r[2],
                    "checkpoints": r[3], "created_at": r[4],
                    "updated_at": r[5], "steps_total": None,
                    "steps_done": None,
                    "backend": (r[backend_idx] if backend_idx is not None else None) or "local"}
            if steps_idx is not None and r[steps_idx]:
                try:
                    steps = json.loads(r[steps_idx])
                    if isinstance(steps, dict):
                        steps = steps.get("steps", [])
                    if isinstance(steps, list):
                        task["steps_total"] = len(steps)
                        task["steps_done"] = sum(
                            1 for s in steps if isinstance(s, dict) and (
                                s.get("status") in ("done", "struck",
                                                    "complete", "completed")
                                or s.get("done") is True))
                except (json.JSONDecodeError, TypeError):
                    pass
            out["tasks"].append(task)
        for status, n in conn.execute(
                "SELECT status, COUNT(*) FROM task_blocks GROUP BY status"):
            out["counts"][status] = n
    finally:
        conn.close()
    return out


def delete_task_block(task_id) -> dict:
    """Archive and delete exactly one task block from the configured ledger."""
    if not isinstance(task_id, str):
        return {"error": "task_id must be a string"}
    task_id = task_id.strip()
    if not task_id or len(task_id) > 128:
        return {"error": "task_id must contain 1 to 128 characters"}
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in task_id):
        return {"error": "task_id cannot contain control characters"}

    path = _tasks_db_path()
    if not os.path.isfile(path):
        return {"error": "task ledger database not found"}

    conn = sqlite3.connect(path, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            row = conn.execute(
                "SELECT * FROM task_blocks WHERE task_id=?", (task_id,)
            ).fetchone()
            if row is None:
                return {"error": f"no task block {task_id!r}"}

            snapshot = {key: row[key] for key in row.keys()}
            deleted_at = datetime.datetime.now(
                datetime.timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS task_blocks_deleted ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "task_id TEXT NOT NULL, deleted_at TEXT NOT NULL, "
                "row_json TEXT NOT NULL)"
            )
            conn.execute(
                "INSERT INTO task_blocks_deleted(task_id,deleted_at,row_json) "
                "VALUES(?,?,?)",
                (
                    task_id,
                    deleted_at,
                    json.dumps(snapshot, ensure_ascii=False, default=str),
                ),
            )
            deleted = conn.execute(
                "DELETE FROM task_blocks WHERE task_id=?", (task_id,)
            ).rowcount
            if deleted != 1:
                raise sqlite3.DatabaseError(
                    f"expected to delete one task block, deleted {deleted}"
                )
        return {
            "status": "deleted",
            "task_id": task_id,
            "goal": snapshot.get("goal", ""),
            "previous_status": snapshot.get("status", ""),
            "archived": True,
        }
    except sqlite3.Error as e:
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        conn.close()


def backend_status() -> dict:
    """Planner backend configuration status (goethe.py v1.13.0's
    PLANNER_BACKEND / _call_planner_backend). Deliberately does NOT make a
    live call to the hosted (paid) backends on every Console refresh —
    'configured' means credentials/config were found, not that a request
    was made and billed. 'local' gets a real health probe since it's a
    free LAN call, same posture as overview()'s Elasticsearch check.

    Mirrors goethe.py's own valve defaults and its GOETHE_<FIELD> env-var
    override convention (goethe_mcp.py) so this reports the same picture
    the planner itself would resolve — but reads env vars directly rather
    than importing goethe.py's Tools class, to keep this module's existing
    zero-coupling-to-goethe.py design (goethe_ui.py has never imported
    goethe.py, only goethe_perms.py, and that's a much smaller surface)."""
    active = _env("GOETHE_PLANNER_BACKEND", "local").strip().lower()

    local_url = _env("GOETHE_NODE3090_LLM_URL", "http://node3090.home.arpa:8080").rstrip("/")
    local_ok = False
    try:
        with urllib.request.urlopen(f"{local_url}/health", timeout=3) as r:
            local_ok = r.status == 200
    except Exception:
        pass

    def _first_existing_path(env_name: str, default_csv: str):
        raw = _env(env_name, default_csv)
        for candidate in raw.split(":"):
            p = os.path.expanduser(candidate.strip())
            if p and os.path.isfile(p):
                return p
        return None

    codex_path = _first_existing_path("GOETHE_PLANNER_CODEX_AUTH_PATHS", "~/.codex/auth.json")
    claude_path = _first_existing_path(
        "GOETHE_PLANNER_CLAUDE_AUTH_PATHS",
        "~/.claude/.credentials.json:~/.config/claude/.credentials.json",
    )
    openai_key = bool(_env("GOETHE_PLANNER_OPENAI_API_KEY", "").strip())
    anthropic_key = bool(_env("GOETHE_PLANNER_ANTHROPIC_API_KEY", "").strip())
    rest_url = _env("GOETHE_PLANNER_REST_URL", "").strip()

    return {
        "active": active,
        "backends": [
            {"id": "local", "label": "Local (llama-server / Ollama / Gemma)",
             "configured": True, "health": "ok" if local_ok else "down",
             "detail": local_url},
            {"id": "chatgpt", "label": "ChatGPT",
             "configured": bool(codex_path or openai_key),
             "auth_source": ("codex-cli-oauth" if codex_path
                              else "api-key" if openai_key else "none"),
             "detail": codex_path or ("PLANNER_OPENAI_API_KEY set" if openai_key else None)},
            {"id": "claude", "label": "Claude",
             "configured": bool(claude_path or anthropic_key),
             "auth_source": ("claude-code-oauth" if claude_path
                              else "api-key" if anthropic_key else "none"),
             "detail": claude_path or ("PLANNER_ANTHROPIC_API_KEY set" if anthropic_key else None)},
            {"id": "rest", "label": "Custom REST",
             "configured": bool(rest_url), "detail": rest_url or None},
        ],
    }


def episode_stats() -> dict:
    """Last 7 day-dirs of episode JSONL: call counts by exit_class + top tools.
    Reads are line-capped per day; gzipped (rotated) days are skipped."""
    eroot = _episode_dir()
    out = {"days": [], "top_tools": [], "episode_dir": eroot}
    if not eroot:
        return out
    try:
        entries = [e for e in os.scandir(eroot)
                   if e.is_dir() and _DAY_RE.match(e.name)]
    except OSError:
        entries = []
    tool_totals: dict = {}
    for e in sorted(entries, key=lambda x: x.name, reverse=True)[:7]:
        day = {"date": e.name, "total": 0,
               "exit": {"ok": 0, "error": 0, "denied": 0, "timeout": 0},
               "sessions": 0}
        lines_read = 0
        try:
            files = [f for f in os.scandir(e.path)
                     if f.is_file() and f.name.endswith(".jsonl")]
        except OSError:
            files = []
        day["sessions"] = len(files)
        for f in files:
            if lines_read >= _MAX_EPISODE_LINES_PER_DAY:
                break
            try:
                with open(f.path, encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        if lines_read >= _MAX_EPISODE_LINES_PER_DAY:
                            break
                        line = line.strip()
                        if not line:
                            continue
                        lines_read += 1
                        try:
                            rec = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        day["total"] += 1
                        ec = rec.get("exit_class", "ok")
                        day["exit"][ec] = day["exit"].get(ec, 0) + 1
                        tool = rec.get("tool")
                        if tool:
                            tool_totals[tool] = tool_totals.get(tool, 0) + 1
            except OSError:
                continue
        out["days"].append(day)
    out["days"].reverse()  # oldest → newest for the chart
    out["top_tools"] = sorted(
        ({"tool": t, "count": n} for t, n in tool_totals.items()),
        key=lambda x: -x["count"])[:10]
    return out


def overview() -> dict:
    """Cheap health summary for the header strip."""
    es_ok, kb_docs = False, None
    try:
        req = urllib.request.Request(f"{_es_url()}/lse-kb/_count")
        with urllib.request.urlopen(req, timeout=3) as r:
            kb_docs = json.loads(r.read().decode("utf-8")).get("count")
            es_ok = True
    except Exception:
        pass
    return {
        "es_ok": es_ok,
        "kb_docs": kb_docs,
        "dream_digest_exists": os.path.isfile(
            os.path.join(_dream_dir(), "latest-digest.md")),
        "tasks_db_exists": os.path.isfile(_tasks_db_path()),
        "episodes_enabled": bool(_episode_dir()),
        "server_time": datetime.datetime.now().astimezone().isoformat(
            timespec="seconds"),
        "ui_version": __version__,
    }


def perms_overview() -> dict:
    """Pending goethe_perms requests + active grants. Read-only — pending()
    and list_grants() are SELECTs; the mutating calls (resolve_request/
    revoke) only happen from _perm_action(), never from here."""
    if _perms is None:
        return {"error": "goethe_perms module not importable",
                "pending": [], "grants": []}
    try:
        return {"pending": _perms.pending(), "grants": _perms.list_grants()}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}", "pending": [], "grants": []}


_PANELS = {
    "/api/ui/overview": overview,
    "/api/ui/kb": kb_stats,
    "/api/ui/dream": dream_stats,
    "/api/ui/ledger": ledger_stats,
    "/api/ui/episodes": episode_stats,
    "/api/ui/perms": perms_overview,
    "/api/ui/backends": backend_status,
}


# --------------------------------------------------------------------------
# Permission actions — one of the two deliberate write surfaces. See the
# module docstring's ROUTES section for the scope this is held to.
# --------------------------------------------------------------------------

def _perm_action(action: str, rid: int, once: bool) -> dict:
    """Resolve a pending request (approve/deny) or revoke a grant. `action`
    is one of 'approve' | 'deny' | 'delete' | 'revoke' — the router maps the
    URL path to this before calling in, so this function never sees a raw path.
    Runs in a worker thread via asyncio.to_thread, same as the read panels.
    """
    if _perms is None:
        return {"error": "goethe_perms module not importable"}
    try:
        if action == "approve":
            status, gid = _perms.resolve_request(rid, approve=True, once=once)
            if status == "not-found":
                return {"error": f"no pending request #{rid}"}
            return {"status": status, "grant_id": gid, "one_time": once}
        if action == "deny":
            status, _gid = _perms.resolve_request(rid, approve=False)
            if status == "not-found":
                return {"error": f"no pending request #{rid}"}
            return {"status": status}
        if action == "delete":
            ok = _perms.delete_unapprovable_request(rid)
            return (
                {"status": "deleted"}
                if ok
                else {"error": f"no pending request #{rid}"}
            )
        if action == "revoke":
            ok = _perms.revoke(rid)
            return {"status": "revoked"} if ok else {"error": f"no active grant #{rid}"}
        return {"error": f"unknown action {action!r}"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def _perm_grant(kind: str, pattern: str, note: str = "") -> dict:
    """Create a proactive ("Active") grant from the Console — the operator
    deciding up front, rather than reacting to an agent request. Mirrors
    `goethe-perm grant <kind> <path>`.

    read/write only. A sudo grant is deliberately NOT creatable here: it has
    to regenerate /etc/sudoers.d/goethe-grants via visudo+install as root,
    which this unprivileged web process cannot (and should not) do. Those
    stay CLI-only so the privileged step happens under the operator's own
    shell.
    """
    if _perms is None:
        return {"error": "goethe_perms module not importable"}
    kind = (kind or "").strip().lower()
    pattern = (pattern or "").strip()
    if kind not in ("read", "write"):
        return {"error": "kind must be 'read' or 'write' "
                         "(sudo grants: use the goethe-perm CLI)"}
    if not pattern.startswith("/"):
        return {"error": "pattern must be an absolute path"}
    try:
        gid = _perms.grant(kind, pattern, note or "granted via Goethe Console")
        return {"status": "granted", "grant_id": gid,
                "kind": kind, "pattern": pattern}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def _perm_delete_invalid() -> dict:
    """Permanently remove all pending requests that fail sudo validation."""
    if _perms is None:
        return {"error": "goethe_perms module not importable"}
    try:
        count = _perms.delete_all_unapprovable_requests()
        return {"status": "deleted", "deleted": count}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


_PERM_ACTION_PATHS = {
    "/api/ui/perms/approve": "approve",
    "/api/ui/perms/deny": "deny",
    "/api/ui/perms/delete": "delete",
    "/api/ui/perms/revoke": "revoke",
}


# --------------------------------------------------------------------------
# ASGI router
# --------------------------------------------------------------------------

class UIRouter:
    """ASGI middleware: serves /ui and /api/ui/*; passes everything else
    through untouched. Sits OUTSIDE goethe_mcp._TokenGuard (so the static
    /ui page loads in a plain browser) and does its own token check on
    /api/ui/* using the same header normalisation as _TokenGuard."""

    def __init__(self, app, token: str = "", html_path: str = ""):
        self.app = app
        self.token = token or ""
        self.html_path = html_path or os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "goethe_dashboard.html")

    def _authorized(self, scope) -> bool:
        if not self.token:
            return True  # same posture as the MCP endpoint: localhost-only
        headers = dict(scope.get("headers", []))
        auth = headers.get(b"authorization", b"").decode().strip()
        received = auth[7:] if auth.lower().startswith("bearer ") else auth
        return received == self.token

    async def _respond(self, send, status: int, body: bytes,
                       content_type: str) -> None:
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", content_type.encode()),
                                (b"cache-control", b"no-store")]})
        await send({"type": "http.response.body", "body": body})

    async def _read_json_body(self, receive, max_bytes: int = 8192) -> dict:
        """Drain the ASGI request body and parse it as JSON. No streaming
        request in this router needs more than a tiny {id, once} object, so
        a hard 8KB cap is generous headroom, not a real limit — this stops
        a malformed/huge body from being buffered in full before the
        json.loads() (and matching) error surfaces anyway."""
        body = b""
        while True:
            msg = await receive()
            if msg.get("type") != "http.request":
                break
            body += msg.get("body", b"")
            if len(body) > max_bytes:
                raise ValueError(f"request body exceeds {max_bytes} bytes")
            if not msg.get("more_body"):
                break
        if not body:
            return {}
        parsed = json.loads(body.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("request body must be a JSON object")
        return parsed

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        method = scope.get("method", "GET")

        if path in ("/ui", "/ui/") and method == "GET":
            try:
                with open(self.html_path, "rb") as f:
                    html = f.read()
                await self._respond(send, 200, html, "text/html; charset=utf-8")
            except OSError as e:
                await self._respond(
                    send, 500,
                    f"goethe_dashboard.html not found: {e}".encode(),
                    "text/plain")
            return

        if path in _PANELS and method == "GET":
            if not self._authorized(scope):
                await self._respond(send, 401, b'{"error":"unauthorized"}',
                                    "application/json")
                return
            t0 = time.monotonic()
            try:
                data = await asyncio.to_thread(_PANELS[path])
            except Exception as e:  # fail-safe contract: never 500 raw
                data = {"error": f"{type(e).__name__}: {e}"}
            data["_elapsed_ms"] = int((time.monotonic() - t0) * 1000)
            await self._respond(
                send, 200,
                json.dumps(data, ensure_ascii=False, default=str).encode(),
                "application/json")
            return

        if path == "/api/ui/ledger/delete" and method == "POST":
            if not self._authorized(scope):
                await self._respond(send, 401, b'{"error":"unauthorized"}',
                                    "application/json")
                return
            try:
                payload = await self._read_json_body(receive)
            except (TypeError, ValueError, json.JSONDecodeError) as e:
                await self._respond(
                    send, 400,
                    json.dumps({"error": f"bad body: {e}"}).encode(),
                    "application/json")
                return
            data = await asyncio.to_thread(
                delete_task_block, payload.get("task_id")
            )
            await self._respond(
                send, 409 if "error" in data else 200,
                json.dumps(data, ensure_ascii=False, default=str).encode(),
                "application/json")
            return

        # Permissions actions — see module docstring for why this is the
        # narrow blast radius (goethe_perms.py's requests/grants tables, and
        # nothing else).
        if path == "/api/ui/perms/grant" and method == "POST":
            if not self._authorized(scope):
                await self._respond(send, 401, b'{"error":"unauthorized"}',
                                    "application/json")
                return
            try:
                payload = await self._read_json_body(receive)
            except (TypeError, ValueError, json.JSONDecodeError) as e:
                await self._respond(
                    send, 400,
                    json.dumps({"error": f"bad body: {e}"}).encode(),
                    "application/json")
                return
            data = await asyncio.to_thread(
                _perm_grant, payload.get("kind", ""), payload.get("pattern", ""),
                payload.get("note", ""))
            await self._respond(
                send, 400 if "error" in data else 200,
                json.dumps(data, ensure_ascii=False, default=str).encode(),
                "application/json")
            return

        if path == "/api/ui/perms/delete-invalid" and method == "POST":
            if not self._authorized(scope):
                await self._respond(send, 401, b'{"error":"unauthorized"}',
                                    "application/json")
                return
            data = await asyncio.to_thread(_perm_delete_invalid)
            await self._respond(
                send, 400 if "error" in data else 200,
                json.dumps(data, ensure_ascii=False, default=str).encode(),
                "application/json")
            return

        if path in _PERM_ACTION_PATHS and method == "POST":
            if not self._authorized(scope):
                await self._respond(send, 401, b'{"error":"unauthorized"}',
                                    "application/json")
                return
            try:
                payload = await self._read_json_body(receive)
                rid = int(payload["id"])
            except KeyError:
                await self._respond(
                    send, 400, b'{"error":"body must include integer \\"id\\""}',
                    "application/json")
                return
            except (TypeError, ValueError, json.JSONDecodeError) as e:
                await self._respond(
                    send, 400,
                    json.dumps({"error": f"bad request body: {e}"}).encode(),
                    "application/json")
                return
            action = _PERM_ACTION_PATHS[path]
            once = bool(payload.get("once", False))
            data = await asyncio.to_thread(_perm_action, action, rid, once)
            status = 200 if "error" not in data else 409
            await self._respond(
                send, status,
                json.dumps(data, ensure_ascii=False, default=str).encode(),
                "application/json")
            return

        await self.app(scope, receive, send)
