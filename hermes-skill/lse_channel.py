#!/usr/bin/env python3
"""
LSE <-> Hermes channel — Hermes producer side (1.7.0-b, Path B).

Deterministic outbox helper. Hermes (agent) calls this via its terminal tool so the
outbox is updated atomically rather than by hand-editing JSON.

Store: ~/.hermes/lse-outbox.json  (a JSON list of envelopes)

Commands:
  enqueue --body TEXT | --body-file PATH
          [--kind notify|ask] [--priority info|action|urgent] [--want-reply]
        -> queue a message for the LSE; prints the correlation_id.
           --body-file reads the payload from a file (use for large ssh logs etc).
  flush -> print the [[HERMES->LSE]]{...}[[/HERMES->LSE]] marker for all undelivered
           messages and mark them delivered. Prints nothing if the outbox is empty.
           Include the printed marker VERBATIM in your reply to the LSE.
           LARGE PAYLOADS RIDE BY REFERENCE: any body over the spill threshold (or
           any marker that would exceed the budget) is written to a ref file under
           REF_DIR on this node; the envelope then carries body_ref (a path the LSE
           SSH-fetches) plus a short preview, keeping the marker inside the poll cap.
  reply --cid CID --text TEXT
        -> record the LSE's reply to an 'ask' envelope.
  list -> dump the outbox (debug).

Contract (must match the LSE parser in Cogitator — do NOT change existing keys):
  marker  : [[HERMES->LSE]]{"messages":[<env>,...]}[[/HERMES->LSE]]
  env keys the LSE reads: correlation_id, kind, priority, body, want_reply
  by-reference (LSE >= v1.7.23 surfaces it; older LSE ignores it safely):
            body_ref  -> absolute path on this node holding the full payload;
                         the LSE fetches it with execute_command SSH.
            body_bytes-> original payload size in bytes.
            When body_ref is set, body holds only a short preview.
"""
import argparse
import json
import os
import tempfile
import time
from datetime import datetime, timezone

STORE = os.path.expanduser("~/.hermes/lse-outbox.json")
MARK_OPEN = "[[HERMES->LSE]]"
MARK_CLOSE = "[[/HERMES->LSE]]"

# By-reference tuning. REF_DIR must be readable by the LSE's SSH user (lse-admin)
# on this node — /tmp is world-traversable and ref files are written world-readable,
# so no sudo is needed to fetch them. Override with LSE_CHANNEL_REF_DIR if desired.
REF_DIR = os.environ.get("LSE_CHANNEL_REF_DIR", "/tmp/lse-channel/refs")
SPILL_THRESHOLD = int(os.environ.get("LSE_CHANNEL_SPILL_THRESHOLD", "800"))  # chars
PREVIEW_CHARS = int(os.environ.get("LSE_CHANNEL_PREVIEW_CHARS", "160"))
MARKER_BUDGET = int(os.environ.get("LSE_CHANNEL_MARKER_BUDGET", "3000"))  # chars


def _load():
    try:
        with open(STORE, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except FileNotFoundError:
        return []
    except Exception:
        return []


def _save(rows):
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(STORE), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, STORE)  # atomic
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _next_cid(rows):
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"hz-{day}-"
    n = 0
    for r in rows:
        cid = r.get("correlation_id", "")
        if cid.startswith(prefix):
            try:
                n = max(n, int(cid[len(prefix):]))
            except ValueError:
                pass
    return f"{prefix}{n + 1:04d}"


def _preview(body):
    """First PREVIEW_CHARS of body, single-lined, with a truncation note."""
    flat = " ".join(str(body).split())
    head = flat[:PREVIEW_CHARS].rstrip()
    nbytes = len(str(body).encode("utf-8"))
    return f"{head}… [truncated; {nbytes} bytes by reference]"


def _spill_ref(cid, body):
    """Write the full payload to REF_DIR/<cid>.txt (world-readable) and return its path.
    The LSE SSH-fetches this path; keeping it out of the marker beats the poll cap."""
    os.makedirs(REF_DIR, exist_ok=True)
    try:
        os.chmod(REF_DIR, 0o755)
    except OSError:
        pass
    path = os.path.join(REF_DIR, f"{cid}.txt")
    fd, tmp = tempfile.mkstemp(dir=REF_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(str(body))
        os.replace(tmp, path)
        os.chmod(path, 0o644)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return path


def _build_msg(r, by_ref):
    """Build a marker envelope for one outbox row. If by_ref, spill body to a file."""
    cid = r["correlation_id"]
    body = r.get("body", "")
    msg = {
        "correlation_id": cid,
        "kind": r.get("kind", "notify"),
        "priority": r.get("priority", "info"),
        "body": body,
        "want_reply": bool(r.get("want_reply")),
    }
    if by_ref:
        path = r.get("body_ref") or _spill_ref(cid, body)
        r["body_ref"] = path  # persist so re-flush reuses the same file
        msg["body"] = _preview(body)
        msg["body_ref"] = path
        msg["body_bytes"] = len(str(body).encode("utf-8"))
    return msg


def _marker(msgs):
    inner = json.dumps({"messages": msgs}, ensure_ascii=False, separators=(",", ":"))
    return f"{MARK_OPEN}{inner}{MARK_CLOSE}"


def cmd_enqueue(a):
    rows = _load()
    if a.body_file:
        with open(a.body_file, encoding="utf-8") as fh:
            body = fh.read()
    else:
        body = a.body
    env = {
        "v": 1,
        "correlation_id": _next_cid(rows),
        "kind": a.kind,
        "priority": a.priority,
        "body": body,
        "want_reply": bool(a.want_reply),
        "created_at": int(time.time()),
        "delivered": 0,
        "delivered_at": None,
        "body_ref": None,
        "reply": None,
        "replied_at": None,
    }
    rows.append(env)
    _save(rows)
    print(env["correlation_id"])


def cmd_flush(a):
    rows = _load()
    pending = [r for r in rows if not r.get("delivered")]
    if not pending:
        return  # print nothing -> LSE maps no-marker to INBOX EMPTY

    # Spill obviously-large bodies up front (or anything already spilled).
    by_ref = {
        r["correlation_id"]: (
            len(str(r.get("body", ""))) > SPILL_THRESHOLD or bool(r.get("body_ref"))
        )
        for r in pending
    }
    msgs = [_build_msg(r, by_ref[r["correlation_id"]]) for r in pending]

    # If the marker still exceeds the budget, spill the largest inline bodies until
    # it fits (or nothing inline remains to spill).
    while len(_marker(msgs)) > MARKER_BUDGET:
        inline = [
            (i, r)
            for i, r in enumerate(pending)
            if not by_ref[r["correlation_id"]]
        ]
        if not inline:
            break
        i, r = max(inline, key=lambda t: len(str(t[1].get("body", ""))))
        by_ref[r["correlation_id"]] = True
        msgs[i] = _build_msg(r, True)

    now = int(time.time())
    for r in pending:
        r["delivered"] = 1
        r["delivered_at"] = now
    _save(rows)
    print(_marker(msgs))


def cmd_reply(a):
    rows = _load()
    hit = None
    for r in rows:
        if r.get("correlation_id") == a.cid:
            r["reply"] = a.text
            r["replied_at"] = int(time.time())
            hit = r
            break
    _save(rows)
    print("recorded" if hit else f"no envelope with correlation_id={a.cid}")


def cmd_list(a):
    print(json.dumps(_load(), ensure_ascii=False, indent=2))


def main():
    p = argparse.ArgumentParser(description="LSE<->Hermes outbox helper (Path B)")
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("enqueue")
    g = e.add_mutually_exclusive_group(required=True)
    g.add_argument("--body")
    g.add_argument("--body-file", dest="body_file")
    e.add_argument("--kind", default="notify", choices=["notify", "ask"])
    e.add_argument("--priority", default="info", choices=["info", "action", "urgent"])
    e.add_argument("--want-reply", action="store_true")
    e.set_defaults(func=cmd_enqueue)

    f = sub.add_parser("flush")
    f.set_defaults(func=cmd_flush)

    r = sub.add_parser("reply")
    r.add_argument("--cid", required=True)
    r.add_argument("--text", required=True)
    r.set_defaults(func=cmd_reply)

    ls = sub.add_parser("list")
    ls.set_defaults(func=cmd_list)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
