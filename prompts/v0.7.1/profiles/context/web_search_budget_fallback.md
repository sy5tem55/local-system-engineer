# WEB SEARCH BUDGET FALLBACK

JIT CONTEXT FILE — v0.7.0 (extracted verbatim from v0.6.3 canonical, 2026-09-19, task 1bfb3e45).
Not part of the always-on BASE prompt. Read this file first when: the web search budget is exhausted and more fetched content is still needed.

---

WEB SEARCH BUDGET FALLBACK
──────────────────────────
When the web search budget is exhausted and more fetched content is still needed:

  Step 1 — Ping node3090:
    ssh_run(host="node3090.home.arpa", command="echo UP")
    (or: execute_command("ping -c1 -W2 node3090.home.arpa && echo UP || echo DOWN"))

  Step 2 — If DOWN:
    Surface: "Search budget exhausted and node3090 is offline — cannot fetch more."
    Stop. Do not attempt further web fetches this session.

  Step 3 — If UP, check whether firecrawl and camoufox are running on node3090:
    search_kb("firecrawl camoufox node3090 status")
    ssh_run(host="node3090.home.arpa",
            command="docker ps --filter name=firecrawl-api --filter name=camofox --format '{{.Names}} {{.Status}}'")

  Step 4 — If BOTH running:
    • General web content  → firecrawl  (search_kb("firecrawl endpoint") for the URL/API)
    • Reddit content        → camoufox   (search_kb("camoufox reddit") for invocation)
    Do NOT fall back to search_web() — route all remaining fetches through these services.

  Step 5 — If NOT running (either or both):
    search_kb("start firecrawl camoufox node3090") for the end-to-end startup procedure.
    Use ssh_script() to start the missing service — nohup/docker startup requires ssh_script,
    not execute_command SSH one-liners.
    Verify both are running (ssh_run → docker ps) before retrying the search.
    After startup: proceed as in Step 4.

  Content routing rule (applies whenever firecrawl/camoufox are in use):
    reddit.com / old.reddit.com  →  camoufox  (renders JS, handles anti-bot)
    everything else              →  firecrawl (faster, structured extraction)
