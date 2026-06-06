# FileMind User Guide

Canonical path: `C:\AI_STATION\filemind\docs\user\FILEMIND_USER_GUIDE.md`

This is the current user-facing guide for FileMind. The legacy root-level guide remains only as a compatibility entry point until all agents finish migrating.

## Quick Start

```bash
# Search the indexed workspace
C:\Users\amirk\.kimi\owl-agent\.venv\Scripts\python.exe C:\AI_STATION\filemind\run.py search "your query here"

# Refresh the index
C:\Users\amirk\.kimi\owl-agent\.venv\Scripts\python.exe C:\AI_STATION\filemind\run.py scan --full

# Run a clean full rebuild from source
C:\Users\amirk\.kimi\owl-agent\.venv\Scripts\python.exe C:\AI_STATION\filemind\run.py scan --rebuild

# Prune files that are now out of scope under current skip rules
C:\Users\amirk\.kimi\owl-agent\.venv\Scripts\python.exe C:\AI_STATION\filemind\run.py scan --prune-excluded

# Inspect health and stats
C:\Users\amirk\.kimi\owl-agent\.venv\Scripts\python.exe C:\AI_STATION\filemind\run.py health
C:\Users\amirk\.kimi\owl-agent\.venv\Scripts\python.exe C:\AI_STATION\filemind\run.py stats
C:\Users\amirk\.kimi\owl-agent\.venv\Scripts\python.exe C:\AI_STATION\filemind\run.py verify
```

## Current Retrieval Stack

- Catalog DB: `C:\AI_STATION\filemind\.index\filemind.db`
- Vector store: shared Qdrant collection `file_chunks` when `AI_STATION_USE_SHARED_QDRANT=1`, otherwise local `C:\AI_STATION\filemind\.index\qdrant\`
- BM25 index: `C:\AI_STATION\filemind\.index\bm25_index.json`
- Dense embeddings default: `BAAI/bge-m3` via `sentence-transformers`
- Supported lexical leg: BM25 over the indexed chunk corpus
- Experimental backend: `flagembedding_experimental` remains opt-in, not the default runtime
- Reranker: `BAAI/bge-reranker-v2-m3`
- Classification default: `gemma3:4b`

## Search Tips

- Use plain English for hybrid search.
- Use `--keyword` for exact wording.
- Use `--type .py` or `--category code` to narrow results.
- If the workspace has just been reorganized, rerun `scan --full` after file moves settle.
- Use `scan --rebuild` when you need a clean source-backed full rebuild of the live chunk corpus.
- Run `verify` after a rebuild to confirm effective scan coverage and chunk parity.
- Default indexing intentionally skips transient churn such as `C:\AI_STATION\.tmp`, `review\duplicates`, prompt-ledger live events, context caches/logs, and Codex runtime temp/plugin-cache folders.

## Legacy Notes

- Older docs may still mention `lancedb`, `FlagEmbedding`, or `gemma4-e4b` defaults. Treat those as historical references.
- Older docs may also still mention the pre-refocus index path `C:\AI_STATION\.index`; the live default is `C:\AI_STATION\filemind\.index`.
- The old path `C:\AI_STATION\FILEMIND_USER_GUIDE.md` is being kept temporarily so other agents do not break during migration.

---
Documentation Signature
Updated by: Codex (GPT-5)
Timestamp: 2026-04-16T13:05:00-04:00
Change summary: Added rebuild and verify guidance, clarified shared-Qdrant vs local vector-store usage, and refreshed the retrieval notes after the clean rebuild.
