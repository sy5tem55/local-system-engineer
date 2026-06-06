"""
Smoke test for LSEChallengeEnv — no model required.

Tests:
  1. reset() loads challenge from DB correctly
  2. step() with a correct JSON response → terminated=True, reward=13.0 (10 bonus + 3 assertions)
  3. step() with a wrong response → partial credit
  4. step() × 3 wrong → truncated=True
  5. render() in ansi mode
  6. list_challenges() returns 10 rows

Run from project root:
    python3 scripts/test_challenge_env.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from lse_challenge_env import LSEChallengeEnv

DB = "/opt/local-se/challenges.db"
PASS = "✅"
FAIL = "❌"

def check(label: str, condition: bool) -> bool:
    icon = PASS if condition else FAIL
    print(f"  {icon}  {label}")
    return condition

def run_tests():
    print("\n=== LSEChallengeEnv smoke test ===\n")
    errors = 0

    env = LSEChallengeEnv(db_path=DB, render_mode="ansi")

    # ── Test 1: reset ─────────────────────────────────────────────────────────
    print("1. reset() — loads pf-t1-001")
    obs, info = env.reset(options={"challenge_id": "pf-t1-001", "model_id": "test-model"})

    ok = check("obs has 'challenge' key", "challenge" in obs)
    ok &= check("obs has 'attempt_history' key", "attempt_history" in obs)
    ok &= check("obs has 'kb_context' key", "kb_context" in obs)
    ok &= check("challenge text contains challenge ID", "pf-t1-001" in obs["challenge"])
    ok &= check("challenge text contains assertion code", "192.168.1.50" in obs["challenge"])
    ok &= check("info.challenge_id == 'pf-t1-001'", info["challenge_id"] == "pf-t1-001")
    ok &= check("info.model_id == 'test-model'", info["model_id"] == "test-model")
    ok &= check("info.attempt_n == 0", info["attempt_n"] == 0)
    ok &= check("info.discipline_multiplier == 1.0", info["discipline_multiplier"] == 1.0)
    ok &= check("attempt_history is empty string", obs["attempt_history"] == "")
    if not ok: errors += 1
    print()

    # ── Test 2: step() — correct response ─────────────────────────────────────
    print("2. step() — correct JSON response → terminated=True, reward=13.0")

    correct_response = """
After querying the pfSense DHCP API and running an ARP scan, here are the results:

```json
{
  "devices": [
    {"ip": "192.168.1.50", "mac": "aa:bb:cc:dd:ee:01", "hostname": "pfsense"},
    {"ip": "192.168.1.57", "mac": "aa:bb:cc:dd:ee:02", "hostname": "LUCIFER"},
    {"ip": "192.168.1.90", "mac": "1c:af:4a:04:5f:b6", "hostname": "Samsung-TV"},
    {"ip": "192.168.1.100", "mac": "aa:bb:cc:dd:ee:04", "hostname": "ha-pi"},
    {"ip": "192.168.1.10", "mac": "aa:bb:cc:dd:ee:05", "hostname": "node2"}
  ]
}
```
"""
    obs2, reward, terminated, truncated, info2 = env.step(correct_response)

    ok = check("terminated == True", terminated is True)
    ok &= check("truncated == False", truncated is False)
    ok &= check("reward == 13.0 (10 bonus + 3 assertions)", reward == 13.0)
    ok &= check("info.attempt_n == 1", info2["attempt_n"] == 1)
    ok &= check("info.assertions_passed == 3", info2["assertions_passed"] == 3)
    ok &= check("attempt_history now has content", len(obs2["attempt_history"]) > 0)
    print(env.render())
    if not ok: errors += 1
    print()

    # ── Test 3: step() — partial credit (2/3 passing) ─────────────────────────
    print("3. step() — partial response → 2/3 assertions, reward=2.0")
    env.reset(options={"challenge_id": "pf-t1-001", "model_id": "test-model"})

    partial_response = """
Found some devices:

```json
{
  "devices": [
    {"ip": "192.168.1.50", "mac": "aa:bb:cc:dd:ee:01"},
    {"ip": "192.168.1.57", "mac": "aa:bb:cc:dd:ee:02"}
  ]
}
```
Note: only found 2 devices with MACs.
"""
    # a1 passes (1.50 found), a2 passes (1.57 found), a3 fails (only 2 with MACs, need 5)
    _, reward3, terminated3, truncated3, info3 = env.step(partial_response)

    ok = check("terminated == False", terminated3 is False)
    ok &= check("truncated == False (attempt 1 of 3)", truncated3 is False)
    ok &= check("reward == 2.0 (2 assertions passed)", reward3 == 2.0)
    ok &= check("assertions_passed == 2", info3["assertions_passed"] == 2)
    print(env.render())
    if not ok: errors += 1
    print()

    # ── Test 4: truncation after max_attempts ─────────────────────────────────
    print("4. 3 wrong responses → truncated=True on attempt 3")
    env.reset(options={"challenge_id": "pf-t1-001", "model_id": "test-model"})

    bad_response = '```json\n{"devices": []}\n```'
    for i in range(1, 4):
        _, _, terminated4, truncated4, info4 = env.step(bad_response)
        if i < 3:
            ok = check(f"attempt {i}: not yet truncated", truncated4 is False)
            if not ok: errors += 1

    ok = check("attempt 3: truncated == True", truncated4 is True)
    ok &= check("attempt 3: terminated == False", terminated4 is False)
    ok &= check("attempt 3: reward == 0.0 (0 assertions passed)", _ == 0.0)
    if not ok: errors += 1
    print()

    # ── Test 5: security challenge — discipline multiplier ─────────────────────
    print("5. pf-t1-006 (security) — discipline_multiplier == 1.3")
    env.reset(options={"challenge_id": "pf-t1-006", "model_id": "test-model"})
    obs5, info5 = env.reset(options={"challenge_id": "pf-t1-006", "model_id": "test-model"})

    ok = check("discipline == 'security'", info5["discipline"] == "security")
    ok &= check("discipline_multiplier == 1.3", info5["discipline_multiplier"] == 1.3)
    ok &= check("challenge text contains firewall rule context", "firewall" in obs5["challenge"].lower())
    if not ok: errors += 1
    print()

    # ── Test 6: dns challenge — is_rfc1918 helper ─────────────────────────────
    print("6. pf-t1-007 (DNS audit) — is_rfc1918 helper in assertion namespace")
    env.reset(options={"challenge_id": "pf-t1-007", "model_id": "test-model"})

    dns_response = """
DNS audit complete:

```json
{
  "dns_resolver_running": true,
  "host_overrides": [
    {"hostname": "lucifer.home.arpa", "ip": "192.168.1.57"},
    {"hostname": "ha.home.arpa", "ip": "192.168.1.100"}
  ]
}
```
"""
    _, reward6, terminated6, _, info6 = env.step(dns_response)

    ok = check("terminated == True (all RFC1918 IPs)", terminated6 is True)
    ok &= check("reward == 13.0", reward6 == 13.0)
    if not ok: errors += 1
    print()

    # ── Test 7: list_challenges ───────────────────────────────────────────────
    print("7. list_challenges() — returns all 10 T1 rows")
    challenges = env.list_challenges(tier=1)

    ok = check(f"10 challenges returned (got {len(challenges)})", len(challenges) == 10)
    ids = {c["id"] for c in challenges}
    ok &= check("pf-t1-001 present", "pf-t1-001" in ids)
    ok &= check("ha-t1-008 present", "ha-t1-008" in ids)
    ok &= check("net-t1-010 present", "net-t1-010" in ids)
    if not ok: errors += 1
    print()

    # ── Summary ───────────────────────────────────────────────────────────────
    print("─" * 50)
    if errors == 0:
        print(f"  {PASS}  All tests passed")
    else:
        print(f"  {FAIL}  {errors} test group(s) had failures")
    print()
    return errors

if __name__ == "__main__":
    # Install gymnasium if not present
    try:
        import gymnasium
    except ImportError:
        print("Installing gymnasium...")
        os.system("pip install gymnasium --break-system-packages -q")
        import gymnasium

    sys.exit(run_tests())
