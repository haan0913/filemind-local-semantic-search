# FileMind Post-Upgrade Benchmark Runbook - 2026-05-10

## Why the first plan was not yet 100%

The original plan had the right safety shape, but it was still narrative. It
did not provide an executable control packet, consistent artifact names,
machine-readable pass/fail gates, or an opt-in guard around destructive rebuild
work. This runbook closes those gaps.

## 100% benchmark-control standard

A FileMind post-upgrade benchmark is acceptable only when it produces a
self-contained run directory with:

1. environment/runtime snapshot
2. command logs for every preflight gate
3. read-only live query quality and latency metrics
4. machine-readable gate status
5. human-readable report
6. optional shadow rebuild evidence, if and only if explicitly requested

The default benchmark must not reset the live `file_chunks` collection.

## Executable harness

Use:

```powershell
C:\AI_STATION\venvs\semantic-core\Scripts\python.exe C:\AI_STATION\filemind\benchmark_post_upgrade.py --strict
```

Default behavior:

- runs `runtime`, `deps`, `scan-status`, `stats`, and `verify`
- runs a read-only live query benchmark through `SearchEngine`
- writes artifacts under `C:\AI_STATION\filemind\.bench\post_upgrade_YYYYMMDD-HHMMSS\`
- exits non-zero only when `--strict` is used and a gate fails

Useful variants:

```powershell
# Use the historical controlled query set as a non-gating live probe.
C:\AI_STATION\venvs\semantic-core\Scripts\python.exe C:\AI_STATION\filemind\benchmark_post_upgrade.py --use-controlled-query-file

# Include reranking in the read-only query benchmark.
C:\AI_STATION\venvs\semantic-core\Scripts\python.exe C:\AI_STATION\filemind\benchmark_post_upgrade.py --rerank --strict

# Run an isolated shadow rebuild and enforce the historical controlled query
# targets there. This is explicit because it is long-running.
C:\AI_STATION\venvs\semantic-core\Scripts\python.exe C:\AI_STATION\filemind\benchmark_post_upgrade.py --shadow-rebuild --use-controlled-query-file --min-hit1 17 --min-hit3 23 --min-hit5 26 --min-mrr 0.68 --strict
```

## Artifact contract

Each run directory contains:

- `environment_snapshot.json`
- `preflight_results.json`
- `command_logs/*.stdout.log`
- `command_logs/*.stderr.log`
- `latency_results.jsonl`
- `quality_results.json`
- `summary.json`
- `BENCHMARK_REPORT.md`
- `shadow_environment.json` and `shadow_rebuild_results.json` only when
  `--shadow-rebuild` is used

## Gates

Baseline gates:

- all preflight commands exit 0
- `filemind/run.py verify` exits 0 unless explicitly skipped
- every live benchmark query returns at least one result

Optional stricter gate:

- `--require-hit-at 5` requires every query with an expected file target to
  place one expected target in the top 5
- For the historical controlled corpus, prefer baseline thresholds instead of
  perfect-hit requirements: `--min-hit1 17 --min-hit3 23 --min-hit5 26
  --min-mrr 0.68` for the no-rerank lane.
- The historical `sparse_eval_medium` query set is a strict gate only against
  its controlled/shadow corpus. Against the live workspace it is a probe, not a
  pass/fail acceptance gate, unless `--allow-live-expected-gate` is supplied.

## Safety notes

- The default benchmark is read-only against the live index.
- Shadow rebuilds use an isolated `FILEMIND_INDEX_DIR` and a separate
  `FILEMIND_QDRANT_COLLECTION`.
- Do not run live `scan --rebuild` as part of benchmarking unless the shadow
  rebuild, verify gate, and query-quality gate have already passed.

## Current 2026-05-10 rerun outcome

Read-only live gate passed:

- `C:\AI_STATION\filemind\.bench\post_upgrade_20260510-034401_codex_final\BENCHMARK_REPORT.md`
- `filemind_verify`: pass
- live query non-zero gate: pass

Controlled shadow rebuild gate partially passed:

- `C:\AI_STATION\filemind\.bench\post_upgrade_20260510-034843_shadow_controlled\BENCHMARK_REPORT.md`
- shadow rebuild: pass
- shadow verify: pass
- controlled no-rerank quality: Hit@1/3/5 = `17/23/25`, MRR = `0.681667`
- 2026-04-16 no-rerank baseline was Hit@1/3/5 = `17/23/26`, MRR = `0.6883`

This is a real retrieval-quality finding, not a benchmark-control failure. It
is tracked as Task Master task `183`, and the quality threshold should not be
lowered unless that task produces evidence that the benchmark expectation or
corpus changed legitimately.
