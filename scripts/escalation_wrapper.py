"""
EscalationWrapper — gymnasium.Wrapper above LSEChallengeEnv.

Adds:
  - KB context injection at episode start (search_kb on challenge description)
  - Attempt embedding + cosine stagnation detection
  - Stagnation-breaking observation injection (before attempt N+1)
  - Mandatory web search before escalation (no penalty, always indexes)
  - Claude API escalation (after web-assisted attempt fails)
  - Dual KB writes on escalation: record_error() + index_to_kb()
  - Point deltas: -5 escalation, +1 indexing, +2 context quality, +2 KB hit

Full wrapper stack:
  LSEChallengeEnv
    └─ EscalationWrapper          ← this file
        └─ TimeLimit(max_episode_steps=3)   (applied externally)
            └─ RecordEpisodeStatistics       (applied externally)

Environment variables / config:
  ES_URL        Elasticsearch base URL       default: http://localhost:9200
  OLLAMA_URL    Ollama base URL              default: http://localhost:11434
  SEARXNG_URL   SearXNG base URL             default: http://localhost:8088
  CLAUDE_MODEL  Anthropic model ID           default: claude-sonnet-4-6
  ANTHROPIC_API_KEY  (from /home/sy5/.lse/secrets or env)
"""

import json
import math
import os
import time
from typing import Optional

import gymnasium as gym
import requests

# ── Constants ─────────────────────────────────────────────────────────────────

ES_URL        = os.getenv("ES_URL",    "http://localhost:9200")
OLLAMA_URL    = os.getenv("OLLAMA_URL","http://localhost:11434")
SEARXNG_URL   = os.getenv("SEARXNG_URL","http://localhost:8088")
CLAUDE_MODEL  = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

EMBED_MODEL   = "nomic-embed-text"
EMBED_PREFIX  = "search_query: "     # required by nomic-embed-text instruction tuning
KB_INDEX      = "lse-kb"
ERR_INDEX     = "lse-errors"
KB_THRESHOLD  = 0.72                 # min score for KB hit
STAGNATION_THRESHOLD = 0.85          # cosine similarity → stagnation


# ── Wrapper ───────────────────────────────────────────────────────────────────

class EscalationWrapper(gym.Wrapper):
    """
    Sits directly above LSEChallengeEnv. Manages the full escalation gate:

    Episode state machine:
      NORMAL      → forward steps to inner env, track embeddings
      STAG_BREAK  → stagnation detected; inject frame-breaking prompt into obs
      WEB_ASSIST  → web search run; result injected into obs; one more attempt
      ESCALATED   → Claude called; episode terminates

    Observation flow:
      reset() → search_kb(challenge_embedding) → inject kb_context if hit
      step()  → embed action → check cosine → forward to inner env
              → on truncated/stagnation: web search → inject → return (not yet terminated)
              → on web-assist failure:   Claude API → KB writes → terminate
    """

    def __init__(
        self,
        env: gym.Env,
        stagnation_threshold: float = STAGNATION_THRESHOLD,
        kb_threshold: float = KB_THRESHOLD,
        verbose: bool = True,
    ):
        super().__init__(env)
        self.stagnation_threshold = stagnation_threshold
        self.kb_threshold = kb_threshold
        self.verbose = verbose

        # Per-episode state
        self._embeddings: list[list[float]] = []
        self._stagnation_count: int = 0
        self._stagnation_injected: bool = False
        self._web_search_done: bool = False
        self._web_search_query: str = ""
        self._web_search_result: str = ""
        self._kb_assisted: bool = False
        self._escalated: bool = False
        self._escalation_context_quality: Optional[str] = None  # "good"|"poor"
        self._last_info: dict = {}

    # ── Gymnasium API ─────────────────────────────────────────────────────────

    def reset(self, seed=None, options=None):
        options = options or {}

        # Reset episode state
        self._embeddings = []
        self._stagnation_count = 0
        self._stagnation_injected = False
        self._web_search_done = False
        self._web_search_query = ""
        self._web_search_result = ""
        self._kb_assisted = False
        self._escalated = False
        self._escalation_context_quality = None

        obs, info = self.env.reset(seed=seed, options=options)

        # Step 0: search_kb on challenge description
        kb_hit = self._search_kb(obs["challenge"])
        if kb_hit:
            self._kb_assisted = True
            options["kb_context"] = kb_hit
            # Re-reset with kb_context injected
            obs, info = self.env.reset(seed=seed, options=options)
            self._log("KB HIT at reset — context injected into observation")

        self._last_info = info
        return obs, info

    def step(self, action: str):
        # 1. Embed the action
        embedding = self._embed(action)
        self._embeddings.append(embedding)

        # 2. Check cosine stagnation (needs at least 2 attempts)
        # stagnation_early (count==1): inject frame-breaking prompt, allow one more attempt
        # stagnation_now  (count>=2): web search fires
        stagnation_early = False
        stagnation_now = False
        if len(self._embeddings) >= 2:
            cos = _cosine(self._embeddings[-1], self._embeddings[-2])
            if cos > self.stagnation_threshold:
                self._stagnation_count += 1
                self._log(f"Cosine similarity: {cos:.3f} > {self.stagnation_threshold} "
                          f"(stagnation_count={self._stagnation_count})")
                stagnation_early = (self._stagnation_count == 1)
                stagnation_now   = (self._stagnation_count >= 2)
            else:
                self._stagnation_count = 0
                self._log(f"Cosine similarity: {cos:.3f} — attempts are diverging")

        # 3. Forward to inner env
        obs, reward, terminated, truncated, info = self.env.step(action)
        self._last_info = info
        n = info["attempt_n"]

        # 4. Solved — index solution to KB, apply KB bonus
        if terminated:
            self._log(f"SOLVED on attempt {n} — reward {reward}")
            self._on_solve(action, info)
            if self._kb_assisted:
                reward += 2.0  # KB hit bonus
                self._log("KB hit bonus +2 applied")
            info["kb_assisted"] = self._kb_assisted
            info["escalated"] = False
            return obs, reward, terminated, truncated, info

        # 5. Stagnation or attempt limit → web search path
        should_go_to_web = stagnation_now or truncated

        if should_go_to_web and not self._web_search_done:
            self._log("Entering web search step — "
                      f"{'stagnation' if stagnation_now else 'attempt limit'}")
            obs, reward, truncated = self._do_web_search(obs, info, stagnation_now)
            info["web_assist"] = True
            info["stagnation_triggered"] = stagnation_now
            return obs, reward, terminated, truncated, info

        # 6. Web-assisted attempt also failed → escalate
        if self._web_search_done and (truncated or stagnation_now):
            self._log("Web-assisted attempt failed — escalating to Claude API")
            reward, terminated, truncated = self._do_escalation(action, info)
            info["escalated"] = True
            info["escalation_context_quality"] = self._escalation_context_quality
            info["kb_assisted"] = self._kb_assisted
            return obs, reward, terminated, truncated, info

        # 7. Normal partial — return as-is
        info["kb_assisted"] = self._kb_assisted
        info["escalated"] = False

        # Inject stagnation-breaking prompt into obs for next attempt
        # Fires on stagnation_early (count==1) — gives model ONE frame-breaking attempt
        # before web search escalates on count>=2
        if stagnation_early and not self._stagnation_injected:
            obs = self._inject_stagnation_break(obs, info)
            self._stagnation_injected = True

        return obs, reward, terminated, truncated, info

    # ── Web search path ───────────────────────────────────────────────────────

    def _do_web_search(self, obs: dict, info: dict, stagnation: bool):
        """
        Step 4 in the escalation gate: mandatory web search.
        No penalty. Always indexes result to KB regardless of outcome.
        Returns modified (obs, reward, truncated=False) — one more attempt allowed.
        """
        challenge = self._last_info.get("challenge_id", "unknown")
        domain = info.get("discipline", "sysadmin")

        # Construct query — stagnation-aware if applicable
        if stagnation and self._embeddings:
            # Search for the failure mode, not the solution
            base = obs["challenge"].split("TASK:")[1][:300] if "TASK:" in obs["challenge"] else ""
            query = f"why fails {domain} {base[:150]} troubleshooting"
            self._log(f"Stagnation-aware query: {query[:80]}...")
        else:
            base = obs["challenge"].split("TASK:")[1][:300] if "TASK:" in obs["challenge"] else obs["challenge"][:300]
            query = f"{domain} {base[:200]}"

        self._web_search_query = query
        result = self._searxng_search(query)
        self._web_search_result = result
        self._web_search_done = True

        # Always index to KB — failure to solve doesn't mean the result is worthless
        self._log("Indexing web search result to KB (unconditional)")
        self._index_to_kb(
            content=f"Query: {query}\n\nResult:\n{result}",
            title=f"web-search: {challenge}",
            topic=domain,
            source_url=f"searxng:{query[:50]}",
            quality_score=0.7,  # community-tier default until authority classifier runs
        )

        # Inject web result into observation
        web_context = (
            f"WEB SEARCH RESULT (query: {query[:100]}):\n\n{result}\n\n"
            f"Use this information in your next attempt. "
            f"This is your final attempt before escalation."
        )
        obs = dict(obs)
        obs["kb_context"] = web_context

        self._log(f"Web search complete — result injected ({len(result)} chars)")
        return obs, 0.0, False  # reward=0, truncated=False → one more attempt

    # ── Escalation path ───────────────────────────────────────────────────────

    def _do_escalation(self, last_action: str, info: dict) -> tuple[float, bool, bool]:
        """
        Step 5: call Claude API with full context.
        Returns (reward, terminated, truncated).
        """
        self._escalated = True

        # Build escalation context package
        inner = self.env.unwrapped
        attempts = getattr(inner, "_attempt_texts", [])
        assertion_results = getattr(inner, "_attempt_assertion_results", [])
        challenge_desc = inner._current_challenge.get("description", "")
        challenge_id = inner._current_challenge.get("id", "unknown")

        failure_reasons = []
        for i, results in enumerate(assertion_results, 1):
            failed = [r for r in results if not r["passed"]]
            if failed:
                failure_reasons.append(
                    f"Attempt {i}: failed assertions — " +
                    "; ".join(f"{r['id']}: {r.get('error', 'assertion not satisfied')}" for r in failed)
                )

        context_quality = _assess_context_quality(attempts, failure_reasons)
        self._escalation_context_quality = context_quality

        escalation_prompt = _build_escalation_prompt(
            challenge_id=challenge_id,
            challenge_desc=challenge_desc,
            attempts=attempts,
            failure_reasons=failure_reasons,
            web_query=self._web_search_query,
            web_result=self._web_search_result,
            success_criteria=inner._current_challenge.get("success_criteria", "{}"),
        )

        self._log(f"Calling Claude API ({CLAUDE_MODEL}) — context quality: {context_quality}")
        claude_solution = self._call_claude(escalation_prompt)

        if claude_solution:
            self._log(f"Claude solution received ({len(claude_solution)} chars)")
            # Dual KB writes
            self._record_error(
                error_text=f"Challenge {challenge_id} — {'; '.join(failure_reasons[:2])}",
                context=challenge_desc[:500],
                resolution=claude_solution[:1000],
            )
            self._index_to_kb(
                content=_build_kb_entry(
                    attempts, failure_reasons,
                    self._web_search_query, self._web_search_result,
                    claude_solution,
                ),
                title=f"escalation: {challenge_id}",
                topic=inner._current_challenge.get("domain", "sysadmin"),
                source_url=f"competition_escalation:{challenge_id}",
                quality_score=1.0,
            )
        else:
            self._log("Claude API call failed — no solution returned")

        # Point deltas
        reward = -5.0   # escalation penalty
        reward += 1.0   # indexing bonus
        if context_quality == "good":
            reward += 2.0  # context quality bonus
            self._log("Context quality bonus +2 applied")

        self._log(f"Escalation complete — net reward delta: {reward:.1f}")
        return reward, True, False  # terminated=True, truncated=False

    # ── Solve handler ─────────────────────────────────────────────────────────

    def _on_solve(self, action: str, info: dict):
        """Index the successful solution to lse-kb at quality 0.9."""
        inner = self.env.unwrapped
        challenge_id = inner._current_challenge.get("id", "unknown")
        domain = inner._current_challenge.get("domain", "sysadmin")

        self._index_to_kb(
            content=f"Challenge: {challenge_id}\n\nSolution:\n{action}",
            title=f"solve: {challenge_id} (attempt {info['attempt_n']})",
            topic=domain,
            source_url=f"competition_solve:{challenge_id}",
            quality_score=0.9,
        )
        self._log(f"Solution indexed to KB (quality 0.9)")

    # ── Stagnation-breaking injection ─────────────────────────────────────────

    def _inject_stagnation_break(self, obs: dict, info: dict) -> dict:
        """
        Modify the observation to include the stagnation-breaking prompt.
        Forces the model to name its prior assumption before the next attempt.
        """
        inner = self.env.unwrapped
        attempts = getattr(inner, "_attempt_texts", [])
        attempt_summary = _summarise_attempts(attempts)

        inject = (
            f"\n\n{'='*60}\n"
            f"STAGNATION DETECTED — Your last two attempts are semantically equivalent.\n"
            f"Similarity score exceeded {self.stagnation_threshold}.\n\n"
            f"Attempts so far:\n{attempt_summary}\n\n"
            f"Before your next attempt, you MUST:\n"
            f"  1. State explicitly: what assumption have all prior attempts made?\n"
            f"  2. State whether that assumption has been verified.\n"
            f"  3. If unverified: approach the problem WITHOUT that assumption.\n"
            f"{'='*60}\n"
        )
        obs = dict(obs)
        obs["challenge"] = obs["challenge"] + inject
        self._log("Stagnation-breaking prompt injected into observation")
        return obs

    # ── Embedding + KB + Search ───────────────────────────────────────────────

    def _embed(self, text: str) -> list[float]:
        """Embed text using Ollama nomic-embed-text. Returns empty list on failure."""
        try:
            resp = requests.post(
                f"{OLLAMA_URL}/api/embeddings",
                json={"model": EMBED_MODEL, "prompt": EMBED_PREFIX + text[:2000]},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json().get("embedding", [])
        except Exception as e:
            self._log(f"Embedding failed: {e}")
            return []

    def _search_kb(self, query_text: str) -> Optional[str]:
        """
        Hybrid kNN + BM25 search against lse-kb.
        Returns the top result content if score >= kb_threshold, else None.
        """
        embedding = self._embed(query_text[:1000])
        if not embedding:
            return None
        try:
            body = {
                "size": 1,
                "min_score": self.kb_threshold,
                "knn": {
                    "field": "embedding",
                    "query_vector": embedding,
                    "k": 5,
                    "num_candidates": 50,
                    "boost": 0.7,
                },
                "query": {
                    "multi_match": {
                        "query": query_text[:500],
                        "fields": ["title^2", "content"],
                        "boost": 0.3,
                    }
                },
            }
            resp = requests.post(
                f"{ES_URL}/{KB_INDEX}/_search",
                json=body, timeout=10,
            )
            resp.raise_for_status()
            hits = resp.json().get("hits", {}).get("hits", [])
            if hits:
                src = hits[0]["_source"]
                score = hits[0]["_score"]
                self._log(f"KB hit — score {score:.3f}: {src.get('title', '')[:60]}")
                return src.get("content", "")
        except Exception as e:
            self._log(f"KB search failed: {e}")
        return None

    def _index_to_kb(
        self,
        content: str,
        title: str,
        topic: str,
        source_url: str,
        quality_score: float,
    ):
        """Index a document to lse-kb. Deduplicates by cosine > 0.92."""
        embedding = self._embed(content[:2000])
        doc = {
            "title": title,
            "content": content,
            "topic": topic,
            "source_url": source_url,
            "quality_score": quality_score,
            "embedding": embedding,
            "competition_kb": True,
            "indexed_at": _now_iso(),
        }
        try:
            resp = requests.post(
                f"{ES_URL}/{KB_INDEX}/_doc",
                json=doc, timeout=10,
            )
            resp.raise_for_status()
            self._log(f"KB indexed: {title[:60]} (quality {quality_score})")
        except Exception as e:
            self._log(f"KB index failed: {e}")

    def _record_error(self, error_text: str, context: str, resolution: str):
        """Record error pattern + resolution to lse-errors index."""
        embedding = self._embed(error_text)
        doc = {
            "error_text": error_text,
            "context": context,
            "resolution": resolution,
            "embedding": embedding,
            "occurrence_count": 1,
            "indexed_at": _now_iso(),
        }
        try:
            resp = requests.post(
                f"{ES_URL}/{ERR_INDEX}/_doc",
                json=doc, timeout=10,
            )
            resp.raise_for_status()
            self._log(f"Error pattern recorded to lse-errors")
        except Exception as e:
            self._log(f"record_error failed: {e}")

    def _searxng_search(self, query: str) -> str:
        """Query SearXNG and return concatenated result snippets."""
        try:
            resp = requests.get(
                f"{SEARXNG_URL}/search",
                params={
                    "q": query,
                    "format": "json",
                    "categories": "general,it",
                    "language": "en",
                },
                headers={"X-Forwarded-For": "127.0.0.1"},
                timeout=20,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])[:5]
            if not results:
                return "No results found."
            parts = []
            for r in results:
                title = r.get("title", "")
                url = r.get("url", "")
                snippet = r.get("content", "")
                parts.append(f"[{title}]({url})\n{snippet}")
            return "\n\n".join(parts)
        except Exception as e:
            self._log(f"SearXNG search failed: {e}")
            return f"Web search unavailable: {e}"

    def _call_claude(self, prompt: str) -> Optional[str]:
        """
        Call Claude API. Uses anthropic Python SDK if available and API key present.
        Falls back to OpenWebUI API endpoint.
        """
        api_key = _load_api_key()

        # Try anthropic SDK
        if api_key:
            try:
                import anthropic
                client = anthropic.Anthropic(api_key=api_key)
                msg = client.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=4096,
                    messages=[{"role": "user", "content": prompt}],
                )
                return msg.content[0].text
            except ImportError:
                self._log("anthropic SDK not installed — trying OpenWebUI")
            except Exception as e:
                self._log(f"Anthropic SDK call failed: {e} — trying OpenWebUI")

        # Fallback: OpenWebUI OpenAI-compat endpoint
        owui_url = os.getenv("OWUI_URL", "http://localhost:3000")
        owui_key = os.getenv("OWUI_KEY", "")
        try:
            resp = requests.post(
                f"{owui_url}/api/chat/completions",
                headers={
                    "Authorization": f"Bearer {owui_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": CLAUDE_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 4096,
                },
                timeout=120,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            self._log(f"OpenWebUI Claude call failed: {e}")
            return None

    # ── Logging ───────────────────────────────────────────────────────────────

    def _log(self, msg: str):
        if self.verbose:
            cid = self._last_info.get("challenge_id", "?")
            n = self._last_info.get("attempt_n", 0)
            print(f"  [EscalationWrapper | {cid} | a{n}] {msg}")


# ── Module-level helpers ──────────────────────────────────────────────────────

def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors. Returns 0.0 if either is empty."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _load_api_key() -> Optional[str]:
    """Load ANTHROPIC_API_KEY from env or /home/sy5/.lse/secrets."""
    key = os.getenv("ANTHROPIC_API_KEY")
    if key:
        return key
    secrets_path = "/home/sy5/.lse/secrets"
    try:
        with open(secrets_path) as f:
            for line in f:
                if line.startswith("ANTHROPIC_API_KEY="):
                    return line.strip().split("=", 1)[1]
    except (FileNotFoundError, PermissionError):
        pass
    return None


def _summarise_attempts(attempts: list[str]) -> str:
    """Return a short summary of each attempt for stagnation injection."""
    lines = []
    for i, text in enumerate(attempts[-3:], max(1, len(attempts) - 2)):
        snippet = text[:200].replace("\n", " ")
        lines.append(f"  Attempt {i}: {snippet}...")
    return "\n".join(lines)


def _assess_context_quality(attempts: list[str], failure_reasons: list[str]) -> str:
    """
    Heuristically assess escalation context quality.
    'good' if failure reasons are specific and attempts are diverse.
    'poor' if failure reasons are vague or no attempts were made.
    """
    if not attempts or not failure_reasons:
        return "poor"
    # Check for specificity in failure reasons
    specific = sum(
        1 for r in failure_reasons
        if any(kw in r for kw in ["assert", "NameError", "KeyError", "ip", "port", "api"])
    )
    if specific >= len(failure_reasons) // 2 and len(attempts) >= 2:
        return "good"
    return "poor"


def _build_escalation_prompt(
    challenge_id: str,
    challenge_desc: str,
    attempts: list[str],
    failure_reasons: list[str],
    web_query: str,
    web_result: str,
    success_criteria: str,
) -> str:
    """Build the full context package sent to Claude."""
    criteria = json.loads(success_criteria) if success_criteria else {}
    assertions = criteria.get("assertions", [])

    parts = [
        f"ESCALATION REQUEST — Challenge {challenge_id}",
        "",
        "CHALLENGE DESCRIPTION:",
        challenge_desc,
        "",
        "ASSERTIONS THAT MUST PASS:",
    ]
    for a in assertions:
        parts.append(f"  [{a['id']}] {a['description']}")
        parts.append(f"         {a['code']}")

    parts += ["", "ATTEMPTS MADE (all failed):"]
    for i, (attempt, reason) in enumerate(
        zip(attempts, failure_reasons + [""] * len(attempts)), 1
    ):
        parts.append(f"\nAttempt {i}:")
        parts.append(attempt[:600])
        if reason:
            parts.append(f"Failure: {reason}")

    if web_query:
        parts += [
            "",
            f"WEB SEARCH PERFORMED: {web_query}",
            "RESULT:",
            web_result[:1000],
            "(Web-assisted attempt also failed.)",
        ]

    parts += [
        "",
        "TASK: Provide a complete, working solution that satisfies all assertions above.",
        "Return your solution as a ```json code block with the keys the assertions reference.",
        "Explain your reasoning briefly before the code block.",
    ]
    return "\n".join(parts)


def _build_kb_entry(
    attempts: list[str],
    failure_reasons: list[str],
    web_query: str,
    web_result: str,
    claude_solution: str,
) -> str:
    """Build the layered KB entry for an escalation event."""
    parts = [
        "ESCALATION KB ENTRY",
        "",
        "ATTEMPTS (what was tried):",
    ]
    for i, (a, r) in enumerate(zip(attempts, failure_reasons + [""] * len(attempts)), 1):
        parts.append(f"  Attempt {i}: {a[:300]}")
        if r:
            parts.append(f"  Failure:   {r}")
    parts += [
        "",
        f"WEB SEARCH QUERY: {web_query}",
        f"WEB SEARCH RESULT: {web_result[:500]}",
        "",
        "CLAUDE SOLUTION (what worked):",
        claude_solution,
    ]
    return "\n".join(parts)
