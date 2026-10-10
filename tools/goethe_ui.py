#!/usr/bin/env python3
"""
goethe_ui.py — Goethe Console: gateway-served dashboard + typed control APIs.
=============================================================================
version: 0.4.0

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
  GET  /kbgraph           → Phase 5 graph renderer (goethe_kbgraph.html, same dir).
                            No token: static page; fetches /api/ui/kbgraph with the token.
  GET  /webSearch         → WebSearch LB console (websearch-lb/frontend/
                            index.html, same dir). No token: static page.
  GET  /webSearch/stats   → proxy to websearch-lb /stats (loopback :9703;
                            override with GOETHE_WEBSEARCH_LB_URL). No token —
                            the frontend contract sends Bearer on /mcp* only;
                            the upstream WEBSEARCH_LB_TOKEN is the auth boundary.
  GET  /api/ui/overview   → gateway/stack health summary          (token-gated)
  GET  /api/ui/kb         → KB trust: aggs + worst/newest docs    (token-gated)
  GET  /api/ui/dream      → TRAUM digest + legacy day-dir map     (token-gated)
  GET  /api/ui/traum/*    → typed TRAUM lifecycle/control API     (token-gated)
  GET  /api/ui/ledger     → tasks.db task blocks + step progress  (token-gated)
  POST /api/ui/ledger/delete {task_id} → archive + delete a task  (token-gated)
  GET  /api/ui/episodes   → 7-day episode call stats by exit_class(token-gated)
  GET  /api/ui/episodes/purge-preview?tool=<name> → read-only purge preview
                            (token-gated) — classifies matches as entire/mixed
  POST /api/ui/episodes/purge {session_ids,reason} → quarantine-only purge
                            (token-gated) — moves 'entire' matches only, never
                            deletes; see docs/SPEC-console-corpus-hygiene-2026-08.md
  GET  /api/ui/perms      → goethe_perms pending requests + grants(token-gated)
  GET  /api/ui/backends   → planner backend config status (read-only,      (token-gated)
  POST /api/ui/backends/select {backend} → set the active planner backend
                            no live calls to paid backends — see backend_status())
  POST /api/ui/traum/proposals/revalidate {limit?} → read-only invariant
                            sweep; auto-resolves proposals the approve path
                            could never apply. Never applies anything.
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

TRAUM controls are a separate plane from Permissions.  They use the existing
gateway bearer token but never read or write goethe_perms grants and never
accept a raw command/path/environment/argv.  The timer API is read-only.

Every legacy GET /api/ui/* endpoint is READ-ONLY by construction: ES access is
a POST to _search only, sqlite opens with mode=ro, and dream/episode access is
os.scandir + open-for-read. The permission actions, task-ledger deletion, backend selection, and
episode-corpus purge are the deliberate, token-gated write exceptions.
Permission actions were added
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
  - Episode-corpus purge (POST /api/ui/episodes/purge) only ever MOVES
    session files with shutil.move() — it never deletes. It accepts exact
    session_ids only, never a free-text pattern; refuses any file whose
    lines span more than one tool ('mixed', re-verified at execution time,
    not trusted from the preview response); and every resolved path is
    checked with os.path.realpath to stay inside _episode_dir() before
    anything touches disk. See docs/SPEC-console-corpus-hygiene-2026-08.md.
Nothing else in this module can mutate state beyond the write surfaces listed
above. All of them use the same bearer token normalisation as
goethe_mcp._TokenGuard ("Bearer <t>" or raw "<t>").

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
import shutil
import sqlite3
import sys
import time
import urllib.request
import urllib.parse
import subprocess
import uuid

try:
    from goethe_node3090_prober import Node3090Prober
except Exception:  # fail-safe contract: an optional UI add-on
    # must never take down the MCP surface at import time
    Node3090Prober = None

__version__ = "0.6.0"
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
# 0.5.0 — Episode corpus hygiene: GET /api/ui/episodes/purge-preview
#          (read-only classify) and POST /api/ui/episodes/purge
#          (quarantine-only write; explicit session_ids; refuses mixed
#          files; calls episode_index.build_manifest(prune=True)). See
#          docs/SPEC-console-corpus-hygiene-2026-08.md.
# 0.6.0 — WebSearch LB console: GET /webSearch (static,
#          websearch-lb/frontend/index.html) and GET /webSearch/stats
#          (same-origin proxy to the loopback websearch-lb /stats).
#          The stats proxy is deliberately untokened: the frontend
#          contract (websearch-frontend/brief.md) sends Bearer tokens
#          on /mcp* requests only.

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

# Same fail-safe loading posture as goethe_perms.  The controller owns only
# /api/ui/traum/*; a partial TRAUM deployment must not break the MCP gateway or
# any pre-existing Console panel.
try:
    import traum_controller as _traum_control
except Exception:
    _traum_control = None

# Persisted planner-backend selection, shared with goethe.py (v1.14.0). Same
# fail-safe loading posture as the two above: if this module is missing, the
# backends panel degrades to reporting the env-var value and the select route
# returns a clean error instead of a 500. A selector that cannot load must not
# take the Console down with it.
try:
    import goethe_planner_state as _planner_state
except Exception:
    _planner_state = None

# episode_index.py lives next to this file too. episode_purge() below reuses
# its build_manifest(prune=True) rather than reimplementing pruning (Hazard D,
# docs/SPEC-console-corpus-hygiene-2026-08.md). ImportError only -- a missing
# or broken sibling module degrades the purge routes to a clean "error" field
# instead of a blind except-Exception (keeps this file's BLE001 count clean).
try:
    import episode_index as _episode_index
except ImportError:
    _episode_index = None

_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MAX_EPISODE_LINES_PER_DAY = 20000   # token-bomb lesson: cap reads at the source
_MAX_DIGEST_BYTES = 64 * 1024
_ES_TIMEOUT = 6
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,200}$")
_PURGE_PREVIEW_CAP = 500


# --------------------------------------------------------------------------
# Friction-signal observability (2026-09-18, task b37bc23a). Consumes the
# SAME classifier table as tools/friction_report.py (single source of truth)
# and adds two signal families the report CLI does not surface in the UI:
#   * guard denials  - per-guard-type breakdown of BLOCKED results
#   * truncation     - model-visible (MAX_OUTPUT_CHARS) vs log-level
#                      (EPISODE_MAX_RESULT_CHARS) clipped results
# All helpers are pure/read-only; the only I/O is the one-shot classifier
# file load below. episode_stats() appends an additive "friction" object --
# every pre-existing field is untouched (see /opt/local-se/
# friction-ui-one-line-assessment.md, verdict: feasible).
# --------------------------------------------------------------------------

FRICTION_CLASSIFIERS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "friction_classifiers.json")


def _load_friction_classifiers() -> list:
    """Load tools/friction_classifiers.json once; [] on any failure.
    A missing/corrupt table must never take the episodes route down --
    categories then simply report as 'unclassified'."""
    try:
        with open(FRICTION_CLASSIFIERS_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return [c for c in data
                    if isinstance(c, dict) and c.get("name")
                    and isinstance(c.get("patterns"), list)]
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return []


_FRICTION_CLASSIFIERS = _load_friction_classifiers()


def _classify_guard_type(result_text: str) -> str:
    """Map a guard denial result to a stable guard_type string.
    Returns '' when the text is not a guard denial. Requires the denial
    marker at the START of the text: docstrings and code snippets that
    merely QUOTE 'BLOCKED:' inside a successful result must not count
    (observed artifact in the 2026-09-12..18 corpus)."""
    t = (result_text or "").lstrip()
    if t.startswith("Blocked command(s) for safety:"):
        return "blocked_commands_safety"
    if not t.startswith("BLOCKED:"):
        return ""
    # first single-quoted token, e.g. 'sudo' in "BLOCKED: 'sudo' detected ..."
    m = re.search(r"'([^']{1,60})'", t)
    quoted = m.group(1) if m else ""
    if "is permanently forbidden" in t:
        return "permanently_forbidden"
    if "is a protected credential file" in t:
        return "credential_file_protected"
    if "working_dir" in t and "outside allowed read paths" in t:
        return "working_dir_outside"
    if "outside allowed write paths" in t:
        return "write_path_outside"
    if "outside allowed read paths" in t:
        return "read_path_outside"
    if "write targeting a privileged path" in t:
        return "privileged_path_write"
    if "SIZE-CHECK" in t:
        return "size_check"
    if "could not create a recovery snapshot" in t:
        return "snapshot_failed"
    if "a download is already running" in t:
        return "download_running"
    if "detected in a chained or complex command" in t:
        return f"chained_complex_{quoted}" if quoted else "chained_complex_other"
    if "detected in command" in t:
        return "command_priv_verb"
    return "blocked_other"


def _is_model_truncated(result_text: str) -> bool:
    """Model-visible truncation: execute_command's MAX_OUTPUT_CHARS cap
    appends '... [TRUNCATED -- N chars total...' to the text the MODEL sees."""
    return "TRUNCATED —" in (result_text or "")


def _is_log_truncated(result_text: str) -> bool:
    """Log-level truncation: the episode logger caps result_truncated at
    EPISODE_MAX_RESULT_CHARS (goethe_mcp.py) and appends '…[truncated]'."""
    return (result_text or "").endswith("…[truncated]")


def _classify_friction_category(result_text: str, classifiers: list) -> str:
    """First category whose literal substring patterns match wins
    (same semantics as tools/friction_report.py.classify). 'unclassified'
    when nothing matches -- the UI must show that bucket, not hide it."""
    t = result_text or ""
    for cat in classifiers:
        for pat in cat["patterns"]:
            if pat and pat in t:
                return cat["name"]
    return "unclassified"


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
                  "origin", "verified_against",
                  "mentor_demoted_at", "failure_count", "demote_reason"]
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
        has_prov = "provenance" in cols  # node provenance (A2A stamp)
        extra_cols = (", steps_json" if has_steps else "") + (", backend" if has_backend else "")
        extra_cols += (", provenance" if has_prov else "")
        sel = "task_id, goal, status, checkpoints, created_at, updated_at" + extra_cols
        rows = conn.execute(
            f"SELECT {sel} FROM task_blocks "
            "ORDER BY updated_at DESC").fetchall()
        steps_idx = 6 if has_steps else None
        backend_idx = 6 + (1 if has_steps else 0) if has_backend else None
        prov_idx = 6 + (1 if has_steps else 0) + (1 if has_backend else 0) if has_prov else None
        for r in rows:
            task = {"task_id": r[0], "goal": r[1], "status": r[2],
                    "checkpoints": r[3], "created_at": r[4],
                    "updated_at": r[5], "steps_total": None,
                    "steps_done": None,
                    "backend": (r[backend_idx] if backend_idx is not None else None) or "local",
                    "provenance": (r[prov_idx] if prov_idx is not None else None) or "node4090"}
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
    env_default = _env("GOETHE_PLANNER_BACKEND", "local").strip().lower()
    if _planner_state is not None:
        active = _planner_state.selected_backend(env_default)
        active_source = _planner_state.resolution_source()
    else:
        active = env_default or "local"
        active_source = "env"

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
    # The claude backend invokes the `claude` CLI (goethe.py's
    # _call_claude_planner), so the CLI is the hard requirement — a
    # credentials file alone no longer means anything is callable.
    # claude_path above is now used ONLY as an existence hint that
    # `claude login` has been run. The file is never opened or parsed,
    # here or anywhere else in the tree.
    claude_cli = shutil.which(
        _env("GOETHE_PLANNER_CLAUDE_CLI", "").strip() or "claude")
    rest_url = _env("GOETHE_PLANNER_REST_URL", "").strip()

    return {
        "active": active,
        # 'store' means an operator chose this in the Console and it will
        # survive a restart; 'env' means it is still the deployment default.
        "active_source": active_source,
        "selectable": _planner_state is not None,
        "backends": [
            {"id": "local", "label": "Local (llama-server / Ollama / Gemma)",
             "configured": True, "health": "ok" if local_ok else "down",
             "detail": local_url},
            {"id": "chatgpt", "label": "ChatGPT",
             "configured": bool(codex_path or openai_key),
             "auth_source": ("codex-cli-oauth" if codex_path
                              else "api-key" if openai_key else "none"),
             "detail": codex_path or ("PLANNER_OPENAI_API_KEY set" if openai_key else None)},
            # Mirrors _call_claude_planner's precedence exactly: no CLI means
            # nothing works; with a CLI, an explicit API key wins over the
            # login session because that function treats a set key as the
            # operator's deliberate choice, not a fallback.
            {"id": "claude", "label": "Claude",
             "configured": bool(claude_cli and (claude_path or anthropic_key)),
             "auth_source": ("none" if not claude_cli
                             else "api-key" if anthropic_key
                             else "claude-login-session" if claude_path
                             else "none"),
             "detail": (
                 "claude CLI not found — "
                 "npm install -g @anthropic-ai/claude-code"
                 if not claude_cli
                 else f"{claude_cli} · PLANNER_ANTHROPIC_API_KEY set (billed)"
                 if anthropic_key
                 else f"{claude_cli} · logged-in session"
                 if claude_path
                 else f"{claude_cli} · installed, run `claude login`")},
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
    # friction-signal accumulators (task b37bc23a) -- pure counters, no I/O
    fr_total = 0
    fr_non_ok = 0
    fr_exit: dict = {}
    fr_guards_total = 0
    fr_by_type: dict = {}
    fr_samples: dict = {}
    fr_model_total = 0
    fr_model_by_tool: dict = {}
    fr_log_total = 0
    fr_log_by_tool: dict = {}
    fr_categories: dict = {}
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
                        # friction signals (read-only; classifier table is
                        # module-level, loaded once -- no per-line I/O)
                        rt = rec.get("result_truncated") or ""
                        fr_total += 1
                        if ec != "ok":
                            fr_non_ok += 1
                            fr_exit[ec] = fr_exit.get(ec, 0) + 1
                            fr_cat = _classify_friction_category(
                                rt, _FRICTION_CLASSIFIERS)
                            fr_categories[fr_cat] = fr_categories.get(fr_cat, 0) + 1
                        gtype = _classify_guard_type(rt)
                        if gtype:
                            fr_guards_total += 1
                            fr_by_type[gtype] = fr_by_type.get(gtype, 0) + 1
                            rts = rec.get("ts") or ""
                            prev = fr_samples.get(gtype)
                            if prev is None or rts >= prev["ts"]:
                                fr_samples[gtype] = {
                                    "type": gtype,
                                    "tool": tool,
                                    "date": rts[:10],
                                    "ts": rts,
                                    "head": rt[:90],
                                }
                        if _is_model_truncated(rt):
                            fr_model_total += 1
                            fr_model_by_tool[tool] = fr_model_by_tool.get(tool, 0) + 1
                        if _is_log_truncated(rt):
                            fr_log_total += 1
                            fr_log_by_tool[tool] = fr_log_by_tool.get(tool, 0) + 1
            except OSError:
                continue
        out["days"].append(day)
    out["days"].reverse()  # oldest → newest for the chart
    out["top_tools"] = sorted(
        ({"tool": t, "count": n} for t, n in tool_totals.items()),
        key=lambda x: -x["count"])[:10]
    # Additive friction aggregate (task b37bc23a) -- days/top_tools/
    # episode_dir above are byte-identical to the pre-change shape.
    out["friction"] = {
        "window": {
            "total": fr_total,
            "non_ok": fr_non_ok,
            "rate_pct": round(100.0 * fr_non_ok / fr_total, 1)
                        if fr_total else 0.0,
            "error": fr_exit.get("error", 0),
            "denied": fr_exit.get("denied", 0),
            "timeout": fr_exit.get("timeout", 0),
        },
        "guards": {
            "total": fr_guards_total,
            "by_type": dict(sorted(fr_by_type.items(), key=lambda x: -x[1])),
            "samples": sorted(fr_samples.values(),
                              key=lambda x: x["ts"], reverse=True),
        },
        "truncation": {
            "model_total": fr_model_total,
            "log_total": fr_log_total,
            "model_by_tool": dict(sorted(fr_model_by_tool.items(),
                                         key=lambda x: -x[1])),
            "log_by_tool": dict(sorted(fr_log_by_tool.items(),
                                       key=lambda x: -x[1])),
        },
        "categories": dict(sorted(fr_categories.items(), key=lambda x: -x[1])),
    }
    return out


# --------------------------------------------------------------------------
# Episode corpus hygiene -- quarantine-only purge. See
# docs/SPEC-console-corpus-hygiene-2026-08.md. This never deletes: matching
# files are relocated with shutil.move() into a timestamped quarantine
# sibling of _episode_dir(). `rm`, `os.remove`/`os.unlink`, and
# `shutil.rmtree` do not appear anywhere below -- deleting a quarantine
# directory afterwards stays a manual, separate action at a shell (Hazard A).
# The destructive POST route takes only explicit session_ids, never a
# free-text pattern (Hazard B), and refuses to move any file whose lines
# span more than one tool (Hazard C) -- re-verified at execution time, not
# trusted from the preview response. Pruning the manifest afterwards always
# goes through episode_index.build_manifest(prune=True); this module does
# not reimplement that logic (Hazard D).
# --------------------------------------------------------------------------


def _manifest_db_path(episode_dir: str) -> str:
    return os.path.join(episode_dir, "manifest.db")


def _classify_session_lines(path: str, tool: str = None):
    """Parse one .jsonl session file's valid lines.

    Returns (total_lines, matching_lines, distinct_tools):
      total_lines     -- count of parseable JSON-object lines.
      matching_lines  -- count of those lines whose "tool" field == `tool`
                         (always 0 if tool is None -- used by the purge
                         re-verification path, which only needs the
                         distinct set, not a specific-tool count).
      distinct_tools  -- set of every "tool" value seen across all lines.

    A file is "entirely" one tool iff distinct_tools == {tool}: every valid
    line in it names that one tool and no other. That single check is used
    both by preview (classifying against the queried tool) and by purge's
    re-verification (checking the file is still single-tool at all,
    independent of which tool -- see episode_purge()). Malformed individual
    lines are skipped, same tolerance as episode_index.parse_session_file.
    """
    total = 0
    matching = 0
    distinct = set()
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict):
                continue
            total += 1
            t = rec.get("tool")
            if isinstance(t, str):
                distinct.add(t)
                if tool is not None and t == tool:
                    matching += 1
    return total, matching, distinct


def episode_purge_preview(tool: str) -> dict:
    """GET /api/ui/episodes/purge-preview?tool=<name>. Side-effect free:
    scans the corpus for .jsonl session files containing at least one line
    with "tool" == `tool`, and classifies each as "entire" (every valid
    line in the file is that tool) or "mixed" (some lines are other
    tools -- never purgeable here, per Hazard C). `tool` is a selector for
    this preview only; it is never sent to, or used by, the purge route.
    """
    tool = (tool or "").strip()
    if not tool:
        return {"error": "tool is required"}

    eroot = _episode_dir()
    if not eroot or not os.path.isdir(eroot):
        return {"error": f"episode directory not found: {eroot!r}"}
    eroot_real = os.path.realpath(eroot)

    manifest_ids = set()
    if _episode_index is not None:
        try:
            manifest_ids = _episode_index._existing_session_ids(
                _manifest_db_path(eroot_real))
        except sqlite3.Error:
            manifest_ids = set()

    try:
        day_entries = sorted(
            (e for e in os.scandir(eroot_real)
             if e.is_dir() and _DAY_RE.match(e.name)),
            key=lambda e: e.name)
    except OSError:
        day_entries = []

    entries = []
    scanned = 0
    truncated = False
    for day_entry in day_entries:
        try:
            files = sorted(
                (f for f in os.scandir(day_entry.path)
                 if f.is_file() and f.name.endswith(".jsonl")),
                key=lambda f: f.name)
        except OSError:
            continue
        for f in files:
            scanned += 1
            if len(entries) >= _PURGE_PREVIEW_CAP:
                truncated = True
                continue
            try:
                total, matching, distinct = _classify_session_lines(f.path, tool)
            except OSError:
                continue
            if matching == 0:
                continue
            session_id = f.name[: -len(".jsonl")]
            classification = "entire" if distinct == {tool} else "mixed"
            entries.append({
                "session_id": session_id,
                "day": day_entry.name,
                "matching_lines": matching,
                "total_lines": total,
                "classification": classification,
                "manifest_has_row": session_id in manifest_ids,
            })

    purgeable = [e["session_id"] for e in entries
                 if e["classification"] == "entire"]
    return {
        "tool": tool,
        "episode_dir": eroot_real,
        "scanned_files": scanned,
        "matched_files": len(entries),
        "entire_count": len(purgeable),
        "mixed_count": len(entries) - len(purgeable),
        "truncated": truncated,
        "entries": entries,
        "purgeable_session_ids": purgeable,
    }


def _valid_session_id(session_id) -> bool:
    return isinstance(session_id, str) and bool(_SESSION_ID_RE.match(session_id))


def _find_session_file(eroot_real: str, session_id: str):
    """Return (day, real_path) for session_id's .jsonl file under
    eroot_real, or (None, None) if it does not exist. Every candidate path
    is resolved with os.path.realpath and required to stay inside
    eroot_real -- a symlink or traversal that would escape the corpus root
    is refused here even though _valid_session_id() already rejects any
    session_id containing '/' (defense in depth, per the anti-goal that
    every resolved path must be verified after os.path.realpath)."""
    try:
        day_entries = sorted(
            (e for e in os.scandir(eroot_real)
             if e.is_dir() and _DAY_RE.match(e.name)),
            key=lambda e: e.name)
    except OSError:
        return None, None
    for day_entry in day_entries:
        candidate = os.path.join(day_entry.path, f"{session_id}.jsonl")
        real = os.path.realpath(candidate)
        if real != candidate and not real.startswith(eroot_real + os.sep):
            continue  # symlink escape -- refuse
        if os.path.isfile(real):
            return day_entry.name, real
    return None, None


def episode_purge(session_ids, reason: str) -> dict:
    """POST /api/ui/episodes/purge. The write surface. `session_ids` must
    be a non-empty list of strings, each matching the strict id pattern --
    never a pattern/glob (Hazard B). Every id is re-verified right now: the
    file must still exist and must still be single-tool ("entire"); a file
    that is now mixed (e.g. it grew a real call since preview, or was
    always mixed and was passed in anyway) is skipped and reported, never
    moved (Hazard C). Matches are relocated with shutil.move() into a
    timestamped quarantine directory next to _episode_dir() -- never
    deleted (Hazard A) -- then episode_index.build_manifest(prune=True) is
    called to drop the now-orphaned manifest rows (Hazard D); pruning
    itself is never reimplemented here.
    """
    if _episode_index is None:
        return {"error": "episode_index module not importable -- purge unavailable"}

    if not isinstance(session_ids, list) or not session_ids:
        return {"error": "session_ids must be a non-empty list"}
    if not all(isinstance(s, str) for s in session_ids):
        return {"error": "session_ids must all be strings"}
    reason = reason.strip() if isinstance(reason, str) else ""
    if not reason:
        return {"error": "reason is required"}

    bad_ids = [s for s in session_ids if not _valid_session_id(s)]
    if bad_ids:
        return {"error": "invalid session_id(s), rejected: "
                          f"{bad_ids[:5]!r}"}

    # De-dup, preserving order -- a repeated id must not be moved twice or
    # double-counted in the response.
    seen = set()
    ids = []
    for s in session_ids:
        if s not in seen:
            seen.add(s)
            ids.append(s)

    eroot = _episode_dir()
    if not eroot or not os.path.isdir(eroot):
        return {"error": f"episode directory not found: {eroot!r}"}
    eroot_real = os.path.realpath(eroot)
    manifest_db = _manifest_db_path(eroot_real)

    try:
        rows_before = len(_episode_index._existing_session_ids(manifest_db))
    except sqlite3.Error as e:
        return {"error": f"could not read manifest: {type(e).__name__}: {e}"}

    slug = re.sub(r"[^a-z0-9]+", "-", reason.lower()).strip("-")[:40] or "purge"
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%f")

    moved = []
    skipped = []
    quarantine_dir = None

    for session_id in ids:
        day, path = _find_session_file(eroot_real, session_id)
        if path is None:
            skipped.append({"session_id": session_id,
                             "reason": "file not found under episode_dir"})
            continue
        try:
            total, _matching, distinct = _classify_session_lines(path)
        except OSError as e:
            skipped.append({"session_id": session_id,
                             "reason": f"could not read file: {e}"})
            continue
        if total == 0:
            skipped.append({"session_id": session_id,
                             "reason": "file has no parseable lines"})
            continue
        if len(distinct) != 1:
            skipped.append({"session_id": session_id,
                             "reason": "file is mixed (contains more than "
                                       "one tool) -- refusing to purge"})
            continue

        if quarantine_dir is None:
            quarantine_dir = os.path.join(
                os.path.dirname(eroot_real),
                f"episodes-quarantine-{slug}-{ts}")
        dest_dir = os.path.join(quarantine_dir, day)
        dest = os.path.join(dest_dir, f"{session_id}.jsonl")
        try:
            os.makedirs(dest_dir, exist_ok=True)
            shutil.move(path, dest)
        except OSError as e:
            skipped.append({"session_id": session_id,
                             "reason": f"move failed: {e}"})
            continue
        moved.append({"session_id": session_id, "day": day,
                       "quarantined_to": dest})

    if quarantine_dir is not None:
        try:
            with open(os.path.join(quarantine_dir, "MOVED-FILES.txt"), "w",
                      encoding="utf-8") as fh:
                fh.write(f"# corpus hygiene purge -- {ts}\n")
                fh.write(f"# reason: {reason}\n")
                for m in moved:
                    fh.write(f"{m['day']}/{m['session_id']}.jsonl\n")
        except OSError:
            pass  # the moves themselves already succeeded and are reported

    try:
        stats = _episode_index.build_manifest(eroot_real, manifest_db, prune=True)
    except (OSError, sqlite3.Error) as e:
        stats = {"error": f"{type(e).__name__}: {e}"}
    rows_after = stats["written"] if "error" not in stats else rows_before

    return {
        "status": "ok",
        "reason": reason,
        "moved_count": len(moved),
        "moved": moved,
        "skipped_count": len(skipped),
        "skipped": skipped,
        "quarantine_path": quarantine_dir,
        "manifest_rows_before": rows_before,
        "manifest_rows_after": rows_after,
        "manifest_prune_stats": stats,
    }


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


def skills_panel() -> dict:
    """Read-only listing of the lse-skills index for the console Skills panel.

    Returns every skill doc (procedure/verification/preconditions/failure_modes/
    provenance included for click-to-expand). No write surface — the panel is
    strictly read-only, same contract as the other _PANELS entries.
    """
    body = {
        "size": 200,
        "query": {"match_all": {}},
        "_source": ["skill_id", "occupation", "task", "quality", "source_tier",
                    "stats", "pinned", "archived", "procedure", "verification",
                    "preconditions", "failure_modes", "provenance"],
        "sort": [{"quality": {"order": "desc", "missing": "_last"}},
                 {"skill_id.keyword": "asc"}],
    }
    try:
        r = _es_search("lse-skills", body)
    except Exception as e:
        return {"error": f"lse-skills: {type(e).__name__}: {e}", "skills": []}
    hits = r.get("hits", {}).get("hits", [])
    skills = [h.get("_source", {}) for h in hits]
    return {"skills": skills, "total": len(skills),
            "archived": sum(1 for s in skills if s.get("archived"))}


KBGRAPH_MAX_ENTITIES = 500
KBGRAPH_MAX_EDGES = 2000
KBGRAPH_MAX_DOCS = 300

def kbgraph_panel() -> dict:
    """Phase 5 knowledge-graph data for the /kbgraph renderer (read-only).

    Returns entities + edges from the lse-graph ES index, bounded to
    KBGRAPH_MAX_ENTITIES / KBGRAPH_MAX_EDGES so a large materialized graph
    cannot blow the response, plus the KB docs referenced by documented_by
    edges (bounded to KBGRAPH_MAX_DOCS) so the renderer can draw evidence.
    Empty/dormant state (index missing or empty) is a clean 200 with
    dormant=true, never an error.
    """
    index = "lse-graph"
    try:
        with urllib.request.urlopen(f"{_es_url()}/{index}", timeout=_ES_TIMEOUT) as r:
            present = r.status < 300
    except Exception:
        present = False
    if not present:
        return {"entities": [], "edges": [], "docs": [],
                "counts": {"entities": 0, "edges": 0, "docs": 0},
                "dormant": True, "index_present": False, "truncated": False}
    ent_body = {"size": KBGRAPH_MAX_ENTITIES,
                "query": {"term": {"kind": "entity"}},
                "_source": ["name", "type"]}
    edge_body = {"size": KBGRAPH_MAX_EDGES,
                 "query": {"term": {"kind": "edge"}},
                 "_source": ["src", "rel", "dst", "evidence_doc_id"]}
    try:
        r_ent = _es_search(index, ent_body)
        r_edge = _es_search(index, edge_body)
    except Exception as e:
        return {"error": f"lse-graph: {type(e).__name__}: {e}",
                "entities": [], "edges": [], "docs": [],
                "counts": {"entities": 0, "edges": 0, "docs": 0},
                "dormant": True, "index_present": True, "truncated": False}
    total_ent = r_ent.get("hits", {}).get("total", {}).get("value", 0)
    total_edge = r_edge.get("hits", {}).get("total", {}).get("value", 0)
    entities = [{"id": h["_id"], "name": s.get("name") or h["_id"][:8],
                 "type": s.get("type") or "unknown"}
                for h in r_ent.get("hits", {}).get("hits", []) for s in [h.get("_source", {})]]
    edges = [{"src": s.get("src"), "rel": s.get("rel"), "dst": s.get("dst"),
              "evidence": s.get("evidence_doc_id")}
             for h in r_edge.get("hits", {}).get("hits", []) for s in [h.get("_source", {})]]
    # Evidence docs: every documented_by edge whose dst is a KB doc id (never
    # an entity id). The KB lookup degrades to docs=[] on failure - the graph
    # view must stay usable even if lse-kb is down.
    entity_ids = {e["id"] for e in entities}
    doc_ids = sorted({e["dst"] for e in edges
                      if e["rel"] == "documented_by" and e["dst"] not in entity_ids})
    docs = []
    if doc_ids:
        doc_body = {"size": KBGRAPH_MAX_DOCS,
                    "query": {"ids": {"values": doc_ids[:KBGRAPH_MAX_DOCS]}},
                    "_source": ["title", "topic", "quality_score", "source_tier",
                                "stale", "origin", "volatility", "source_url"]}
        try:
            r_docs = _es_search("lse-kb", doc_body)
            docs = [{"id": h["_id"],
                     "title": (s.get("title") or h["_id"][:8]),
                     "topic": s.get("topic") or "",
                     "quality_score": s.get("quality_score"),
                     "source_tier": s.get("source_tier") or "",
                     "stale": bool(s.get("stale")),
                     "origin": s.get("origin") or "",
                     "volatility": s.get("volatility") or "",
                     "source_url": s.get("source_url") or ""}
                    for h in r_docs.get("hits", {}).get("hits", [])
                    for s in [h.get("_source", {})]]
        except Exception:
            docs = []
    return {"entities": entities, "edges": edges, "docs": docs,
            "counts": {"entities": total_ent, "edges": total_edge,
                       "docs": len(doc_ids)},
            "dormant": total_ent == 0,
            "index_present": True,
            "truncated": (total_ent > len(entities) or total_edge > len(edges)
                          or len(doc_ids) > len(docs))}

def _kb_docs_by_ids(doc_ids) -> list:
    """Fetch KB docs by id from lse-kb (read-only, degrading).

    Returns [] on any failure so callers stay usable when lse-kb is down.
    """
    ids = sorted(set(doc_ids))[:KBGRAPH_MAX_DOCS]
    if not ids:
        return []
    body = {"size": len(ids),
            "query": {"ids": {"values": ids}},
            "_source": ["title", "topic", "quality_score", "source_tier",
                        "stale", "origin", "volatility", "source_url"]}
    try:
        r = _es_search("lse-kb", body)
    except Exception:
        return []
    out = []
    for h in r.get("hits", {}).get("hits", []):
        s = h.get("_source", {})
        out.append({"id": h["_id"],
                    "title": s.get("title") or h["_id"][:8],
                    "topic": s.get("topic") or "",
                    "quality_score": s.get("quality_score"),
                    "source_tier": s.get("source_tier") or "",
                    "stale": bool(s.get("stale")),
                    "origin": s.get("origin") or "",
                    "volatility": s.get("volatility") or "",
                    "source_url": s.get("source_url") or ""})
    return out


def kbgraph_neighbors(target: str) -> dict:
    """One-hop neighbourhood for the /kbgraph inspector (read-only).

    target = entity id: the entity, its edges, peer entities, and the KB
        docs evidencing those edges.
    target = KB doc id: the doc, one hop of edges around the entities it
        documents, and the docs referenced by those edges.
    Unknown id: clean response with known=false — never a 500.
    """
    def _empty():
        return {"entities": [], "edges": [], "docs": [],
                "counts": {"entities": 0, "edges": 0, "docs": 0}}

    if not target:
        return dict(_empty(), id="", known=False, error="missing id")
    t0 = time.monotonic()
    try:
        probe = _es_search("lse-graph", {"size": 1,
                                         "query": {"ids": {"values": [target]}},
                                         "_source": ["kind", "name", "type"]})
        ph = probe.get("hits", {}).get("hits", [{}])
        ps = ph[0].get("_source", {}) if ph else {}
        is_entity = ps.get("kind") == "entity"
        r_edges = _es_search("lse-graph", {
            "size": KBGRAPH_MAX_EDGES,
            "query": {"bool": {"should": [{"term": {"src": target}},
                                          {"term": {"dst": target}}],
                                "minimum_should_match": 1}},
            "_source": ["src", "rel", "dst", "evidence_doc_id"]})
    except Exception as e:
        return dict(_empty(), id=target, known=False,
                    error=f"lse-graph: {type(e).__name__}: {e}")
    edges = [{"src": s.get("src"), "rel": s.get("rel"), "dst": s.get("dst"),
              "evidence": s.get("evidence_doc_id")}
             for h in r_edges.get("hits", {}).get("hits", [])
             for s in [h.get("_source", {})]]
    entities = []
    if is_entity:
        entities = [{"id": target,
                     "name": ps.get("name") or target[:8],
                     "type": ps.get("type") or "unknown"}]
    else:
        # Doc target: add one hop of edges around the entities that are
        # documented_by this doc, so the inspector shows context.
        doc_peers = [e["src"] for e in edges
                     if e["rel"] == "documented_by" and e["src"] != target]
        if doc_peers:
            try:
                seen = {(e["src"], e["rel"], e["dst"], e["evidence"])
                        for e in edges}
                r_hop = _es_search("lse-graph", {
                    "size": KBGRAPH_MAX_EDGES,
                    "query": {"bool": {"should": [
                        {"terms": {"src": doc_peers}},
                        {"terms": {"dst": doc_peers}}],
                        "minimum_should_match": 1}},
                    "_source": ["src", "rel", "dst", "evidence_doc_id"]})
                for h in r_hop.get("hits", {}).get("hits", []):
                    s = h.get("_source", {})
                    e2 = {"src": s.get("src"), "rel": s.get("rel"),
                          "dst": s.get("dst"),
                          "evidence": s.get("evidence_doc_id")}
                    k = (e2["src"], e2["rel"], e2["dst"], e2["evidence"])
                    if k not in seen:
                        seen.add(k)
                        edges.append(e2)
            except Exception:
                pass
    peer_ids = sorted(({e["src"] for e in edges} | {e["dst"] for e in edges})
                      - {target})
    if peer_ids:
        try:
            r_peers = _es_search("lse-graph", {
                "size": len(peer_ids),
                "query": {"ids": {"values": peer_ids}},
                "_source": ["kind", "name", "type"]})
            have_ids = {n["id"] for n in entities}
            for h in r_peers.get("hits", {}).get("hits", []):
                s = h.get("_source", {})
                if s.get("kind") == "entity" and h["_id"] not in have_ids:
                    have_ids.add(h["_id"])
                    entities.append({"id": h["_id"],
                                     "name": s.get("name") or h["_id"][:8],
                                     "type": s.get("type") or "unknown"})
        except Exception:
            pass
    entity_ids = {n["id"] for n in entities}
    doc_ids = {e["dst"] for e in edges
               if e["rel"] == "documented_by" and e["dst"] not in entity_ids}
    if not is_entity:
        doc_ids.add(target)  # the doc itself is its own inspector node
    docs = _kb_docs_by_ids(doc_ids)
    known = is_entity or any(d["id"] == target for d in docs)
    out = dict(_empty())
    out.update({"id": target, "known": known,
                "entities": entities, "edges": edges, "docs": docs,
                "counts": {"entities": len(entities),
                           "edges": len(edges),
                           "docs": len(docs)},
                "elapsed_ms": int((time.monotonic() - t0) * 1000)})
    if not known:
        out["error"] = "unknown id"
    return out


_PANELS = {
    "/api/ui/overview": overview,
    "/api/ui/kb": kb_stats,
    "/api/ui/dream": dream_stats,
    "/api/ui/ledger": ledger_stats,
    "/api/ui/episodes": episode_stats,
    "/api/ui/perms": perms_overview,
    "/api/ui/skills": skills_panel,
    "/api/ui/backends": backend_status,
    "/api/ui/kbgraph": kbgraph_panel,
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


def select_backend(backend: str) -> dict:
    """Set the active planner backend (POST /api/ui/backends/select).

    The third deliberate write surface on this Console, and by some margin
    the narrowest: it writes one enum value to one JSON file. It cannot name
    a path, a command, a model, a URL or a credential — `backend` is
    validated against goethe_planner_state.VALID_BACKENDS before anything
    touches the filesystem, so an arbitrary string cannot get through.

    Selecting a backend with no credentials configured is ALLOWED, and
    reported back in 'warning' rather than refused. That is deliberate: an
    operator may well switch to 'claude' precisely so they can then go run
    `claude login`, and a selector that refuses to record the intent until
    the credential already exists makes that a chicken-and-egg. planner()
    still returns a clear ERROR string if it is called in the meantime.
    """
    if _planner_state is None:
        return {"error": "goethe_planner_state module not importable — "
                         "backend selection unavailable"}
    try:
        record = _planner_state.write_selection(backend, actor="console")
    except ValueError as e:
        return {"error": str(e)}
    except OSError as e:
        return {"error": f"could not persist selection: {e}"}

    result = {"status": "selected", "active": record["backend"],
              "selected_at": record["selected_at"]}
    # Advisory post-check. Never fail the write because the probe failed —
    # the selection is already durable at this point and reporting it as an
    # error would be a lie the operator then acts on.
    try:
        entry = next((b for b in backend_status().get("backends", [])
                      if b.get("id") == record["backend"]), None)
        if entry is not None:
            if not entry.get("configured", False):
                result["warning"] = (
                    f"{record['backend']} is now active but has no credentials "
                    "configured — planner() will error until it does"
                )
            elif entry.get("health") == "down":
                result["warning"] = (
                    f"{record['backend']} is now active but its health probe "
                    "is failing"
                )
    except Exception:
        pass
    return result


_PERM_ACTION_PATHS = {
    "/api/ui/perms/approve": "approve",
    "/api/ui/perms/deny": "deny",
    "/api/ui/perms/delete": "delete",
    "/api/ui/perms/revoke": "revoke",
}


# --------------------------------------------------------------------------
# ASGI router
# --------------------------------------------------------------------------

# WebSearch LB upstream (tools/websearch-lb) — loopback by deployment
# default; override for non-default ports. The /webSearch/stats proxy
# fetches {base}/stats; the static page comes from websearch-lb/frontend/.
_WEBSEARCH_LB_URL = os.environ.get(
    "GOETHE_WEBSEARCH_LB_URL", "http://127.0.0.1:9703").rstrip("/")
_WEBSEARCH_LB_TIMEOUT = 8

class UIRouter:
    """ASGI middleware: serves /ui and /api/ui/*; passes everything else
    through untouched. Sits OUTSIDE goethe_mcp._TokenGuard (so the static
    /ui page loads in a plain browser) and does its own token check on
    /api/ui/* using the same header normalisation as _TokenGuard."""

    def __init__(self, app, token: str = "", html_path: str = "",
                 traum_controller=None):
        self.app = app
        self.token = token or ""
        self.html_path = html_path or os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "goethe_dashboard.html")
        self._traum = traum_controller
        self._traum_init_attempted = traum_controller is not None
        self._traum_init_error = None
        # node3090 remote-services prober (daemon thread; 30s interval;
        # writes /opt/local-se/state/node3090_services.json for the
        # read-only /webSearch/nodes route). Optional: a failure here
        # degrades the dashboard panel, never the gateway.
        self.node3090_prober = None
        if Node3090Prober is not None:
            try:
                self.node3090_prober = Node3090Prober()
                self.node3090_prober.start()
            except Exception:
                self.node3090_prober = None

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

    def _traum_controller(self):
        """Lazily construct the controller so non-TRAUM routes never create
        its SQLite database or depend on its deployment being complete."""
        if not self._traum_init_attempted:
            self._traum_init_attempted = True
            try:
                if _traum_control is None:
                    raise RuntimeError("traum_controller module not importable")
                self._traum = _traum_control.TraumController()
            except Exception as exc:
                self._traum_init_error = exc
        if self._traum is None:
            exc = self._traum_init_error or RuntimeError(
                "TRAUM controller unavailable")
            raise RuntimeError(f"{type(exc).__name__}: {exc}")
        return self._traum

    @staticmethod
    def _query(scope) -> dict:
        raw = scope.get("query_string", b"")
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        return urllib.parse.parse_qs(raw, keep_blank_values=True)

    @staticmethod
    def _one_query(query: dict, name: str, default=None):
        values = query.get(name)
        if not values:
            return default
        if len(values) != 1:
            raise ValueError(f"query parameter {name!r} may appear once")
        return values[0]

    def _websearch_nodes(self) -> dict:
        """node3090 remote-service status for the /webSearch dashboard.
        Sync (run via asyncio.to_thread). File reads only - the prober
        daemon in this gateway refreshes node3090_services.json every
        30s. Fail-safe: missing/corrupt state degrades to
        {'services': [], 'error': 'state missing'}; never raw-500s."""
        state_dir = os.environ.get("GOETHE_WEBSEARCH_STATE_DIR",
                                   "/opt/local-se/state")
        n_path = state_dir + "/node3090_services.json"
        try:
            with open(n_path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("services"), list):
                return data
            return {"services": [], "error": "state missing"}
        except (OSError, ValueError):
            return {"services": [], "error": "state missing"}

    def _websearch_stats(self) -> dict:
        """GET {_WEBSEARCH_LB_URL}/stats and return the parsed JSON object.
        Sync (run via asyncio.to_thread). Fail-safe contract: any
        network/parse failure degrades to {"error": ...} — the gateway
        never raw-500s a UI proxy route."""
        req = urllib.request.Request(
            f"{_WEBSEARCH_LB_URL}/stats",
            headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=_WEBSEARCH_LB_TIMEOUT) as r:
                body = r.read()
        except Exception as e:
            return {"error": f"websearch-lb /stats unreachable: "
                             f"{type(e).__name__}: {e}"}
        try:
            data = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            return {"error": f"websearch-lb /stats returned non-JSON: {e}"}
        if not isinstance(data, dict):
            return {"error": "websearch-lb /stats did not return a JSON object"}
        return data

    def _websearch_quota(self) -> dict:
        """Tavily (gateway-primary) quota/status for the /webSearch dashboard.
        Sync (run via asyncio.to_thread). File reads only —
        tavily_quota.json is refreshed on demand only (after a successful
        search via WebMixin._tavily_refresh_quota, rate-limited to 10 min;
        NO background probe); this route never touches the network and never
        reads the key file.
        Fail-safe: missing state degrades to {"configured": False}."""
        state_dir = os.environ.get("GOETHE_WEBSEARCH_STATE_DIR",
                                   "/opt/local-se/state")
        out = {"configured": False, "plan": None, "limit": None,
               "usage": None, "remaining": None, "usage_checked_at": None,
               "last_query_ts": None}
        q_path = state_dir + "/tavily_quota.json"
        try:
            with open(q_path, encoding="utf-8") as f:
                q = json.load(f)
            acct = (q.get("raw") or {}).get("account") or {}
            limit = acct.get("plan_limit")
            usage = acct.get("plan_usage")
            if q.get("checked_at") or acct.get("current_plan"):
                out.update({
                    "configured": True,
                    "plan": acct.get("current_plan"),
                    "limit": limit,
                    "usage": usage,
                    "remaining": (None if (limit is None or usage is None)
                                  else limit - usage),
                    "usage_checked_at": q.get("checked_at"),
                })
        except (OSError, ValueError):
            pass
        log_path = state_dir + "/websearch_log.jsonl"
        try:
            with open(log_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if rec.get("backend") == "tavily":
                        out["last_query_ts"] = rec.get("ts")
        except OSError:
            pass
        return out

    # Fixed, argument-free command. Deliberately a module-level constant and
    # not built from request data — see _open_sync_terminal.
    _SYNC_CMD = "goethe-perm sync-sudoers"

    def _open_sync_terminal(self) -> dict:
        """Open a terminal window with the sync command ready to run.

        WHY THIS DOES NOT WIDEN THE TRUST BOUNDARY. The module docstring above
        states that the Console never writes /etc/sudoers.d/goethe-grants, and
        that making a sudo grant effective at the OS level requires a human at
        a terminal. That is still true after this method exists:

          - It does NOT run `goethe-perm sync-sudoers`. It launches an
            interactive terminal with that text pre-typed and NOT executed
            (no trailing newline is sent). The operator reads it, presses
            Enter if they agree, and then still authenticates to sudo, because
            _sync() shells out to `sudo install` and there is no NOPASSWD rule
            for it.
          - It therefore cannot install a sudoers rule, escalate privilege, or
            act while nobody is watching. It removes the friction of
            remembering the command, nothing more.
          - The command is the fixed constant _SYNC_CMD. No part of it comes
            from the request body, the query string, or the database, so there
            is no injection surface: the argv below contains no interpolated
            caller-controlled data.

        Mechanism: WSL2 -> Windows interop. Windows Terminal is preferred; a
        plain conhost window is the fallback. If interop is unavailable (a
        headless host, or the Console reached from another machine) this
        returns ok=false with the command, and the UI falls back to
        copy-to-clipboard so the operator is never stuck.
        """
        import shlex  # noqa: PLC0415
        import subprocess  # noqa: PLC0415

        distro = os.environ.get("WSL_DISTRO_NAME", "")
        if not distro or not os.path.exists("/mnt/c/Windows/System32/wsl.exe"):
            return {
                "ok": False,
                "command": self._SYNC_CMD,
                "error": "no WSL interop on this host — copy the command "
                         "and run it in a terminal",
            }

        # `read -e -i <text>` pre-fills the prompt WITHOUT executing it, so the
        # operator sees exactly what will run and confirms with Enter.
        inner = (
            "printf '%s\\n' "
            + shlex.quote("Review, then press Enter to run (sudo will prompt):")
            + "; read -e -i " + shlex.quote(self._SYNC_CMD) + " -r _c"
            + '; eval "$_c"'
            + "; printf '%s\\n' 'done — press Enter to close'; read -r _"
        )
        wsl_argv = ["/mnt/c/Windows/System32/wsl.exe", "-d", distro,
                    "--", "bash", "-lic", inner]

        wt = ("/mnt/c/Users/" + os.environ.get("WIN_USER", "SY5")
              + "/AppData/Local/Microsoft/WindowsApps/wt.exe")
        candidates = []
        if os.path.exists(wt):
            candidates.append(
                [wt, "new-tab", "--title", "goethe-perm sync-sudoers"]
                + wsl_argv)
        candidates.append(wsl_argv)

        for argv in candidates:
            try:
                subprocess.Popen(
                    argv, stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    start_new_session=True)
                return {"ok": True, "command": self._SYNC_CMD,
                        "note": "terminal opened — the command is pre-typed "
                                "but NOT executed; press Enter to run it, "
                                "then authenticate to sudo"}
            except OSError:
                continue
        return {"ok": False, "command": self._SYNC_CMD,
                "error": "could not launch a terminal — copy the command "
                         "and run it yourself"}

    async def _traum_response(self, send, fn, *args, **kwargs):
        t0 = time.monotonic()
        try:
            data = await asyncio.to_thread(fn, *args, **kwargs)
            status = 200
        except Exception as exc:
            if _traum_control is not None and isinstance(
                    exc, _traum_control.TraumControlError):
                status = exc.status
                data = {"error": str(exc)}
            elif (_traum_control is not None
                  and getattr(_traum_control, "traum_state", None) is not None
                  and isinstance(exc, _traum_control.traum_state.NotFoundError)):
                status = 404
                data = {"error": str(exc)}
            elif (_traum_control is not None
                  and getattr(_traum_control, "traum_state", None) is not None
                  and isinstance(exc, _traum_control.traum_state.ConflictError)):
                status = 409
                data = {"error": str(exc)}
            elif isinstance(exc, (TypeError, ValueError, json.JSONDecodeError)):
                status = 400
                data = {"error": f"bad request: {exc}"}
            else:
                status = 503
                data = {"error": f"{type(exc).__name__}: {exc}"}
        data["_elapsed_ms"] = int((time.monotonic() - t0) * 1000)
        await self._respond(
            send, status,
            json.dumps(data, ensure_ascii=False, default=str).encode(),
            "application/json")

    async def _handle_traum(self, scope, receive, send, path: str,
                            method: str) -> None:
        """Dispatch the narrow typed TRAUM surface.

        No route accepts executable names, argv, paths, environment variables,
        PIDs, systemd units, or timer mutations.  Dynamic path components are
        opaque state IDs and are validated again by TraumController.
        """
        try:
            ctl = self._traum_controller()
        except Exception as exc:
            await self._traum_response(
                send, lambda e=exc: (_ for _ in ()).throw(e))
            return

        query = self._query(scope)
        if method == "GET" and path == "/api/ui/traum/status":
            await self._traum_response(send, ctl.status)
            return
        if method == "GET" and path == "/api/ui/traum/timer":
            await self._traum_response(send, ctl.timer_status)
            return
        if method == "GET" and path == "/api/ui/traum/runs":
            try:
                archived = self._one_query(query, "archived", "false")
                if archived not in ("true", "false"):
                    raise ValueError("archived must be true or false")
                limit = int(self._one_query(query, "limit", "50"))
            except (TypeError, ValueError) as exc:
                await self._traum_response(
                    send, lambda e=exc: (_ for _ in ()).throw(e))
                return
            await self._traum_response(
                send, ctl.list_runs,
                include_archived=(archived == "true"), limit=limit)
            return
        if method == "GET" and path == "/api/ui/traum/proposals":
            try:
                proposal_state = self._one_query(query, "state", None)
                limit = int(self._one_query(query, "limit", "200"))
                offset = int(self._one_query(query, "offset", "0"))
                actionable = self._one_query(query, "actionable", "false")
                if actionable not in ("true", "false"):
                    raise ValueError("actionable must be true or false")
            except (TypeError, ValueError) as exc:
                await self._traum_response(
                    send, lambda e=exc: (_ for _ in ()).throw(e))
                return
            await self._traum_response(
                send, ctl.list_proposals, state=proposal_state, limit=limit,
                offset=offset, actionable_only=(actionable == "true"))
            return

        match = re.fullmatch(r"/api/ui/traum/runs/([^/]+)", path)
        if method == "GET" and match:
            await self._traum_response(send, ctl.get_run, match.group(1))
            return
        match = re.fullmatch(r"/api/ui/traum/runs/([^/]+)/logs", path)
        if method == "GET" and match:
            try:
                attempt_id = self._one_query(query, "attempt_id", None)
                limit = int(self._one_query(query, "limit", "200"))
            except (TypeError, ValueError) as exc:
                await self._traum_response(
                    send, lambda e=exc: (_ for _ in ()).throw(e))
                return
            await self._traum_response(
                send, ctl.logs, match.group(1),
                attempt_id=attempt_id, limit=limit)
            return

        if method == "POST" and path == "/api/ui/traum/runs":
            try:
                payload = await self._read_json_body(receive)
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                await self._traum_response(
                    send, lambda e=exc: (_ for _ in ()).throw(e))
                return
            await self._traum_response(send, ctl.start_run, payload)
            return

        if method == "POST" and path == "/api/ui/traum/proposals/revalidate":
            try:
                payload = await self._read_json_body(receive)
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                await self._traum_response(
                    send, lambda e=exc: (_ for _ in ()).throw(e))
                return
            await self._traum_response(send, ctl.revalidate_queue, payload)
            return

        post_routes = (
            (r"/api/ui/traum/runs/([^/]+)/retry", "retry"),
            (r"/api/ui/traum/runs/([^/]+)/cancel", "cancel"),
            (r"/api/ui/traum/runs/([^/]+)/archive", "archive_run"),
            (r"/api/ui/traum/attempts/([^/]+)/acknowledge", "acknowledge_attempt"),
            (r"/api/ui/traum/proposals/([^/]+)/preview", "preview_proposal"),
            (r"/api/ui/traum/proposals/([^/]+)/decision", "decide_proposal"),
        )
        if method == "POST":
            for pattern, method_name in post_routes:
                match = re.fullmatch(pattern, path)
                if match:
                    try:
                        payload = await self._read_json_body(receive)
                    except (TypeError, ValueError, json.JSONDecodeError) as exc:
                        await self._traum_response(
                            send, lambda e=exc: (_ for _ in ()).throw(e))
                        return
                    await self._traum_response(
                        send, getattr(ctl, method_name), match.group(1), payload)
                    return

        await self._respond(
            send, 404, b'{"error":"unknown TRAUM route"}',
            "application/json")

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

        if path in ("/kbgraph", "/kbgraph/") and method == "GET":
            # Phase 5 graph renderer: same posture as /ui — static page with
            # no data of its own; data comes from the token-gated
            # /api/ui/kbgraph panel that the page fetches with the token
            # (shared localStorage key "goethe_token").
            kb_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "goethe_kbgraph.html")
            try:
                with open(kb_path, "rb") as f:
                    html = f.read()
                await self._respond(send, 200, html, "text/html; charset=utf-8")
            except OSError as e:
                await self._respond(
                    send, 500,
                    f"goethe_kbgraph.html not found: {e}".encode(),
                    "text/plain")
            return

        # WebSearch LB console — static page, same posture as /ui (no token,
        # no data of its own; the page fetches /webSearch/stats same-origin).
        if path in ("/webSearch", "/webSearch/") and method == "GET":
            wb_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "websearch-lb", "frontend", "index.html")
            try:
                with open(wb_path, "rb") as f:
                    html = f.read()
                await self._respond(send, 200, html, "text/html; charset=utf-8")
            except OSError as e:
                await self._respond(
                    send, 500,
                    f"websearch-lb/frontend/index.html not found: {e}".encode(),
                    "text/plain")
            return

        # /webSearch/stats — same-origin proxy to the loopback websearch-lb
        # /stats. Deliberately NOT token-gated: the frontend contract
        # (websearch-frontend/brief.md) sends Bearer tokens on /mcp* requests
        # only, so a gated proxy would 401 every poll in served mode. The
        # upstream WEBSEARCH_LB_TOKEN remains the auth boundary for this data.
        if path == "/webSearch/stats" and method == "GET":
            t0 = time.monotonic()
            data = await asyncio.to_thread(self._websearch_stats)
            data["_elapsed_ms"] = int((time.monotonic() - t0) * 1000)
            await self._respond(
                send, 200 if "error" not in data else 502,
                json.dumps(data, ensure_ascii=False, default=str).encode(),
                "application/json")
            return

        # /webSearch/quota — same ungated posture as /webSearch/stats: the
        # console (unauthenticated static page) needs the gateway-primary
        # Tavily status on the same poll cycle. File reads only; serves
        # plan/counts/timestamps, never the key, never query text.
        if path == "/webSearch/quota" and method == "GET":
            data = await asyncio.to_thread(self._websearch_quota)
            await self._respond(
                send, 200,
                json.dumps(data, ensure_ascii=False, default=str).encode(),
                "application/json")
            return

        # /webSearch/nodes - same ungated posture as /webSearch/quota:
        # the static console page needs node3090 remote-service status on
        # the same poll cycle. File reads only (the prober daemon writes
        # it); serves up/down, latency and timestamps - nothing else.
        if path == "/webSearch/nodes" and method == "GET":
            data = await asyncio.to_thread(self._websearch_nodes)
            await self._respond(
                send, 200,
                json.dumps(data, ensure_ascii=False, default=str).encode(),
                "application/json")
            return

        # Deep Search console — same posture as /ui: static page, no token;
        # data comes from the token-gated /deepSearch/* JSON endpoints the
        # page fetches with the shared localStorage key "goethe_token".
        # Served per request (file read on each hit) so HTML edits apply
        # without a gateway restart (spec section 11).
        if path in ("/deepSearch", "/deepSearch/") and method == "GET":
            ds_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "deep_search.html")
            try:
                with open(ds_path, "rb") as f:
                    html = f.read()
                await self._respond(send, 200, html, "text/html; charset=utf-8")
            except OSError as e:
                await self._respond(
                    send, 500,
                    f"deep_search.html not found: {e}".encode(),
                    "text/plain")
            return

        # Deep Search topic index — token-gated, read-only file read (spec §6;
        # same posture as the /api/ui/* endpoints).
        if path == "/deepSearch/topics" and method == "GET":
            if not self._authorized(scope):
                await self._respond(
                    send, 401, b'{"error":"unauthorized"}',
                    "application/json")
                return
            try:
                data = await asyncio.to_thread(
                    _deep_search_read_json,
                    os.path.join(DEEP_SEARCH_STATE_DIR, "topics.json"))
            except (OSError, json.JSONDecodeError) as e:
                await self._respond(
                    send, 500,
                    json.dumps({"error": f"read topics.json: {e}"}).encode(),
                    "application/json")
                return
            await self._respond(
                send, 200,
                json.dumps(data, ensure_ascii=False, default=str).encode(),
                "application/json")
            return

        # Deep Search read one topic dossier — token-gated (spec §6).
        if (path.startswith("/deepSearch/topics/") and method == "GET"
                and path != "/deepSearch/topics/"):
            if not self._authorized(scope):
                await self._respond(
                    send, 401, b'{"error":"unauthorized"}',
                    "application/json")
                return
            tid = path[len("/deepSearch/topics/"):]
            if ("/" in tid or not tid or "." in tid
                    or not all(c.isalnum() or c in "-_" for c in tid)):
                await self._respond(
                    send, 400, b'{"error":"invalid topic id"}',
                    "application/json")
                return
            tpath = os.path.join(DEEP_SEARCH_STATE_DIR, "topics",
                                 os.path.basename(tid) + ".json")
            if not os.path.isfile(tpath):
                await self._respond(
                    send, 404,
                    json.dumps({"error": f"topic not found: {tid}"}).encode(),
                    "application/json")
                return
            try:
                dossier = _deep_search_read_json(tpath)
            except json.JSONDecodeError as e:
                await self._respond(
                    send, 500,
                    json.dumps({"error": f"corrupt dossier: {e}"}).encode(),
                    "application/json")
                return
            await self._respond(
                send, 200,
                json.dumps(dossier, ensure_ascii=False, default=str).encode(),
                "application/json")
            return

        # Deep Search delete topic — token-gated write (spec §6). Removes
        # the dossier file, the topics.json index entry, and every
        # runs/<run_id>/ directory listed in the dossier's passes.
        # Fail-closed: a run dir is removed only if its state.json is
        # absent OR confirms topic_id == tid. 409 while the topic has an
        # active QUEUED|RUNNING pass; 404 when the dossier is missing.
        if (path.startswith("/deepSearch/topics/") and method == "DELETE"
                and len(path.split("/")) == 4):
            if not self._authorized(scope):
                await self._respond(
                    send, 401, b'{"error":"unauthorized"}',
                    "application/json")
                return
            tid = path[len("/deepSearch/topics/"):]
            if (not tid or "/" in tid or "." in tid
                    or not all(c.isalnum() or c in "-_" for c in tid)):
                await self._respond(
                    send, 400, b'{"error":"invalid topic id"}',
                    "application/json")
                return
            try:
                data = await asyncio.to_thread(_deep_search_delete_topic, tid)
            except FileNotFoundError as e:
                await self._respond(
                    send, 404,
                    json.dumps({"error": str(e)}).encode(),
                    "application/json")
                return
            except PermissionError as e:
                await self._respond(
                    send, 409,
                    json.dumps({"error": str(e)}).encode(),
                    "application/json")
                return
            except (OSError, json.JSONDecodeError) as e:
                await self._respond(
                    send, 500,
                    json.dumps({"error": f"delete topic: {e}"}).encode(),
                    "application/json")
                return
            await self._respond(
                send, 200,
                json.dumps(data, ensure_ascii=False, default=str).encode(),
                "application/json")
            return

        # Deep Search read one run state — token-gated, READ-ONLY (contract
        # v0.3 §5: runs/<run_id>/state.json is the UI poll target).
        if (path.startswith("/deepSearch/runs/") and method == "GET"
                and path != "/deepSearch/runs/"
                and not path.endswith("/result")):
            if not self._authorized(scope):
                await self._respond(
                    send, 401, b'{"error":"unauthorized"}',
                    "application/json")
                return
            rid = path[len("/deepSearch/runs/"):]
            if ("/" in rid or not rid or "." in rid
                    or not all(c.isalnum() or c in "-_" for c in rid)):
                await self._respond(
                    send, 400, b'{"error":"invalid run id"}',
                    "application/json")
                return
            spath = os.path.join(DEEP_SEARCH_STATE_DIR, "runs",
                                 os.path.basename(rid), "state.json")
            if not os.path.isfile(spath):
                await self._respond(
                    send, 404,
                    json.dumps({"error": f"run not found: {rid}"}).encode(),
                    "application/json")
                return
            try:
                rstate = _deep_search_read_json(spath)
            except json.JSONDecodeError as e:
                await self._respond(
                    send, 500,
                    json.dumps({"error": f"corrupt run state: {e}"}).encode(),
                    "application/json")
                return
            await self._respond(
                send, 200,
                json.dumps(rstate, ensure_ascii=False, default=str).encode(),
                "application/json")
            return

        # Deep Search read one run RESULT — token-gated, READ-ONLY
        # (runs/<run_id>/result.json, terminal artifact).
        if (path.startswith("/deepSearch/runs/") and method == "GET"
                and path.endswith("/result")):
            if not self._authorized(scope):
                await self._respond(
                    send, 401, b'{"error":"unauthorized"}',
                    "application/json")
                return
            rid = path[len("/deepSearch/runs/"):-len("/result")]
            if ("/" in rid or not rid or "." in rid
                    or not all(c.isalnum() or c in "-_" for c in rid)):
                await self._respond(
                    send, 400, b'{"error":"invalid run id"}',
                    "application/json")
                return
            respath = os.path.join(DEEP_SEARCH_STATE_DIR, "runs",
                                   os.path.basename(rid), "result.json")
            if not os.path.isfile(respath):
                await self._respond(
                    send, 404,
                    json.dumps({"error": f"result not found: {rid}"}).encode(),
                    "application/json")
                return
            try:
                result = _deep_search_read_json(respath)
            except json.JSONDecodeError as e:
                await self._respond(
                    send, 500,
                    json.dumps({"error": f"corrupt result: {e}"}).encode(),
                    "application/json")
                return
            await self._respond(
                send, 200,
                json.dumps(result, ensure_ascii=False, default=str).encode(),
                "application/json")
            return

        # Deep Search start a pass — token-gated, spawns detached worker.
        if (method == "POST" and path.startswith("/deepSearch/topics/")
                and path.endswith("/passes")
                and len(path.split("/")) == 5):
            if not self._authorized(scope):
                await self._respond(
                    send, 401, b'{"error":"unauthorized"}',
                    "application/json")
                return
            tid = path[len("/deepSearch/topics/"):-len("/passes")]
            if (not tid or "/" in tid or "." in tid
                    or not all(c.isalnum() or c in "-_" for c in tid)):
                await self._respond(
                    send, 400, b'{"error":"invalid topic id"}',
                    "application/json")
                return
            tpath = os.path.join(DEEP_SEARCH_STATE_DIR, "topics",
                                 tid + ".json")
            if not os.path.isfile(tpath):
                await self._respond(
                    send, 404,
                    json.dumps({"error": f"topic not found: {tid}"}).encode(),
                    "application/json")
                return
            try:
                payload = await self._read_json_body(receive)
                question = str(payload.get("question", "")).strip()
                instructions = str(payload.get("instructions", "")).strip()
                max_steps = int(payload.get("max_steps", 8))
                max_sources = int(payload.get("max_sources", 10))
            except (ValueError, json.JSONDecodeError) as e:
                await self._respond(
                    send, 400,
                    json.dumps({"error": f"bad body: {e}"}).encode(),
                    "application/json")
                return
            if not question:
                await self._respond(
                    send, 400, b'{"error":"question is required"}',
                    "application/json")
                return
            max_steps = max(1, min(50, max_steps))
            max_sources = max(1, min(30, max_sources))
            try:
                data = await asyncio.to_thread(
                    _deep_search_spawn_pass, tid, question, instructions,
                    max_steps, max_sources)
            except PermissionError as e:
                await self._respond(
                    send, 409,
                    json.dumps({"error": str(e)}).encode(),
                    "application/json")
                return
            except (OSError, ValueError) as e:
                await self._respond(
                    send, 500,
                    json.dumps({"error": f"spawn pass: {e}"}).encode(),
                    "application/json")
                return
            await self._respond(
                send, 202,
                json.dumps(data, ensure_ascii=False, default=str).encode(),
                "application/json")
            return

        # Deep Search create topic — token-gated write (spec §6).
        if path == "/deepSearch/topics" and method == "POST":
            if not self._authorized(scope):
                await self._respond(
                    send, 401, b'{"error":"unauthorized"}',
                    "application/json")
                return
            try:
                payload = await self._read_json_body(receive)
                title = str(payload.get("title", "")).strip()
            except (ValueError, json.JSONDecodeError) as e:
                await self._respond(
                    send, 400,
                    json.dumps({"error": f"bad body: {e}"}).encode(),
                    "application/json")
                return
            if not title:
                await self._respond(
                    send, 400, b'{"error":"title is required"}',
                    "application/json")
                return
            try:
                data = await asyncio.to_thread(_deep_search_create_topic, title)
            except ValueError as e:
                await self._respond(
                    send, 409,
                    json.dumps({"error": str(e)}).encode(),
                    "application/json")
                return
            except (OSError, json.JSONDecodeError) as e:
                await self._respond(
                    send, 500,
                    json.dumps({"error": f"create topic: {e}"}).encode(),
                    "application/json")
                return
            await self._respond(
                send, 201,
                json.dumps(data, ensure_ascii=False, default=str).encode(),
                "application/json")
            return

        if path == "/api/ui/kbgraph/neighbors" and method == "GET":
            if not self._authorized(scope):
                await self._respond(
                    send, 401, b'{"error":"unauthorized"}',
                    "application/json")
                return
            q = urllib.parse.parse_qs(
                scope.get("query_string", b"").decode(),
                keep_blank_values=True)
            target = self._one_query(q, "id", None)
            if not target:
                await self._respond(
                    send, 400,
                    b'{"error":"missing id query parameter"}',
                    "application/json")
                return
            t0 = time.monotonic()
            try:
                data = await asyncio.to_thread(kbgraph_neighbors, target)
            except Exception as e:  # fail-safe: degrade, never 500 raw
                data = {"error": f"{type(e).__name__}: {e}"}
            data["_elapsed_ms"] = int((time.monotonic() - t0) * 1000)
            await self._respond(
                send, 200,
                json.dumps(data, ensure_ascii=False, default=str).encode(),
                "application/json")
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

        # TRAUM is independently token-gated but deliberately does not use
        # or alter the goethe_perms / Active Grants plane.
        if path.startswith("/api/ui/traum"):
            # Unlike the historical localhost-only read panels, this control
            # surface fails closed when no token is configured.  Production
            # binds the gateway beyond loopback; mutation without explicit
            # authentication is never permitted.
            if not self.token:
                await self._respond(
                    send, 503,
                    b'{"error":"TRAUM controls disabled: gateway token not configured"}',
                    "application/json")
                return
            if not self._authorized(scope):
                await self._respond(send, 401, b'{"error":"unauthorized"}',
                                    "application/json")
                return
            await self._handle_traum(scope, receive, send, path, method)
            return

        if path == "/api/ui/backends/select" and method == "POST":
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
                select_backend, payload.get("backend", ""))
            await self._respond(
                send, 400 if "error" in data else 200,
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

        # Episode corpus hygiene -- quarantine-only write surface. See the
        # module docstring's ROUTES section and
        # docs/SPEC-console-corpus-hygiene-2026-08.md. Preview never writes;
        # purge only ever moves files (never deletes) and only accepts
        # explicit session_ids, never a pattern.
        if path == "/api/ui/episodes/purge-preview" and method == "GET":
            if not self._authorized(scope):
                await self._respond(send, 401, b'{"error":"unauthorized"}',
                                    "application/json")
                return
            query = self._query(scope)
            try:
                tool = self._one_query(query, "tool", "")
            except ValueError as e:
                await self._respond(
                    send, 400,
                    json.dumps({"error": str(e)}).encode(),
                    "application/json")
                return
            t0 = time.monotonic()
            data = await asyncio.to_thread(episode_purge_preview, tool)
            data["_elapsed_ms"] = int((time.monotonic() - t0) * 1000)
            await self._respond(
                send, 400 if "error" in data else 200,
                json.dumps(data, ensure_ascii=False, default=str).encode(),
                "application/json")
            return

        if path == "/api/ui/episodes/purge" and method == "POST":
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
                episode_purge, payload.get("session_ids"),
                payload.get("reason", ""))
            await self._respond(
                send, 400 if "error" in data else 200,
                json.dumps(data, ensure_ascii=False, default=str).encode(),
                "application/json")
            return

        # Open a terminal with `goethe-perm sync-sudoers` ready to run.
        # DOES NOT SYNC. See _open_sync_terminal for why this does not widen
        # the trust boundary described in the module docstring.
        if path == "/api/ui/perms/sync-terminal" and method == "POST":
            if not self._authorized(scope):
                await self._respond(send, 401, b'{"error":"unauthorized"}',
                                    "application/json")
                return
            result = self._open_sync_terminal()
            await self._respond(
                send, 200 if result.get("ok") else 503,
                json.dumps(result, ensure_ascii=False).encode(),
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


# ──────────────────────────────────────────────────────────────────────────
# Deep Search Dashboard (spec: tools/DEEP_SEARCH_DASHBOARD_SPEC.md v0.3)
# State layout: /opt/local-se/state/deep_search/{topics.json, topics/,
#               runs/<run_id>/, promotions.json}
# Single-writer rules + atomic writes per spec §2.
# ──────────────────────────────────────────────────────────────────────────

DEEP_SEARCH_STATE_DIR = os.environ.get(
    "DEEP_SEARCH_STATE_DIR", "/opt/local-se/state/deep_search")


def _deep_search_read_json(path: str):
    """Read + parse a Deep Search state file. Read-only by contract (spec §2)."""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _deep_search_write_json_atomic(path: str, data) -> None:
    """Atomic write: <path>.tmp → fsync → os.replace (spec §2)."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _deep_search_generate_run_id() -> str:
    """run_id = ds-<UTC:%Y%m%dT%H%M%S>-<4hex> (spec §2)."""
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y%m%dT%H%M%S")
    return f"ds-{stamp}-{os.urandom(2).hex()}"


def _deep_search_generate_topic_id(title: str) -> str:
    """topic_id = topic-<slug> (spec §2)."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if not slug:
        slug = "untitled"
    return f"topic-{slug[:48].rstrip('-')}"


def _deep_search_now() -> str:
    return datetime.datetime.now(
        datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _deep_search_create_topic(title: str) -> dict:
    """POST /deepSearch/topics handler body (spec §3/§6). Atomic: dossier
    file first, then the topics.json index rewrite. Duplicate topic_id is
    raised as ValueError (route maps it to 409)."""
    tid = _deep_search_generate_topic_id(title)
    tpath = os.path.join(DEEP_SEARCH_STATE_DIR, "topics", tid + ".json")
    if os.path.exists(tpath):
        raise ValueError(f"topic already exists: {tid}")
    now = _deep_search_now()
    dossier = {
        "id": tid, "title": title, "status": "researching",
        "created_at": now, "updated_at": now,
        "passes": [], "findings": [], "sources": [],
        "convergence": {"open_questions": 0, "contradictions": 0,
                        "stable_passes": 0, "kb_covered": False,
                        "sufficient": False},
        "handoff": None,
        "budget": {"steps": 0, "sources_fetched": 0, "passes": 0},
    }
    _deep_search_write_json_atomic(tpath, dossier)
    ipath = os.path.join(DEEP_SEARCH_STATE_DIR, "topics.json")
    index = _deep_search_read_json(ipath)
    if not isinstance(index, list):
        index = []
    index.append({"id": tid, "title": title, "status": "researching",
                  "updated_at": now})
    _deep_search_write_json_atomic(ipath, index)
    return {"id": tid, "title": title, "status": "researching"}


def _deep_search_delete_topic(tid: str) -> dict:
    """DELETE /deepSearch/topics/{tid} handler body (spec §6). Deletes the
    dossier file, the topics.json index entry, and every runs/<run_id>/
    directory listed in the dossier's passes. Fail-closed: a run directory
    is removed only when its state.json is absent (run died before the
    terminal write) OR confirms topic_id == tid. Active QUEUED|RUNNING
    passes for this topic raise PermissionError (route maps to 409)."""
    tpath = os.path.join(DEEP_SEARCH_STATE_DIR, "topics", tid + ".json")
    if not os.path.isfile(tpath):
        raise FileNotFoundError(f"topic not found: {tid}")
    try:
        dossier = _deep_search_read_json(tpath)
    except json.JSONDecodeError:
        dossier = {}
    listed = []
    passes = dossier.get("passes", []) if isinstance(dossier, dict) else []
    for p in passes:
        rid = p if isinstance(p, str) else str((p or {}).get("run_id", ""))
        if rid:
            listed.append(rid)
    active = [a for a in _deep_search_active_runs(DEEP_SEARCH_STATE_DIR)
              if a["topic_id"] == tid]
    if active:
        raise PermissionError(
            "topic has active run(s) "
            + ", ".join(a["run_id"] for a in active)
            + " — wait for the pass to finish before deleting")
    deleted_runs = []
    for rid in listed:
        if ("/" in rid or not rid or "." in rid
                or not all(c.isalnum() or c in "-_" for c in rid)):
            continue
        rdir = os.path.join(DEEP_SEARCH_STATE_DIR, "runs", rid)
        if not os.path.isdir(rdir):
            continue
        spath = os.path.join(rdir, "state.json")
        if os.path.isfile(spath):
            try:
                st = _deep_search_read_json(spath)
                if str((st or {}).get("topic_id", "")) != tid:
                    continue  # fail-closed: state.json says another topic
            except (OSError, json.JSONDecodeError):
                continue  # fail-closed: corrupt state, leave for forensics
        shutil.rmtree(rdir)
        deleted_runs.append(rid)
    os.remove(tpath)
    ipath = os.path.join(DEEP_SEARCH_STATE_DIR, "topics.json")
    index = _deep_search_read_json(ipath)
    if not isinstance(index, list):
        index = []
    index = [e for e in index
             if not (isinstance(e, dict) and e.get("id") == tid)]
    _deep_search_write_json_atomic(ipath, index)
    return {"deleted_topic": tid, "deleted_runs": deleted_runs}


def _deep_search_active_runs(state_dir: str):
    """Active runs from runs/<run_id>/state.json (status QUEUED|RUNNING).
    Corrupt files are skipped — a broken state file must not wedge the cap."""
    out = []
    rdir = os.path.join(state_dir, "runs")
    if not os.path.isdir(rdir):
        return out
    for name in os.listdir(rdir):
        spath = os.path.join(rdir, name, "state.json")
        if not os.path.isfile(spath):
            continue
        try:
            st = _deep_search_read_json(spath)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(st, dict):
            continue
        if str(st.get("status", "")).upper() in ("QUEUED", "RUNNING"):
            out.append({"run_id": name,
                        "topic_id": str(st.get("topic_id", "")),
                        "status": str(st.get("status", ""))})
    return out


def _deep_search_spawn_pass(tid, question, instructions,
                            max_steps, max_sources):
    """POST .../passes handler body (spec §5/§6). Detached worker via
    Popen(start_new_session=True) == setsid: survives gateway restart.
    Concurrency caps: 2 global, 1 per topic. Secrets inherited from the
    gateway env (GOETHE_PLANNER_FORCE_API_KEY etc)."""
    active = _deep_search_active_runs(DEEP_SEARCH_STATE_DIR)
    if len(active) >= 2:
        raise PermissionError(
            "global concurrency cap reached (max 2 active runs)")
    if any(a["topic_id"] == tid for a in active):
        raise PermissionError(f"topic {tid} already has an active pass")
    now = _deep_search_now()
    run_id = "ds-" + now.replace("-", "").replace(":", "").replace(
        "Z", "") + "-" + uuid.uuid4().hex[:4]
    rdir = os.path.join(DEEP_SEARCH_STATE_DIR, "runs", run_id)
    os.makedirs(os.path.join(rdir, "worker.audit"), exist_ok=True)
    logf = open(os.path.join(rdir, "worker.out"), "ab")
    env = dict(os.environ)
    env["DEEP_SEARCH_LOG_DIR"] = os.path.join(rdir, "worker.audit")
    here = os.path.dirname(os.path.abspath(__file__))
    worker = os.path.join(here, "deep_search_worker.py")
    proc = subprocess.Popen(
        [sys.executable, worker, run_id, tid, question, instructions,
         str(max_steps), str(max_sources), DEEP_SEARCH_STATE_DIR],
        stdout=logf, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        env=env,
        cwd=here,
    )
    logf.close()
    # Contract v0.3: runner-owned state.json is the UI poll target.
    state = {
        "run_id": run_id, "topic_id": tid, "status": "RUNNING",
        "state": "PLANNING",
        "step": {"i": 0, "n": max_steps},
        "trace_tail": [],
        "budgets": {"steps_used": 0, "sources_used": 0,
                    "elapsed_s": 0, "limit_s": 1800},
        "heartbeat_ts": now, "started_at": now, "pid": proc.pid,
    }
    _deep_search_write_json_atomic(os.path.join(rdir, "state.json"), state)
    return {"run_id": run_id, "topic_id": tid, "status": "RUNNING"}
