# FileMind — Agent Scope

Local semantic file search. Hybrid Qdrant (dense BGE-M3 + sparse + RRF fusion) +
cross-encoder rerank + optional Ollama classification. No cloud dependency.

## Runtime

- Python: `C:\AI_STATION\venvs\semantic-core\Scripts\python.exe` (the AI_STATION semantic runtime)
- Bootstrap: `C:\AI_STATION\projects\source\ai_station_context\scripts\bootstrap_semantic_core.ps1`
  enforces CUDA Torch (`torch==2.11.0+cu130`) on this NVIDIA workstation.
- Test runner: use the semantic-core runtime for live CLI/runtime checks; use
  workstation `python -m pytest ...` only when the task explicitly needs the
  broader developer test environment.
- Entrypoint: `C:\AI_STATION\filemind\run.py`
- Qdrant: shared HTTP (`http://127.0.0.1:6333`) is the AI_STATION default for
  CLI verify/search and acceptance. Local embedded Qdrant is a legacy/scratch
  mode only; opt into it explicitly with `FILEMIND_QDRANT_MODE=local`.
- GPU: CUDA 13.2, RTX 3080 Ti

## Key modules

| Layer | File | What it does |
|---|---|---|
| Scan | `scanner.py` | Walk + mtime/MD5 change detection |
| Extract | `extractor.py` | PDF / DOCX / text / JSON |
| Classify | `classifier.py` | Ollama LLM + rule fallback |
| Chunk | `chunker.py` | Splitter |
| Embed | `embedder.py` | BGE-M3 dense + sparse |
| Store | `vector_store.py` | Qdrant hybrid + RRF |
| Search | `search.py` | RRF fuse → rerank → HyDE |
| Pipeline | `nightly.py` | `run_index_pipeline()` |
| CLI | `run.py` | User surface |

## Retrieval order when working here

1. Open the task's `allowed_files` — read only those.
2. If broader context needed, grep within `filemind/` (never outside).
3. Read the public surface (`run.py`, `search.py`) before touching internals.
4. Do not pull in upstream `mem0/` or `hub/` unless the task explicitly allows.

## Test / acceptance

```
python -m pyright --project C:\AI_STATION\.pre-commit-pyright.json
python -m pytest filemind/tests -x -q
python C:\AI_STATION\filemind\run.py search "smoke" --top-k 3
```

`search` returning any result is the acceptance floor. A zero-result `smoke`
query is a regression even if pytest passes.

Pyright is a hard-error standard-mode gate for FileMind's opted-in Python files.
Generated benchmark corpus snapshots under `filemind/.bench` are excluded from
the publication gate; do not add new warning-level demotions for real type
errors.

## Do / don't

- Do: single-file edits, narrow patches, add tests alongside behavior change.
- Don't: rewrite `vector_store.py` or the embedding path without a ticket that
  names it in `allowed_files`. Those are high-blast-radius modules.
- Don't: run `scan --full` as a side effect of an edit. It's hours of work.

---
Documentation Signature
Updated by: Codex (GPT-5.5)
Timestamp: 2026-05-18T12:28:50-04:00
Change summary: Updated FileMind lint guidance for the restored hard-error Pyright standard-mode gate.
