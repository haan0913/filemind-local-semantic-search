# Embedding Backend Evaluation - 2026-04-16

## Scope

This pass finalized the stable-vs-experimental promotion gate for FileMind's
BGE-M3 embedding backend.

Compared backends:

- `sentence_transformers` - current supported default
- `flagembedding_experimental` - optional experimental backend

Primary artifacts used:

- `C:\AI_STATION\filemind\.bench\sparse_eval_medium\comparison_summary.json`
- `C:\AI_STATION\filemind\.bench\sparse_eval_medium\comparison_summary_rerank.json`
- `C:\AI_STATION\filemind\.bench\sparse_eval_medium\stable.out.log`
- `C:\AI_STATION\filemind\.bench\sparse_eval_medium\sparse.out.log`
- `C:\AI_STATION\filemind\logs\live_rebuild_20260416-211847.out.log`

Supplemental measurements captured in this session:

- medium-corpus cold/warm search latency for both backends
- medium-corpus `verify` parity/completeness for both backends

## KPI Matrix

Bench corpus: `C:\AI_STATION\filemind\.bench\sparse_eval_medium\corpus`

| KPI | Stable | Experimental | Notes |
| --- | --- | --- | --- |
| Search quality, no rerank - Hit@1 | 17/30 | 18/30 | Experimental +1 |
| Search quality, no rerank - Hit@3 | 23/30 | 25/30 | Experimental +2 |
| Search quality, no rerank - Hit@5 | 26/30 | 28/30 | Experimental +2 |
| Search quality, no rerank - MRR | 0.6883 | 0.7122 | Experimental +0.0239 |
| Search quality, rerank - Hit@1 | 18/30 | 17/30 | Stable +1 |
| Search quality, rerank - Hit@3 | 25/30 | 26/30 | Experimental +1 |
| Search quality, rerank - Hit@5 | 26/30 | 26/30 | Tie |
| Search quality, rerank - MRR | 0.7083 | 0.6889 | Stable +0.0194 |
| Rebuild duration | 1299.8s | 1039.5s | Experimental 20.0% faster |
| Cold search latency - engine load | 0.2057s | 0.2048s | Essentially tied |
| Cold search latency - first query | 17.2214s | 14.7281s | Experimental 14.5% faster |
| Warm search latency - avg | 0.3828s | 0.0840s | Experimental 4.6x faster |
| Warm search latency - p50 | 0.3793s | 0.0845s | Experimental faster |
| Warm search latency - p95 | 0.4364s | 0.0942s | Experimental faster |
| Verify completeness | 100.0% | 100.0% | Tie |
| Verify embedding coverage | 98.33% | 98.33% | Tie |
| Verify chunk parity | OK | OK | Tie |

## Live Shared-HTTP Readiness

Experimental live rebuild evidence on the real shared corpus:

- `2843` indexed files
- `23208` chunks
- `0` errors
- `445.4s` total rebuild time
- `100.0%` completeness
- `96.8%` embedding coverage
- chunk parity `OK`

Observed retrieval note from the live corpus:

- repo-scoped/code-filtered smoke queries look good
- unrestricted live queries are noisier because prompt-ledger and broader corpus
  content now compete in the ranking space

This live run is strong readiness evidence, but it is not by itself sufficient to
change the default backend for all environments.

## Decision

The project should **not** promote `flagembedding_experimental` to the global
default backend yet.

What we are deciding now:

1. Keep `sentence_transformers` as the default supported backend.
2. Keep `flagembedding_experimental` as an opt-in backend for controlled
   experiments, shadow runs, and dedicated rebuild environments.
3. Treat BM25 as the supported lexical engine in the stable stack today.
4. Treat Qdrant sparse prefetch as optional experimental acceleration, not as a
   required property of the default runtime.

Why:

- The experimental backend is faster and slightly better on the medium corpus
  without reranking.
- The reranked evaluation is mixed rather than decisive.
- The experimental path still depends on a separate environment and operational
  handling that the default runtime does not yet guarantee.
- The live corpus still needs cleaner, production-style evaluation sets before a
  default flip would be low-risk.

## Promotion Criteria For A Future Default Flip

Promote the experimental backend only after all of the following are true:

1. It wins or clearly ties on a broader live-corpus query set, not just the
   medium bench corpus.
2. The runtime story is unified enough that the default environment can depend on
   it safely.
3. Alias-backed shadow rebuilds are in place so live rebuilds can verify then
   swap with fast rollback.
4. The retrieval policy is simplified enough that docs, tests, and operator
   expectations match the actual runtime path.

## Next Project Step

The next implementation priority is:

1. Alias-backed shadow rebuilds for shared Qdrant collections.

After that:

2. Add a broader live query set that excludes benchmark/self-index noise.
3. Re-run the backend promotion gate against the alias-backed shadow path.
