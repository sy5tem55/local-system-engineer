# LSE Neural Search Engine — Design & Implementation Plan

**Target:** node3090 (RTX 3090 24GB, i9-9900K, 32GB RAM, Ubuntu 24.04)
**Date:** 2026-07-17 · Audited live via Goethe (ssh_run / execute_command)

## Audit findings (live, verified)

| Resource | State | Constraint |
|---|---|---|
| VRAM | 20.7 / 24 GB used (llama-server Qwen3.6-27B, ctx 131072) | ~3.8 GB free → time-share required |
| Disk `/` | 88% full, 109 GB free | Caps corpus at ~50 GB indexed (keep 50 GB buffer) |
| RAM | 20 GB available | ES heap + HNSW graphs fit |
| Elasticsearch | `lse-kb-es` 8.13.0, localhost:9200, basic license | dense_vector + int8_hnsw ✔; **RRF query fusion needs paid license → fuse in code** |
| Firecrawl | API up on :3002 (health route 404, service responds) | Crawler ready |
| SearxNG | `sear_primary` on node3090:8088 + LSE-host instance :8088 (200 OK) | Engine plugin target |

## Architecture

```
                        ┌─────────────────────────────────────────┐
Query ──► SearxNG ──►  │  neural engine plugin (neural_search.py) │
                        └───────────────┬─────────────────────────┘
                                        ▼
                          neural-search-api (FastAPI :8090)
                                        │
                          ┌── Auto Search Router ──┐
                          │  keyword-ish → BM25    │
                          │  semantic  → hybrid    │
                          └─────────┬──────────────┘
                    ┌───────────────┼────────────────┐
                    ▼               ▼                ▼
             embed query      BM25 match       (fallback: live
             (gpu-sidecar)    lse-web-idx       SearxNG results
                    │               │            → re-rank path)
                    ▼               │
             kNN dense_vector       │
                    └──────┬────────┘
                       RRF fusion (in code, k=60)
                           ▼
                    re-ranker (top-30 → top-10)
                           ▼
                        results
```

### Ingest pipeline
Firecrawl (crawl allowlisted domains) → markdown → chunker (512-token chunks, 64 overlap, heading-aware) → embed (batch, GPU sidecar) → bulk index to ES.

### ES index `lse-web-idx` (mapping sketch)
```json
{
  "mappings": {
    "properties": {
      "url":      {"type": "keyword"},
      "title":    {"type": "text"},
      "chunk":    {"type": "text"},
      "domain":   {"type": "keyword"},
      "fetched":  {"type": "date"},
      "emb": {
        "type": "dense_vector", "dims": 1024,
        "index": true, "similarity": "cosine",
        "index_options": {"type": "int8_hnsw"}
      }
    }
  }
}
```
int8_hnsw quarters HNSW RAM (~1 GB per million chunks vs ~4 GB float32).

## Models (GPU sidecar, time-shared)

| Role | Model | VRAM (GGUF Q8) |
|---|---|---|
| Embeddings | bge-m3 (1024-dim, multilingual, 8k ctx) | ~0.7 GB |
| Re-ranker | bge-reranker-v2-m3 | ~0.7 GB |

Served by a **second llama-server instance** (`:8090` embeddings, `:8091` reranker) — same binary already at `/opt/llama.cpp/bin/llama-server`, `--embeddings` flag. Combined ~1.5 GB actually fits inside the 3.8 GB free headroom, so "time-share" is implemented as **lazy-start + idle-stop** rather than evicting Qwen:

- systemd units `emb-server.service` / `rerank-server.service`, started on demand by the API
- idle watchdog stops them after 10 min without requests (frees VRAM back to Qwen KV growth)
- cold start ≈ 2–4 s (small models); API holds the request during warm-up
- **Bulk indexing runs off-hours** via timer, when Qwen is idle — checked via `/metrics` slot activity before starting large batches

If Qwen's KV cache growth ever squeezes below ~1.5 GB free, fallback is ONNX int8 on CPU (same models, ~200–500 ms/query — acceptable).

## Auto Search Router

Cheap heuristic first (no model call, <1 ms):

- **BM25-only:** quoted phrases, `site:`/operators, mostly digits/IDs/error codes, ≤2 tokens
- **Hybrid (default):** natural-language queries, questions, ≥3 tokens
- **Re-rank-live:** router detects freshness intent ("latest", "2026", "release", "news") → skip local index, pull SearxNG live results, embed titles+snippets, re-rank, return

Log router decisions; revisit with a learned classifier once there's click data.

## Fusion & re-ranking (in code — ES basic license has no RRF)

```python
def rrf(bm25_hits, knn_hits, k=60):
    scores = defaultdict(float)
    for rank, h in enumerate(bm25_hits): scores[h.id] += 1/(k+rank+1)
    for rank, h in enumerate(knn_hits):  scores[h.id] += 1/(k+rank+1)
    return sorted(scores, key=scores.get, reverse=True)
```
Top-30 fused → cross-encoder re-ranker → top-10 to SearxNG.

## SearxNG integration

Custom engine `searx/engines/neural_search.py` in `sear_primary` (and optionally LSE-host instance):

```yaml
- name: neural
  engine: neural_search
  shortcut: nl
  base_url: http://127.0.0.1:8090
  timeout: 6.0
  categories: [general]
```
Engine calls `GET /search?q=...`, maps results to SearxNG result dicts (url, title, content, score). Falls through gracefully (empty list) if the API is down — web engines still answer.

## Budgets

- **Disk:** cap corpus at 40 GB raw crawl → ~50 GB with ES overhead. Alert at 92% via existing Prometheus/node-exporter.
- **VRAM:** sidecars ≤1.6 GB; never start bulk embed while Qwen slots active.
- **Latency target:** hybrid query ≤400 ms warm (embed 15 ms + kNN 20 ms + BM25 10 ms + rerank 30×~8 ms), +3 s cold-start worst case.

## Implementation phases

1. **Sidecar serving** — ✅ DONE 2026-07-17. `lse-emb.service` :8090 / `lse-rerank.service` :8091 (models in `/opt/models/local/embeddings/`), watchdog timer every 5 min. Measured: sidecars +1.35 GB VRAM → 22.3/24.6 GB total with Qwen loaded. Smoke tests pass (1024-dim embeddings, correct rerank ordering). Disk now 73% (238 GB free).
2. **Index + ingest** — ✅ DONE 2026-07-17. `lse-web-idx`: 43,996 chunks / 962 MB (Arch Wiki dump 33,413 · grafana 6,498 · prometheus 3,031 · searxng-docs 1,054). `ingest.py` (Firecrawl, `--job-id` resume) + `ingest_dir.py` (local HTML dumps). Incident: idle watchdog stopped `lse-emb` during a long scrape phase → `embed()` now auto-restarts + retries.
3. **Search API** — ✅ DONE 2026-07-17. `lse-neural-api.service` :8092 (venv — Ubuntu's `python3-fastapi` apt package is broken, don't use it). Router/RRF/rerank verified; warm latency 67–83 ms. 50-query eval vs BM25 baseline still TODO.
4. **SearxNG engine** — ✅ DONE 2026-07-17. Registered in `sear_primary` (config: `/home/sy5/searxng-deployment/searxng/settings.yml`, NOT the LSE-host path) as `json_engine` → `http://172.19.0.1:8092`, shortcut `!nl`. Gotcha: plain-HTTP engines need `enable_http: true` or they crash with "HTTP protocol is disabled".
5. **Re-rank-live path + scheduler** — ✅ DONE 2026-07-17 (except Grafana panel). Freshness queries → sear_primary live results → cross-encoder rerank, hybrid fallback when web engines are suspended. Recursion guard: the SearxNG engine's `search_url` pins `mode=hybrid`. `lse-recrawl.timer` Sundays 03:15: waits for idle Qwen slots, re-crawls all doc domains, purges stale chunks via `_delete_by_query` on `fetched < run-start`. URLs normalized at ingest.

### Remaining backlog
- Grafana panel for lse-neural-api latency/QPS + index size
- 50-query eval: hybrid vs BM25 baseline; tune router thresholds
- sear_primary web-engine health: upstreams (brave/ddg/startpage) throw 429/403 quickly — consider engine set tuning; Firecrawl's `SEARXNG_ENDPOINT=192.168.5.41:5580` is stale (nothing listens) and should be repointed at sear_primary
- Neural engine `weight` in SearxNG if it keeps dominating mixed results
- VRAM test under concurrent Qwen generation + embedding batch load

## Risks

- **VRAM contention** is the only hard risk — mitigated by lazy sidecars + CPU fallback; add a pre-flight `nvidia-smi` check in the API startup.
- **Disk 88%** — enforce crawl allowlist + size cap before first big crawl; consider pruning `/opt/models` (bartowski/DavidAU/etc. duplicates) to reclaim space.
- **SearxNG config drift** — per KB P22 correction: settings live in `/home/sy5/docker/searxng_data`; read paths/tokens from `docker inspect` or `observability.env`, never memory.
