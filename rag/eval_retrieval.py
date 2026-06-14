#!/usr/bin/env python3
"""
eval_retrieval.py — retrieval quality harness for lse-kb (trajectory S2.2).

Runs eval/retrieval-gold-v1.jsonl against Elasticsearch and reports recall@1,
recall@3 and MRR per retrieval MODE, so the hybrid decision (S2.3) and the
0.72-threshold question (S2.4) are made on numbers, not vibes.

MODES
  knn     pure semantic kNN over the 768-dim nomic embedding (cosine).
  bm25    pure lexical multi_match over title^2 + content.
  linear  the CURRENT production search_kb: kNN(boost 0.7) + multi_match(boost 0.3)
          summed in one ES query. This is the baseline we are trying to beat.
  rrf     client-side Reciprocal Rank Fusion of the knn and bm25 result lists
          (k=60). ES-native, zero infra, robust to score-scale mismatch.

Matching is by SOURCE FILENAME (basename of source_path), because doc_id is a
content hash. A gold row's `expected` is a list of acceptable filenames; a query
is a hit at rank r if any expected filename appears at distinct-basename rank r.

USAGE
  python3 rag/eval_retrieval.py --compare                 # all modes, side by side
  python3 rag/eval_retrieval.py --mode rrf --verbose      # per-query detail
  python3 rag/eval_retrieval.py --threshold-report --mode linear
  python3 rag/eval_retrieval.py --self-test               # no ES/Ollama needed
Requires (live modes): ES at --es-url, Ollama nomic-embed-text at --ollama-url.
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict

GOLD_DEFAULT = os.path.join(os.path.dirname(__file__), "..", "eval", "retrieval-gold-v1.jsonl")
ES_INDEX = "lse-kb"
EMBED_MODEL = "nomic-embed-text"
EMBED_PREFIX = "search_query: "
RRF_K = 60
MEASURE_SIZE = 10  # retrieve top-N for measurement; recall@k slices this


# ── helpers (pure, unit-testable) ─────────────────────────────────────────────

def basename(path):
    return os.path.basename(path or "").strip()


def distinct_basenames(hits):
    """hits: ordered list of dicts with 'source'. Return ranked distinct basenames,
    keeping first (best-ranked) occurrence — collapses chunked docs."""
    seen, out = set(), []
    for h in hits:
        b = basename(h.get("source"))
        if b and b not in seen:
            seen.add(b)
            out.append(b)
    return out


def first_hit_rank(ranked_basenames, expected):
    """1-based rank of the first expected basename, or None."""
    exp = set(expected)
    for i, b in enumerate(ranked_basenames, 1):
        if b in exp:
            return i
    return None


def rrf_fuse(list_a, list_b, k=RRF_K):
    """Reciprocal Rank Fusion of two ranked basename lists. Returns fused ranked
    list of basenames by descending RRF score; ties broken by appearance order."""
    score = defaultdict(float)
    order = []
    for lst in (list_a, list_b):
        for rank, b in enumerate(lst, 1):
            if b not in score:
                order.append(b)
            score[b] += 1.0 / (k + rank)
    return sorted(order, key=lambda b: (-score[b], order.index(b)))


def metrics_for(ranks, n):
    """ranks: list of (rank-or-None) per query. Returns dict of recall@1/@3 + MRR."""
    r1 = sum(1 for r in ranks if r is not None and r <= 1) / n
    r3 = sum(1 for r in ranks if r is not None and r <= 3) / n
    mrr = sum((1.0 / r) for r in ranks if r is not None) / n
    return {"recall@1": r1, "recall@3": r3, "MRR": mrr}


# ── ES retrieval (live) ───────────────────────────────────────────────────────

def embed(text, ollama_url):
    import requests
    r = requests.post(
        f"{ollama_url}/api/embed",
        json={"model": EMBED_MODEL, "input": EMBED_PREFIX + text[:5000]},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["embeddings"][0]


def _hits(resp):
    out = []
    for h in resp["hits"]["hits"]:
        s = h.get("_source", {})
        out.append({"source": s.get("source_path") or s.get("source_url") or "",
                    "score": h.get("_score", 0.0)})
    return out


def retrieve(es, query, mode, ollama_url, size=MEASURE_SIZE):
    """Return an ordered list of hit dicts for the given mode."""
    src = ["title", "source_path", "source_url", "topic", "quality_score"]
    if mode in ("knn", "linear", "rrf"):
        vec = embed(query, ollama_url)
    if mode == "bm25":
        body = {"query": {"multi_match": {"query": query,
                "fields": ["title^2", "content"]}}, "_source": src, "size": size}
        return _hits(es.search(index=ES_INDEX, body=body))
    if mode == "knn":
        body = {"knn": {"field": "embedding", "query_vector": vec, "k": size,
                "num_candidates": 50}, "_source": src, "size": size}
        return _hits(es.search(index=ES_INDEX, body=body))
    if mode == "linear":  # current production search_kb
        body = {
            "knn": {"field": "embedding", "query_vector": vec, "k": size,
                    "num_candidates": 50, "boost": 0.7},
            "query": {"bool": {"must": [{"multi_match": {"query": query,
                      "fields": ["title^2", "content"], "boost": 0.3}}]}},
            "_source": src, "size": size,
        }
        return _hits(es.search(index=ES_INDEX, body=body))
    if mode == "rrf":
        kbody = {"knn": {"field": "embedding", "query_vector": vec, "k": size,
                 "num_candidates": 50}, "_source": src, "size": size}
        bbody = {"query": {"multi_match": {"query": query,
                 "fields": ["title^2", "content"]}}, "_source": src, "size": size}
        knn_b = distinct_basenames(_hits(es.search(index=ES_INDEX, body=kbody)))
        bm_b = distinct_basenames(_hits(es.search(index=ES_INDEX, body=bbody)))
        fused = rrf_fuse(knn_b, bm_b)
        return [{"source": b, "score": None} for b in fused]
    raise ValueError(f"unknown mode {mode}")


# ── run ───────────────────────────────────────────────────────────────────────

def load_gold(path):
    return [json.loads(l) for l in open(path) if l.strip()]


def evaluate(es, gold, mode, ollama_url, verbose=False, collect_threshold=False):
    ranks, per_topic = [], defaultdict(list)
    thresh_rows = []
    for row in gold:
        hits = retrieve(es, row["query"], mode, ollama_url)
        ranked = distinct_basenames(hits) if mode != "rrf" else [h["source"] for h in hits]
        rank = first_hit_rank(ranked, row["expected"])
        ranks.append(rank)
        per_topic[row["topic"]].append(rank)
        if collect_threshold and hits and hits[0].get("score") is not None:
            thresh_rows.append({"id": row["id"], "top_score": hits[0]["score"],
                                "top1_correct": rank == 1})
        if verbose:
            tag = f"rank {rank}" if rank else "MISS"
            print(f"  [{row['id']}] {tag:8} {row['query'][:60]}")
            if rank != 1:
                print(f"       got: {ranked[:3]}  want: {row['expected']}")
    n = len(gold)
    return metrics_for(ranks, n), per_topic, thresh_rows


def print_metrics(name, m):
    print(f"  {name:8}  recall@1={m['recall@1']:.2f}  recall@3={m['recall@3']:.2f}  MRR={m['MRR']:.3f}")


def threshold_sweep(rows):
    """Given [{top_score, top1_correct}], sweep a min_score cut and report how many
    correct top-1 hits survive vs wrong top-1 hits rejected — informs S2.4."""
    if not rows:
        print("  (no scored rows — threshold sweep needs knn/bm25/linear mode)")
        return
    scores = sorted({round(r["top_score"], 3) for r in rows})
    print(f"  {'cut':>7}  {'kept_correct':>12}  {'kept_wrong':>10}  {'rejected_correct':>16}")
    n_corr = sum(1 for r in rows if r["top1_correct"])
    for cut in scores:
        kc = sum(1 for r in rows if r["top1_correct"] and r["top_score"] >= cut)
        kw = sum(1 for r in rows if not r["top1_correct"] and r["top_score"] >= cut)
        rc = n_corr - kc
        print(f"  {cut:7.3f}  {kc:12d}  {kw:10d}  {rc:16d}")
    print(f"  (production default min_score=0.72; total correct top-1 = {n_corr}/{len(rows)})")


# ── self-test (no ES / no Ollama) ─────────────────────────────────────────────

def self_test(gold_path):
    ok = True
    # 1. gold integrity: valid json, fields present, expected files exist if kb/ present
    gold = load_gold(gold_path)
    kb_dir = os.path.join(os.path.dirname(gold_path), "..", "kb")
    present = set()
    if os.path.isdir(kb_dir):
        for root, _, files in os.walk(kb_dir):
            present.update(files)
    for r in gold:
        assert r["query"] and r["expected"] and r["topic"], f"bad row {r.get('id')}"
        if present:
            for e in r["expected"]:
                if e not in present:
                    print(f"  FAIL gold: {r['id']} expects missing file {e}"); ok = False
    print(f"  gold: {len(gold)} rows, fields OK" + (", all expected files exist" if present else ""))
    # 2. RRF math
    a = ["x", "y", "z"]   # ranks 1,2,3
    b = ["y", "w", "x"]   # ranks 1,2,3
    fused = rrf_fuse(a, b)
    # y: 1/61 + 1/61 ; x: 1/61 + 1/63 ; z: 1/63 ; w: 1/62
    assert fused[0] == "y", f"RRF top should be y, got {fused}"
    assert fused[1] == "x", f"RRF 2nd should be x, got {fused}"
    print(f"  rrf_fuse: {fused} (y>x>… as expected) OK")
    # 3. dedupe-by-basename + first_hit_rank
    hits = [{"source": "/kb/a.md"}, {"source": "/kb/a.md"}, {"source": "/kb/b.md"}]
    db = distinct_basenames(hits)
    assert db == ["a.md", "b.md"], db
    assert first_hit_rank(db, ["b.md"]) == 2
    assert first_hit_rank(db, ["zzz.md"]) is None
    print(f"  distinct_basenames + first_hit_rank OK")
    # 4. metrics
    m = metrics_for([1, 2, None, 3], 4)
    assert abs(m["recall@1"] - 0.25) < 1e-9 and abs(m["recall@3"] - 0.75) < 1e-9
    assert abs(m["MRR"] - (1 + 0.5 + 1/3) / 4) < 1e-9
    print(f"  metrics_for OK  ({m})")
    print("SELF-TEST PASSED" if ok else "SELF-TEST FAILED")
    return ok


def main():
    ap = argparse.ArgumentParser(description="lse-kb retrieval eval (S2.2)")
    ap.add_argument("--gold", default=GOLD_DEFAULT)
    ap.add_argument("--es-url", default="http://localhost:9200")
    ap.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    ap.add_argument("--mode", default="rrf", choices=["knn", "bm25", "linear", "rrf"])
    ap.add_argument("--compare", action="store_true", help="run all four modes")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--threshold-report", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()

    if a.self_test:
        sys.exit(0 if self_test(a.gold) else 1)

    from elasticsearch import Elasticsearch
    es = Elasticsearch(a.es_url, request_timeout=15)
    gold = load_gold(a.gold)
    print(f"Gold: {len(gold)} queries | index: {ES_INDEX} | "
          f"topics: {dict(Counter(r['topic'] for r in gold))}\n")

    modes = ["knn", "bm25", "linear", "rrf"] if a.compare else [a.mode]
    results = {}
    for mode in modes:
        if a.verbose:
            print(f"── mode: {mode} ──")
        m, per_topic, thr = evaluate(es, gold, mode, a.ollama_url, a.verbose,
                                     collect_threshold=a.threshold_report)
        results[mode] = (m, per_topic, thr)

    print("\n=== SUMMARY ===")
    for mode in modes:
        print_metrics(mode, results[mode][0])
    if a.compare:
        base = results["linear"][0]
        best = max(modes, key=lambda mo: (results[mo][0]["recall@3"], results[mo][0]["MRR"]))
        print(f"\nbest by recall@3 then MRR: {best}")
        d3 = results[best][0]["recall@3"] - base["recall@3"]
        print(f"hybrid(rrf) vs production(linear): "
              f"Δrecall@3={results['rrf'][0]['recall@3']-base['recall@3']:+.2f} "
              f"ΔMRR={results['rrf'][0]['MRR']-base['MRR']:+.3f}")
        print("SHIP rrf only if Δ is a real improvement; otherwise keep linear and record it.")

    if a.threshold_report:
        mode = a.mode if not a.compare else "linear"
        print(f"\n=== THRESHOLD SWEEP (mode={mode}) — S2.4 ===")
        threshold_sweep(results[mode][2])


if __name__ == "__main__":
    main()
