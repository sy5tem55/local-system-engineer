"""goethe_web.py — WebMixin: web/reddit search, URL fetch, download monitoring.

D7 Step 10 (2026-07-31), fourth and final mixin extraction in the series
(NetSec -> NodeLifecycle -> Planner -> Web). Same shape as goethe_kb.KBMixin:
a plain mixin class with no __init__ and no Valves declaration, reading
self.valves / self._log / self._NODE_REGISTRY from the host Tools class at
runtime via MRO. This module must never import goethe.py — that would be a
cycle. Import direction is one-way: goethe.py imports this module.

MEMBERSHIP (16 elements: 8 public/private group methods + 8 helpers).
Group (named in docs/D7-MIXIN-EXTRACTION-PLAN.md Step 10): search_web,
search_reddit, fetch_url, get_github_release, verify_source_claims,
monitor_download, _fetch_via_browser, _active_download_guard.
Helpers (the plan's "8 external dependencies", 9 named including _log):
_budget_gate, _camoufox_scrape, _consume_time_banner, _extract_pdf_text,
_extract_text_from_html, _parse_reddit_posts, _reddit_browser_fallback,
_strip_years. _log is NOT included — it is the universal shared base method
and stays on Tools per the standing rule established in Steps 3-9.

COUPLING ANALYSIS (recorded in /tmp/d7_web_decision.md before any edit was
made, per the plan's Step 10 requirement to decide in writing first). A full
call-graph scan found ZERO of the 8 named helpers called from outside this
group — cleaner than NodeLifecycleMixin's one shared dependency
(_live_node_profile, Step 8). Three second-order findings, none of which
block extraction:

  1. _consume_time_banner (moved) calls self._time_banner() and
     self._dream_banner(). Both are ALSO called by Tools.time_check, which
     has nothing to do with web/fetch. _time_banner and _dream_banner are
     deliberately LEFT ON TOOLS and reached via self through MRO — the same
     pattern as _live_node_profile in Step 8. self._time_banner_emitted is
     an instance attribute set in Tools.__init__, not a method; no action
     needed, it is readable via self from any mixin automatically.
  2. fetch_url (moved) reads self._fetch_cache, also a Tools.__init__
     instance attribute (line ~431: self._fetch_cache: dict = {}). Same
     situation as above — no method to leave behind, just an attribute
     that any mixin can read via self once Tools.__init__ has run.
  3. _reddit_browser_fallback (moved) reads self._NODE_REGISTRY, which
     already lives on NodeLifecycleMixin (Step 8) — a cross-mixin read
     resolved by MRO once both mixins sit in Tools' bases, not a
     duplication. The existing D6 regression assertion
     (t._NODE_REGISTRY["node3090"]["hostname"] == "node3090.home.arpa") is
     re-run as this step's runtime proof for exactly this reason.

REVERSE COUPLING: _active_download_guard (moved) is called by
Tools._validate_command_safety — the safety-gate method, permanently
excluded from all D7 extraction. This is a Tools method reaching into a
WebMixin method; MRO resolves it the same direction as everything else
(Tools inherits WebMixin). Called out explicitly, not silently relied on,
because D5 (2026-07-31) found live vulnerabilities in this exact safety
code path and any change to what it can reach deserves a named check.

COMMENT-ABSORPTION CORRECTIONS. Two of the sixteen elements' immediately-
preceding comments were NOT absorbed despite being multi-line, because they
are not specific to the element: _budget_gate sat directly below a generic
"# -- Tool functions --" section-header comment that demarcates the whole
remaining class, not this method, so only its own
"# -- Anti-spiral budget gate (v1.7.1) --" header moved with it. search_web
sat directly below a stray historical comment about the unrelated
pfsense_graphql/pfsense_query extraction (a prior, unconnected refactor) —
that comment was left in place in goethe.py rather than deleted or moved,
since it documents something else entirely. Every other multi-line
absorption (_camoufox_scrape, _strip_years, _fetch_via_browser) was verified
by reading its content and confirmed specific to the element it precedes.

Byte-for-byte relocation: no method body, signature, or docstring was
edited while moving. Only module-level imports were added below, matching
the established pattern from goethe_netsec.py / goethe_node.py (methods in
this codebase import requests/re/time/HTMLParser locally inside their own
bodies per convention; only json/os/subprocess/datetime were relying on
goethe.py's module-level imports and needed to be replicated here).
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime

from goethe_constants import _LOOPBACK, _LSE_BASE_PATH


class WebMixin:
    """Web/reddit search, URL fetch, GitHub release lookup, download monitoring.

    Mixed into Tools alongside KBMixin, NetSecMixin, NodeLifecycleMixin, and
    PlannerMixin. Reads self.valves, self._log, self._NODE_REGISTRY,
    self._time_banner, self._dream_banner and the self._fetch_cache /
    self._time_banner_emitted instance attributes via MRO — none of those
    are declared on this class, all resolve through the host Tools instance.
    """

    # ── Anti-spiral budget gate (v1.7.1) ─────────────────────────────────────

    def _budget_gate(self) -> str:
        """Rolling-window budget shared by search_web/search_reddit/fetch_url.

        Returns '' (allowed), a low-budget banner (allowed, prepend/append it),
        or refusal text starting with 'BUDGET EXHAUSTED' (caller must return it
        without executing). Code-level enforcement: never relies on model attention.
        """
        import json as _json  # noqa: PLC0415
        import time  # noqa: PLC0415
        import os  # noqa: PLC0415

        path = os.path.join(
            os.path.dirname(self.valves.TASKS_DB) or ".", ".search_budget.json"
        )
        window_s = max(1, int(self.valves.SEARCH_BUDGET_WINDOW_MIN)) * 60
        budget = max(1, int(self.valves.SEARCH_BUDGET))
        now = time.time()
        try:
            with open(path, encoding="utf-8") as f:
                stamps = [t for t in _json.load(f) if now - t < window_s]
        except (OSError, json.JSONDecodeError):
            stamps = []
        if len(stamps) >= budget:
            retry_min = int((window_s - (now - stamps[0])) / 60) + 1
            self._log(f"BUDGET-GATE: refused (≥{budget} in {window_s//60}min)")
            return (
                f"BUDGET EXHAUSTED — web access paused: {budget} search/fetch calls "
                f"in {window_s // 60} min (anti-spiral gate). Do NOT retry or "
                "reformulate the query.\n"
                "REQUIRED NOW, in this order:\n"
                "  1. task_checkpoint(...) — record findings, UNVERIFIED items, and "
                "the next_prompt a future session should start from.\n"
                "  2. Surface your best partial answer to the user immediately, "
                "explicitly marking every unverified claim as unverified.\n"
                f"Budget resets in ~{retry_min} min. Continuing to search instead of "
                "surfacing is a protocol violation. UNVERIFIED-URL RULE: any URL or "
                "hostname you did not receive from a tool result is UNVERIFIED — "
                "presenting one to the user is a protocol violation."
            )
        stamps.append(now)
        try:
            with open(path, "w", encoding="utf-8") as f:
                _json.dump(stamps, f)
        except OSError:
            pass
        remaining = budget - len(stamps)
        if remaining <= 2:
            return (
                f"\n\n⚠ SEARCH BUDGET: only {remaining} of {budget} web calls left "
                f"in this {window_s // 60}-min window. Surface findings NOW; if the "
                "task is incomplete, call task_checkpoint() before anything else."
            )
        return ""


    def _active_download_guard(self, command: str) -> str:
        """Block starting a NEW download while one is already running on the host,
        so the LSE cannot clobber an in-progress partial file (data corruption,
        SY5 report). Returns a refusal string when `command` initiates a download
        AND a real downloader process is already active; '' otherwise.

        Code-level enforcement: the LSE has repeatedly re-issued download commands
        (curl / hf download) instead of calling monitor_download() to check
        progress, restarting the transfer and producing partial/corrupt files —
        docstrings did not hold. Conservative to avoid false positives: pgrep only
        runs for download-initiating commands; curl must carry an output flag so a
        health-check curl never trips it; hf/wget/aria2c/git-lfs always qualify;
        fail-open if the host cannot be probed."""
        import re as _re  # noqa: PLC0415
        import subprocess as _sp  # noqa: PLC0415

        _INITIATORS = (
            "curl ", "wget ", "aria2c ", "hf download",
            "huggingface-cli download", "git lfs pull", "git lfs fetch",
        )
        if not any(t in command.lower() for t in _INITIATORS):
            return ""  # not a download command — skip the probe entirely
        try:
            ps = _sp.run(
                ["pgrep", "-af",
                 "curl|wget|aria2c|hf download|huggingface-cli|git-lfs"],
                capture_output=True, text=True, timeout=5,
            )
        except subprocess.SubprocessError:
            return ""  # cannot probe — fail open, do not block
        qualify = _re.compile(
            r"(?:wget |aria2c |hf download|huggingface-cli download|git-lfs|"
            r"curl\b.*(?:-O\b|-o |--output|--remote-name))"
        )
        active = [
            ln.strip()
            for ln in ps.stdout.splitlines()
            if ln.strip() and "pgrep" not in ln and qualify.search(ln)
            and "/dev/null" not in ln  # health-probe curls, not downloads
            and not _re.search(r"-o\s+-(?:\s|$)", ln)
        ]
        if not active:
            return ""
        self._log(f"DOWNLOAD-GUARD: blocked new download; active={active[0][:120]}")
        return (
            "BLOCKED: a download is already running on this host:\n"
            f"    {active[0][:200]}\n"
            "Starting another download now writes a second stream into the same "
            "partial file and CORRUPTS it — this is the reported failure.\n"
            "  • To CHECK progress, call the monitor_download tool with "
            "(file_path, expected_bytes). Do NOT re-run the download command.\n"
            "  • Start a new download ONLY after the current one COMPLETES, or "
            "after you intentionally kill it AND delete the partial file."
        )

    def search_web(self, query: str, max_results: int = 5) -> str:
        """
        Search the web via the local SearxNG instance at localhost:8088.

        KB-FIRST RULE — mandatory, no exceptions:
          ALWAYS call search_kb() before calling this function.
          If search_kb() returns results with quality_score >= 0.6, use those directly.
          Only call search_web() when search_kb() returns "KB miss" or quality < 0.6.
          After finding a good result here, call index_to_kb() to store it for next time.
          Skipping search_kb() before search_web() is a protocol violation.

        GATE: Only call this when search_kb() has been called first and returned a miss.

        REQUIRED SEQUENCE — follow this exactly, no exceptions:
          Step 1: Write to the user BEFORE calling this function:
                  "Searching for [topic] because [reason training knowledge is insufficient]."
          Step 2: Call search_web exactly once for this topic.
          Step 3: SEARCH-THEN-FETCH — if the snippet (≤300 chars) is too short to answer
                  the question fully, call fetch_url() on the top result URL to get the
                  full page content before synthesising. Skip fetch if snippet is sufficient.
          Step 4: Synthesise the answer in ≤3 sentences. Do NOT paste raw results verbatim.
          Step 5: Call index_to_kb() with the synthesised result.

        Skipping Step 1 is a protocol violation — do not call this function without
        first announcing what you are searching for and why.
        Do not call search_web more than once for the same topic.

        TIME DISCIPLINE (v0.3.1 — ENFORCED IN CODE, not prose; CHRONOS-4 retired
        the old YEAR-INJECTION and 30d/7d staleness rules from this docstring):
          - Standalone years (e.g. "2025") are STRIPPED from the query server-side —
            they filter out current results. Compound ids like CVE-2025-1234 survive.
          - The first search_kb/search_web return of each session carries a [TIME]
            banner (system-clock based; call time_check() for NTP-verified time).
          - KB freshness is enforced by volatility TTLs in search_kb ([EXPIRED] tags
            + rerank demotion) — no manual date arithmetic needed.
          For version lookups of GitHub projects, prefer get_github_release.
        """
        import requests  # noqa: PLC0415

        query = self._strip_years(query)
        _tb = self._consume_time_banner()

        self._log(f"SEARCH: {query} max={max_results}")
        _gate = self._budget_gate()
        if _gate.startswith("BUDGET EXHAUSTED"):
            return _tb + _gate
        try:
            resp = requests.get(
                self.valves.SEARXNG_URL,
                params={"q": query, "format": "json", "categories": "general"},
                headers={"X-Forwarded-For": _LOOPBACK, "X-Real-IP": _LOOPBACK},
                timeout=(5, 10),
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])[:max_results]
            if not results:
                return _tb + "No results found." + _gate
            lines = []
            for r in results:
                title = r.get("title", "Untitled")
                url = r.get("url", "")
                snippet = r.get("content", "")[:300]
                lines.append(f"**{title}**\n{url}\n{snippet}")
            return _tb + "\n---\n".join(lines) + _gate
        except (requests.RequestException, json.JSONDecodeError) as e:
            return f"ERROR searching SearxNG: {str(e)}"


    # ── CAMOUFOX REDDIT SCRAPING (v0.3.10) ──────────────────────────────────

    def _camoufox_scrape(self, url: str, wait_s: int = 8) -> str:
        """Use Camoufox on node3090 to scrape a URL. Returns accessibility tree text."""
        import requests  # noqa: PLC0415
        import time  # noqa: PLC0415

        base = self.valves.CAMOUFOX_URL.rstrip("/")
        try:
            # Step 1: Open tab
            resp = requests.post(
                f"{base}/tabs",
                json={"userId": "lse", "sessionKey": "lse", "url": url},
                timeout=15,
            )
            resp.raise_for_status()
            tab_id = resp.json().get("tabId")
            if not tab_id:
                return ""

            # Step 2: Wait for page load
            time.sleep(wait_s)

            # Step 3: Get snapshot
            snap_resp = requests.get(
                f"{base}/tabs/{tab_id}/snapshot",
                params={"userId": "lse", "sessionKey": "lse"},
                timeout=10,
            )
            snap_resp.raise_for_status()
            snapshot = snap_resp.json().get("snapshot", "")

            # Close tab
            try:
                requests.delete(
                    f"{base}/tabs/{tab_id}",
                    params={"userId": "lse", "sessionKey": "lse"},
                    timeout=5,
                )
            except Exception:  # noqa: BLE001 (tab cleanup)
                pass  # Non-critical cleanup

            return snapshot
        except requests.RequestException as e:
            self._log(f"CAMOUFOX-ERROR: {e}")
            return ""


    def _parse_reddit_posts(self, snapshot: str) -> list:
        """Extract Reddit posts from Camoufox accessibility tree.
        Returns list of dicts: {title, url, votes, comments, author, time}
        
        Actual format from Reddit search:
          heading "Title" [level=2]:
            link "Title" [eN]:
              /url: /r/subreddit/comments/...
          text: ·
          time: Xh ago
          link "Title" [eN]:
            /url: /r/subreddit/comments/...
          text: N votes·N comments
        """
        import re  # noqa: PLC0415

        posts = []
        lines = snapshot.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]
            # Look for heading level=2 (Reddit post titles)
            if 'heading "' in line and '[level=2]' in line:
                m = re.search(r'heading "([^"]+)"', line)
                if m:
                    title = m.group(1)
                    post = {"title": title, "url": "", "votes": "", "comments": "", "author": "", "time": ""}

                    # Look for URL in next 10 lines
                    for j in range(i+1, min(len(lines), i+15)):
                        url_m = re.search(r'/url: (https?://www\.reddit\.com/r/[^\s]+)', lines[j])
                        if url_m:
                            post["url"] = url_m.group(1)
                            break

                    # Look for time in next 15 lines
                    for j in range(i+1, min(len(lines), i+20)):
                        time_m = re.search(r'time: (.+)', lines[j])
                        if time_m:
                            post["time"] = time_m.group(1).strip()
                            break

                    # Look for votes·comments in next 20 lines
                    for j in range(i+1, min(len(lines), i+25)):
                        vc_m = re.search(r'(\d+) votes·(\d+) comments', lines[j])
                        if vc_m:
                            post["votes"] = vc_m.group(1)
                            post["comments"] = vc_m.group(2)
                            break

                    posts.append(post)
            i += 1

        return posts


    def search_reddit(
        self,
        query: str,
        subreddit: str = "",
        max_results: int = 5,
    ) -> str:
        """
        Search Reddit for posts and discussions.

        PRIMARY: Camoufox browser on node3090 — renders JS, bypasses Reddit anti-bot,
        returns structured post data (title, URL, votes, comments, author, time).
        FALLBACK: SearxNG site:reddit.com search if Camoufox is unavailable.

        KB-FIRST RULE — mandatory:
          Call search_kb() before this function. Only call search_reddit() on a KB miss.
          After finding useful results, call index_to_kb() to store for next time.

        REQUIRED SEQUENCE — follow exactly:
          Step 1: Write to user: "Searching Reddit for [topic]."
          Step 2: Call search_reddit() once for this topic.
          Step 3: If snippets are too short, call fetch_url() on the most relevant post URL.
          Step 4: Synthesise in ≤3 sentences. Do NOT paste raw results verbatim.
          Step 5: Call index_to_kb() with the synthesised result.

        Args:
            query:       Search terms (e.g. "RTX 3090 thermal paste replacement")
            subreddit:   Optional subreddit without r/ prefix (e.g. "homelab", "hardware")
                         If empty, searches all of reddit.com
            max_results: Number of results to return (default 5)

        Returns:
            Formatted search results string.
        """
        self._log(f"SEARCH-REDDIT: subreddit={subreddit!r} query={query!r}")

        # ── PRIMARY: Camoufox on node3090 ──────────────────────────────────
        try:
            url = f"https://www.reddit.com/r/{subreddit}/search/?q={query}&sort=hot" if subreddit else f"https://www.reddit.com/search/?q={query}&sort=hot"
            snapshot = self._camoufox_scrape(url, wait_s=8)
            if snapshot:
                posts = self._parse_reddit_posts(snapshot)[:max_results]
                if posts:
                    lines = []
                    for p in posts:
                        title = p.get("title", "Untitled")
                        url = p.get("url", "")
                        votes = p.get("votes", "")
                        comments = p.get("comments", "")
                        author = p.get("author", "")
                        time_ = p.get("time", "")
                        snippet = f"{votes} • {comments}" if votes and comments else ""
                        if author:
                            snippet += f" • u/{author}"
                        if time_:
                            snippet += f" • {time_}"
                        snippet = snippet.lstrip(" • ")
                        lines.append(f"**{title}**\n{url}\n{snippet}")
                    return "\n---\n".join(lines) if lines else "No posts found."
        except Exception as e:  # noqa: BLE001 (camoufox complex chain)
            self._log(f"CAMOUFOX-FAIL: {e}")

        # ── FALLBACK: SearxNG ─────────────────────────────────────────────
        self._log("SEARCH-REDDIT: falling back to SearxNG")
        site = f"site:reddit.com/r/{subreddit}" if subreddit else "site:reddit.com"
        full_query = f"{site} {query}"
        return self.search_web(full_query, max_results=max_results)


    # ── CHRONOS — enforced sense of time (v0.3.1, Workstream B) ─────────────

    def _strip_years(self, query: str) -> str:
        """CHRONOS-4 (v0.3.1): year injection defined out of existence — strip
        standalone 19xx/20xx tokens from search queries (they filter out current
        results). Compound tokens survive: CVE-2025-1234, ubuntu-24.04, b2025x."""
        import re as _re  # noqa: PLC0415

        stripped = _re.sub(r"(?<![\w.\-])(?:19|20)\d{2}(?![\w.\-])", " ", query)
        stripped = _re.sub(r"\s{2,}", " ", stripped).strip()
        if stripped and stripped != query.strip():
            self._log(f"SEARCH year-strip: {query!r} -> {stripped!r}")
            return stripped
        return query


    def _consume_time_banner(self) -> str:
        """Return the [TIME] banner exactly once per session (server-side
        enforcement — compliance must not depend on the model reading
        docstrings). TRAUM Thread 3 (v0.4.0-a): also appends the [DREAM]
        banner (Prompt 3.5) on this same first-call gate — one server-side
        injection point covers both time-anchoring and dream-digest
        awareness before the session's first real search_kb result.
        Do NOT add a second, separate once-per-session flag for [DREAM] —
        reusing _time_banner_emitted is what guarantees the two banners can
        never desync (one firing without the other)."""
        if self._time_banner_emitted:
            return ""
        self._time_banner_emitted = True
        banner = self._time_banner(verified=False)
        dream_line = self._dream_banner()
        if dream_line:
            banner += "\n" + dream_line
        return banner + "\n\n"


    # ------------------------------------------------------------------
    # Browser-rendering fallback helpers (v1.5.29)
    # Used by fetch_url when a reddit.com URL returns empty content
    # or an HTTP error (reddit blocks plain requests with 429/403).
    # ------------------------------------------------------------------

    def _fetch_via_browser(self, url: str, firecrawl_base: str, max_chars: int) -> str:
        """
        POST url to Firecrawl's /v1/scrape endpoint (JS-rendering stack).
        Returns extracted markdown text (capped at max_chars) or "" on any failure.

        firecrawl_base examples:
          "http://localhost:3002"            — node3090 local
          "http://node3090.home.arpa:3002"   — from LUCIFER over LAN
        """
        import requests as _req  # noqa: PLC0415

        try:
            resp = _req.post(
                f"{firecrawl_base}/v1/scrape",
                json={"url": url, "formats": ["markdown"]},
                timeout=45,
            )
            if resp.ok:
                data = resp.json()
                text = ((data.get("data") or {}).get("markdown") or "").strip()
                if text:
                    self._log(
                        f"FETCH-BROWSER: {len(text)} chars from {firecrawl_base}"
                    )
                    return text[:max_chars]
                self._log(f"FETCH-BROWSER: empty markdown from {firecrawl_base}")
            else:
                self._log(
                    f"FETCH-BROWSER: HTTP {resp.status_code} from {firecrawl_base}"
                )
        except _req.RequestException as exc:
            self._log(f"FETCH-BROWSER: error ({firecrawl_base}): {exc}")
        return ""


    def _reddit_browser_fallback(self, url: str, max_chars: int) -> str:
        """
        Route a reddit.com URL to the JS-rendering stack when plain requests
        returns empty content or errors.

        Routing logic (hostname-aware):
          node3090 → local Firecrawl at localhost:3002
          LUCIFER / other → ping node3090.home.arpa; if up, use Firecrawl
                            at node3090:3002 over LAN; if down, return "".

        Returns extracted text or "" (caller must handle the empty case).
        """
        import socket as _socket  # noqa: PLC0415
        import subprocess as _sp  # noqa: PLC0415

        hostname = _socket.gethostname().lower()

        if "node3090" in hostname:
            self._log("REDDIT-FALLBACK: node3090 — local Firecrawl")
            return self._fetch_via_browser(url, self.valves.FIRECRAWL_URL, max_chars)

        # LUCIFER or other node — check node3090 reachability first.
        self._log(f"REDDIT-FALLBACK: pinging {self._NODE_REGISTRY['node3090']['hostname']}")
        ping = _sp.run(
            ["ping", "-c", "1", "-W", "2", self._NODE_REGISTRY["node3090"]["hostname"]],
            capture_output=True,
        )
        if ping.returncode != 0:
            self._log("REDDIT-FALLBACK: node3090 offline — no browser rendering")
            return ""

        self._log("REDDIT-FALLBACK: node3090 up — using remote Firecrawl")
        return self._fetch_via_browser(
            url, self.valves.FIRECRAWL_REMOTE_URL, max_chars
        )


    def _extract_text_from_html(self, html: str, max_chars: int) -> str:
        """Extract plain text from HTML, stripping tags and control chars."""
        from html.parser import HTMLParser
        import re as _re  # noqa: PLC0415

        def _sanitize(s):
            # Strip control chars so stray binary bytes are removed
            return _re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", s)


        class _TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self._text = []
                self._skip = False

            def handle_starttag(self, tag, attrs):
                if tag in ("script", "style", "nav", "footer", "head"):
                    self._skip = True

            def handle_endtag(self, tag):
                if tag in ("script", "style", "nav", "footer", "head"):
                    self._skip = False

            def handle_data(self, data):
                if not self._skip and data.strip():
                    self._text.append(data.strip())

            def get_text(self):
                return " ".join(self._text)


        def _sanitize(s):
            # Strip control chars (except \n\t) so a stray binary byte can never
            # derail the OWUI markdown/HTML renderer downstream (v1.7.7).
            return _re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", s)

        parser = _TextExtractor()
        parser.feed(html)
        return _sanitize(parser.get_text())[:max_chars]


    def fetch_url(self, url: str, max_chars: int = 20000) -> str:
        """
        Fetch the full text content of a URL. Use as Step 3 of the SEARCH-THEN-FETCH
        protocol when search_web returns a snippet too short to answer the question.

        WHEN TO CALL:
          After search_web, if the snippet (≤300 chars) is truncated or insufficient.
          Call on the top result URL only — do not fetch multiple URLs per search.

        WHEN NOT TO CALL:
          If the search_web snippet already answers the question fully.
          Do not use as a substitute for search_web — always search first.

        UNVERIFIED-URL RULE — mandatory:
          Only fetch URLs received from a tool result (search_web, search_kb, KB
          docs, user message). NEVER construct a URL or hostname from memory; if
          a guessed hostname fails DNS, that is evidence the hostname is wrong —
          not that the network is broken. Presenting a self-generated URL to the
          user is a protocol violation.

        Returns plain text with HTML tags stripped, capped at max_chars characters.

        REDDIT BROWSER FALLBACK (v1.5.29):
          When the URL contains "reddit.com" and the plain requests fetch returns
          empty content OR raises an HTTP error (reddit blocks bots with 429/403),
          fetch_url automatically routes to _reddit_browser_fallback():
            node3090: local Firecrawl at localhost:3002
            LUCIFER:  pings node3090, then uses Firecrawl at node3090:3002 over LAN
          Successful browser-rendered results are prefixed "[browser-rendered]"
          and cached normally. If the fallback also fails, the original
          "No text content extracted" or error message is returned.
          Use search_reddit() as a further alternative when both paths fail.
        """
        _gate = self._budget_gate()
        if _gate.startswith("BUDGET EXHAUSTED"):
            self._log(f"FETCH BLOCKED (budget): {url}")
            return _gate
        import requests  # noqa: PLC0415
        self._log(f"FETCH: {url}")
        try:
            resp = requests.get(
                url,
                timeout=15,
                headers={
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
                },
            )
            resp.raise_for_status()
            ctype = resp.headers.get("Content-Type", "").lower()
            head = resp.content[:5]

            # CONTENT-TYPE GUARD (v1.7.7): never feed binary to the HTML parser.
            # A PDF/image/octet-stream body decoded as text is raw FlateDecode
            # garbage — it pollutes context AND breaks OWUI <details> rendering.
            is_pdf = "application/pdf" in ctype or head == b"%PDF-"
            if is_pdf:
                text = self._extract_pdf_text(resp.content)
                if text.strip():
                    import re as _re  # noqa: PLC0415
                    out = _re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", " ".join(text.split()))[:max_chars]
                    self._fetch_cache[url] = {
                        "text": out,
                        "ts": datetime.now().timestamp(),
                    }
                    mandate = (
                        f'\n\n[SOURCE-VERIFY MANDATE] Call verify_source_claims(url="{url}", '
                        'claims="<fact1>, <fact2>") before asserting any version number, '
                        "date, or specific value from this source. NOT_FOUND = report as UNVERIFIED."
                    )
                    return ("[PDF text-extracted] " + out + mandate) + _gate
                return (
                    f"PDF at {url} ({len(resp.content)} bytes) — text could not be "
                    "extracted here (no pdfminer/pypdf). Binary NOT returned. "
                    "Find an HTML source for the same content, or ask the operator "
                    "to run pdftotext. Do NOT retry this URL."
                ) + _gate
            if ctype and not (
                "text/html" in ctype
                or "text/plain" in ctype
                or "xml" in ctype
                or "json" in ctype
            ):
                return (
                    f"Non-text content at {url} (Content-Type: {ctype or 'unknown'}). "
                    "Binary NOT returned to avoid context pollution. Use an HTML "
                    "source. Do NOT retry this URL."
                ) + _gate

            text = self._extract_text_from_html(resp.text, max_chars)
            if text:
                self._fetch_cache[url] = {
                    "text": text,
                    "ts": datetime.now().timestamp(),
                }
                mandate = (
                    f'\n\n[SOURCE-VERIFY MANDATE] Call verify_source_claims(url="{url}", '
                    'claims="<fact1>, <fact2>") before asserting any version number, '
                    "date, or specific value from this source. NOT_FOUND = report as UNVERIFIED."
                )
                return (text + mandate) + _gate
            # Empty extract — try browser rendering for reddit URLs (v1.5.29)
            if "reddit.com" in url.lower():
                self._log("FETCH: empty for reddit URL — trying browser fallback")
                _br = self._reddit_browser_fallback(url, max_chars)
                if _br:
                    _br_mandate = (
                        f'\n\n[SOURCE-VERIFY MANDATE] Call verify_source_claims(url="{url}", '
                        'claims="<fact1>, <fact2>") before asserting any version number, '
                        "date, or specific value from this source. NOT_FOUND = report as UNVERIFIED."
                    )
                    self._fetch_cache[url] = {
                        "text": _br,
                        "ts": datetime.now().timestamp(),
                    }
                    return ("[browser-rendered] " + _br + _br_mandate) + _gate
            return "No text content extracted." + _gate
        except requests.RequestException as e:
            # HTTP error (e.g. 403/429) — also try browser fallback for reddit (v1.5.29)
            if "reddit.com" in url.lower():
                self._log(f"FETCH: exception for reddit URL ({e}) — trying browser fallback")
                _br = self._reddit_browser_fallback(url, max_chars)
                if _br:
                    _br_mandate = (
                        f'\n\n[SOURCE-VERIFY MANDATE] Call verify_source_claims(url="{url}", '
                        'claims="<fact1>, <fact2>") before asserting any version number, '
                        "date, or specific value from this source. NOT_FOUND = report as UNVERIFIED."
                    )
                    self._fetch_cache[url] = {
                        "text": _br,
                        "ts": datetime.now().timestamp(),
                    }
                    return ("[browser-rendered] " + _br + _br_mandate) + _gate
            return f"ERROR fetching {url}: {e}"


    def _extract_pdf_text(self, pdf_bytes: bytes) -> str:
        """Extract text from PDF. Tries pdfminer, falls back to pypdf."""
        try:
            import io  # noqa: PLC0415
            from pdfminer.high_level import extract_text as _pe  # noqa: PLC0415
            return _pe(io.BytesIO(pdf_bytes)) or ""
        except Exception:  # noqa: BLE001 (pdfminer fallback chain)
            try:
                import io  # noqa: PLC0415
                from pypdf import PdfReader as _PR  # noqa: PLC0415
                rdr = _PR(io.BytesIO(pdf_bytes))
                return "\n".join(
                    (p.extract_text() or "") for p in rdr.pages)
            except Exception:  # noqa: BLE001 (pypdf fallback end)
                return ""


    def verify_source_claims(self, url: str, claims: str) -> str:
        """
        SPEC: Re-fetch a source URL and check whether specific factual claims appear
        in it verbatim. Call BEFORE asserting any version number, date, release name,
        or config value derived from fetch_url. Returns FOUND / PARTIAL / NOT_FOUND
        per claim with verbatim ±300-char excerpts.

        MANDATORY after every fetch_url — do NOT skip:
        The fabrication#5 root cause was synthesis-overwrite: the model had the
        correct source in context yet emitted phantom version strings. Prompt fences
        do not hold at synthesis (P25 proven). This function re-fetches the source
        in code and returns what is ACTUALLY there — the model cannot fabricate it.

        NOT_FOUND: claim absent from source. Label it UNVERIFIED. Do NOT retry.
        PARTIAL:   a token from your claim is present but the full claim is absent.
        FOUND:     the claim appears verbatim.

        This call does NOT count against the search budget.

        RULE — UNVERIFIED-URL: only fetch URLs received from a tool result.
        Never construct a URL or hostname from memory.

        NOTES:
        Args: url (source URL from a tool result), claims (comma-separated facts).
        Returns one FOUND/PARTIAL/NOT_FOUND line per claim with verbatim excerpt.
        """
        import re as _re  # noqa: PLC0415

        claim_list = [c.strip() for c in claims.split(",") if c.strip()]
        if not claim_list:
            return 'ERROR: no claims provided. Pass comma-separated facts to verify, e.g. claims="07.23.5, released 2026-05-30"'

        # ── Use cache or re-fetch ────────────────────────────────────────────
        ttl = max(0, int(getattr(self.valves, "SOURCE_VERIFY_CACHE_TTL", 300)))
        cached = self._fetch_cache.get(url)
        if cached and ttl > 0 and (datetime.now().timestamp() - cached["ts"]) < ttl:
            text = cached["text"]
            source_note = "(cached)"
        else:
            import requests as _req  # noqa: PLC0415
            self._log(f"VERIFY-FETCH: {url}")
            try:
                resp = _req.get(
                    url,
                    timeout=15,
                    headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"},
                )
                resp.raise_for_status()
                ctype = resp.headers.get("Content-Type", "").lower()
                is_pdf = "application/pdf" in ctype or resp.content[:5] == b"%PDF-"
                if is_pdf:
                    text = self._extract_pdf_text(resp.content)
                else:
                    text = self._extract_text_from_html(resp.text, 80000)
                text = _re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)[:80000]
                self._fetch_cache[url] = {
                    "text": text,
                    "ts": datetime.now().timestamp(),
                }
                source_note = "(re-fetched)"
            except _req.RequestException as e:
                return (
                    f"VERIFY ERROR: could not fetch {url}: {e}\n"
                    "All claims remain UNVERIFIED — label them as such in your response."
                )

        text_l = text.lower()
        WINDOW = 300

        # ── Check each claim ─────────────────────────────────────────────────
        results = [f"Source: {url} {source_note}"]
        for claim in claim_list:
            claim_l = claim.lower()

            # Exact substring match
            idx = text_l.find(claim_l)
            if idx >= 0:
                start = max(0, idx - WINDOW)
                end = min(len(text), idx + len(claim) + WINDOW)
                excerpt = text[start:end].strip().replace("\n", " ")
                results.append(
                    f"  FOUND    | {claim!r}\n" f"           | excerpt: ...{excerpt}..."
                )
                continue

            # Token-level: version strings first, then long words
            ver_tokens = _re.findall(r"\b\d{1,3}[\.\d]{2,}\b", claim)
            word_tokens = _re.findall(r"\b[a-z0-9_-]{5,}\b", claim_l)
            tokens_to_try = (ver_tokens or []) + word_tokens

            found_tok = None
            for tok in tokens_to_try:
                tidx = text_l.find(tok.lower())
                if tidx >= 0 and found_tok is None:
                    start = max(0, tidx - WINDOW)
                    end = min(len(text), tidx + len(tok) + WINDOW)
                    found_tok = (tok, text[start:end].strip().replace("\n", " "))

            if found_tok:
                tok, exc = found_tok
                results.append(
                    f"  PARTIAL  | {claim!r}\n"
                    f"           | token {tok!r} found but full claim absent.\n"
                    f"           | Read excerpt for what source ACTUALLY says:\n"
                    f"           | ...{exc}..."
                )
            else:
                src_vers = _re.findall(r"\b\d{2}\.\d{2}[\.\d]*\b", text)
                ver_ctx = (
                    ", ".join(dict.fromkeys(src_vers[:8]))
                    if src_vers
                    else "(none found)"
                )
                results.append(
                    f"  NOT_FOUND| {claim!r}\n"
                    f"           | source version strings: {ver_ctx}\n"
                    f"           | → label this claim UNVERIFIED in your response"
                )

        return "\n".join(results)


    def get_github_release(self, repo: str) -> str:
        """
        Return the latest release tag, name, and publish date for a public GitHub repository.
        Use this for version lookups — it is faster and more reliable than search_web
        and avoids date-injection problems.

        WHEN TO USE:
          - Checking the latest llama.cpp release:   get_github_release("ggerganov/llama.cpp")
          - Checking the latest open-webui release:  get_github_release("open-webui/open-webui")
          - Any public GitHub project where you need the current version number.

        WHEN NOT TO USE:
          - Projects not hosted on GitHub (use search_web instead).
          - Package versions managed by apt/pip (use execute_command with apt-cache or pip index).

        Do NOT append a year or any date to the repo string.
        The repo parameter must be in "owner/name" format, e.g. "ggerganov/llama.cpp".
        """
        import requests  # noqa: PLC0415

        repo = repo.strip().strip("/")
        if "/" not in repo or len(repo.split("/")) != 2:
            return f"ERROR: Invalid repo format '{repo}'. Expected 'owner/name'."

        url = f"https://api.github.com/repos/{repo}/releases/latest"
        self._log(f"GITHUB-RELEASE: {repo}")
        try:
            resp = requests.get(
                url,
                headers={
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=10,
            )
            if resp.status_code == 404:
                return f"No releases found for '{repo}' (repo may not exist or have no releases)."
            resp.raise_for_status()
            data = resp.json()
            tag = data.get("tag_name", "unknown")
            name = data.get("name", tag)
            published = data.get("published_at", "unknown date")[:10]  # YYYY-MM-DD
            prerelease = data.get("prerelease", False)
            draft = data.get("draft", False)
            html_url = data.get("html_url", "")

            flags = []
            if prerelease:
                flags.append("pre-release")
            if draft:
                flags.append("draft")
            flag_str = f" [{', '.join(flags)}]" if flags else ""

            return (
                f"Latest release: {tag}{flag_str}\n"
                f"Name:           {name}\n"
                f"Published:      {published}\n"
                f"URL:            {html_url}"
            )
        except requests.RequestException as e:
            return f"ERROR querying GitHub API: {str(e)}"


    def monitor_download(
        self, file_path: str, expected_bytes: int, interface: str = ""
    ) -> str:
        """
        Check download progress using Prometheus network metrics + file size.
        Returns a single status line with completion %, speed, ETA, and SLEEP N.

        PROTOCOL (zero-polling — one call, one sleep, one check):
          1. result = monitor_download(path, size)
          2. COMPLETE  → proceed to next block, call record_outcome()
          3. STALLED   → alert user immediately, do not sleep-loop
          4. Otherwise → parse SLEEP N from result → execute_command("sleep N") → goto 1

        OUTPUT:
          DOWNLOADING | 26.3% | 4.21/16.0 GB | 28.3 MB/s (eth0) | ETA 423s | SLEEP 472
          COMPLETE    | 100%  | 16.0/16.0 GB | elapsed 10m 17s
          STALLED     | 26.3% | 4.21/16.0 GB | 0.0 MB/s | no traffic on eth0 | SLEEP 30

        Speed source: Prometheus localhost:9090 — same data as Grafana Network Download
          Speed dashboard at http://localhost:3002/d/lse-net-speed-01/network-download-speed
        Sleep buffer: SLEEP = ceil(ETA * 1.08 + 15)
        Script: /opt/local-se/download-monitor.py — deploy once if not present.
        """
        import subprocess  # noqa: PLC0415
        import shutil  # noqa: PLC0415
        import os as _os  # noqa: PLC0415

        monitor_script = _os.path.join(_LSE_BASE_PATH, "download-monitor.py")
        # Prefer the miniforge interpreter when it actually exists; otherwise fall
        # back to whatever python3 is on PATH. The previous logic used the hardcoded
        # miniforge path unconditionally unless python3 was missing from PATH, which
        # broke on hosts without miniforge installed.
        python_bin = "/home/sy5/miniforge3/bin/python3"  # miniforge python for Prometheus client; falls back to PATH python3 if missing
        if not _os.path.exists(python_bin):
            python_bin = shutil.which("python3") or "python3"

        if not _os.path.exists(monitor_script):
            return (
                "SETUP_REQUIRED | download-monitor.py not found at /opt/local-se/. "  # user-facing message text; intentionally literal
                "Deploy: write_file /opt/local-se/download-monitor.py from "
                "tools/download-monitor.py in the LSE repo, then chmod +x."
            )

        cmd = [python_bin, monitor_script, file_path, str(expected_bytes)]
        if interface:
            cmd.append(interface)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            output = result.stdout.strip()
            if not output and result.stderr:
                return f"ERROR | {result.stderr.strip()}"
            return output if output else "ERROR | no output from monitor script"
        except subprocess.TimeoutExpired:
            return "ERROR | monitor script timed out (Prometheus unreachable)"
        except (subprocess.SubprocessError, OSError) as exc:
            return f"ERROR | {exc}"
