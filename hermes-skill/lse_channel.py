#!/usr/bin/env python3
"""
LSE <-> Hermes channel — Hermes producer side (1.7.0-b, Path B).

Deterministic outbox helper. Hermes (agent) calls this via its terminal tool so the
outbox is updated atomically rather than by hand-editing JSON.

Store: ~/.hermes/lse-outbox.json  (a JSON list of envelopes)

Commands:
  enqueue --body TEXT [--kind notify|ask] [--priority info|action|urgent] [--want-reply]
        -> queue a message for the LSE; prints the correlation_id.
  flush -> print the [[HERMES->LSE]]{...}[[/HERMES->LSE]] marker for all undelivered
           messages and mark them delivered. Prints nothing if the outbox is empty.
           Include the printed marker VERBATIM in your reply to the LSE.
  reply --cid CID --text TEXT
        -> record the LSE's reply to an 'ask' envelope.
  list -> dump the outbox (debug).

Contract (must match the LSE parser in Cogitator >= v1.7.19 — do NOT change):
  marker  : [[HERMES->LSE]]{"messages":[<env>,...]}[[/HERMES->LSE]]
  env keys the LSE reads: correlation_id, kind, priority, body, want_reply
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


def cmd_enqueue(a):
    rows = _load()
    env = {
        "v": 1,
        "correlation_id": _next_cid(rows),
        "kind": a.kind,
        "priority": a.priority,
        "body": a.body,
        "want_reply": bool(a.want_reply),
        "created_at": int(time.time()),
        "delivered": 0,
        "delivered_at": None,
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
    msgs = [
        {
            "correlation_id": r["correlation_id"],
            "kind": r.get("kind", "notify"),
            "priority": r.get("priority", "info"),
            "body": r.get("body", ""),
            "want_reply": bool(r.get("want_reply")),
        }
        for r in pending
    ]
    now = int(time.time())
    for r in pending:
        r["delivered"] = 1
        r["delivered_at"] = now
    _save(rows)
    inner = json.dumps({"messages": msgs}, ensure_ascii=False, separators=(",", ":"))
    print(f"{MARK_OPEN}{inner}{MARK_CLOSE}")


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
    e.add_argument("--body", required=True)
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
