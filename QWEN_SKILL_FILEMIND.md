# FileMind — Qwen Code Skill Reference

## What I Can Do RIGHT NOW (No Agent Loop Needed)

I (Qwen Code) can use FileMind's CLI tools through my shell access to search, analyze, and reason about your indexed files.

### Available Commands
```bash
# Search indexed files
python run.py search "your query here"                  # Hybrid search (default)
python run.py search "query" --keyword                  # Keyword search only
python run.py search "query" --semantic                 # Vector search only
python run.py search "query" --type .py                 # Filter by extension
python run.py search "query" --rerank                   # With cross-encoder reranking
python run.py search "query" --hyde                     # With HyDE query expansion

# Get index intelligence
python run.py stats          # Category breakdown, file counts, top types
python run.py duplicates     # Find duplicate file groups
python run.py health         # System health (Ollama, GPU, DB status)
python run.py verify         # Index completeness vs actual disk

# Run indexing
python run.py scan           # Quick scan (detect changes, ~2s)
python run.py scan --full    # Full pipeline (extract + embed + classify)
python run.py scan --rebuild # Force re-chunk + re-embed ALL files

# Interactive mode
python run.py interactive    # REPL for fast queries
```

### Current Index State (as of April 8, 2026 — Post-Rebuild)
- **3,388 files** indexed across 8 scan roots
- **3,383 chunks** in Qdrant vector store (up from 405)
- **Categories:** code (934), config (1157), documentation (1150), ai_project (398), personal (88), research (107), unknown (60), finance (5), archive (3)
- **Top types:** .json (1300), .md (1057), .py (760), .txt (185), .log (185)
- **Vector store:** Qdrant local mode, dense + sparse (RRF fusion)
- **Embeddings:** BGE-M3 via sentence-transformers (CUDA)
- **Search latency:** ~7s cold start (model load), ~2s warm

### Architecture
| Component | Technology | Status |
|---|---|---|
| Vector store | Qdrant (local mode) | ✅ Hybrid search (dense+sparse+RRF) |
| Embeddings | BGE-M3 (sentence-transformers) | ✅ Dense working, sparse empty |
| Classification | Ollama gemma4-e4b-json + RuleBasedClassifier | ✅ 94%+ accuracy |
| Reranking | FlagReranker (BAAI/bge-reranker-v2-m3) | ⚙️ Implemented, disabled by default |
| Query expansion | HyDE via llama3 | ⚙️ Implemented, disabled by default |
| Pipeline | Nightly orchestrator with batch embedding | ✅ Batch of 8 files, no OOM |
| Safety | Deleted file verification, mass deletion cap | ✅ 100+ deletes triggers warning |

### Limitations
- **Sparse vectors empty** — sentence-transformers can't extract BGE-M3 lexical weights. Hybrid search is dense-only right now.
- **500-char content_summary** — catalog stores truncated summaries. Chunks are cut from these, so large files get short, low-quality chunks.
- **Some index noise** — old scan root artifacts (subagent JSON files) still in index. Next delta scan will clean.
- **BGE-M3 cold start** — ~7s model load per new search session. No persistent model server yet.

### GitHub
- **Repo:** https://github.com/haan0913/filemind (private)
- **Skill:** `hub/agents/skills/github/` — read repos, create files, commit, push, PRs
- **Auth:** PAT verified, username haan0913

### When to Use This
- When you ask me to find files, organize projects, clean up duplicates
- When I need context about your codebase before making changes
- When I should reference existing documentation before writing new docs
- When I need to verify what files exist before proposing architecture changes

### Research-First Protocol
Before implementing non-trivial changes, I MUST:
1. Evaluate current knowledge (what do we actually know vs assume?)
2. Identify knowledge gaps
3. Generate precise research prompt (see `docs/RESEARCH_FIRST_PROTOCOL.md`)
4. Run deep research or ask user to approve
5. Implement with experimental + reliable backup pattern
