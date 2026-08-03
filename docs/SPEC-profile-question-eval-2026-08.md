# SPEC — a gold set for profile-synthesis questions

> Design: Opus 5, 2026-08-02. Authoring: Opus + operator. Running: LSE.
> Verification: V1. Roadmap `docs/ROADMAP-2026-08.md` §1b.
>
> This is the **exit condition** for the web-search milestone. Without it,
> "considerably improve web search" has no definition of done and improvement
> is judged by vibes — the one thing this project has been rigorous about
> avoiding.

---

## 1. What already exists (do not rebuild it)

`rag/eval_retrieval.py` is a mature harness: modes `knn` / `bm25` / `linear`
/ `rrf`, metrics recall@1, recall@3, MRR, matching by source filename.
`eval/retrieval-gold-v1.jsonl` holds **50** queries, and its first two rows
are already profile questions:

```
q01  "canonical llama-server launch command for node3090"
q02  "what ctx-size and flags does node3090 use to start the model"
```

So this task is **not** "build an eval harness". It is: author the question
set that profile synthesis actually asks, and — critically — separate the
questions by *which mechanism should answer them*.

---

## 2. The insight this spec turns on

`retrieval-gold-v1` measures one thing: can we retrieve a document already in
the KB. The profile work asks three different kinds of question, and only one
of them is a retrieval problem:

| Class | Example | Answered by | Failure if misrouted |
|---|---|---|---|
| **A — KB-retrievable** | "what flags does node3090 launch with" | `search_kb` | already measured by v1 |
| **B — web-answerable, checkable** | "memory bandwidth of an RTX 4090" | `search_web` → KB | **this is the milestone** |
| **C — locally measurable** | "how much VRAM does node3090 have" | `node_facts.py` probe | searching for it invites a plausible wrong answer |

**Class C is the one that matters most and is easiest to get wrong.** A model
asked "how much VRAM does node3090 have" will happily answer "24 GB" from
training priors. That is *probably* right and entirely unverified — exactly
the inference-as-measurement error this project has paid for repeatedly
(three wrong wake-procedure conclusions; a stale-process misdiagnosis; the R1
premise). Enumerating class C explicitly means the system can *refuse* to
search for it and probe instead.

---

## 3. What to produce

### 3.1 `eval/profile-questions-v1.jsonl`

One row per question:

```json
{"id":"p01","query":"memory bandwidth of the NVIDIA RTX 4090",
 "class":"B","expected_value":"1008 GB/s","tolerance":"±2%",
 "verify":"vendor spec page or two independent reputable sources",
 "note":"needed to reason about KV-cache throughput at long context"}
```

- **class A** rows carry `expected` filenames, like v1 — reuse the harness.
- **class B** rows carry `expected_value` plus a tolerance and a
  verification rule. A number with no tolerance is not checkable.
- **class C** rows carry `probe` naming the `node_facts` field that answers
  it, and **`expected_value` must be absent** — the whole point is that the
  answer comes from the machine, not the corpus.

Cover, at minimum, the questions Layer 3 will actually ask:

- VRAM bandwidth and capacity per GPU in the fleet (3090 / 4090 / 5090)
- KV-cache size at a given context and quant — the arithmetic and the rule of thumb
- Which weight quant suits coding vs planning vs long-context work
- Dense vs MoE tradeoffs at a fixed VRAM budget, including CPU-offload cost
- How to evaluate a newly-downloaded model (there is a live case:
  `Ornith-1.0-35b-Q5_K_M` is already on disk, untested)
- What `--spec-type draft-mtp` requires of a model, and when it beats ngram

Aim for 25–40 rows. Fewer is fine if each is genuinely load-bearing; padding
the set to hit a number makes the metric meaningless.

### 3.2 A baseline measurement

Run the class-A rows through the existing harness. Run class B by hand or
with a thin driver and record, per question: did search return a correct,
*sourced* answer; how many results were needed; did it hallucinate a
plausible number. Record class C as "must not be searched" and assert the
probe answers it.

**Publish the baseline before improving anything.** An improvement measured
against an unrecorded starting point is not a measurement.

---

## 4. Anti-goals

- Do **not** modify `rag/eval_retrieval.py` for class A. Reuse it.
- Do **not** invent `expected_value` numbers from memory. Every class-B
  answer needs a citable source recorded in the row. An unsourced expected
  value makes the eval measure agreement-with-the-author, not correctness.
- Do **not** put class C questions in the searchable set "for completeness".
  Their presence is a routing assertion, not a retrieval target.
- Do **not** tune search while authoring the set. Author, baseline, *then*
  improve — otherwise the set gets shaped to flatter the current behaviour.

---

## 5. Acceptance

- `eval/profile-questions-v1.jsonl` exists, every row has a class, every
  class-B row has `expected_value` + `tolerance` + a source.
- Class A baseline recorded via the existing harness.
- Class B baseline recorded with per-question outcomes.
- Class C assertions pass against `node_facts.py`.
- A short written statement of **what "good enough" means** — the number
  that, when reached, closes the web-search milestone. Without that line
  this document has failed at its one job.

---

## 6. Report

`docs/reports/YYYY-MM-DD-profile-question-eval.md`, ACCEPTANCE block per
`WORKFLOW-thread-handover.md` §1b.

---

## 7. Context

- Why: `docs/ROADMAP-2026-08.md` §1b, hardware-aware inference profiles.
- Facts API for class C: `tools/node_facts.py` (`24391cb`).
- Existing harness and gold set: `rag/eval_retrieval.py`,
  `eval/retrieval-gold-v1.jsonl` (50 rows).
