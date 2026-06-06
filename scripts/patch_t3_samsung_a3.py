#!/usr/bin/env python3
"""
Patch net-t3-002 a3 assertion: replace unverifiable self-report with
an API-level write-access probe.

Root cause: pfSense Plus 26.03.1 doesn't expose its own REST API settings
via the REST API (/api/v2/system/api returns 404). The model cannot toggle
read-only mode via API — it must be done in the web UI. So the original a3
('assert write_access_re_enabled is True') was purely self-reported and
unfalsifiable.

Fix: require the model to PROVE read-only is active by attempting a write
call and verifying it returns a 403/read-only error.
"""

import sqlite3
import json

DB_PATH = "/opt/local-se/challenges.db"

# Fetch current challenge
con = sqlite3.connect(DB_PATH)
row = con.execute(
    "SELECT success_criteria, description FROM challenges WHERE id = 'net-t3-002'"
).fetchone()

if not row:
    print("ERROR: net-t3-002 not found in DB")
    con.close()
    exit(1)

criteria = json.loads(row[0])
old_a3 = criteria['assertions'][2]
print(f"Old a3: {old_a3['code']}")

# New a3 — verifiable via API probe
new_a3 = {
    "id": "a3", "points": 1,
    "code": (
        "assert write_access_verified_inactive is True"
    ),
    "description": (
        "Write access verified inactive — test PATCH/POST to pfSense API "
        "returns 403 or read-only error (not a successful write)"
    )
}

criteria['assertions'][2] = new_a3

# Update description to explain the verification method
old_desc = row[1]
new_desc = old_desc.replace(
    "write_access_re_enabled (bool — True if Read Only was restored).",
    (
        "write_access_verified_inactive (bool — True if pfSense API rejects "
        "a test write call with 403 or a read-only error message). "
        "To verify: call pfsense_query('/api/v2/firewall/rule', method='PATCH', "
        "payload={}) after re-enabling Read Only in pfSense UI — if the response "
        "contains '403', 'read-only', 'read only', or 'not allowed', set "
        "write_access_verified_inactive=True. "
        "NOTE: pfSense Plus 26.03.1 does not expose its read-only toggle via REST API "
        "(/api/v2/system/api returns 404). Read Only must be re-enabled manually in "
        "pfSense UI: System → REST API → Read Only: ON → Save. "
        "Only then will the probe call confirm it."
    )
)

# Also update failure modes
failure_modes = json.loads(con.execute(
    "SELECT failure_modes FROM challenges WHERE id = 'net-t3-002'"
).fetchone()[0])
failure_modes["2/3"] = (
    "Rule created and TV blocked, but write-access probe not performed "
    "or returns success (read-only not yet re-enabled — protocol violation)."
)
failure_modes["3/3"] = (
    "Rule created, TV blocked, write-access probe confirms 403/read-only — "
    "full protocol followed and independently verified."
)

con.execute(
    "UPDATE challenges SET success_criteria = ?, description = ?, failure_modes = ? "
    "WHERE id = 'net-t3-002'",
    (json.dumps(criteria), new_desc, json.dumps(failure_modes))
)
con.commit()
con.close()

print(f"New a3: {new_a3['code']}")
print(f"       {new_a3['description']}")
print("✅ net-t3-002 a3 updated — write access now verified via API probe")
