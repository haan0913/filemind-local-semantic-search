# FileMind Project Plan Report

**Generated:** 2026-04-08 14:00
**Project Phase:** SEARCH_QUALITY_VERIFICATION
**Last Updated:** 2026-04-08T13:30:00-04:00

## ⏰ Active Reminders

- **R-001**: After smart chunking rebuild completes, switch classification model from gemma4-e4b-json to gemma3:4b (trigger: `rebuild_complete`)

## ⚠️ Active Risks

- 🔴 **[CRITICAL] RISK-001**: Rebuild crash mid-process = lost chunks with no recovery. Backup exists at vault/backups/index_20260408_124500_preSmartRebuild
  - *Mitigation:* If rebuild fails, restore from backup and investigate root cause before retrying

## 📋 TODO (by priority)

- [HIGH] **T-MODEL-001**: Switch classification model from gemma4-e4b-json to gemma3:4b (half VRAM, better tool-calling reliability) (blocked by: T-CHUNK-002)
  - WAIT for rebuild to complete. Steps: ollama pull gemma3:4b → config change → verify on unknown files.
- [HIGH] **T-SPARSE-001**: Research BGE-M3 sparse vector extraction alternatives — sentence-transformers returns empty dicts, killing half of hybrid search
  - Research prompt created: docs/RESEARCH_PROMPT_SPARSE_VECTORS.md. Plan B: standalone BM25.
- [HIGH] **T-SPARSE-002**: Implement sparse vector extraction (or BM25 fallback) based on research findings (blocked by: T-SPARSE-001)
  - Awaiting research results. Config switch: ENABLE_SPARSE_VECTORS.
- [MEDIUM] **T-NOISE-001**: Delta scan to clean remaining index noise (old scan root artifacts) (blocked by: T-CHUNK-002)
  - Run python run.py scan --full after rebuild to remove old subagent JSON noise.

## ✅ Completed

- [HIGH] **T-CHUNK-001**: Smart chunking implemented (AST for Python, structure for JSON/YAML/TOML, header-based for Markdown, layout for PDF)
- [CRITICAL] **T-DEPS-001**: Dependency validation system — check_deps.py validates all optional features at startup, auto-disables missing
- [HIGH] **T-RERANK-001**: Switch reranker from FlagEmbedding (not installable on Python 3.14/Windows) to sentence_transformers.CrossEncoder
- [MEDIUM] **T-CONTENT-001**: Increase MAX_CONTENT_LENGTH from 50K to 200K characters per file
- [MEDIUM] **T-GITHUB-001**: Push latest code to GitHub private repo
- [HIGH] **T-CHUNK-002**: Force rebuild: re-chunk all 3,838 files with smart chunking strategy
- [HIGH] **T-PLAN-001**: Implement dual-audience project planning system (JSON orchestration + auto-generated markdown)
- [MEDIUM] **T-RERANK-002**: Enable reranking (ENABLE_RERANKING = True) — CrossEncoder verified working, now active
- [MEDIUM] **T-PLAN-002**: Migrate SYSTEM_NOTES.md items (1-74) into unified plan.json decisions section
- [HIGH] **T-TEST-001**: Verify search quality after smart chunking rebuild — results documented

## 📌 Key Decisions

- **D-001**: Use Qdrant (not LanceDB) as vector store — serverless local mode with hybrid RRF fusion
  - *Rationale:* Already implemented, working. Hybrid search functional.
- **D-002**: Batch embedding (8 files/batch, sequential) instead of ThreadPoolExecutor to avoid VRAM OOM
  - *Rationale:* 32-thread ThreadPoolExecutor caused 26.4GB VRAM allocation on 12GB GPU.
- **D-003**: Research-first protocol before non-trivial changes
  - *Rationale:* FlagReranker crash proved we enable features without validating dependencies.
- **D-004**: Flat task list for JSON orchestration (not nested hierarchical)
  - *Rationale:* Research confirmed: flat arrays are simpler for LLM parsing, easier to enforce priority order.
- **D-005**: Enable reranking via sentence_transformers.CrossEncoder, not FlagEmbedding
  - *Rationale:* FlagEmbedding doesn't compile on Python 3.14/Windows. CrossEncoder verified working.
- **D-006**: Local Ollama first — never rely on external free models (they rotate/deprecated)
  - *Rationale:* OpenRouter free tier limited to 50 requests/day. Free models return 404 frequently.
- **D-007**: gemma3:4b recommended as primary worker over gemma4-e4b until gemma4 patterns established
  - *Rationale:* Research: gemma4-e4b has 18/42 shared KV layers + SWA(512) — less reliable tool-calling.
- **D-008**: 3-layer enforcement: input rails, pre-execution validation, mandatory search-first protocol
  - *Rationale:* Research paper: 'Simply instructing an agent to use files is insufficient; system must be architecturally constrained.'
- **D-009**: Vault backups excluded from scanning — they duplicate current files and pollute search
  - *Rationale:* Vault copies appeared in top 5 search results for 'FileMind configuration scan roots'.
- **D-010**: Multi-model swarm architecture: Worker (gemma3:4b), Critic (qwen2.5:3b), Router (phi4:mini)
  - *Rationale:* Research paper recommended this architecture. Total VRAM ~10GB fits in 12GB.
- **D-011**: Smart chunking with file-type-aware dispatch (AST, structure, headers, layout)
  - *Rationale:* Research PDF 'Beyond Fixed-Size Chunks' provided complete blueprint. Rebuild: 3,877 files, 5,896 chunks, 0 errors.

---
**Summary:** 10/14 done, 0 in progress, 4 remaining
*This report is auto-generated from `plan.json`. Do not edit directly.*