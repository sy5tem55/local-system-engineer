#!/usr/bin/env python3
"""Seed lse-skills with the first hand-distilled skills (trajectory S3.4).

Mirrors cogitator skill_record EXACTLY: same embed prefix ("search_query: ",
tool _embed convention — NOT 03-kb-seed's "search_document: "), same
embed_text construction, same doc_id = sha256(skill_id)[:16]. This keeps the
tool's dedup (cosine > 0.92) consistent with seeded docs.

Run on LUCIFER:  python3 rag/07-seed-skills.py
Idempotent — existing doc ids are skipped (use --force to overwrite).

Skill #1: sudo-blocker / permission-blocked cleanup (S0.3)
Skill #2: node3090 llama-server + hermes-gateway restart (t3-003/004 distillation)
"""
import hashlib
import re
import sys
from datetime import datetime

import requests
from elasticsearch import Elasticsearch

ES_URL = "http://localhost:9200"
OLLAMA_URL = "http://127.0.0.1:11434"
EMBED_MODEL = "nomic-embed-text"
INDEX = "lse-skills"

SKILLS = [
    {
        "task": "perform file operations in a privileged path when execute_command blocks sudo",
        "occupation": "linux-sysadmin",
        "preconditions": (
            "execute_command blocks sudo by SUBSTRING match; "
            "target path owned by a different user/group"
        ),
        "procedure": (
            "confirm the block is structural: id; ls -ld <dir>; stat -c '%U %G %a' <dir>; "
            "do NOT attempt sudo variants or escalation — blocklist is intentional, workarounds are protocol violations; "
            "fix structurally via human operator: group membership (usermod -aG) or setgid dir — group changes need a fresh session; "
            "verify write access with a probe: touch <dir>/.probe && rm <dir>/.probe; "
            "for deletions verify BEFORE unlink: readlink -f + stat -c %i on BOTH paths (one inode = symlink, not duplicate), sha256 the survivor, then delete and confirm df delta"
        ),
        "verification": (
            "touch/rm probe exits 0 as the unprivileged user; original operation's "
            "ground-truth check passes (file absent / df delta / survivor sha256 unchanged)"
        ),
        "failure_modes": (
            "sudo substring triggers even inside strings or echo; "
            "glob expands before sudo in non-root shell — literal 'No such file'; "
            "group membership not effective in existing sessions; "
            "'duplicate' behind a symlink is ONE inode — deletion destroys the only copy"
        ),
        "provenance": (
            "episodes #32-34 node-t3-005; docs/self-learning-trajectory.md S0.3; "
            "docs/incident-2026-06-11-model-deletion.md; kb/skills/linux-sysadmin--permission-blocked-cleanup.md"
        ),
        "quality": 0.5,
    },
    {
        "task": "restart llama-server backend and hermes-gateway on node3090 safely",
        "occupation": "sre",
        "preconditions": (
            "SSH lse-admin@192.168.5.41; canonical launch script "
            "/opt/local-se/scripts/start-llama-server.sh; backend ALWAYS before gateway; "
            "ONE operator at a time"
        ),
        "procedure": (
            "kill with self-match-safe pattern: pkill -f \"[l]lama-server\" — bracket class stops the SSH one-liner matching itself; "
            "poll nvidia-smi memory.used until ~0 — NEVER a fixed sleep (3s sleep caused a silent relaunch failure); "
            "tail /home/lse-admin/llama-server.log to see why the previous run died (OOM vs file error vs graceful); "
            "launch ONLY via /opt/local-se/scripts/start-llama-server.sh — never freehand args, script is the single source of truth; "
            "poll http://localhost:8080/health up to 3 min (15.4GB model load takes 60-120s); "
            "sudo systemctl reset-failed hermes-gateway — it hits the systemd start-limit while the backend is down; "
            "sudo systemctl start hermes-gateway; verify: systemctl is-active hermes-gateway hermes-socat"
        ),
        "verification": (
            "/health returns ok; nvidia-smi shows ~22.6GB used; "
            "systemctl is-active reports both hermes-gateway and hermes-socat active"
        ),
        "failure_modes": (
            "pkill -f llama-server self-matches the SSH command line — kills the session AND a healthy server; "
            "fixed sleep instead of VRAM poll — silent relaunch failure; "
            "gateway start without reset-failed — inactive(dead) from start-limit; "
            "two operators restarting concurrently — recover from ground-truth survey (pgrep/nvidia-smi), never from agent self-reports"
        ),
        "provenance": (
            "node-t3-003/004 episodes; Restart _Hermes.md; "
            "kb/session-learnings.md 2026-06-11 + 2026-06-12; docs/incident-2026-06-11-model-deletion.md"
        ),
        "quality": 0.5,
    },
]


def embed(text: str) -> list:
    r = requests.post(
        f"{OLLAMA_URL}/api/embed",
        json={"model": EMBED_MODEL, "input": "search_query: " + text[:5000]},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["embeddings"][0]


def main() -> int:
    force = "--force" in sys.argv
    es = Elasticsearch(ES_URL, request_timeout=10)
    if not es.indices.exists(index=INDEX):
        print(f"{INDEX} missing — run rag/06-skills-index-setup.py first.")
        return 1
    _split = lambda s: [p.strip() for p in re.split(r"[;\n]+", s) if p.strip()]
    now = datetime.now().astimezone().isoformat()
    for s in SKILLS:
        steps = _split(s["procedure"])
        slug = re.sub(r"[^a-z0-9]+", "-", s["task"].lower()).strip("-")[:60]
        skill_id = f"{s['occupation']}/{slug}"
        doc_id = hashlib.sha256(skill_id.encode()).hexdigest()[:16]
        if es.exists(index=INDEX, id=doc_id) and not force:
            print(f"SKIP (exists): {skill_id}")
            continue
        embed_text = f"{s['occupation']}: {s['task']}\n" + "\n".join(steps)
        es.index(index=INDEX, id=doc_id, document={
            "skill_id": skill_id, "occupation": s["occupation"], "task": s["task"],
            "preconditions": _split(s["preconditions"]), "procedure": steps,
            "verification": s["verification"], "failure_modes": _split(s["failure_modes"]),
            "provenance": _split(s["provenance"]),
            "embedding": embed(embed_text[:8000]), "quality": s["quality"],
            "stats": {"uses": 0, "episode_successes": 0,
                      "episode_failures": 0, "last_used": None},
            "pinned": False, "archived": False,
            "created_at": now, "updated_at": now, "version": 1,
        })
        print(f"SEEDED: {skill_id} | quality={s['quality']:.2f}")
    print("Verify:  curl -s 'localhost:9200/lse-skills/_count'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
