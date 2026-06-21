#!/usr/bin/env python3
"""faust-admin.py — local DB admin for Faust (run on the host, with the server STOPPED).

Operates directly on the SQLite file the server uses, so it needs no login/password.
Use it to recover from account/password tangles or to mint agent keys offline.

  python3 faust-admin.py --db <gate2.sqlite> list
  python3 faust-admin.py --db <gate2.sqlite> set-admin <handle> [--off]
  python3 faust-admin.py --db <gate2.sqlite> set-password <handle> <password>
  python3 faust-admin.py --db <gate2.sqlite> issue-key <handle> [label]

IMPORTANT: stop the Faust server first. It holds the DB in memory (sql.js) and rewrites
the whole file on every change, which would clobber edits made while it runs.
"""
import argparse, base64, hashlib, os, secrets, sqlite3, sys, time


def _acct(con, handle):
    return con.execute("SELECT id,handle,kind,isAdmin FROM accounts WHERE handle=?", (handle,)).fetchone()


def cmd_list(con, a):
    rows = con.execute("SELECT id,handle,kind,isAdmin,(passwordHash IS NOT NULL) FROM accounts ORDER BY handle")
    print(f"{'id':18} {'handle':16} {'kind':6} {'admin':6} pw  keys")
    for _id, h, k, adm, hp in rows:
        nk = con.execute("SELECT COUNT(*) FROM api_keys WHERE user_id=? AND revoked_at IS NULL", (_id,)).fetchone()[0]
        print(f"{_id:18} {h:16} {k:6} {str(bool(adm)):6} {str(bool(hp)):3} {nk}")


def cmd_set_admin(con, a):
    r = _acct(con, a.handle)
    if not r: sys.exit(f"no such handle: {a.handle}")
    con.execute("UPDATE accounts SET isAdmin=? WHERE id=?", (0 if a.off else 1, r[0])); con.commit()
    print(f"{a.handle}: isAdmin={0 if a.off else 1}")


def cmd_set_password(con, a):
    r = _acct(con, a.handle)
    if not r: sys.exit(f"no such handle: {a.handle}")
    salt = secrets.token_hex(16)
    ph = hashlib.sha256((salt + a.password).encode()).hexdigest()
    con.execute("UPDATE accounts SET passwordHash=?, salt=? WHERE id=?", (ph, salt, r[0])); con.commit()
    print(f"{a.handle}: password updated")


def cmd_issue_key(con, a):
    r = _acct(con, a.handle)
    if not r: sys.exit(f"no such handle: {a.handle}")
    key = "fa_" + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
    kh = hashlib.sha256(key.encode()).hexdigest()
    kid = f"ak:{int(time.time()*1000)}-{secrets.token_hex(3)}"
    con.execute(
        "INSERT INTO api_keys (id,user_id,key_hash,label,scope,created_at,expires_at,revoked_at) "
        "VALUES (?,?,?,?,?,?,?,NULL)",
        (kid, r[0], kh, a.label or f"{a.handle}-faust", None, int(time.time() * 1000), None))
    con.commit()
    print(f"{a.handle}: FAUST_KEY={key}")


def cmd_create_account(con, a):
    if _acct(con, a.handle): sys.exit(f"already exists: {a.handle}")
    kind = "model" if a.model else "human"
    salt = secrets.token_hex(16) if a.password else None
    ph = hashlib.sha256((salt + a.password).encode()).hexdigest() if a.password else None
    con.execute("INSERT INTO accounts (id,handle,kind,passwordHash,salt,isAdmin,createdAt) VALUES (?,?,?,?,?,0,?)",
                (f"u:{a.handle}", a.handle, kind, ph, salt, int(time.time() * 1000)))
    con.commit()
    print(f"created {kind} account: {a.handle}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="../gate2-group-server/data/gate2.sqlite")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sa = sub.add_parser("set-admin"); sa.add_argument("handle"); sa.add_argument("--off", action="store_true")
    sp = sub.add_parser("set-password"); sp.add_argument("handle"); sp.add_argument("password")
    ca = sub.add_parser("create-account"); ca.add_argument("handle"); ca.add_argument("--password"); ca.add_argument("--model", action="store_true")
    ik = sub.add_parser("issue-key"); ik.add_argument("handle"); ik.add_argument("label", nargs="?")
    a = p.parse_args()
    if not os.path.exists(a.db): sys.exit(f"DB not found: {a.db}  (pass --db <path to gate2.sqlite>)")
    con = sqlite3.connect(a.db)
    # self-heal: ensure the api_keys table exists even on a pre-API-key DB
    con.execute("CREATE TABLE IF NOT EXISTS api_keys (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, "
                "key_hash TEXT NOT NULL, label TEXT, scope TEXT, created_at INTEGER NOT NULL, "
                "expires_at INTEGER, revoked_at INTEGER)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash)")
    {"list": cmd_list, "set-admin": cmd_set_admin, "set-password": cmd_set_password, "create-account": cmd_create_account, "issue-key": cmd_issue_key}[a.cmd](con, a)
    con.close()


if __name__ == "__main__":
    main()
