# LSE Current State
> Auto-reconcile at session start: read file headers, update this table.
> Last updated: 2026-06-02

## Deployed Versions

| Component | Version | File | Notes |
|---|---|---|---|
| Tool | v1.5.12 | `tools/openwebui-tool-v1.5.12.py` | `v1.5.10.py` is a stale duplicate — delete it |
| Prompt | v0.5.10 | `prompts/v0.5.10.md` | deploy to OpenWebUI pending |
| RAG Tools | v2 | (embedded in tool) | search_kb, index_to_kb, record_error, check_error_kb |
| Routing filter | v1.1.0 | `tools/lse-routing-filter-v1.1.0.py` | |
| Context monitor | retired | — | removed in v0.5.4; replaced by Grafana alert pipeline |
| Launch script (CLI) | v1.073 | `/opt/local-se/lse-stack-launch-1.073.ps1` | |
| Launch script (GUI) | v1.1 | `/opt/local-se/lse-stack-launch-gui/lse-stack-launch-gui.ps1` | |
| Eval framework | Run 4 last complete | `eval/eval-report-v4.md` | Run 5 was partial subset only |
| Test suite | v3.5 | `eval/test-suite-v2.md` (header) | 21 tests |

## Hardware / Stack

| Service | Port | Notes |
|---|---|---|
| llama-server (Qwen3.6-27B-Q4_K_M) | :8080 | RTX 4090, sm_89, CUDA 13.3 |
| OpenWebUI | :3000 | venv at ~/owui |
| SearxNG | :8088 | Docker, lse-net |
| Elasticsearch | :9200 | Docker, lse-net, mem_limit=2g |
| Ollama (nomic-embed-text) | :11434 | CPU-only |
| Grafana | :3002 | |
| Prometheus | :9090 | |
| llama-context-exporter | :9836 | systemd |
| grafana-owui-adapter | :9837 | systemd |

## Known Gaps (as of last reconcile)

- Prompt v0.5.10 written — deploy to OpenWebUI Admin → Models
- `openwebui-tool-v1.5.10.py` is a stale duplicate of `v1.5.11.py` — safe to delete
- `fetch_url` and `monitor_download` added in v1.5.11 but **missing from tool changelog** — added to CHANGELOG.md

## Eval Score Trajectory

| Run | Tool | Prompt | Mode | Score |
|---|---|---|---|---|
| Run 1 | v1.4.0 | v0.1-baseline | thinking | unscored baseline |
| Run 2 | v1.5.1 | v0.4.1 | thinking | 45/57 |
| Run 3 | v1.5.4 | v0.5.1 | thinking (budget 3072) | **57/57** |
| Run 4 | v1.5.5 | v0.5.2 | no-think (budget 0) | 49/57 |
| Run 5 (partial) | v1.5.6 | v0.5.2 | thinking (budget 3072) | 15/21 subset |
| Run 6 | — | — | — | **pending** |
