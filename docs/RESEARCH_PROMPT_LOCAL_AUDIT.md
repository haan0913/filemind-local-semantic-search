# FileMind Phase 0.5 — Local Audit & Validation Research Prompt

## Agent Briefing

You are a **local-file-access-capable agent** auditing the FileMind project. You have direct access to the codebase, configuration, index, and environment. Your job is to **validate every research finding and implementation plan** against the actual state of the system. Do NOT trust documentation at face value — read the code, run diagnostics, and confirm or refute each claim.

This prompt contains the complete context of two rounds of remote research. Your task is to ground-truth all of it against reality.

---

## Project Root & Key Directories

```
C:\AI_STATION\filemind\          ← Project root
├── config.py                     ← Central configuration (READ THIS FIRST)
├── scanner.py                    ← Directory walker, SKIP_DIRS logic
├── extractor.py                  ← Content extraction (PDF, DOCX, etc.)
├── chunker.py                    ← Smart chunking (AST, JSON, etc.)
├── embedder.py                   ← BGE-M3 embeddings via sentence-transformers
├── classifier.py                 ← Ollama LLM classification + rule fallback
├── catalog.py                    ← SQLite catalog with FTS5
├── vector_store.py               ← Qdrant vector store (dense + sparse)
├── search.py                     ← Hybrid search (FTS5 + dense + RRF + reranking)
├── nightly.py                    ← Pipeline orchestrator (scan → extract → classify → embed)
├── duplicates.py                 ← Duplicate detection
├── run.py                        ← CLI entry point
├── api.py                        ← FastAPI REST API
├── dashboard.py                  ← Gradio dashboard
├── check_deps.py                 ← Dependency validation
├── agent/
│   ├── run.py                    ← smolagents CodeAgent (9 tools)
│   └── kpi_logger.py             ← KPI logging
├── docs/                         ← 30+ documentation files
├── tests/                        ← Unit + E2E tests
├── vault/                        ← Session checkpoints + backups
├── logs/                         ← KPI logs

C:\AI_STATION\.index\             ← External index directory
├── filemind.db                   ← SQLite catalog
└── qdrant\                       ← Qdrant vector store

C:\Users\amirk\AppData\Local\Programs\Ollama\  ← Ollama installation
http://localhost:11434             ← Ollama API endpoint
```

**Scan roots** (configured in config.py — verify these):
- `C:\AI_STATION` (primary workspace)
- `C:\Users\amirk\.kimi` (agent directory)
- `C:\Users\amirk\Obsidian Vault` (personal notes)
- `C:\Users\amirk\pc-focus` (personal project)
- `C:\Users\amirk\.cline`, `.claude`, `.openclaw`, `.agents` (agent configs)

---

## Hardware & Environment (Verify These)

| Claim | How to Verify |
|-------|---------------|
| RTX 3080 Ti with 12GB VRAM | Run `nvidia-smi` or `torch.cuda.get_device_properties(0)` |
| Ryzen 9 5900X (12C/24T) | Check `os.cpu_count()` or system info |
| 32GB system RAM | Check `psutil.virtual_memory().total` |
| Python 3.14 | Run `python --version` in the project |
| FlagEmbedding fails compilation | Check `pip list | findstr FlagEmbedding` |
| Ollama models installed | Run `ollama list` — verify: gemma4-e4b, gemma4-e4b-json, gemma3:4b, llama3, llama3.2, nomic-embed-text |

---

## Research Findings to Validate

Two rounds of remote research produced definitive answers for 7 technical debt gaps + 4 flagged uncertainties. **Your job is to verify each one against the actual codebase.**

### Gap 1: BGE-M3 Sparse Vectors → BM25 Standalone

**Research claim**: `sentence-transformers` returns empty dicts `{}` for BGE-M3 sparse/lexical vectors. The `transformers` library directly also cannot expose sparse output — only `FlagEmbedding.BGEM3FlagModel` can, and it fails C compilation on Python 3.14. Therefore, standalone BM25 with RRF fusion is the recommended solution.

**What to verify**:
1. Read `embedder.py` — confirm how BGE-M3 is currently loaded and whether sparse vector extraction is attempted
2. Read `vector_store.py` — check if Qdrant sparse collection exists and what data it contains
3. Run a quick test:
   ```python
   from sentence_transformers import SentenceTransformer
   model = SentenceTransformer("BAAI/bge-m3", device="cuda")
   result = model.encode("test", return_dense=True, return_sparse=True)
   print(type(result), result)
   ```
   Does sparse output come back empty?
4. Read `search.py` — check how hybrid search currently fuses results. Is RRF implemented? What's the actual fusion code?
5. Check if `rank_bm25` is already installed: `pip list | findstr bm25`

**Expected outcome**: Confirm or refute that sparse vectors are broken and BM25 is needed.

---

### Gap 2: Low Chunk Coverage (~33%)

**Research claim**: Only ~1,585 out of ~4,804 indexed files have vector representations. ~67% of indexed files cannot be found via semantic search.

**What to verify**:
1. Query the SQLite catalog:
   ```python
   import sqlite3
   conn = sqlite3.connect(r"C:\AI_STATION\.index\filemind.db")
   cur = conn.cursor()
   cur.execute("SELECT COUNT(*) FROM files")  # Total indexed files
   cur.execute("SELECT COUNT(*) FROM chunks")  # Total chunks
   cur.execute("SELECT extension, COUNT(*) FROM files GROUP BY extension ORDER BY COUNT(*) DESC")
   print(cur.fetchall())
   ```
2. What's the actual file count? Chunk count? File type distribution?
3. Read `chunker.py` — verify smart chunking is implemented (Python AST, JSON structure, Markdown headers, etc.)
4. Read `nightly.py` — check the pipeline flow. Does extraction happen before chunking? Are there silent failure paths where files get indexed but not chunked/embedded?
5. Check if there's a `--rebuild` flag and how it works in `run.py`

**Expected outcome**: Confirm actual coverage numbers. Identify which file types are being skipped and why.

---

### Gap 3: Classifier Model — gemma4-e4b-json vs gemma3:4b

**Research claim**: Default is `gemma4-e4b-json` (8.7GB VRAM). `gemma3:4b` (3.5GB VRAM) was tested and works with JSON schema format. Switching saves 5.2GB VRAM, enabling larger embedding batches.

**What to verify**:
1. Read `config.py` — what is `CLASSIFICATION_MODEL` set to right now?
2. Read `classifier.py` — how does the Ollama call work? Does it handle gemma3:4b's JSON schema requirement?
3. Run `ollama list` — confirm gemma3:4b is actually installed
4. Test classification with both models:
   ```python
   import requests
   # Test gemma4-e4b-json
   resp = requests.post("http://localhost:11434/api/chat", json={
       "model": "gemma4-e4b-json",
       "messages": [{"role": "user", "content": "Classify this file: import os, sys"}],
       "format": "json"
   })
   # Test gemma3:4b
   resp = requests.post("http://localhost:11434/api/chat", json={
       "model": "gemma3:4b",
       "messages": [{"role": "user", "content": "Classify this file: import os, sys"}],
       "format": {"type": "object", "properties": {"category": {"type": "string"}}}
   })
   ```
5. Measure VRAM usage during each: `nvidia-smi --query-gpu=memory.used --format=csv`

**Expected outcome**: Confirm current model, verify gemma3:4b works, document exact config change needed.

---

### Gap 4: Agent Skips Mandatory Search

**Research claim**: Despite `_run_mandatory_search()` in code, gemma4-e4b can still answer from parametric knowledge. A critic model loop (gemma3:4b) with hybrid grounding (regex path extraction + LLM semantic check) is recommended.

**What to verify**:
1. Read `agent/run.py` — find `_run_mandatory_search()`, `_build_grounding_context()`, `_validate_answer()`
2. How does the mandatory search actually work? Is it truly before the agent loop, or can the agent bypass it?
3. What does `_validate_answer()` check? Is it just string matching for file paths?
4. Read the agent's system prompt — does it have refusal templates for empty results?
5. Check `agent/kpi_logger.py` — what metrics are tracked?
6. Read `learnings.jsonl` — are there past examples of the agent skipping search?

**Expected outcome**: Confirm the vulnerability exists. Document the exact code paths that need modification for the critic loop.

---

### Gap 5: Index Noise — Incomplete SKIP_DIRS Cleanup

**Research claim**: Index contains noise from browser cache, build artifacts, node_modules. SKIP_DIRS audit was partially done but not verified.

**What to verify**:
1. Read `config.py` — what are the current `SKIP_SUBDIRS` and `HIGH_VALUE_INCLUDE_PATTERNS`?
2. Read `scanner.py` — how are skip patterns applied? Is symlink/junction detection implemented?
3. Query the index for known noise patterns:
   ```python
   cur.execute("SELECT path FROM files WHERE path LIKE '%node_modules%' OR path LIKE '%.git%' OR path LIKE '%__pycache__%' OR path LIKE '%Thumbs.db%' OR path LIKE '%.venv%' OR path LIKE '%dist/%' OR path LIKE '%build/%'")
   noise_files = cur.fetchall()
   print(f"Found {len(noise_files)} noise files in index")
   ```
4. How many noise files actually exist in the current index?
5. Check the most recent scan — was it a full scan or incremental?

**Expected outcome**: Quantify actual noise in the index. List the specific SKIP_DIRS patterns that need to be added.

---

### Gap 6: Reranker Identity Unknown

**Research claim**: FlagEmbedding was removed (Python 3.14). An alternative reranker is in use but identity/functionality is unverified.

**What to verify**:
1. Read `search.py` — find the reranking code. What library is imported? What model is loaded?
2. Check `check_deps.py` — is the reranker dependency validated?
3. Check `config.py` — what is `ENABLE_RERANKING` set to? What model name is configured?
4. Run `pip list | findstr -i "cross rerank flag sentence"` — what reranking libraries are installed?
5. Test the reranker:
   ```python
   # Try the actual reranker code path with a sample query
   # Log top-5 results before rerank and after rerank
   # Does the order change? If not, reranker is broken or returning identity
   ```

**Expected outcome**: Identify the actual reranker in use. Confirm it's producing meaningful reordering.

---

### Gap 7: Dynamic Embedding Batch Size

**Research claim**: Static batch size of 8 is suboptimal. FP16 reduces VRAM by 50%, enabling larger batches. Dynamic sizing (try 32 → OOM → halve) is recommended.

**What to verify**:
1. Read `embedder.py` — what's the current batch size? Is there any dynamic sizing logic?
2. Is FP16 currently enabled? Check for `torch_dtype`, `.half()`, or `torch.float16` references
3. Test current VRAM usage during embedding:
   ```python
   import torch
   print(f"VRAM allocated: {torch.cuda.memory_allocated() / 1e9:.2f} GB")
   print(f"VRAM reserved: {torch.cuda.memory_reserved() / 1e9:.2f} GB")
   ```
4. What's the model's current dtype?
   ```python
   from sentence_transformers import SentenceTransformer
   model = SentenceTransformer("BAAI/bge-m3", device="cuda")
   print(next(model.parameters()).dtype)
   ```
5. Test batch size scaling: try encoding 16, 24, 32, 48 chunks at once. At what point does OOM occur?

**Expected outcome**: Confirm current batch size and dtype. Measure the actual VRAM headroom. Determine the optimal batch size.

---

## Implementation Plan to Validate

The file `docs/PHASE05_IMPLEMENTATION_PLAN.md` contains a 6-phase implementation plan with dependency graph, file modification list, and risk register.

**What to verify**:
1. Read the plan file
2. Cross-reference each proposed file modification against the actual code — are the right files identified?
3. Are the dependencies correct? (e.g., does #4 Critic actually need #1 gemma3:4b switch?)
4. Are the effort estimates realistic given the actual code complexity?
5. Are there missing risks or missing files that need modification?
6. Is the force rebuild step (`scan --rebuild`) actually sufficient to apply all changes?

---

## Additional Diagnostics to Run

### 1. Dependency Audit
```bash
cd C:\AI_STATION\filemind
pip list
python check_deps.py
python -c "import qdrant_client; print('qdrant-client OK')"
python -c "import sentence_transformers; print('sentence-transformers OK')"
python -c "import torch; print(f'torch {torch.__version__}, CUDA: {torch.cuda.is_available()}')"
python -c "import smolagents; print('smolagents OK')"
```

### 2. Index Health Check
```bash
cd C:\AI_STATION\filemind
python -m filemind run.py stats
python -m filemind run.py health
```

### 3. Git Status
```bash
cd C:\AI_STATION\filemind
git log --oneline -10
git status
git diff --stat
```

### 4. Test Suite
```bash
cd C:\AI_STATION\filemind
python -m pytest tests/ -v
```

### 5. End-to-End Search Test
```bash
cd C:\AI_STATION\filemind
python -m filemind run.py search "semantic file search configuration"
```

---

## Output Requirements

Produce a comprehensive audit report with the following sections:

### Section 1: Environment Verification
- Confirmed hardware specs (GPU, CPU, RAM)
- Confirmed Python version
- Confirmed installed Ollama models
- Confirmed dependency status (what's installed, what's missing)

### Section 2: Gap-by-Gap Validation
For each of the 7 gaps:
- **Status**: ✅ Confirmed / ❌ Refuted / ⚠️ Partially confirmed
- **Evidence**: What you found in the code/data
- **Discrepancies**: Where reality differs from the research claims
- **Actionable findings**: What needs to change in the implementation plan

### Section 3: Codebase Health
- Test results (pass/fail counts)
- Git status (clean? uncommitted changes?)
- Index health (file count, chunk count, error rate)
- Search quality (run 3 sample queries, evaluate result relevance)

### Section 4: Implementation Plan Review
- Are the 6 phases in the right order?
- Are dependencies accurate?
- Are effort estimates realistic?
- Missing files or risks?
- Recommended changes to the plan

### Section 5: Priority Recommendations
Based on actual findings, rank the 7 gaps by:
1. **Severity** (how much does this degrade user experience?)
2. **Fix complexity** (how hard is it to fix?)
3. **Dependencies** (does fixing this unblock other fixes?)

Produce a revised implementation order with justification.

### Section 6: Definitive Next Actions
A numbered list of concrete actions to take, each with:
- What file to read/modify/create
- What command to run
- What output to expect
- What constitutes success/failure

---

## Constraints

- **Do NOT modify any files** during this audit. Read-only analysis.
- **Do NOT delete or modify the index** at `C:\AI_STATION\.index\`.
- **Do NOT run `scan --rebuild`** — that's a production action for the implementation phase.
- **Do run diagnostic queries** against SQLite, Qdrant, and Ollama — these are read-only.
- **Do run the test suite** and health checks.
- **Preserve all evidence** — include code snippets, query results, and command outputs in your report.

---

## Reference Documents

These files in the project contain relevant context:
- `docs/PHASE05_IMPLEMENTATION_PLAN.md` — The implementation plan to validate
- `docs/RESEARCH_PROMPT_PHASE05_GAPS.md` — Original research prompt with gap descriptions
- `docs/SESSION_LEARNING_EXTRACT_20260413.md` — Session findings from architecture review
- `docs/SESSION_LEARNING_EXTRACT_20260408.md` — Earlier session findings
- `SYSTEM_NOTES.md` — Numbered system-wide notes (items 1-112)
- `docs/LOCAL_MODEL_REGISTRY.md` — Ollama model specifications
- `docs/HIERARCHICAL_SCANNING_ARCHITECTURE.md` — Scanning design (DO NOT re-research)
- `docs/RESEARCH_PAPER_GROUNDING_FRAMEWORK.md` — Agent grounding research
- `docs/RESEARCH_PAPER_GEMMA4_RELIABILITY.md` — gemma4-e4b reliability analysis
