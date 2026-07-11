#!/usr/bin/env python3
"""
distill_learnings.py — SCRIBE-2 backfill distiller (TRAUM Thread 1, Prompt 1.7).
=============================================================================
One-shot script: parses the EXISTING kb/session-learnings.md corpus (24
entries as of 2026-07-11, ~860 lines — see docs/dreaming/corpus-audit.md §d)
and proposes index_to_kb / skill_record candidates, the same way SCRIBE-1's
live debrief flow would have if it had existed when these sessions were
written. This is the backfill half of "unify the write path" — SCRIBE-1
covers new sessions going forward, this script covers the sessions that
already happened.

NO AUTO-COMMIT. Two passes, always:

  PASS 1 (default) — read-only. Parses the corpus, classifies candidates,
    writes:
      docs/dreaming/backfill-proposals.jsonl   (one proposal object per line —
        same shape as docs/dreaming/DESIGN.md §6.2: type/call/args/why, plus
        a stable "id" and top-level "provenance")
      docs/dreaming/backfill-review.md         (human-readable diff-style
        list, grouped by source session, for reading in a PR-review style —
        this is what gets reviewed "together in this thread")
    Prints proposed/candidate counts to stdout. Touches NO ES index.

  PASS 2 (--apply IDS_FILE) — the ONLY code path that writes to ES. Reads a
    plain text file of approved proposal ids (one per line, '#' comments and
    blank lines ignored), filters backfill-proposals.jsonl to just those ids,
    calls the real goethe.py Tools.index_to_kb / Tools.skill_record for each
    (direct Python import, no MCP gateway needed — same pattern
    tests/test_planner_ledger.py uses), and writes
    docs/dreaming/backfill-applied.jsonl (append-only log: id, tool return
    value, timestamp — for the "record counts in the thread debrief" step).
    Every id not in the approved set is implicitly rejected; nothing happens
    to it. Prints applied/failed counts to stdout.

CLASSIFICATION — heuristic, not an LLM pass. This is a deterministic,
re-runnable script, not a chat model, so it leans on the ENTRY FORMAT's own
discipline rather than trying to "understand" prose:
  - Every `### Key facts` bullet is ALREADY, by the template's own instruction
    ("one fact per line"), a standalone atomic fact — propose 1:1 as a
    kb-fact candidate. Highest-confidence category, no heuristic needed.
  - Each `### What failed and why` block's `**Fix:**` clause is usually
    ALSO a fact (the corrected value/command) — propose as kb-fact UNLESS it
    reads as a multi-step procedure (heuristic: >=2 distinct command-like
    segments), in which case propose as a skill-candidate instead.
  - `### What worked` bullets propose as skill-candidate only when they read
    as a reusable multi-step procedure (a command plus a verify/check signal
    or explicit sequencing) — a single-fact "What worked" bullet is skipped
    here, not double-counted, because it's normally already covered by a Key
    facts or Fix-derived kb-fact candidate for the same session (see SKILL.md
    §"Note what did NOT get proposed" for the reasoning this mirrors).
  - Fix-derived candidates are deduped against Key-facts candidates from the
    SAME entry by token-overlap — a Fix that just restates a Key fact does
    not get proposed twice.
  - Any non-standard H3 section (e.g. the 2026-06-08 entry's "What is safe
    across a full Docker reset" — see corpus-audit.md §d) has its bullets
    treated the same as Key facts: one candidate per line. The parser does
    not require the three canonical headers to be present or exhaustive.

This is a FIRST DRAFT for human tightening, not a finished proposal set — see
"why" on each candidate and the review file. Titles/topics/tiers are
best-effort; the review step is where a human (or Claude, reading the review
file in-thread) corrects them before any id is approved.

SECRET HYGIENE: session-learnings.md predates TRAUM's redaction discipline
and contains at least one plaintext credential-shaped value in the existing
corpus (a Vaultwarden item name paired with what reads as its actual value).
Before building any proposal's content/evidence, a lightweight pattern sweep
(mirrors tools/goethe_mcp.py's _PATTERN_SECRET_RE / _BEARER_RE, applied here
independently since this script has no reason to import the MCP gateway
module) redacts anything shaped like a live secret and flags the candidate
with "secrets_redacted": true so a reviewer knows to check the fact is still
useful without the raw value (usually yes: "the password lives in Vaultwarden
under X" survives redaction fine; the value itself never needs to be in KB).

USAGE
  python3 scripts/distill_learnings.py                    # pass 1 (propose)
  python3 scripts/distill_learnings.py --apply ids.txt     # pass 2 (commit approved)
  python3 scripts/distill_learnings.py --input other.md --out-dir /tmp/x   # overrides
"""

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = "/opt/local-se/kb/session-learnings.md"
DEFAULT_OUT_DIR = REPO_ROOT / "docs" / "dreaming"

__version__ = "1.0.0"
# 1.0.0 — initial release (TRAUM Thread 1, Prompt 1.7).

# --- topic classification (index_to_kb's own known tag list) ---------------

TOPIC_KEYWORDS = {
    "llama-cpp": ["llama-server", "llama.cpp", "llama-cpp", "flash-attn", "kv cache",
                  "k cache", "kv-cache", "reasoning_content", "gguf"],
    "searxng": ["searxng"],
    "pfsense": ["pfsense", "pf-sense", "pf sense", "opnsense"],
    "openwebui": ["openwebui", "owui", "open webui"],
    "wan2.1": ["wan2.1", "wan 2.1", "wan2 "],
    "comfyui": ["comfyui"],
    "stable-diffusion": ["stable diffusion", "sdxl"],
    "infrastructure": ["grafana", "docker", "prometheus", "wsl2", "wsl ", "ntfs",
                        " ssh ", "exporter", "node3090", "node4090", "hermes",
                        "elasticsearch", " es ", "vaultwarden", "systemd", "overlay2"],
}
DEFAULT_TOPIC = "lse-operations"

# --- provenance format contract (docs/dreaming/DESIGN.md §6.2) -------------
# Three fixed, non-interchangeable formats. dream_apply.py (Thread 2) is
# expected to validate against the same patterns — kept here as the one
# place that already has to construct one of them (the backfill form) so
# tests import a single source of truth instead of re-deriving the regex.

PROVENANCE_BACKFILL_RE = re.compile(r"^debrief-backfill-\d{4}-\d{2}-\d{2}$")
PROVENANCE_LIVE_DEBRIEF_RE = re.compile(r"^debrief \d{4}-\d{2}-\d{2}$")
PROVENANCE_DREAM_RE = re.compile(r"^dream-\d{4}-\d{2}-\d{2}$")
_PROVENANCE_PATTERNS = {
    "backfill": PROVENANCE_BACKFILL_RE,
    "live-debrief": PROVENANCE_LIVE_DEBRIEF_RE,
    "dream": PROVENANCE_DREAM_RE,
}


def is_valid_provenance(value: str, kind: str = "any") -> bool:
    """Validate a proposal's provenance string against the fixed formats.
    kind: 'backfill' ("debrief-backfill-YYYY-MM-DD", this script's own
    output), 'live-debrief' ("debrief YYYY-MM-DD", space — SKILL.md's live
    confirm-gate flow), 'dream' ("dream-YYYY-MM-DD", hyphen — Thread 2), or
    'any' (matches whichever of the three). The space-vs-hyphen distinction
    between live-debrief and backfill/dream is deliberate and fixed by their
    respective source prompts — this validator does not normalize between
    them, it only checks conformance."""
    if kind == "any":
        return any(p.match(value) for p in _PROVENANCE_PATTERNS.values())
    pat = _PROVENANCE_PATTERNS.get(kind)
    if pat is None:
        raise ValueError(f"unknown provenance kind {kind!r}")
    return bool(pat.match(value))


# --- secret pattern sweep (mirrors goethe_mcp.py's redaction, standalone) --

_SECRET_VALUE_RE = re.compile(
    r"(?i)\b((?:value|password|passwd|pwd|secret|token|api[_ -]?key)\s*[:=]?\s*)"
    r"[`\"']([A-Za-z0-9][A-Za-z0-9_\-.!@#$%^&*]{7,})[`\"']"
)


def redact_secrets(text: str) -> tuple:
    """Returns (redacted_text, was_redacted)."""
    if not text:
        return text, False
    hit = [False]

    def _sub(m):
        hit[0] = True
        return f"{m.group(1)}<redacted-by-distiller>"

    out = _SECRET_VALUE_RE.sub(_sub, text)
    return out, hit[0]


# --- markdown parsing --------------------------------------------------------

SESSION_HEADER_RE = re.compile(
    r"^##\s*Session\s+(\d{4}-\d{2}-\d{2})\s*[—-]\s*(.+?)\s*$", re.MULTILINE
)
SUBHEADER_RE = re.compile(r"^###\s*(.+?)\s*$", re.MULTILINE)
FAILED_BLOCK_RE = re.compile(
    r"\*\*Attempted:\*\*\s*(?P<attempted>.+?)\s*\n"
    r"\s*\*\*Failed because:\*\*\s*(?P<failed_because>.+?)\s*\n"
    r"\s*\*\*Fix:\*\*\s*(?P<fix>.+)",
    re.DOTALL,
)


class SessionEntry:
    def __init__(self, session_date, topic_line, order):
        self.session_date = session_date
        self.topic_line = topic_line
        self.order = order  # 1-based position in the file, for stable ids
        self.what_worked = []       # list[str]
        self.what_failed = []       # list[dict(attempted, failed_because, fix, raw_ok)]
        self.key_facts = []         # list[str]
        self.other_sections = {}    # dict[header title] -> list[str bullets]


def _bullets(block_text: str) -> list:
    """Extract top-level '- ...' bullet lines (not sub-bullets) from a block."""
    out = []
    for line in block_text.splitlines():
        m = re.match(r"^-\s+(.+)$", line.strip())
        if m:
            out.append(m.group(1).strip())
    return out


def _split_failed_blocks(block_text: str) -> list:
    """Split a 'What failed and why' section into per-bullet chunks (blank-line
    separated) and parse each into attempted/failed_because/fix."""
    chunks = [c.strip() for c in re.split(r"\n\s*\n", block_text) if c.strip()]
    results = []
    for chunk in chunks:
        chunk = re.sub(r"^-\s+", "", chunk)  # drop leading bullet marker
        m = FAILED_BLOCK_RE.match(chunk)
        if m:
            results.append({
                "attempted": m.group("attempted").strip(),
                "failed_because": m.group("failed_because").strip(),
                "fix": m.group("fix").strip(),
                "raw_ok": True,
            })
        elif chunk:
            # Off-template block — keep the raw text as a low-confidence
            # candidate rather than silently dropping it.
            results.append({"attempted": "", "failed_because": "", "fix": chunk, "raw_ok": False})
    return results


def parse_entries(text: str) -> list:
    headers = list(SESSION_HEADER_RE.finditer(text))
    entries = []
    for i, h in enumerate(headers):
        start = h.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        body = text[start:end]
        entry = SessionEntry(h.group(1), h.group(2), i + 1)

        subheaders = list(SUBHEADER_RE.finditer(body))
        for j, sh in enumerate(subheaders):
            s_start = sh.end()
            s_end = subheaders[j + 1].start() if j + 1 < len(subheaders) else len(body)
            section_body = body[s_start:s_end]
            title = sh.group(1).strip().lower()
            if title == "what worked":
                entry.what_worked.extend(_bullets(section_body))
            elif title == "what failed and why":
                entry.what_failed.extend(_split_failed_blocks(section_body))
            elif title == "key facts":
                entry.key_facts.extend(_bullets(section_body))
            else:
                entry.other_sections.setdefault(sh.group(1).strip(), []).extend(_bullets(section_body))
        entries.append(entry)
    return entries


# --- classification heuristics ----------------------------------------------

_STEP_SIGNAL_RE = re.compile(r"`[^`]+`.*`[^`]+`|;\s*\S|&&|\bthen\b", re.IGNORECASE)
_VERIFY_SIGNAL_RE = re.compile(r"\bverif|\bcheck\b|\bconfirm|curl |-w \"%\{http_code", re.IGNORECASE)


def _looks_procedural(text: str) -> bool:
    """Heuristic: multi-step command sequence, optionally with a verify signal.
    Deliberately conservative — false negatives (routed to kb-fact instead)
    are safe; false positives (a single fact mis-labeled as a procedure) are
    the ones worth avoiding, per the "classify, don't transcribe" discipline
    this mirrors from SKILL.md."""
    return bool(_STEP_SIGNAL_RE.search(text)) and len(text) > 60


def _guess_topic(*texts) -> str:
    joined = " ".join(t.lower() for t in texts if t)
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(kw in joined for kw in keywords):
            return topic
    return DEFAULT_TOPIC


def _short_title(text: str, limit: int = 90) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^-+\s*", "", text)
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def _extract_verification(text: str, context: dict) -> tuple:
    """Best-effort verification text for a skill-candidate, honestly flagged
    when nothing usable was found — never re-purpose "why the OLD approach
    failed" as "how the NEW one was verified", those are different claims."""
    for candidate_text in (text, context.get("fix", "")):
        if candidate_text:
            for sentence in re.split(r"(?<=[.!?])\s+", candidate_text):
                if _VERIFY_SIGNAL_RE.search(sentence):
                    return sentence.strip(), True
    return ("Not separately captured in the original debrief entry — verify by "
            "re-applying and confirming expected behavior before trusting this "
            "skill record."), False


def _token_overlap(a: str, b: str) -> float:
    ta = set(re.findall(r"[a-z0-9]{3,}", a.lower()))
    tb = set(re.findall(r"[a-z0-9]{3,}", b.lower()))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def build_proposals(entry: SessionEntry) -> list:
    """Returns a list of raw candidate dicts (pre-id, pre-provenance):
    {"kind": "kb-fact"|"skill-candidate", "source_field": str, "text": str}."""
    candidates = []

    # Key facts: 1:1, highest confidence.
    for fact in entry.key_facts:
        candidates.append({"kind": "kb-fact", "source_field": "key_facts", "text": fact})

    # Off-template sections: same treatment as Key facts.
    for header, bullets in entry.other_sections.items():
        for b in bullets:
            candidates.append({"kind": "kb-fact", "source_field": f"other:{header}", "text": b})

    # Fix clauses: fact by default, procedure if it reads as multi-step.
    kb_fact_texts = [c["text"] for c in candidates]
    for block in entry.what_failed:
        fix = block["fix"]
        if not fix:
            continue
        if _looks_procedural(fix):
            candidates.append({"kind": "skill-candidate", "source_field": "fix",
                                "text": fix, "context": block})
        else:
            # Dedup against Key facts already captured for this entry.
            if any(_token_overlap(fix, kf) > 0.5 for kf in kb_fact_texts):
                continue
            candidates.append({"kind": "kb-fact", "source_field": "fix", "text": fix,
                                "context": block})
            kb_fact_texts.append(fix)

    # What-worked bullets: skill-candidate only if procedural, and not a
    # restatement of something already proposed for this entry.
    all_texts_so_far = [c["text"] for c in candidates]
    for item in entry.what_worked:
        if not _looks_procedural(item):
            continue  # a single-fact "worked" bullet — not a procedure, skip
        if any(_token_overlap(item, t) > 0.6 for t in all_texts_so_far):
            continue  # restates a fact/fix already captured
        candidates.append({"kind": "skill-candidate", "source_field": "what_worked", "text": item})

    return candidates


def make_proposal(entry: SessionEntry, candidate: dict, seq: int) -> dict:
    prov = f"debrief-backfill-{entry.session_date}"
    assert is_valid_provenance(prov, kind="backfill"), f"malformed provenance: {prov!r}"
    # entry.order (1-based file position) disambiguates same-date sessions —
    # three entries in this corpus share 2026-06-07 alone; date-only ids would
    # silently collide and make --apply ambiguous across unrelated sessions.
    pid = f"{entry.session_date}-e{entry.order}-{seq}"
    text, redacted = redact_secrets(candidate["text"])
    context = candidate.get("context") or {}
    evidence_bits = [text]
    if context.get("attempted"):
        att, r2 = redact_secrets(context["attempted"])
        evidence_bits.insert(0, f"Attempted: {att}")
        redacted = redacted or r2
    if context.get("failed_because"):
        fb, r3 = redact_secrets(context["failed_because"])
        evidence_bits.insert(1 if context.get("attempted") else 0, f"Failed because: {fb}")
        redacted = redacted or r3
    evidence = " | ".join(evidence_bits)[:800]

    topic = _guess_topic(entry.topic_line, text)
    why_source = {
        "key_facts": "Key facts bullet — template already writes these as standalone atomic facts.",
        "fix": "Corrected value/command from a What-failed-and-why block.",
        "what_worked": "Reads as a multi-step reusable procedure, not a single fact.",
    }.get(candidate["source_field"], f"Bullet under non-standard section '{candidate['source_field']}'.")

    if candidate["kind"] == "kb-fact":
        has_evidence = len(evidence) >= 40
        source_tier = "ground_truth" if has_evidence else "primary"
        quality_score = 0.85 if has_evidence else 0.6
        # Triage aid, not a tool argument: key_facts bullets are atomic by the
        # template's own construction (highest confidence); fix-derived facts
        # carry more inferred framing (medium); anything secret-redacted drops
        # a tier regardless, since the redaction changed the original text.
        confidence = "high" if candidate["source_field"] == "key_facts" else "medium"
        if redacted:
            confidence = "low"
        proposal = {
            "id": pid,
            "confidence": confidence,
            "type": "kb-fact",
            "call": "index_to_kb",
            "provenance": prov,
            "args": {
                "content": text,
                "title": _short_title(text),
                "topic": topic,
                "source_tier": source_tier,
                "quality_score": quality_score,
                "evidence": evidence if source_tier == "ground_truth" else "",
                "verified_against": "",
                "volatility": "slow",
            },
            "why": f"{why_source} From session {entry.session_date} ({entry.topic_line}).",
            "secrets_redacted": redacted,
            "source_entry_order": entry.order,
        }
    else:
        occupation = "network-engineer" if topic == "pfsense" else "Local System Engineer"
        verification, verification_found = _extract_verification(text, context)
        confidence = "medium" if verification_found else "low"
        if redacted:
            confidence = "low"
        proposal = {
            "id": pid,
            "confidence": confidence,
            "type": "skill-candidate",
            "call": "skill_record",
            "provenance": prov,
            "args": {
                "task": _short_title(text, 90),
                "occupation": occupation,
                "procedure": text,
                "verification": verification,
                "preconditions": "",
                "failure_modes": context.get("failed_because", "") if context else "",
                "provenance": prov,
                "source_tier": "ground_truth",
                "quality": 0.6,
            },
            "why": f"{why_source} From session {entry.session_date} ({entry.topic_line})."
                   + ("" if verification_found else " NEEDS TIGHTENING: no explicit verify "
                      "step found in the source text — confirm/rewrite verification before approving."),
            "secrets_redacted": redacted,
            "source_entry_order": entry.order,
        }
    return proposal


# --- pass 1: propose ---------------------------------------------------------

def render_review_md(proposals: list, entries: list) -> str:
    by_order = {}
    for p in proposals:
        by_order.setdefault(p["source_entry_order"], []).append(p)

    by_conf = {"high": [], "medium": [], "low": []}
    for p in proposals:
        by_conf[p["confidence"]].append(p["id"])

    lines = [
        "# SCRIBE-2 backfill — candidate review",
        "",
        f"Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')} by "
        "scripts/distill_learnings.py from kb/session-learnings.md.",
        "",
        f"Total candidates: {len(proposals)} "
        f"({sum(1 for p in proposals if p['type']=='kb-fact')} kb-fact, "
        f"{sum(1 for p in proposals if p['type']=='skill-candidate')} skill-candidate).",
        "",
        f"Confidence breakdown (triage aid, not a tool field — see each proposal's "
        f"'confidence'): **high** {len(by_conf['high'])} (Key-facts bullets — atomic by "
        f"the template's own construction), **medium** {len(by_conf['medium'])} "
        f"(fix-derived facts / skill-candidates with a verify signal found), "
        f"**low** {len(by_conf['low'])} (secrets were redacted from the source text, or "
        f"no explicit verification step could be found — read these before approving).",
        "",
        "Approve by writing approved ids (one per line) to a text file and running:",
        "`python3 scripts/distill_learnings.py --apply ids.txt`",
        "",
        "All high-confidence ids, if you want a starting point:",
        "```",
        "\n".join(by_conf["high"]),
        "```",
        "",
        "---",
        "",
    ]
    for entry in entries:
        entry_proposals = by_order.get(entry.order, [])
        if not entry_proposals:
            continue
        lines.append(f"## Session {entry.session_date} — {entry.topic_line}")
        lines.append("")
        for p in entry_proposals:
            flag = " ⚠ secrets redacted — check before approving" if p["secrets_redacted"] else ""
            lines.append(f"### [{p['id']}] ({p['confidence']}) {p['type']} → `{p['call']}`{flag}")
            if p["type"] == "kb-fact":
                a = p["args"]
                lines.append(f"- title: {a['title']}")
                lines.append(f"- topic: {a['topic']} | source_tier: {a['source_tier']} | "
                              f"quality_score: {a['quality_score']}")
                lines.append(f"- content: {a['content']}")
                if a["evidence"]:
                    lines.append(f"- evidence: {a['evidence']}")
            else:
                a = p["args"]
                lines.append(f"- task: {a['task']}")
                lines.append(f"- occupation: {a['occupation']} | provenance: {a['provenance']}")
                lines.append(f"- procedure: {a['procedure']}")
                lines.append(f"- verification: {a['verification']}")
            lines.append(f"- why: {p['why']}")
            lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def run_pass1(input_path: str, out_dir: Path) -> dict:
    text = Path(input_path).read_text(encoding="utf-8")
    entries = parse_entries(text)

    proposals = []
    for entry in entries:
        raw_candidates = build_proposals(entry)
        for seq, cand in enumerate(raw_candidates, 1):
            proposals.append(make_proposal(entry, cand, seq))

    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / "backfill-proposals.jsonl"
    review_path = out_dir / "backfill-review.md"

    with open(jsonl_path, "w", encoding="utf-8") as f:
        for p in proposals:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    review_path.write_text(render_review_md(proposals, entries), encoding="utf-8")

    stats = {
        "entries": len(entries),
        "candidates": len(proposals),
        "kb_fact": sum(1 for p in proposals if p["type"] == "kb-fact"),
        "skill_candidate": sum(1 for p in proposals if p["type"] == "skill-candidate"),
        "secrets_redacted": sum(1 for p in proposals if p["secrets_redacted"]),
        "jsonl_path": str(jsonl_path),
        "review_path": str(review_path),
    }
    return stats


# --- pass 2: apply -----------------------------------------------------------

def _load_tools_instance():
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    import goethe  # noqa: E402
    return goethe.Tools()


def read_ids_file(path: str) -> set:
    ids = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            ids.add(line.split()[0])
    return ids


def run_pass2(ids_path: str, out_dir: Path) -> dict:
    approved = read_ids_file(ids_path)
    jsonl_path = out_dir / "backfill-proposals.jsonl"
    if not jsonl_path.exists():
        raise SystemExit(f"[distill_learnings] {jsonl_path} not found — run pass 1 first")

    proposals = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                proposals.append(json.loads(line))

    to_apply = [p for p in proposals if p["id"] in approved]
    unknown_ids = approved - {p["id"] for p in proposals}
    if unknown_ids:
        print(f"[distill_learnings] WARNING: {len(unknown_ids)} approved id(s) not found in "
              f"{jsonl_path}: {sorted(unknown_ids)}", file=sys.stderr)

    inst = _load_tools_instance()
    applied_log_path = out_dir / "backfill-applied.jsonl"
    applied, failed = 0, 0

    with open(applied_log_path, "a", encoding="utf-8") as log:
        for p in to_apply:
            ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
            try:
                if p["call"] == "index_to_kb":
                    result = inst.index_to_kb(**p["args"])
                elif p["call"] == "skill_record":
                    result = inst.skill_record(**p["args"])
                else:
                    raise ValueError(f"unknown call type {p['call']!r}")
                ok = not (isinstance(result, str) and result.startswith(("BLOCKED:", "ERROR")))
                applied += 1 if ok else 0
                failed += 0 if ok else 1
                log.write(json.dumps({"ts": ts, "id": p["id"], "call": p["call"],
                                       "ok": ok, "result": str(result)[:2000]},
                                      ensure_ascii=False) + "\n")
                print(f"[distill_learnings] {p['id']} ({p['call']}): "
                      f"{'OK' if ok else 'FAILED'} — {str(result)[:150]}")
            except Exception as e:
                failed += 1
                log.write(json.dumps({"ts": ts, "id": p["id"], "call": p["call"],
                                       "ok": False, "result": f"EXCEPTION: {e}"},
                                      ensure_ascii=False) + "\n")
                print(f"[distill_learnings] {p['id']} ({p['call']}): EXCEPTION — {e}", file=sys.stderr)

    return {
        "proposed": len(proposals),
        "approved": len(to_apply),
        "rejected": len(proposals) - len(to_apply),
        "applied_ok": applied,
        "applied_failed": failed,
        "unknown_ids": sorted(unknown_ids),
        "applied_log_path": str(applied_log_path),
    }


def main():
    ap = argparse.ArgumentParser(description="SCRIBE-2 backfill distiller.")
    ap.add_argument("--input", default=DEFAULT_INPUT,
                     help=f"path to session-learnings.md (default: {DEFAULT_INPUT})")
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR),
                     help=f"output directory (default: {DEFAULT_OUT_DIR})")
    ap.add_argument("--apply", metavar="IDS_FILE", default=None,
                     help="pass 2: apply approved ids from this file (commits to ES)")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)

    if args.apply:
        stats = run_pass2(args.apply, out_dir)
        print(f"\n[distill_learnings] proposed={stats['proposed']} "
              f"approved={stats['approved']} rejected={stats['rejected']} "
              f"applied_ok={stats['applied_ok']} applied_failed={stats['applied_failed']}")
        if stats["unknown_ids"]:
            print(f"[distill_learnings] unknown ids ignored: {stats['unknown_ids']}")
        print(f"[distill_learnings] applied log: {stats['applied_log_path']}")
    else:
        stats = run_pass1(args.input, out_dir)
        print(f"[distill_learnings] {stats['entries']} session entries -> "
              f"{stats['candidates']} candidates "
              f"({stats['kb_fact']} kb-fact, {stats['skill_candidate']} skill-candidate, "
              f"{stats['secrets_redacted']} with secrets redacted)")
        print(f"[distill_learnings] proposals: {stats['jsonl_path']}")
        print(f"[distill_learnings] review:    {stats['review_path']}")
        print("[distill_learnings] NO writes made — review, then run with --apply ids.txt")


if __name__ == "__main__":
    main()
