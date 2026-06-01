"""
official_docs_map.py
--------------------
Canonical trusted-domain registry for the LSE knowledge base.

Used by index_to_kb to auto-classify source_authority when a URL is provided.
Classification is domain-prefix based; more specific prefixes win.

Authority levels:
  official_vendor  — canonical docs published by the project's primary authors
  community        — reputable community sources (Stack Overflow, GitHub issues, etc.)
  (anything else defaults to 'inferred' in the caller)

To add a new topic: append to OFFICIAL_DOCS_MAP or COMMUNITY_DOMAINS.
"""

from urllib.parse import urlparse

# ── primary: official vendor documentation ────────────────────────────────────
# Key  = URL prefix (scheme + authority + optional path prefix)
# Value = human-readable topic label

OFFICIAL_DOCS_MAP: dict[str, str] = {
    # Microsoft / PowerShell / Windows
    "https://learn.microsoft.com/en-us/powershell":           "PowerShell",
    "https://learn.microsoft.com/en-us/windows":              "Windows",
    "https://learn.microsoft.com/en-us/dotnet":               ".NET",
    "https://learn.microsoft.com/en-us/azure":                "Azure",

    # Python
    "https://docs.python.org":                                "Python",
    "https://peps.python.org":                                "Python PEP",

    # Docker / container tooling
    "https://docs.docker.com":                                "Docker",
    "https://docs.podman.io":                                 "Podman",

    # Elasticsearch / Elastic stack
    "https://www.elastic.co/docs":                            "Elasticsearch",
    "https://www.elastic.co/guide":                           "Elasticsearch",
    "https://elastic.co/docs":                                "Elasticsearch",

    # llama.cpp  (README + /docs in the canonical repo)
    "https://github.com/ggerganov/llama.cpp":                 "llama.cpp",

    # ComfyUI
    "https://github.com/comfyanonymous/ComfyUI":              "ComfyUI",
    "https://docs.comfy.org":                                 "ComfyUI",

    # OpenWebUI
    "https://docs.openwebui.com":                             "OpenWebUI",
    "https://github.com/open-webui/open-webui":               "OpenWebUI",

    # Ubuntu / Debian
    "https://manpages.ubuntu.com":                            "Ubuntu",
    "https://ubuntu.com/server/docs":                         "Ubuntu",
    "https://help.ubuntu.com":                                "Ubuntu",
    "https://www.debian.org/doc":                             "Debian",

    # NVIDIA / CUDA
    "https://docs.nvidia.com":                                "NVIDIA/CUDA",
    "https://developer.nvidia.com/docs":                      "NVIDIA/CUDA",

    # SearxNG
    "https://docs.searxng.org":                               "SearxNG",
    "https://github.com/searxng/searxng":                     "SearxNG",

    # Playwright
    "https://playwright.dev/docs":                            "Playwright",
    "https://playwright.dev/python/docs":                     "Playwright",

    # Node.js / npm
    "https://nodejs.org/en/docs":                             "Node.js",
    "https://nodejs.org/docs":                                "Node.js",
    "https://docs.npmjs.com":                                 "npm",

    # Git
    "https://git-scm.com/docs":                               "Git",
    "https://git-scm.com/book":                               "Git",

    # Linux kernel / man pages
    "https://man7.org/linux/man-pages":                       "Linux",
    "https://www.kernel.org/doc":                             "Linux Kernel",

    # systemd
    "https://systemd.io":                                     "systemd",
    "https://www.freedesktop.org/software/systemd/man":       "systemd",

    # Bash / GNU
    "https://www.gnu.org/software/bash/manual":               "Bash",
    "https://www.gnu.org/manual":                             "GNU",

    # WSL
    "https://learn.microsoft.com/en-us/windows/wsl":          "WSL",

    # Hugging Face (model cards / transformers docs)
    "https://huggingface.co/docs/transformers":               "HuggingFace Transformers",
    "https://huggingface.co/docs/hub":                        "HuggingFace Hub",

    # FastAPI / Pydantic / Uvicorn
    "https://fastapi.tiangolo.com":                           "FastAPI",
    "https://docs.pydantic.dev":                              "Pydantic",
    "https://www.uvicorn.org":                                 "Uvicorn",

    # SQLite
    "https://www.sqlite.org/docs.html":                       "SQLite",
    "https://www.sqlite.org/lang":                            "SQLite",
}

# ── secondary: reputable community sources ────────────────────────────────────
# These are classified as 'community', not 'official_vendor'.
# They are NOT junk — they can legitimately inform KB entries — but they carry
# a lower authority ceiling (0.75 vs 1.0).

COMMUNITY_DOMAINS: set[str] = {
    "stackoverflow.com",
    "superuser.com",
    "unix.stackexchange.com",
    "askubuntu.com",
    "serverfault.com",
    "github.com",           # any GH repo that is NOT in OFFICIAL_DOCS_MAP above
    "gist.github.com",
    "reddit.com",
    "discourse.ubuntu.com",
    "forums.developer.nvidia.com",
    "discuss.pytorch.org",
    "discuss.huggingface.co",
}

# ── classifier ────────────────────────────────────────────────────────────────

def classify_url(url: str) -> tuple[str, str]:
    """
    Given a URL, return (source_authority, topic_label).

    Rules (first match wins):
      1. URL prefix is in OFFICIAL_DOCS_MAP  →  ('official_vendor', <label>)
      2. URL domain is in COMMUNITY_DOMAINS  →  ('community',        'community')
      3. Otherwise                            →  ('inferred',         'unknown')
    """
    if not url:
        return ("inferred", "unknown")

    url = url.strip().rstrip("/")

    # 1. official vendor — try longest-prefix match
    best_len   = 0
    best_auth  = "inferred"
    best_topic = "unknown"

    for prefix, topic in OFFICIAL_DOCS_MAP.items():
        p = prefix.rstrip("/")
        if url.startswith(p) and len(p) > best_len:
            best_len   = len(p)
            best_auth  = "official_vendor"
            best_topic = topic

    if best_auth == "official_vendor":
        return (best_auth, best_topic)

    # 2. community domain
    try:
        domain = urlparse(url).netloc.lower()
        # strip leading www.
        if domain.startswith("www."):
            domain = domain[4:]
        if domain in COMMUNITY_DOMAINS:
            return ("community", "community")
    except Exception:
        pass

    return ("inferred", "unknown")
