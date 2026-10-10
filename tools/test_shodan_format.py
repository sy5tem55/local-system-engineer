#!/usr/bin/env python3
"""Unit tests for shodan_mcp_server.py table formatting (no network, no key).

Run:  /home/sy5/miniforge3/bin/python /home/sy5/projects/local-system-engineer/tools/test_shodan_format.py
Exits non-zero on any failure.
"""

import sys

sys.path.insert(0, "/home/sy5/projects/local-system-engineer/tools")

from shodan_mcp_server import (  # noqa: E402
    _build_table,
    _device_label,
    _format_ports,
)

HEADER = "| Device | IP | Ports | Geo Location | GPS Coordinates |"
COLUMNS = ["Device", "IP", "Ports", "Geo Location", "GPS Coordinates"]

# Mock Shodan match shapes (per tools/shodan_api_facts.md response shape).
FULL_MATCH = {
    "ip": 1616761883,
    "ip_str": "96.93.212.27",
    "port": 443,
    "product": "nginx",
    "version": "1.18.0",
    "os": None,
    "hostnames": ["three.webapplify.net"],
    "http": {"title": "Welcome", "server": "nginx"},
    "location": {
        "city": "Denver",
        "region_code": "CO",
        "longitude": -104.9078,
        "latitude": 39.7301,
        "country_code": "US",
        "country_name": "United States",
    },
}

# Same host, second service on another port (should merge into one row).
SECOND_PORT_MATCH = {
    "ip": 1616761883,
    "ip_str": "96.93.212.27",
    "port": 80,
    "product": "nginx",
    "version": None,
    "os": None,
    "hostnames": ["three.webapplify.net"],
    "http": {},
    "location": FULL_MATCH["location"],
}

# Match missing product, hostnames, and location — the hard cases.
SPARSE_MATCH = {
    "ip": 3104568883,
    "ip_str": "185.11.246.51",
    "port": 8080,
    "product": None,
    "version": None,
    "os": None,
    "hostnames": [],
    "http": {},
    "location": None,
}

# Sparse but has an os (device should fall through to os).
OS_ONLY_MATCH = {
    "ip": 9999999,
    "ip_str": "0.60.247.51",
    "port": 22,
    "product": None,
    "version": None,
    "os": "Linux",
    "hostnames": None,
    "http": None,
    "location": {"city": None, "country_code": "RU", "country_name": "Russia",
                 "latitude": 55.7386, "longitude": 37.6068},
}

failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"PASS: {name}")
    else:
        print(f"FAIL: {name} {detail}")
        failures.append(name)


# --- _device_label ---------------------------------------------------------
check("device: product wins", _device_label([FULL_MATCH]) == "nginx")
check("device: falls to http.title when no product",
      _device_label([{**FULL_MATCH, "product": None}]) == "Welcome")
check("device: falls to hostnames[0]",
      _device_label([{**FULL_MATCH, "product": None, "http": {}}])
      == "three.webapplify.net")
check("device: falls to os", _device_label([OS_ONLY_MATCH]) == "Linux")
check("device: unknown when all missing",
      _device_label([SPARSE_MATCH]) == "unknown")

# --- _format_ports ---------------------------------------------------------
check("ports: simple join", _format_ports([80, 443]) == "80, 443")
many = list(range(20, 40))
check("ports: caps at 8 with overflow count",
      _format_ports(many) == "20, 21, 22, 23, 24, 25, 26, 27 (+12 more)")
check("ports: empty", _format_ports([]) == "")
check("ports: sorted", _format_ports([443, 80]) == "80, 443")

# --- _build_table: the exact-column contract --------------------------------
rows_full = [{
    "device": "nginx",
    "ip": "96.93.212.27",
    "ports": _format_ports([443, 80]),
    "location": FULL_MATCH["location"],
}, {
    "device": "unknown",
    "ip": "185.11.246.51",
    "ports": _format_ports([8080]),
    "location": {},
}, {
    "device": "Linux",
    "ip": "0.60.247.51",
    "ports": _format_ports([22]),
    "location": OS_ONLY_MATCH["location"],
}]

table = _build_table("webcam country:DE", 4321, rows_full)
print("\n--- sample table ---")
print(table)
print("---- end sample ----\n")

check("table: header has all five exact columns", HEADER in table)
for col in COLUMNS:
    check(f"table: column name present: {col!r}", col in table)
check("table: header appears once (no dupes)", table.count(HEADER) == 1)
check("table: full host row shows city,cc",
      "| nginx | 96.93.212.27 | 80, 443 | Denver, US | 39.7301, -104.9078 |"
      in table)
check("table: sparse host shows — placeholders",
      "| unknown | 185.11.246.51 | 8080 | — | — |" in table)
check("table: city-null location falls to country name",
      "| Linux | 0.60.247.51 | 22 | Russia (RU) | 55.7386, 37.6068 |" in table)
check("table: total matches line", "Total matches: 4321" in table)
check("table: hosts-shown count", "Hosts shown: 3" in table)
check("table: query echoed", "# Shodan search: webcam country:DE" in table)

empty = _build_table("nonexistentquery", 0, [])
check("table: empty result placeholder", "(no results)" in empty)
check("table: empty still has header", HEADER in empty)

# --- merge behavior sanity: same ip on two ports => one row -----------------
merged = _format_ports([FULL_MATCH["port"], SECOND_PORT_MATCH["port"]])
check("merge: two matches on same ip -> two ports", merged == "80, 443")

print()
if failures:
    print(f"RESULT: {len(failures)} FAILED: {failures}")
    sys.exit(1)
print("RESULT: ALL TESTS PASSED")
