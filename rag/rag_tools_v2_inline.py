"""
LSE RAG Tools v2
Authority-aware KB indexing for OpenWebUI.
Tools: index_to_kb, record_outcome, mentor_correct
"""

import json
from datetime import datetime, timezone
from typing import Optional

# ── module-level helpers (shared across all tool calls) ───────────────────────

_ES_URL   = "http://localhost:9200"
_KB_INDEX = "lse-kb"

_AUTHORITY_CEILINGS = {
    "official_vendor": 1.00,
    "mentor":          1.00,
    "empirical":       0.95,
    "community":       0.75,
    "inferred":        0.60,
}

_OFFICIAL_DOCS_MAP = {
    "https://learn.microsoft.com/en-us/powershell":     "PowerShell",
    "https://learn.microsoft.com/en-us/windows/wsl":    "WSL",
    "https://learn.microsoft.com/en-us/windows":        "Windows",
    "https://learn.microsoft.com/en-us/dotnet":         ".NET",
    "https://learn.microsoft.com/en-us/azure":          "Azure",
    "https://docs.python.org":                          "Python",
    "https://peps.python.org":                          "Python PEP",
    "https://docs.docker.com":                          "Docker",
    "https://docs.podman.io":                           "Podman",
    "https://www.elastic.co/docs":                      "Elasticsearch",
    "https://www.elastic.co/guide":                     "Elasticsearch",
    "https://elastic.co/docs":                          "Elasticsearch",
    "https://github.com/ggerganov/llama.cpp":           "llama.cpp",
    "https://github.com/comfyanonymous/ComfyUI":        "ComfyUI",
    "https://docs.comfy.org":                           "ComfyUI",
    "https://docs.openwebui.com":                       "OpenWebUI",
    "https://github.com/open-webui/open-webui":         "OpenWebUI",
    "https://manpages.ubuntu.com":                      "Ubuntu",
    "https://ubuntu.com/server/docs":                   "Ubuntu",
    "https://help.ubuntu.com":                          "Ubuntu",
    "https://www.debian.org/doc":                       "Debian",
    "https://docs.nvidia.com":                          "NVIDIA/CUDA",
    "https://developer.nvidia.com/docs":                "NVIDIA/CUDA",
    "https://docs.searxng.org":                         "SearxNG",
    "https://github.com/searxng/searxng":               "SearxNG",
    "https://playwright.dev/docs":                      "Playwright",
    "https://playwright.dev/python/docs":               "Playwright",
    "https://nodejs.org/en/docs":                       "Node.js",
    "https://nodejs.org/docs":                          "Node.js",
    "https://docs.npmjs.com":                           "npm",
    "https://git-scm.com/docs":                         "Git",
    "https://git-scm.com/book":                         "Git",
    "https://man7.org/linux/man-pages":                 "Linux",
    "https://www.kernel.org/doc":                       "Linux Kernel",
    "https://systemd.io":                               "systemd",
    "https://www.freedesktop.org/software/systemd/man": "systemd",
    "https://www.gnu.org/software/bash/manual":         "Bash",
    "https://www.gnu.org/manual":                       "GNU",
    "https://huggingface.co/docs/transformers":         "HuggingFace Transformers",
    "https://huggingface.co/docs/hub":                  "HuggingFace Hub",
    "https://fastapi.tiangolo.com":                     "FastAPI",
    "https://docs.pydantic.dev":                        "Pydantic",
    "https://www.uvicorn.org":                          "Uvicorn",
    "https://www.sqlite.org/docs.html":                 "SQLite",
    "https://www.sqlite.org/lang":                      "SQLite",
}

_COMMUNITY_DOMAINS = {
    "stackoverflow.com", "superuser.com", "unix.stackexchange.com",
    "askubuntu.com", "serverfault.com", "github.com", "gist.github.com",
    "reddit.com", "discourse.ubuntu.com", "forums.developer.nvidia.com",
    "discuss.pytorch.org", "discuss.huggingface.co",
}


def _classify_url(url: str) -> tuple:
    if not url:
        return ("inferred", "unknown")
    url = url.strip().rstrip("/")
    best_len, best_auth, best_topic = 0, "inferred", "unknown"
    for prefix, topic in _OFFICIAL_DOCS_MAP.items():
        p = prefix.rstrip("/")
        if url.startswith(p) and len(p) > best_len:
            best_len, best_auth, best_topic = len(p), "official_vendor", topic
    if best_auth == "official_vendor":
        return (best_auth, best_topic)
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        if domain in _COMMUNITY_DOMAINS:
            return ("community", "community")
    except Exception:
        pass
    return ("inferred", "unknown")


def _get_es():
    from elasticsearch import Elasticsearch
    return Elasticsearch(_ES_URL)


def _compute_quality(raw_score, source_authority, empirical_runs,
                     empirical_failures, mentor_verified, updated_at):
    ceiling = _AUTHORITY_CEILINGS.get(source_authority, 0.60)
    total   = empirical_runs + empirical_failures
    if total == 0:
        conf_w = 1.0
    else:
        sr     = empirical_runs / total
        conf   = min(total / 10.0, 1.0)
        conf_w = 0.5 + conf * (sr - 0.5)
    rec_w = 1.0
    if updated_at:
        try:
            ts    = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            age   = (datetime.now(timezone.utc) - ts).days
            rec_w = max(0.70, 1.0 - (age / 365) * 0.15)
        except (ValueError, TypeError):
            pass
    if mentor_verified:
        return min(ceiling, raw_score)
    return min(ceiling, raw_score * conf_w * rec_w)


# ── OpenWebUI requires all tool methods inside a class named 'Tools' ──────────

class Tools:

    def index_to_kb(
        self,
        title:              str,
        content:            str,
        topic:              str,
        tags:               list          = None,
        source_url:         str           = "",
        source_authority:   str           = "",
        quality_score:      float         = 0.7,
        empirical_runs:     int           = 0,
        empirical_failures: int           = 0,
        doc_id:             Optional[str] = None,
    ) -> str:
        """
        Index a knowledge entry into the LSE KB with authority metadata.

        Args:
            title:              Short descriptive title.
            content:            Full text to index.
            topic:              Broad topic keyword (e.g. 'PowerShell', 'Docker').
            tags:               Optional keyword tags.
            source_url:         Source URL — enables auto-classification of authority tier.
            source_authority:   Override tier: official_vendor | empirical | mentor | community | inferred.
            quality_score:      Base score before composite formula (0.0–1.0).
            empirical_runs:     Known successful executions confirming this entry.
            empirical_failures: Known executions that contradict this entry.
            doc_id:             Optional stable ID for upsert / idempotent indexing.

        Returns:
            JSON with doc_id, computed quality_score, and authority tier.
        """
        now = datetime.now(timezone.utc).isoformat()

        if not source_authority:
            source_authority, _ = _classify_url(source_url)
        if source_authority not in _AUTHORITY_CEILINGS:
            source_authority = "inferred"

        computed_quality = _compute_quality(
            raw_score=quality_score,
            source_authority=source_authority,
            empirical_runs=empirical_runs,
            empirical_failures=empirical_failures,
            mentor_verified=False,
            updated_at=now,
        )

        doc = {
            "title":              title,
            "content":            content,
            "topic":              topic,
            "tags":               tags or [],
            "source_url":         source_url,
            "source_authority":   source_authority,
            "authority_score":    _AUTHORITY_CEILINGS[source_authority],
            "quality_score":      round(computed_quality, 4),
            "empirical_runs":     empirical_runs,
            "empirical_failures": empirical_failures,
            "mentor_verified":    False,
            "mentor_note":        "",
            "conflicting":        False,
            "created_at":         now,
            "updated_at":         now,
        }

        es     = _get_es()
        kwargs = {"index": _KB_INDEX, "document": doc}
        if doc_id:
            kwargs["id"] = doc_id

        resp = es.index(**kwargs)
        es.indices.refresh(index=_KB_INDEX)

        return json.dumps({
            "status":        "indexed",
            "doc_id":        resp["_id"],
            "quality_score": doc["quality_score"],
            "authority":     source_authority,
        })

    def record_outcome(
        self,
        doc_id:  str,
        success: bool,
        note:    str = "",
    ) -> str:
        """
        Record a real-world execution result against a KB entry.

        Increments empirical_runs (success=True) or empirical_failures (success=False)
        and recomputes quality_score. Call after every procedure execution.

        Args:
            doc_id:  Elasticsearch document ID of the KB entry.
            success: True if the procedure worked; False if it failed.
            note:    Optional context (e.g. error message on failure).

        Returns:
            JSON with updated quality_score and run counts.
        """
        es  = _get_es()
        now = datetime.now(timezone.utc).isoformat()

        try:
            hit = es.get(index=_KB_INDEX, id=doc_id)
        except Exception as exc:
            return json.dumps({"error": f"Doc {doc_id} not found: {exc}"})

        src      = hit["_source"]
        runs     = src.get("empirical_runs", 0)     + (1 if success else 0)
        failures = src.get("empirical_failures", 0) + (0 if success else 1)

        new_quality = _compute_quality(
            raw_score=src.get("quality_score", 0.7),
            source_authority=src.get("source_authority", "inferred"),
            empirical_runs=runs,
            empirical_failures=failures,
            mentor_verified=src.get("mentor_verified", False),
            updated_at=now,
        )

        update_body: dict = {"doc": {
            "empirical_runs":     runs,
            "empirical_failures": failures,
            "quality_score":      round(new_quality, 4),
            "updated_at":         now,
        }}
        if note:
            tag      = "[success]" if success else "[failure]"
            existing = src.get("mentor_note", "")
            update_body["doc"]["mentor_note"] = f"{existing}\n{now} {tag}: {note}".strip()

        es.update(index=_KB_INDEX, id=doc_id, body=update_body)
        es.indices.refresh(index=_KB_INDEX)

        return json.dumps({
            "doc_id":             doc_id,
            "success":            success,
            "empirical_runs":     runs,
            "empirical_failures": failures,
            "quality_score":      round(new_quality, 4),
        })

    def mentor_correct(
        self,
        doc_id:        str,
        correction:    str,
        authority:     str            = "human",
        new_score:     Optional[float]= None,
        mark_correct:  bool           = True,
        flag_conflict: bool           = False,
    ) -> str:
        """
        Apply a mentor correction to a KB entry. Highest-authority write operation.

        mark_correct=True  — endorses entry: mentor_verified=True, quality→0.95
        mark_correct=False — deprecates entry: quality→0.10, conflicting=True

        Args:
            doc_id:        ES document ID to correct.
            correction:    The mentor's note / correction text.
            authority:     'human' | 'opus-4' | 'opus-4-5' — recorded in mentor_note.
            new_score:     Explicit quality override (0.0–1.0).
            mark_correct:  True = endorse; False = deprecate.
            flag_conflict: Also set conflicting=True (auto-set when mark_correct=False).

        Returns:
            JSON confirming the update.
        """
        es  = _get_es()
        now = datetime.now(timezone.utc).isoformat()

        try:
            hit = es.get(index=_KB_INDEX, id=doc_id)
        except Exception as exc:
            return json.dumps({"error": f"Doc {doc_id} not found: {exc}"})

        src = hit["_source"]

        if mark_correct:
            quality     = new_score if new_score is not None else 0.95
            verified    = True
            conflicting = flag_conflict
        else:
            quality     = new_score if new_score is not None else 0.10
            verified    = False
            conflicting = True

        tag      = f"[{authority}] {'✓ CORRECT' if mark_correct else '✗ INCORRECT'}"
        existing = src.get("mentor_note", "")
        new_note = f"{existing}\n{now} {tag}: {correction}".strip()

        es.update(index=_KB_INDEX, id=doc_id, body={"doc": {
            "source_authority": "mentor",
            "authority_score":  1.00,
            "quality_score":    round(quality, 4),
            "mentor_verified":  verified,
            "mentor_note":      new_note,
            "conflicting":      conflicting,
            "updated_at":       now,
        }})
        es.indices.refresh(index=_KB_INDEX)

        return json.dumps({
            "doc_id":          doc_id,
            "mentor":          authority,
            "mark_correct":    mark_correct,
            "quality_score":   round(quality, 4),
            "mentor_verified": verified,
            "conflicting":     conflicting,
            "note_preview":    new_note[:200],
        })
