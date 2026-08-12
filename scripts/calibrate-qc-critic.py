#!/usr/bin/env python3
"""scripts/calibrate-qc-critic.py — run tools/qc_critic.py against the
2026-08-12 labelled diagnosis-adjudication set and report agreement with
the human's actual (REJECTED/APPLIED) decision.

Read-only: opens the traum-state.db copy via file:...?mode=ro, and the
critic itself (tools/qc_critic.py) has no write path at all (Hazard D,
proven in tests/test_qc_critic.py::test_module_has_no_write_path).

The 16 proposal_ids and their R1/R2/R3 verdicts below are transcribed
verbatim from docs/reports/2026-08-11-auto-adjudication.md §4's dry-run
output (the 16 PENDING diagnosis proposals that batch evaluated) — this
script does not re-derive the rule verdicts, it reuses the recorded ones as
already-measured ground truth for what the mechanical layer decided, same
as docs/reports/2026-08-12-qc-critic-calibration.md's analysis.

Usage:
    python3 scripts/calibrate-qc-critic.py --db /path/to/copy/of/traum-state.db
"""
from __future__ import annotations

import argparse
import functools
import json
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import dream_runner  # noqa: E402
import qc_critic  # noqa: E402

# proposal_id -> (rule_verdict, rule_name_or_None)
# Verbatim from docs/reports/2026-08-11-auto-adjudication.md §4.
RULE_VERDICTS = {
    "prp_50f883fed87f4b3aad257475fd4cfd68": ("PENDING", None),
    "prp_eb3873ee5eea483aa85c81d0a66fc2f7": ("SUPERSEDED", "R1"),
    "prp_c1e66c9235a2423aa3e088d776328a40": ("SYSTEM_REJECTED", "R3"),
    "prp_2a94912f70614b0c9c64999f3364e4bf": ("SUPERSEDED", "R1"),
    "prp_52584a9ebb3b445990eefb99ea04fb01": ("PENDING", None),
    "prp_358ca782c4e049619c7615c4a8717492": ("SUPERSEDED", "R1"),
    "prp_c6fbb0a811154e8083c8c67550d2064d": ("PENDING", None),
    "prp_4c17cf8ecb7741ea8402eb035810c078": ("SUPERSEDED", "R1"),
    "prp_9533c3c740dd4be58d38c6c53702de45": ("PENDING", None),
    "prp_06c937864d6e4eec95f3542f67ae9eb3": ("PENDING", None),
    "prp_c384e68723bc4e5488c69c477ca3419e": ("SYSTEM_REJECTED", "R2"),
    "prp_8a7560280d0f4280aaf4f7f47f7c5ed0": ("SUPERSEDED", "R1"),
    "prp_9ec21b7dc4244ae7b6e69d05b6cfdcba": ("SUPERSEDED", "R1"),
    "prp_b8c683001c33455a9d1a375f931d318c": ("SUPERSEDED", "R1"),
    "prp_caecef6140474152ace4c3d31be1561b": ("SYSTEM_REJECTED", "R2"),
    "prp_31b7db5c6c5849e58ce32318f2b45c7b": ("SUPERSEDED", "R1"),
}


def _rule_verdict_str(pid: str) -> str | None:
    verdict, name = RULE_VERDICTS.get(pid, (None, None))
    if name is None:
        return None
    return f"{name}: {verdict}"


def load_calibration_set(db_path: str) -> list:
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    ids = list(RULE_VERDICTS.keys())
    rows = conn.execute(
        f"SELECT proposal_id, proposal_type, state, reason, payload_json "
        f"FROM proposals WHERE proposal_id IN ({','.join('?' * len(ids))})",
        ids,
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        payload = json.loads(r["payload_json"])
        out.append({
            "proposal_id": r["proposal_id"],
            "type": "diagnosis",
            "payload": payload,
            "human_state": r["state"],
            "human_reason": r["reason"],
        })
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True)
    args = ap.parse_args()

    proposals = load_calibration_set(args.db)
    print(f"[calibrate-qc-critic] loaded {len(proposals)} labelled proposals from {args.db}",
          file=sys.stderr)

    cfg = dream_runner.DreamConfig(
        episode_dir=dream_runner._episode_dir_default(),
        dream_dir=dream_runner._dream_dir_default(),
        manifest_db="",
        es_url=dream_runner._es_url_default(),
        tasks_db=dream_runner._tasks_db_default(),
        agent_log=dream_runner._agent_log_default(),
        dream_llm_url=dream_runner._dream_llm_url_default(),
        node3090_llm_url=dream_runner._node3090_llm_url_default(),
        node3090_ollama_url=dream_runner._node3090_ollama_url_default(),
        node3090_fallback_model=dream_runner._node3090_fallback_model_default(),
        ollama_url=dream_runner._ollama_url_default(),
        embed_model=dream_runner._embed_model_default(),
        dedup_floor=dream_runner._dedup_floor_default(),
        dedup_threshold=dream_runner._dedup_threshold_default(),
        error_cluster_threshold=dream_runner._error_cluster_threshold_default(),
        runner_session_prefix=dream_runner._dream_runner_prefix_default(),
        sessions_limit=1,
        since=None,
        pass_name="qc-critic-calibration",
        dry_run=True,
    )
    call_llm = functools.partial(dream_runner.call_dream_llm, cfg=cfg)

    rule_verdict_strs = {pid: _rule_verdict_str(pid) for pid in RULE_VERDICTS}
    results, counts = qc_critic.run_qc_critic(proposals, call_llm, rule_verdict_strs)
    results_by_id = {r["proposal_id"]: r for r in results}

    print(f"\n{'proposal_id':38} {'human':10} {'rule':20} {'critic':10} {'agrees?':8} reason")
    agree = 0
    total = 0
    for p in proposals:
        pid = p["proposal_id"]
        human_reject = p["human_state"] == "REJECTED"
        crit = results_by_id.get(pid, {"verdict": "MISSING", "reason": ""})
        critic_reject = crit["verdict"] in ("reject", "needs_work")
        agrees = critic_reject == human_reject
        total += 1
        agree += int(agrees)
        rverd, rname = RULE_VERDICTS.get(pid, (None, None))
        rule_str = f"{rname or '-'}:{rverd}"
        print(f"{pid:38} {p['human_state']:10} {rule_str:20} {crit['verdict']:10} "
              f"{'YES' if agrees else 'NO':8} {crit['reason'][:80]}")

    print(f"\n[calibrate-qc-critic] critic agrees with human on {agree}/{total}")
    print(f"[calibrate-qc-critic] verdict counts: {counts}")

    # The interesting comparison: does the critic catch what R1/R2/R3 missed?
    print("\n--- rule mismatches (where the mechanical rule disagreed with the human) ---")
    for p in proposals:
        pid = p["proposal_id"]
        rverd, rname = RULE_VERDICTS.get(pid, (None, None))
        rule_reject = rverd in ("SUPERSEDED", "SYSTEM_REJECTED")
        human_reject = p["human_state"] == "REJECTED"
        if rule_reject != human_reject:
            crit = results_by_id.get(pid, {"verdict": "MISSING", "reason": ""})
            caught = (crit["verdict"] in ("reject", "needs_work")) == human_reject
            print(f"  {pid}: rule={rname}:{rverd} human={p['human_state']} "
                  f"critic={crit['verdict']} caught={'YES' if caught else 'NO'} — {crit['reason'][:100]}")


if __name__ == "__main__":
    main()
