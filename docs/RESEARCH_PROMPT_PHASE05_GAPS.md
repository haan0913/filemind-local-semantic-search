# Research Prompt: FileMind Phase 0.5 — Resolve Outstanding Technical Debt

## Context

You are researching solutions for **FileMind**, a local-first semantic file search engine for Windows (planning native macOS port). This is NOT a greenfield project — it has an existing codebase with known bugs and technical debt that are actively degrading search quality. Your job is to find definitive, actionable solutions for each gap below.

**What FileMind does:**
- Scans directories on a Windows PC (currently ~4,800 files across 8 directories, planning to expand to ~2TB)
- Extracts content from PDFs, DOCX, XLSX, PPTX, EML files
- Chunks text with file-type-aware strategy (Python AST, JSON structure, Markdown headers, etc.)
- Generates BGE-M3 embeddings (dense + sparse vectors) via sentence-transformers
- Classifies files into categories using local LLM (Ollama) with rule-based fallback
- Stores in SQLite catalog with FTS5 full-text search + Qdrant vector database
- Hybrid search: FTS5 keyword + dense vector semantic, fused with RRF (k=60)
- Cross-encoder reranking (BAAI/bge-reranker-v2-m3)
- HyDE query expansion via Ollama llama3 (optional)
- AI agent layer (smolagents + Ollama) with 9 tools for agentic file management
- **Zero cloud dependency** — everything runs locally

**Hardware:**
- **Current**: RTX 3080 Ti (12GB VRAM), Ryzen 9 5900X (12C/24T), 32GB RAM, Windows
- **Target**: M1 Pro MacBook Pro, 16GB unified memory, 1TB SSD (native port planned)

**Software Stack:**
- Python 3.14 (critical: FlagEmbedding fails C compilation on 3.14)
- Qdrant (local vector store, dense + sparse collections)
- Ollama (local LLM serving at http://localhost:11434)
- Models: gemma4-e4b (7.5B Q8_0, ~9GB VRAM), gemma3:4b (4B, ~3.5GB VRAM), llama3:8B, llama3.2:3.2B
- sentence-transformers (BGE-M3 embeddings)
- PyMuPDF, python-docx, openpyxl, python-pptx, extract-msg (content extraction)
- watchdog (file watching, currently manual-only)
- Gradio (dashboard), FastAPI (REST API)

**Current Index State:**
- ~4,804 files in SQLite catalog
- ~1,585 chunks in Qdrant (~33% coverage after smart chunking rebuild)
- Top categories: config (1,638), documentation (1,218), code (1,015), ai_project (647)
- Top types: .json (1,169), .py (943), .js (337), .md (209)
- 1,205 duplicate groups found
- Index stored at: `C:\AI_STATION\.index\filemind.db` + `C:\AI_STATION\.index\qdrant`

---

## Gap 1: BGE-M3 Sparse Vectors Return Empty Dicts

### The Problem
FileMind uses BGE-M3 via `sentence-transformers` for embeddings. BGE-M3 is designed to produce both **dense vectors** (semantic meaning) and **sparse/lexical vectors** (keyword matching) — enabling hybrid search. However, `sentence-transformers` returns **empty dictionaries `{}`** for the sparse/lexical component. This means half of the hybrid search (the keyword-matching half) is dead. The system degrades to dense-only vector search + FTS5, losing the precision that sparse vectors provide.

### What We Know
- `sentence-transformers` wraps BGE-M3 but doesn't properly expose the lexical weight output
- The dense vectors work fine (cosine similarity produces meaningful results)
- The sparse vectors should be token ID → weight mappings (like BM25 scores)
- FlagEmbedding (the official BGE-M3 library) fails C compilation on Python 3.14
- Qdrant has a sparse vector collection ready but receiving empty data

### Research Questions
1. **Is there a working Python 3.14-compatible way to extract BGE-M3 sparse/lexical vectors?**
   - Can `sentence-transformers` be configured/patched to expose them?
   - Is there a fork, alternative wrapper, or direct transformers pipeline that works?
   - Can the `transformers` library be used directly (bypassing sentence-transformers) to get both dense and sparse outputs?

2. **If BGE-M3 sparse vectors are truly inaccessible on Python 3.14, what's the best replacement?**
   - BM25 standalone (via `rank_bm25` or `whoosh` or `tantivy-py`)
   - SPLADE (learned sparse embeddings)
   - Custom token-frequency-based sparse vectors
   - Compare accuracy, speed, memory, and Python 3.14 compatibility for each

3. **What does a production hybrid search system actually use?**
   - Do most systems use BGE-M3's native sparse output, or do they pair dense embeddings with a separate BM25 index?
   - What's the RRF (Reciprocal Rank Fusion) formula and optimal `k` parameter when combining dense + sparse results?
   - How do Qdrant's sparse vector features work — what format does it expect the data in?

4. **Implementation specifics needed:**
   - Exact Python code to extract sparse vectors (if possible) OR exact code to build a BM25 index alongside Qdrant dense vectors
   - How to format sparse vectors for Qdrant (what's the exact data structure: `{"indices": [...], "values": [...]}`?)
   - Performance comparison: BGE-M3 native sparse vs. BM25 standalone (indexing time, search latency, accuracy)

---

## Gap 2: Low Chunk Coverage (~33% of Indexed Files Have Vectors)

### The Problem
Only ~1,585 out of ~4,804 indexed files have vector representations in Qdrant. This means **~67% of indexed files cannot be found via semantic search**. The user can find them via FTS5 keyword search, but the core value proposition (search by meaning) fails for most files.

### What We Know
- Smart chunking is implemented (file-type-aware: Python AST, JSON structure, Markdown headers)
- Force rebuild exists: `python -m filemind run.py scan --rebuild`
- Previous full scan: 842 files scanned, 619 indexed, 1,585 chunks, 0 errors, 564.5s duration
- Embedding pipeline uses batch size 8 to avoid GPU OOM
- `torch.cuda.empty_cache()` is called between batches

### Research Questions
1. **Why did the rebuild only produce 1,585 chunks for 4,804 files?**
   - Is this expected? (Some files are images, binaries, too small to chunk)
   - Or is there a bug in the chunker/extraction pipeline?
   - What percentage of the 4,804 files are actually chunkable text content vs. non-text files?

2. **What's the optimal chunk coverage target?**
   - Should every text file have at least 1 chunk?
   - What's a realistic chunk-to-file ratio for a mixed code/documentation/config corpus?
   - At what point does over-chunking hurt search quality (too many tiny fragments diluting semantic signal)?

3. **Incremental re-indexing strategy:**
   - How to efficiently re-embed only the files that are missing vectors without re-processing everything?
   - What metadata should be tracked to know which files need embedding?
   - How to handle files whose content changed since last embedding (mtime comparison isn't enough — need hash comparison)?

---

## Gap 3: Classifier Model Selection — gemma4-e4b-json vs gemma3:4b

### The Problem
The default classification model is `gemma4-e4b-json` (7.5B quantized to Q8_0, ~8.7GB VRAM). Research shows this model has architectural weaknesses: 18/42 shared KV layers with sliding window attention, making it less reliable for structured tool-calling and JSON output. The alternative `gemma3:4b` (4B model, ~3.5GB VRAM) has better tool-calling reliability and uses less than half the VRAM.

### What We Know
- Classification happens during indexing: files are tagged as "code", "documentation", "config", "personal", etc.
- Rule-based classifier runs first (extension map + directory heuristics)
- Ollama LLM classifies only uncertain files (batch size 5)
- `gemma3:4b` was tested and works with JSON schema format (not plain string `format: "json"`)
- Current config: `CLASSIFICATION_MODEL = "gemma4-e4b-json"` with gemma3:4b as fallback

### Research Questions
1. **What's the definitive accuracy comparison between gemma4-e4b and gemma3:4b for file classification tasks?**
   - Not tool-calling — specifically text classification/categorization
   - Does gemma3:4b produce equally accurate category labels?
   - Are there benchmark results for classification (not generation) quality?

2. **VRAM budget analysis:**
   - Current: gemma4-e4b-json uses ~8.7GB during classification, leaving ~3.3GB for BGE-M3 embedding (batch size constrained)
   - If switched to gemma3:4b (~3.5GB): ~8.5GB available for BGE-M3 (could increase batch size from 8 to 16-24?)
   - What's the net throughput impact? (slower per-batch classification but faster embedding due to larger batches)

3. **Recommendation:**
   - Should gemma3:4b become the default classifier?
   - Or should gemma4-e4b-json remain default for accuracy and gemma3:4b stay as fallback?
   - What Ollama parameters are optimal for each model? (num_ctx, temperature, repeat_penalty)

---

## Gap 4: Agent Still Skips Mandatory Search

### The Problem
The FileMind agent has a mandatory search-first protocol implemented in **code** (not just prompt): `_run_mandatory_search()` runs before the agent loop, and results are injected into context via `_build_grounding_context()`. Despite this, `gemma4-e4b` can still produce answers from its parametric knowledge without referencing the search results, especially when search returns empty or low-confidence results.

### What We Know
- Answer validation exists: `_validate_answer()` checks if the agent's response references index content (file_ids, paths, scores)
- System prompt has 200+ lines with 9 rules, decision flowchart, and examples for both empty and populated results
- Max steps = 5 (prevents infinite loops but also limits thoroughness)
- The issue is worse when search returns empty results — the agent fills the gap from general knowledge

### Research Questions
1. **What techniques actually prevent LLMs from answering from parametric knowledge when evidence is absent?**
   - "I don't know" training / refusal prompting — does it work?
   - Structured output constraints (force JSON with evidence field)?
   - Multi-step verification (answer → critique → refine)?
   - Confidence scoring (agent must score its own answer's grounding)?

2. **Is gemma4-e4b fundamentally unreliable for this task?**
   - Compare with gemma3:4b, qwen2.5:3b, phi4:mini for tool-calling reliability
   - Are there specific Ollama parameters that improve grounding? (temperature 0.0, repeat_penalty 1.5, etc.)
   - What's the industry standard for local agent grounding?

3. **Architectural solutions:**
   - Should there be a separate "critic" model that validates the agent's answer against search results?
   - Should empty search results trigger a different response template?
   - Is the answer validation strict enough? (Does it catch subtle hallucinations vs. obvious ones?)

---

## Gap 5: Index Noise — Incomplete SKIP_DIRS Cleanup

### The Problem
The index contains noise from browser cache, build artifacts, node_modules, and other non-valuable files. A SKIP_DIRS audit was performed (fine-grained patterns replacing blanket directory skips), but the cleanup was not verified complete.

### What We Know
- Current SKIP_SUBDIRS: 27 patterns (replacing blanket `.kimi` skip)
- HIGH_VALUE_INCLUDE_PATTERNS: 15 patterns (override skip patterns for valuable subdirectories)
- Scanner detects symlinks/junctions to prevent infinite recursion
- 4,804 files indexed — likely includes noise files
- No verification was done to confirm noise files are actually excluded

### Research Questions
1. **What are the most common noise sources in a developer's file system?**
   - Node modules, Python __pycache__, .git directories, browser cache, build artifacts (dist/, build/, out/), IDE caches (.idea/, .vscode/), OS metadata (Thumbs.db, .DS_Store), temp files
   - What patterns reliably catch these without false positives?

2. **How to verify index cleanliness?**
   - What queries would reveal noise files in the index? (e.g., search for "node_modules" in file paths)
   - Is there an automated way to audit the index and flag likely noise files?
   - Should there be a "noise score" per file based on path patterns + file characteristics?

3. **Should the index be cleaned by re-scanning with better patterns, or should noise files be removed individually?**
   - Re-scan: cleaner but time-consuming (564s for full scan)
   - Individual removal: faster but error-prone
   - What's the safest approach?

---

## Gap 6: Reranker Identity Unknown

### The Problem
The original reranker was `FlagEmbedding` (BAAI/bge-reranker-v2-m3), which fails C compilation on Python 3.14. It was removed and replaced with an alternative, but the identity and functionality of this replacement is unknown/unverified.

### What We Know
- `ENABLE_RERANKING = True` in config
- The reranker is supposed to be BAAI/bge-reranker-v2-m3
- FlagEmbedding library fails on Python 3.14
- An alternative was installed but not documented
- Reranking adds ~200ms latency per query (CPU-based)

### Research Questions
1. **What are the Python 3.14-compatible alternatives to FlagEmbedding for cross-encoder reranking?**
   - `sentence-transformers` CrossEncoder class (does it support bge-reranker-v2-m3?)
   - Direct transformers pipeline with AutoModelForSequenceClassification
   - Alternative reranker models (bge-reranker-base, bge-reranker-large, ms-marco-MiniLM)
   - Compare accuracy, speed, and Python 3.14 compatibility

2. **Is the current reranker actually producing scores?**
   - What would the code look like to verify this?
   - If it's broken, is silent failure happening (reranking enabled but returning original order)?

3. **Is reranking worth the 200ms latency cost?**
   - What's the accuracy improvement vs. hybrid search alone?
   - At what query volume does the latency become unacceptable?
   - Should it be optional (enabled for ambiguous queries, disabled for specific ones)?

---

## Gap 7: Dynamic Embedding Batch Size

### The Problem
The current embedding pipeline uses a static batch size of 8 files per batch. This is a workaround to avoid GPU OOM but is not optimized for the actual hardware (RTX 3080 Ti with 12GB VRAM).

### What We Know
- RTX 3080 Ti: 12GB VRAM
- BGE-M3 model: ~2.2GB model weights
- Current batch size: 8 files (conservative)
- `torch.cuda.empty_cache()` called between batches
- Smart chunking produces variable-sized chunks (a 50KB Python file might produce 3 chunks, a 5KB JSON file might produce 1)

### Research Questions
1. **What's the optimal batch size for BGE-M3 on RTX 3080 Ti (12GB VRAM)?**
   - How to calculate: (available VRAM - model weights) / per-sample memory
   - Does chunk size variability affect the optimal batch size?
   - Should batch size be dynamic based on total tokens in the batch?

2. **What's the performance difference between batch size 8 vs. 16 vs. 24 vs. 32?**
   - Throughput (files/second) vs. batch size
   - At what point does OOM risk outweigh throughput gains?
   - Is there a safe auto-detection method? (Start high, reduce on OOM)

3. **Would gradient checkpointing or mixed precision help?**
   - FP16 vs. FP32 for BGE-M3 embeddings (accuracy trade-off)
   - Gradient checkpointing for inference (does it apply?)

---

## Output Requirements

For each gap, provide:

1. **Root cause analysis** — Why does this problem exist? (technical explanation, not just symptoms)
2. **Definitive answers** with source citations (documentation, GitHub issues, benchmarks, papers)
3. **Concrete numbers** — latency, throughput, memory usage, accuracy percentages. Not vague "it depends."
4. **Ranked recommendations** — Option A vs. B vs. C with clear justification for the winner
5. **Implementation specifics** — exact code snippets, exact config changes, exact commands
6. **Known pitfalls** — what looks good on paper but breaks in practice
7. **Dependencies** — does fixing this gap enable or block other fixes?
8. **Estimated effort** — rough complexity (hours, not days): trivial (<1h), small (1-4h), medium (4-8h), large (8-16h)

**Validation rules:**
- Cross-reference all claims against multiple sources
- If sources conflict, explain why and which you trust more
- Prioritize Python 3.14 compatibility in all recommendations
- Consider the user's hardware constraints (12GB VRAM, 32GB RAM, Ryzen 9 5900X)
- Flag any recommendation that would require changing the core architecture (not just config)

**Format:** One section per gap, with a summary table at the end showing all recommendations ranked by priority and effort.
