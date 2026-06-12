# lse-kb Reseed Procedure — Canonical

> Written 2026-06-12 (P21) after the full ES recovery. This document lives IN the KB so
> `search_kb("reseed")` finds it. Follow it exactly — every rule below was paid for.

## Architecture facts (verified 2026-06-12)

- ONE real KB directory: the repo `kb/` at `/mnt/c/Users/SY5/Claude/Projects/local-system-engineer/kb/`.
  `/opt/local-se/kb` is a symlink to it. Old pre-link copy: `/opt/local-se/kb.pre-link.bak` (frozen).
- Seeder: `rag/03-kb-seed.py` in the repo. Default `--kb-dir` is `/opt/local-se/kb` — NEVER override it.
  Doc ids are `sha256(filepath:chunk_idx)`: the path STRING is identity. Seeding via any other path
  string creates full duplicates of every chunk.
- `--reindex` semantics: without it, existing doc ids are SKIPPED (updated files stay stale in the
  index). With it, every chunk is re-embedded and updated in place. Reseeds after KB edits need it.
- `lse-kb` also holds organic web/curated docs (`source_path: null`, `source_url` set or null).
  These are NOT seed docs — never delete them during reseed cleanup.
- Embeddings: Ollama `nomic-embed-text` (768-dim). ES on LUCIFER WSL, port 9200.
- Related indices: `lse-errors`, `lse-search-cache` (created by `rag/02-es-setup.py` — idempotent,
  canonical mappings, never freehand-create); `lse-rfc-kb` (created/seeded by `scripts/rfc_kb.py`,
  upserts by section_id, `--tag-only` resumes incomplete tagging).

## LSE execution constraints

- `execute_command` times out at 30s — the seeder ALWAYS exceeds it (Ollama embedding).
- The safety layer blocks writes to `/opt/` and nohup log redirects from the tool.
- Therefore: LSE prepares and verifies; the HUMAN runs the long command. Delegation template:

```
Please run in your terminal:
nohup python3 /mnt/c/Users/SY5/Claude/Projects/local-system-engineer/rag/03-kb-seed.py --reindex > /tmp/kb-seed.log 2>&1 &
sleep 90; tail -20 /tmp/kb-seed.log; curl -s "localhost:9200/_cat/indices/lse-kb?h=docs.count"
```

## Procedure

1. **Pre-check** (LSE can do): record the current doc count —
   `curl -s "localhost:9200/_cat/indices/lse-kb?h=docs.count"`
   and confirm all indices exist:
   `curl -s "localhost:9200/lse-kb,lse-errors,lse-rfc-kb,lse-search-cache/_count"`
   (a 404 here means an index was silently lost — run `rag/02-es-setup.py` first; it skips existing).
2. **Run the seeder** with `--reindex` via the delegation template above. Do NOT pass `--kb-dir`.
3. **Verify count**: expected = (previous file-doc count ± chunk drift from edited files) + new files'
   chunks. Organic docs are untouched. Big unexplained growth = path-string duplication (see 5).
4. **Verify log**: `tail /tmp/kb-seed.log` must show per-file indexing and no embedding errors.
   "Embedding failed" lines mean Ollama is down or overloaded — fix and re-run (idempotent with ids).
5. **Duplicate audit** (run after every reseed):

```
curl -s 'localhost:9200/lse-kb/_search?size=200&_source=source_path,created_at' -H 'Content-Type: application/json' -d '{"query":{"exists":{"field":"source_path"}}}' | python3 -c "
import json,sys,collections
h=json.load(sys.stdin)['hits']['hits']
print(collections.Counter('/'.join(d['_source']['source_path'].split('/')[:4]) for d in h))"
```

   Exactly ONE path prefix (`/opt/local-se/kb`) is correct. A second prefix = duplicates; remove with
   `delete_by_query` on the WRONG prefix only:

```
curl -s -X POST localhost:9200/lse-kb/_delete_by_query -H 'Content-Type: application/json' -d '{"query":{"prefix":{"source_path.keyword":"<WRONG-PREFIX>"}}}'
```

6. **Report**: before/after counts + duplicate-audit result. STOP and escalate on anything unexpected —
   do not improvise index surgery.

## History

- 2026-06-08: es-data Docker volume lost in WSL cascade → all indices wiped; only lse-kb partially
  reseeded; lse-errors/lse-rfc-kb silently missing until 2026-06-12 (missing indices 404 on read but
  auto-create on write — absence is invisible until something reads).
- 2026-06-12: full recovery — indices recreated from canonical scripts, KB consolidated to one real
  dir, reseed 53 → 131 docs (77 file + 54 organic), verified duplicate-free.
