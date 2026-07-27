# TRAUM A/B Learning-Lift Eval — Design v2

> Status: implementation contract, 2026-07-27. This supersedes the execution
> protocol in `traum-ab-design.md` for future runs. The v1 design and
> `eval-report-traum-1.md` remain historical records; their figures and
> pre-registered protocol verdict are not rewritten.

## 1. Decision and causal question

The v2 experiment asks whether KB changes accumulated during a real TRAUM
learning window improve outcomes relative to an immutable baseline, with all
other inputs held fixed. A protocol score and a causal conclusion are separate:
report 1 remains a protocol **LOSS**, while its causal interpretation is
**INCONCLUSIVE** because A and B were effectively the same corpus, only one
unseeded trial was run, and B used production surfaces with side effects.

V2 refuses to start Condition B until a minimum wall-clock interval has elapsed
from the immutable A capture. The default is 24 hours and the implementation
refuses any value below one hour. A useful deployment should select a window
that spans several scheduled dream cycles, not merely the minimum floor.

## 2. Boundary and data flow

```text
immutable spec + isolation attestations
                 |
                 v
      offline traum_eval registry
       |         |             |
       v         v             v
  A/v1 export  B/v1 export  paired trial artifacts
       |       (time gate)      |
       +------------+-----------+
                    v
          paired CI + safety gates
                    |
                    v
       GUI status / policy-review nomination
             (never auto-apply)
```

`tools/traum_eval.py` has no HTTP client, subprocess runner, Elasticsearch
client, or Goethe import. It cannot start an eval worker or change a corpus. An
operator or later privilege-separated worker produces exports and trials only
on isolated targets; this tool admits their files, verifies their declared
identity, freezes them, and analyzes them.

Trade-off: this boundary does not cryptographically prove that an external
worker told the truth. It makes the safety claim explicit, pins the attestation
bytes, rejects known production ports/roots in code, and requires each trial to
declare zero production writes and input mutations. A future worker should add
container/mount/network-policy evidence without weakening these checks.

## 3. Immutable identity and resumable stages

An evaluation ID has the form `traum-v2-YYYYMMDDTHHMMSSZ-<12 hex>`. The ID,
plan hash, pinned inputs, seeds, endpoints, minimum interval, and statistical
gates never change. Every completed operation writes its artifact and manifest
atomically before advancing `state.json`. On restart, the registry reconciles
completed manifests back into state, so an interruption does not require a new
evaluation or overwrite an artifact.

Stages are:

1. `initialized` — immutable spec/pins/attestations recorded.
2. `baseline_wait` / `b_window_ready` — A mapping, documents, and config frozen;
   the wall-clock gate is blocked or ready.
3. `b_window_open` — the elapsed gate passed; B may now be exported.
4. `trials_running` — separate versioned A/B exports exist and paired trials are
   being recorded.
5. `trials_complete` — both conditions exist for every pinned seed.
6. `analyzed` — confidence intervals and gates are immutable.

Repeated calls with the same bytes are idempotent. A conflicting second capture
or trial fails closed.

## 4. Isolation requirements

Both conditions require a `traum.eval.isolation.v1` attestation. A and B must
have distinct store URLs, gateway URLs, and disjoint absolute filesystem roots.
Ports `9200` and `9700` are hard rejected for every hostname spelling,
including `localhost`, `127.0.0.1`, and `[::1]`; an attestation cannot override
the rejection. Known production filesystem roots such as `/opt/local-se` and
`/var/lib/elasticsearch` are also rejected.

Loopback is permitted only on non-production, explicitly numbered isolated
ports, allowing disposable local containers such as `:19201`/`:19202` and
gateways such as `:19701`/`:19702`.

The A and B stores are versioned independently under
`conditions/A/v1/export` and `conditions/B/v1/export`. B's mapping and retrieval
config hashes must equal A; only the document export may change. Source files
are hashed before and after copying and are never modified.

Every capture source must resolve, after symlink resolution, to a regular file
inside that condition's own attested `filesystem_root`. A path outside the root,
a path inside the other condition's root, and a path under a production data
root are all rejected as `unsafe_path`/`production_filesystem` before any byte is
copied. Containment is checked rather than trusted, so an isolation attestation
cannot be paired with an export that was actually taken from production.

## 4.1 The corpus must actually have changed

An A/B run is only causally informative if the learning window changed the
corpus. Capture of Condition B fails with `no_learning_delta` when the document
export is byte-identical to frozen A, and also when the bytes differ but no
document was added, removed, or modified (for example a re-serialized or
reordered export). `analyze` re-checks the same property from the immutable
manifests, so an evaluation frozen before this guard existed cannot be scored as
learning lift either.

Condition B's manifest and the analysis summary record a `corpus_delta`
(baseline/candidate document counts, added, removed, modified, and up to 100
changed document IDs). This is the evidence that answers "what did the dream
cycles actually contribute?" The GUI renders the counts only; document IDs stay
in the offline registry. This is exactly the property v1 lacked: report 1 scored
two corpora that were effectively the same.

## 5. Fixed inputs and paired trials

The immutable spec pins all of these:

- model ID and binary/weights SHA-256;
- prompt bytes;
- tool-schema bytes;
- retriever configuration bytes;
- embedding model ID and SHA-256;
- dataset bytes;
- at least three unique trial seeds.

Every trial declares the combined input fingerprint, the relevant condition
export fingerprint, and all six runtime fingerprints. A mismatch is rejected.
Each A trial has exactly one B partner with the same seed. Raw transcripts and
retrieval outputs are mandatory and retained with SHA-256 hashes.

## 6. Statistics and decision gates

V2 computes paired Student-t 95% confidence intervals for suite-score delta,
tool-call reduction, wrong-KB-hit delta, recall@3 delta, and MRR delta. The
pre-registered plan pins noninferiority margins and wrong-hit allowances.

A **WIN** requires all noninferiority and wrong-hit gates plus either a suite
score improvement whose lower confidence bound exceeds zero or a tool-call
reduction whose lower bound meets the pinned threshold. Demonstrated harm is a
**LOSS**. Fully safe but undemonstrated lift is **NULL**. Wide intervals that do
not establish safety are **INCONCLUSIVE**. No mean-only win is allowed.

Wrong-KB hits have three gates: the upper confidence bound of the mean increase,
the maximum per-pair increase, and total increase. This prevents an aggregate
mean from hiding one poisoned trial.

## 7. Stable GUI adapter contract

The authoritative registry path is supplied via `--registry`; its cached index
is `<registry>/registry.json`, and evaluation directories remain authoritative.
The following read operations are stable:

- `traum_eval.py status` → `traum.eval.registry.v2`, all evaluations
  (`traum-eval-registry-v2.schema.json`);
- `traum_eval.py status --eval-id ID` → `traum.eval.status.v2`, one evaluation;
- `traum_eval.py evidence-status` →
  `traum.continuous-evidence.summary.v1`, grouped learning evidence
  (`traum-evidence-summary-v1.schema.json`);
- condition and trial manifest references in status lead to retained artifact
  hashes inside the same contained eval directory.

`eval/traum-eval-status-v2.schema.json` is the typed GUI contract. A GUI should
render `stage`, `readiness`, `next_actions`, elapsed `not_before`, A/B export
fingerprints, the `corpus_delta` counts, trial coverage, gate results, the
contained `artifacts` hash index, and evidence eligibility. It should not parse
CLI prose.

Safe typed actions are `init`, `freeze-a`, `open-b`, `capture-b`,
`record-trial`, `analyze`, and `record-evidence`. Resume is implicit/idempotent.
There is deliberately no remote `start`, arbitrary command, delete, or
production retry action in v2. A future `cancel` should only mark a registry
record abandoned; it must not delete raw evidence.

## 8. Continuous evidence and the human gate

`traum.continuous-evidence.v1` records, per stable proposal ID/type:

- accepted/rejected/expired/superseded decision and decision authority;
- reversal observed, confirmed not reversed, not yet observed, or not applicable;
- retrieval opportunities, retrievals, and actual uses;
- positive/negative usefulness observations;
- hashes of supporting raw artifacts.

Events are immutable cumulative snapshots. A proposal may receive a later
snapshot when reversal, retrieval, or usefulness evidence changes. Summaries
retain every event for audit but count only the latest `observed_at` snapshot
per proposal, so updating an outcome cannot inflate acceptance or usage rates.

The summary reports Wilson 95% intervals for acceptance, reversal, and
usefulness. Only `dedup-exact` and `reverify` can ever become *eligible for a
future policy review*, and only after minimum evidence and confidence gates.
Semantic changes (`demote`, `kb-fact`, `skill`, prompt/tool changes, and unknown
types) remain human-gated. Eligibility is evidence for a later policy decision,
not permission: every event, status, plan, trial, and summary fixes
`auto_apply_enabled=false`, and the implementation contains no enable action.

## 9. Operational sequence

All `--mapping`, `--documents`, and `--config` paths below must be absolute and
must live inside the condition's attested `filesystem_root` (`$A_ROOT`,
`$B_ROOT`), because that is what the isolation attestation claims.

```text
traum_eval.py --registry R init --spec spec.json
traum_eval.py --registry R freeze-a --eval-id ID --mapping $A_ROOT/export/mapping.json \
  --documents $A_ROOT/export/documents.jsonl --config $A_ROOT/export/config.json
# Wait until status says b_window_ready; external dreaming proceeds elsewhere.
traum_eval.py --registry R open-b --eval-id ID
traum_eval.py --registry R capture-b --eval-id ID --mapping $B_ROOT/export/mapping.json \
  --documents $B_ROOT/export/documents.jsonl --config $B_ROOT/export/config.json
# capture-b refuses an unchanged corpus (no_learning_delta) and any source
# outside $B_ROOT (unsafe_path).
# Record A/B for every pinned seed, then:
traum_eval.py --registry R analyze --eval-id ID
```

This sequence prepares and evaluates evidence only. It never deploys, touches
`/opt`, invokes the live Goethe gateway, or changes `DREAM_AUTO_APPLY`.

## 10. Revisit points

As the system grows, revisit cryptographically signed worker attestations,
registry locking for concurrent writers, stratified/bootstrap intervals for
larger datasets, and a non-destructive `abandoned` state. None should weaken the
immutable input, elapsed-window, isolation, wrong-hit, or no-auto-apply gates.
