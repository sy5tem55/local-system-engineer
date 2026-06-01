# LSE RAG Stack

Elasticsearch + nomic-embed-text semantic search layer for the Local System Engineer.
Replaces raw SearxNG hits with a self-improving, curated knowledge base.

## Architecture

```
User query
    │
    ▼
[LSE Tool] search_kb(query)
    │
    ├─ HIT (score ≥ 0.72) ──► return KB result + quality_score
    │
    └─ MISS ──► SearxNG / Playwright web search
                    │
                    └─ Good result found ──► index_to_kb()
                                                │
                                                └─ Near-duplicate? → refine existing doc
                                                   New topic?      → create new entry

[On any error]
    LSE calls check_error_kb() before acting
    LSE calls record_error() after resolving
```

## KB Document Quality

Documents start at a quality_score reflecting their current state:

| Score | Meaning |
|-------|---------|
| 0.3   | Stub / single fact (image-generation-tools.md, launcher-script-location.md, etc.) |
| 0.5   | Rough — content present but incomplete or potentially stale |
| 0.6   | Reasonable — large doc, probably mostly correct |
| 0.8   | Good — verified by a web search cross-reference |
| 1.0   | Authoritative — manually verified or sourced from official docs |

The goal is to drive all 12 KB docs toward ≥ 0.8 through autonomous refinement
as the LSE searches and finds better sources.

## Current KB (12 files, ~69KB)

| File | Topic | Initial Quality | Priority |
|------|-------|-----------------|----------|
| WAN2.1-architecture-and-environment-audit.md | wan2.1 | 0.6 | High |
| llama.md | llama-cpp | 0.6 | High |
| searxng-metrics-and-query-tracking.md | searxng | 0.5 | Medium |
| pfsense-api-automation.md | pfsense | 0.5 | Medium |
| searxng-deployment-complete.md | searxng | 0.5 | Medium |
| searxng-sqlite-deployment-plan.md | searxng | 0.5 | Medium |
| searxng-config.md | searxng | 0.5 | Medium |
| llama-cpp-build.md | llama-cpp | 0.3 | **Stub** |
| port-and-container-audit.md | infrastructure | 0.3 | **Stub** |
| image-generation-tools.md | stable-diffusion | 0.3 | **Stub** |
| searxng-docker-port-fact.md | searxng | 0.3 | **Stub** |
| launcher-script-location.md | lse-launcher | 0.3 | **Stub** |

## Setup (in order)

### Prerequisites
- Elasticsearch 8.x deployed via Portainer (port 9200, security disabled)
- WSL Ubuntu-24.04, Python 3.10+

### Step 1 — Ollama + nomic-embed-text
```bash
bash 01-ollama-setup.sh
```
Installs Ollama CPU-only (no GPU), pulls nomic-embed-text (274MB), verifies 768-dim endpoint.

### Step 2 — Create ES indices
```bash
python3 02-es-setup.py --es-url http://localhost:9200
```
Creates `lse-kb`, `lse-search-cache`, `lse-errors` with correct mappings.

### Step 3 — Seed from /opt/local-se/kb/
```bash
# Preview first
python3 03-kb-seed.py --dry-run

# Seed
python3 03-kb-seed.py

# Re-embed after editing KB files
python3 03-kb-seed.py --reindex
```

### Step 4 — Add tool functions to LSE
Paste contents of `04-lse-tool-additions.py` into `tools/openwebui-tool-v1.5.9.py`.
New functions: `search_kb`, `index_to_kb`, `record_error`, `check_error_kb`.

### Step 5 — Update LSE system prompt
Add to the prompt (after the existing tool list):
```
Before searching the web, always call search_kb() first.
After finding useful information from a web search, call index_to_kb() to store it.
After recovering from any error, call record_error() so the mistake is not repeated.
```

## Elasticsearch Portainer config

```yaml
Image:    elasticsearch:8.17.0
Name:     lse-elasticsearch
Ports:    9200:9200
Env:
  discovery.type: single-node
  xpack.security.enabled: "false"
  ES_JAVA_OPTS: "-Xms512m -Xmx1g"
Volumes:
  es-data:/usr/share/elasticsearch/data
```
