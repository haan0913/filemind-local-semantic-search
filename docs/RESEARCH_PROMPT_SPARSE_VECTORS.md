# Research Prompt 2: BGE-M3 Sparse Vector Extraction on Python 3.14 / Windows

**Priority:** HIGH — half of hybrid search is dead without sparse vectors  
**Date:** 2026-04-08  
**Status:** Ready for deep research agent

---

## Context

We have a local semantic file search engine (FileMind) running on Windows 11 with:
- **Qdrant** vector store (local mode, serverless) with hybrid search: `Fusion.RRF` of dense + sparse vectors
- **BGE-M3** embeddings — a model designed for dense + sparse (lexical) + multi-lingual retrieval
- **sentence-transformers** library for loading BGE-M3 (the only library that works on Python 3.14 / Windows)
- **RTX 3080 Ti** (12GB VRAM), **Python 3.14**, **CUDA 13.2**

## The Problem

BGE-M3 natively produces **three types of output**:
1. **Dense vectors** (1024 dims) — working perfectly via sentence-transformers
2. **Sparse/lexical weights** (token_id → weight dict, ~30-95 tokens per chunk) — **BROKEN** — sentence-transformers returns empty dicts `{}`
3. **Multi-lingual support** — not needed for our use case

**Impact:** Our hybrid search in Qdrant is effectively dense-only. The sparse vector leg of the RRF fusion receives empty dicts, meaning exact-term matching, technical keyword recall, and specialized terminology search is significantly degraded. We lose ~30-50% retrieval quality on technical queries.

**Why this matters:** BGE-M3's sparse weights are its killer feature over standard embedding models. They capture exact term importance (like BM25) in a learned way. Without them, we might as well use any standard dense embedding model — BGE-M3's advantage is wasted.

## What We've Already Tried

1. **sentence-transformers with `return_sparse=True`** — Returns empty dicts `{}`. This is a known limitation — sentence-transformers only wraps the dense embedding head of BGE-M3, not the sparse lexical head.

2. **FlagEmbedding library** — Does NOT work on Python 3.14 / Windows due to C compilation failures (`ir-datasets` dependency requires `zlib.h` which doesn't compile on Windows Python 3.14).

3. **Direct BGE-M3 via transformers** — Attempted but the BGE-M3 model card uses custom architecture code that doesn't integrate cleanly with the standard transformers pipeline for sparse output.

4. **Ollama nomic-embed-text** — Only produces dense vectors, not sparse.

## What We Know

1. **BGE-M3's sparse head exists** — The model has three heads: `colbert_linear`, `sparse_linear`, and the dense head. The sparse head is trained with the same architecture as SPLADE (Sparse Lexical and Expansion).

2. **FlagEmbedding works on Linux** — The official BGE-M3 library correctly extracts sparse vectors. The issue is purely a deployment/compatibility problem on Windows Python 3.14.

3. **Alternative sparse extraction methods exist** — There may be ways to extract sparse weights directly from the model's `sparse_linear` head using raw PyTorch, without needing the full FlagEmbedding pipeline.

4. **SPLADE-style sparse extraction** — The sparse weights are essentially a learned BM25. The model's `sparse_linear` head takes the last hidden state and produces a vocabulary-sized sparse vector with weights for each token.

## Constraints

- **OS:** Windows 11 (non-negotiable)
- **Python:** 3.14 (non-negotiable — this is what our system runs)
- **No C compilation** — Any library requiring native extension compilation will fail
- **GPU:** RTX 3080 Ti (12GB VRAM) — sparse extraction must not require more than ~2.5GB additional VRAM
- **Must work offline** — No cloud API calls for extraction
- **Batch processing** — Must handle batch encoding of multiple text chunks (we embed 8 files at a time, each with multiple chunks)
- **Output format:** Dict mapping token string → float weight (compatible with Qdrant sparse vector format)

## Specific Questions to Answer

1. **Can we extract BGE-M3 sparse weights directly via PyTorch?** — The model has a `sparse_linear` head. Can we load the model with `transformers.AutoModel`, pass text through it, and manually apply the sparse head? What's the exact code to do this?

2. **Is there a pre-compiled Windows wheel for FlagEmbedding?** — Has anyone built a `manylinux` or `win_amd64` wheel that bypasses the C compilation requirement?

3. **Can we use ONNX Runtime for BGE-M3 sparse extraction?** — If the model is exported to ONNX, ONNX Runtime has pre-compiled Windows binaries. Can we run the sparse head through ONNX?

4. **Are there alternative libraries that provide BGE-M3 sparse extraction without C deps?** — Any pure-Python or pre-compiled library that can extract BGE-M3 sparse weights?

5. **Can we approximate sparse weights from the dense model?** — If we can't get the true sparse head, is there a method to derive approximate lexical weights from the dense embeddings (e.g., via attention weights, gradient-based saliency, or other techniques)?

6. **Is there a way to run FlagEmbedding in a minimal WSL2 subprocess?** — Could we install FlagEmbedding in WSL2, run sparse extraction there, and pass results back to Python on Windows? What's the overhead?

7. **What's the trade-off analysis: true sparse vs. approximated sparse vs. pure dense?** — How much does retrieval quality actually improve with sparse vectors at our scale (3,400 files)? Is the effort worth the gain?

## Expected Output

A structured answer covering:

1. **Primary solution** — The most reliable, working method to extract BGE-M3 sparse vectors on Windows Python 3.14, with exact code
2. **Fallback options** — If primary doesn't work, ranked alternatives
3. **Installation commands** — Exact pip install or download commands
4. **Integration code** — Python code showing how to integrate with our existing `embedder.py`, maintaining the same interface (`return_sparse=True`)
5. **Performance impact** — VRAM usage, latency per batch, comparison to current dense-only timing
6. **Trade-off analysis** — How much retrieval quality improves with sparse vs. without (with reasoning)
7. **If no working solution exists** — Clear statement of what's possible vs. impossible, with a recommended plan B (e.g., switch to a different embedding model that provides sparse output on Windows, or add standalone BM25 as the sparse leg)

**OUTPUT FORMAT:** Save all findings as a `.md` file at `C:\AI_STATION\filemind\docs\RESEARCH_FINDINGS_YYYYMMDD_SPARSE_VECTORS.md` so Qwen can read it directly in the next session.

## Decision Criteria

We'll consider the research actionable if it provides:
- At least one working method that extracts non-empty sparse dicts from BGE-M3 on Windows Python 3.14
- Exact Python code we can copy-paste into `embedder.py`
- No C compilation requirements
- Clear fallback plan if BGE-M3 sparse extraction proves impossible on our platform

---

## Experimental + Reliable Backup Plan

**Experimental path:** Extract true BGE-M3 sparse lexical weights via one of the methods above  
**Reliable backup:** Keep current dense-only search (working, functional) AND/OR add standalone BM25 as the sparse leg of hybrid search  
**Switch mechanism:** `config.ENABLE_SPARSE_VECTORS = True/False` in config.py  
**Verification test:** Search "API key authentication" and "FileMind configuration scan roots" — with sparse vectors, exact technical terms should boost relevant results. Compare RRF scores with and without sparse leg.

### Plan B: Standalone BM25 as Sparse Replacement

If BGE-M3 sparse extraction proves impossible, the fallback is to add a standalone BM25 index (via `rank-bm25` or `quickbm25` — both pure Python, no C deps) as the sparse leg of hybrid search. This gives us:
- Dense: BGE-M3 semantic vectors (current)
- Sparse: BM25 lexical matching (new, replaces BGE-M3 sparse)
- Fusion: RRF (current)

This is a reliable, well-understood approach that works on any platform.
