#!/usr/bin/env python3
"""
ChallengeGenerator — discovery-driven challenge authorship.

When an episode produces interesting findings (unexpected ports, anomalies,
high-volume traffic sources), the generator proposes a follow-up challenge
that turns the discovery into a machine-checkable eval.

Architecture:
    SignalDetector     — rule-based scan of parsed episode JSON for triggers
    ChallengeAuthor    — LLM call to generate title/description/assertions
    ChallengeGenerator — orchestrates pipeline, writes to ChallengeDB

Triggered from run_episode.py after each solved episode. Proposed challenges
go in with status='pending_review' — human approves before they run.

Usage:
    from challenge_generator import ChallengeGenerator
    gen = ChallengeGenerator()
    proposed = gen.process_episode(result_dict, last_response_json)
    # proposed is a list of challenge dicts (may be empty)

CLI:
    python3 scripts/challenge_generator.py --list-pending
    python3 scripts/challenge_generator.py --approve auto-nas-t2-001
    python3 scripts/challenge_generator.py --reject  auto-nas-t2-001
    python3 scripts/challenge_generator.py --show    auto-nas-t2-001
"""

import hashlib
import json
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

# ── Config ────────────────────────────────────────────────────────────────────

DB_PATH      = "/opt/local-se/challenges.db"
OLLAMA_URL   = os.getenv("OLLAMA_URL", "http://localhost:11434")
AUTHOR_MODEL = "llama3.2:3b"        # fast enough for challenge authorship
OWUI_URL     = os.getenv("OWUI_URL", "http://localhost:3000")
OWUI_KEY     = os.getenv("OWUI_KEY", "")


# ── Signal definitions ────────────────────────────────────────────────────────

# Each signal: (field_name, predicate, trigger_label, tier_delta, discipline)
# predicate receives the field value and returns True if signal fires
SIGNALS = [
    {
        "field":       "unexpected_ports",
        "predicate":   lambda v: isinstance(v, list) and len(v) > 0,
        "label":       "unexpected_ports",
        "description": "Unexpected open ports found during subnet scan",
        "tier_delta":  1,
        "discipline":  "security",
        "multiplier":  1.3,
    },
    {
        "field":       "unexpected_findings",
        "predicate":   lambda v: isinstance(v, str) and len(v.strip()) > 20,
        "label":       "unexpected_findings",
        "description": "Unexpected findings reported in network audit",
        "tier_delta":  1,
        "discipline":  "security",
        "multiplier":  1.3,
    },
    {
        "field":       "anomalies",
        "predicate":   lambda v: isinstance(v, str) and len(v.strip()) > 20,
        "label":       "anomalies",
        "description": "Anomalous traffic patterns detected in firewall logs",
        "tier_delta":  1,
        "discipline":  "debugging",
        "multiplier":  1.5,
    },
    {
        "field":       "top_blocked_ips",
        "predicate":   lambda v: isinstance(v, list) and v and
                                  isinstance(v[0], dict) and
                                  int(v[0].get("count", 0)) > 200,
        "label":       "high_volume_blocker",
        "description": "High-volume source IP blocked repeatedly — warrants investigation",
        "tier_delta":  1,
        "discipline":  "security",
        "multiplier":  1.3,
    },
]


# ── SignalDetector ────────────────────────────────────────────────────────────

class SignalDetector:
    """Scans parsed episode JSON for signals that warrant a follow-up challenge."""

    def detect(self, response_json: dict, episode_result: dict) -> list[dict]:
        """
        Returns list of fired signals, each with:
          signal_label, finding_summary, discipline, multiplier, tier_delta
        """
        fired = []
        for sig in SIGNALS:
            val = response_json.get(sig["field"])
            if val is None:
                continue
            try:
                if sig["predicate"](val):
                    summary = self._summarise(sig["field"], val)
                    fired.append({
                        "signal_label":   sig["label"],
                        "field":          sig["field"],
                        "finding":        summary,
                        "description":    sig["description"],
                        "discipline":     sig["discipline"],
                        "multiplier":     sig["multiplier"],
                        "tier_delta":     sig["tier_delta"],
                        "raw_value":      val,
                    })
            except Exception:
                pass
        return fired

    def _summarise(self, field: str, value) -> str:
        if isinstance(value, list):
            if value and isinstance(value[0], dict):
                # Show first 3 items as compact JSON
                preview = json.dumps(value[:3], separators=(",", ":"))
                return f"{field}: {len(value)} items — {preview[:200]}"
            return f"{field}: {value[:5]}"
        if isinstance(value, str):
            return f"{field}: {value[:300]}"
        return f"{field}: {value}"


# ── ChallengeAuthor ───────────────────────────────────────────────────────────

_AUTHOR_PROMPT = """\
You are a senior network security engineer writing evaluation challenges for an AI sysadmin.

A network audit episode just produced this finding:
CHALLENGE THAT FOUND IT: {parent_challenge_title}
FINDING TYPE: {signal_description}
FINDING DETAIL: {finding_summary}
NETWORK CONTEXT: {network_context}

Write a follow-up investigation challenge. Return ONLY valid JSON matching this schema exactly:
{{
  "title": "short descriptive title (max 60 chars)",
  "description": "2-3 sentence task description. Be specific about IPs, ports, services found. Tell the model what to investigate and what to produce.",
  "assertions": [
    {{"id": "a1", "code": "assert ...", "description": "one line description"}},
    {{"id": "a2", "code": "assert ...", "description": "one line description"}},
    {{"id": "a3", "code": "assert ...", "description": "one line description"}}
  ],
  "failure_modes": {{
    "0/3": "what 0 assertions passing means",
    "1/3": "what partial means",
    "2/3": "what almost-complete means",
    "3/3": "what full success looks like"
  }}
}}

Rules for assertions:
- Use only: assert, len(), isinstance(), all(), any(), int(), str(), bool()
- Variables come from the model's JSON response — name them clearly
- a1 should check that data was retrieved (list not empty, key present)
- a2 should check classification or analysis was performed
- a3 should check a recommendation or remediation was produced
- NO imports, NO function calls other than builtins listed above

Return only the JSON object, no markdown fences, no explanation."""

NETWORK_CONTEXT = (
    "Network: 192.168.1.0/24 (LAN), 192.168.5.0/24 (NAS subnet), "
    "192.168.10.0/24 (IoT/solar). "
    "Known hosts: pfSense 192.168.1.50, LUCIFER 192.168.1.57, "
    "Samsung TV 192.168.1.90, NAS 192.168.5.10. "
    "pfSense REST API: https://192.168.1.50/api/v2 (read-only). "
    "Tools available: pfsense_query(), nmap_summary(), pfsense_log_summary(), execute_command()."
)


class ChallengeAuthor:
    """Calls a small LLM to generate challenge text and assertions from a signal."""

    def author(
        self,
        signal: dict,
        parent_challenge_id: str,
        parent_challenge_title: str,
    ) -> Optional[dict]:
        """
        Returns a challenge dict (without id/metadata) or None on failure.
        """
        prompt = _AUTHOR_PROMPT.format(
            parent_challenge_title=parent_challenge_title,
            signal_description=signal["description"],
            finding_summary=signal["finding"][:400],
            network_context=NETWORK_CONTEXT,
        )

        # Try Ollama first (llama3.2:3b)
        content = self._call_ollama(prompt)

        # Fallback: OpenWebUI local model
        if not content:
            content = self._call_owui(prompt)

        if not content:
            return None

        return self._parse_response(content)

    def _call_ollama(self, prompt: str) -> str:
        try:
            resp = requests.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model":   AUTHOR_MODEL,
                    "prompt":  prompt,
                    "stream":  False,
                    "options": {"num_predict": 600, "temperature": 0.4},
                },
                timeout=90,
            )
            if resp.status_code == 200:
                return resp.json().get("response", "").strip()
        except Exception as e:
            print(f"  [author] Ollama failed: {e}")
        return ""

    def _call_owui(self, prompt: str) -> str:
        try:
            resp = requests.post(
                f"{OWUI_URL}/api/chat/completions",
                headers={"Authorization": f"Bearer {OWUI_KEY}",
                         "Content-Type": "application/json"},
                json={"model": "local", "messages": [{"role": "user", "content": prompt}],
                      "max_tokens": 600},
                timeout=120,
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"  [author] OWUI failed: {e}")
        return ""

    def _parse_response(self, content: str) -> Optional[dict]:
        """Extract and validate the JSON challenge dict from LLM response."""
        # Strip markdown fences if present
        clean = re.sub(r"```(?:json)?\s*", "", content).strip().rstrip("`")

        # Find outermost { ... }
        match = re.search(r"\{.*\}", clean, re.DOTALL)
        if not match:
            return None

        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

        # Validate required keys
        required = {"title", "description", "assertions", "failure_modes"}
        if not required.issubset(data.keys()):
            return None

        # Validate assertions
        assertions = data.get("assertions", [])
        if len(assertions) != 3:
            return None
        for a in assertions:
            if not {"id", "code", "description"}.issubset(a.keys()):
                return None
            # Basic safety check — no imports or dangerous builtins
            if any(kw in a["code"] for kw in ("import", "open(", "exec(", "eval(")):
                return None

        return data


# ── ChallengeGenerator ────────────────────────────────────────────────────────

class ChallengeGenerator:
    """
    Orchestrates signal detection + challenge authorship + DB insertion.
    Called from run_episode.py after each solved episode.
    """

    def __init__(self, db_path: str = DB_PATH):
        self.db_path   = db_path
        self.detector  = SignalDetector()
        self.author    = ChallengeAuthor()

    def process_episode(
        self,
        episode_result: dict,
        last_response_json: dict,
        verbose: bool = True,
    ) -> list[dict]:
        """
        Scan episode findings for signals. For each signal, author a challenge
        and insert it into ChallengeDB as pending_review.

        Returns list of inserted challenge dicts.
        """
        if episode_result.get("outcome") != "SOLVED":
            return []   # only generate from successful episodes

        signals = self.detector.detect(last_response_json, episode_result)
        if not signals:
            return []

        parent_id    = episode_result.get("challenge_id", "unknown")
        episode_id   = episode_result.get("leaderboard_episode_id")
        parent_title = self._get_challenge_title(parent_id)
        parent_tier  = self._get_challenge_tier(parent_id)

        if verbose:
            print(f"\n  [ChallengeGenerator] {len(signals)} signal(s) detected from {parent_id}")

        inserted = []
        for sig in signals:
            if verbose:
                print(f"    Signal: {sig['signal_label']} — {sig['finding'][:80]}...")

            # Check for duplicate signal from same parent (don't re-author)
            if self._duplicate_exists(parent_id, sig["signal_label"]):
                if verbose:
                    print(f"    Skipping — duplicate already exists for {parent_id}/{sig['signal_label']}")
                continue

            authored = self.author.author(sig, parent_id, parent_title)
            if not authored:
                if verbose:
                    print(f"    Authorship failed for signal {sig['signal_label']}")
                continue

            new_tier = min((parent_tier or 1) + sig["tier_delta"], 5)
            challenge = self._build_challenge(
                authored, sig, parent_id, episode_id, new_tier, parent_tier
            )

            row_id = self._insert(challenge)
            if row_id:
                inserted.append(challenge)
                if verbose:
                    print(f"    ✅ Proposed: {challenge['id']} — {challenge['title']}")
                    print(f"       Status: pending_review | Tier: {new_tier} | {sig['discipline']} {sig['multiplier']}×")

        return inserted

    def _build_challenge(
        self,
        authored: dict,
        signal: dict,
        parent_id: str,
        episode_id: Optional[int],
        new_tier: int,
        parent_tier: int,
    ) -> dict:
        """Build a complete challenge row from authored content + metadata."""
        # Deterministic ID: hash of parent + signal + title
        id_input  = f"{parent_id}:{signal['signal_label']}:{authored['title']}"
        short_hash = hashlib.sha1(id_input.encode()).hexdigest()[:6]
        challenge_id = f"auto-{parent_id}-{signal['signal_label'][:8]}-{short_hash}"

        return {
            "id":               challenge_id,
            "title":            authored["title"][:80],
            "description":      authored["description"],
            "domain":           self._get_challenge_domain(parent_id),
            "discipline":       signal["discipline"],
            "tier":             new_tier,
            "mode":             "read_only",
            "starting_state":   json.dumps({
                "parent_challenge_id": parent_id,
                "parent_episode_id":   episode_id,
                "signal":              signal["signal_label"],
                "finding":             signal["finding"][:500],
                "network_context":     NETWORK_CONTEXT,
            }),
            "success_criteria": json.dumps({"assertions": authored["assertions"]}),
            "failure_modes":    json.dumps(authored["failure_modes"]),
            "kb_target":        f"auto/{parent_id}/{signal['signal_label']}",
            "rollback_defined": 0,
            "requires_human_approval": 1,
            "discipline_multiplier": signal["multiplier"],
            "max_attempts":     3,
            "claude_only_override": 0,
            "auto_generated":   1,
            "parent_episode_id": episode_id,
            "status":           "pending_review",
        }

    def _insert(self, challenge: dict) -> Optional[int]:
        """Insert challenge into ChallengeDB. Returns rowid or None."""
        con = sqlite3.connect(self.db_path)
        try:
            cur = con.execute("""
                INSERT OR IGNORE INTO challenges
                  (id, title, description, domain, discipline, tier, mode,
                   starting_state, success_criteria, failure_modes, kb_target,
                   rollback_defined, requires_human_approval, discipline_multiplier,
                   max_attempts, claude_only_override, created_at,
                   auto_generated, parent_episode_id, status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                challenge["id"], challenge["title"], challenge["description"],
                challenge["domain"], challenge["discipline"], challenge["tier"],
                challenge["mode"], challenge["starting_state"],
                challenge["success_criteria"], challenge["failure_modes"],
                challenge["kb_target"], challenge["rollback_defined"],
                challenge["requires_human_approval"],
                challenge["discipline_multiplier"], challenge["max_attempts"],
                challenge["claude_only_override"], _now_iso(),
                challenge["auto_generated"], challenge["parent_episode_id"],
                challenge["status"],
            ))
            con.commit()
            return cur.lastrowid if cur.rowcount > 0 else None
        except Exception as e:
            print(f"  [ChallengeGenerator] DB insert failed: {e}")
            return None
        finally:
            con.close()

    def _duplicate_exists(self, parent_id: str, signal_label: str) -> bool:
        con = sqlite3.connect(self.db_path)
        try:
            row = con.execute(
                "SELECT id FROM challenges WHERE auto_generated=1 "
                "AND id LIKE ? AND status != 'rejected'",
                (f"auto-{parent_id}-{signal_label[:8]}%",),
            ).fetchone()
            return row is not None
        finally:
            con.close()

    def _get_challenge_title(self, challenge_id: str) -> str:
        con = sqlite3.connect(self.db_path)
        try:
            row = con.execute("SELECT title FROM challenges WHERE id=?",
                              (challenge_id,)).fetchone()
            return row[0] if row else challenge_id
        finally:
            con.close()

    def _get_challenge_tier(self, challenge_id: str) -> int:
        con = sqlite3.connect(self.db_path)
        try:
            row = con.execute("SELECT tier FROM challenges WHERE id=?",
                              (challenge_id,)).fetchone()
            return row[0] if row else 1
        finally:
            con.close()

    def _get_challenge_domain(self, challenge_id: str) -> str:
        con = sqlite3.connect(self.db_path)
        try:
            row = con.execute("SELECT domain FROM challenges WHERE id=?",
                              (challenge_id,)).fetchone()
            return row[0] if row else "sysadmin"
        finally:
            con.close()

    # ── Review CLI helpers ────────────────────────────────────────────────────

    def list_pending(self) -> list[dict]:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(
                "SELECT id, title, discipline, discipline_multiplier, tier, "
                "parent_episode_id, created_at "
                "FROM challenges WHERE status='pending_review' ORDER BY created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            con.close()

    def approve(self, challenge_id: str) -> bool:
        """Set status to 'active' — challenge will now run in episodes."""
        return self._set_status(challenge_id, "active")

    def reject(self, challenge_id: str) -> bool:
        """Set status to 'rejected' — will not run, won't re-generate."""
        return self._set_status(challenge_id, "rejected")

    def show(self, challenge_id: str) -> Optional[dict]:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        try:
            row = con.execute("SELECT * FROM challenges WHERE id=?",
                              (challenge_id,)).fetchone()
            return dict(row) if row else None
        finally:
            con.close()

    def _set_status(self, challenge_id: str, status: str) -> bool:
        con = sqlite3.connect(self.db_path)
        try:
            cur = con.execute("UPDATE challenges SET status=? WHERE id=?",
                              (status, challenge_id))
            con.commit()
            return cur.rowcount > 0
        finally:
            con.close()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    import argparse
    p = argparse.ArgumentParser(description="ChallengeGenerator review CLI")
    p.add_argument("--list-pending", action="store_true")
    p.add_argument("--approve",  type=str, metavar="ID")
    p.add_argument("--reject",   type=str, metavar="ID")
    p.add_argument("--show",     type=str, metavar="ID")
    p.add_argument("--db",       type=str, default=DB_PATH)
    args = p.parse_args()

    gen = ChallengeGenerator(db_path=args.db)

    if args.list_pending:
        rows = gen.list_pending()
        if not rows:
            print("  No pending challenges.")
            return
        print(f"\n  {'ID':<40}  {'Tier':>4}  {'Disc':<12}  {'Mult':>5}  Title")
        print(f"  {'─'*40}  {'─'*4}  {'─'*12}  {'─'*5}  {'─'*40}")
        for r in rows:
            print(f"  {r['id']:<40}  {r['tier']:>4}  {r['discipline']:<12}  "
                  f"{r['discipline_multiplier']:>5.1f}  {r['title'][:40]}")
        print()

    elif args.approve:
        ok = gen.approve(args.approve)
        print(f"  {'✅ Approved' if ok else '❌ Not found'}: {args.approve}")

    elif args.reject:
        ok = gen.reject(args.reject)
        print(f"  {'✅ Rejected' if ok else '❌ Not found'}: {args.reject}")

    elif args.show:
        c = gen.show(args.show)
        if not c:
            print(f"  Not found: {args.show}")
            return
        print(f"\n  {c['id']} — {c['title']}")
        print(f"  Status: {c.get('status')}  |  Tier: {c['tier']}  |  "
              f"{c['discipline']} {c['discipline_multiplier']}×")
        print(f"\n  Description:\n  {c['description']}")
        criteria = json.loads(c.get('success_criteria', '{}'))
        print(f"\n  Assertions:")
        for a in criteria.get('assertions', []):
            print(f"    [{a['id']}] {a['description']}")
            print(f"           {a['code']}")
        state = json.loads(c.get('starting_state', '{}'))
        if state.get('finding'):
            print(f"\n  Parent finding:\n  {state['finding'][:300]}")
        print()

    else:
        p.print_help()


if __name__ == "__main__":
    main()
