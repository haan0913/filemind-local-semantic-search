# Research Prompt 1: Chunking Strategy for Heterogeneous File Search

**Priority:** HIGH — force multiplier for all search quality  
**Date:** 2026-04-08  
**Status:** Ready for deep research agent

---

## Context

We have a local semantic file search engine (FileMind) running on Windows 11 with:
- **Qdrant** vector store (local mode, serverless)
- **BGE-M3** embeddings (via sentence-transformers, CUDA on RTX 3080 Ti 12GB)
- **~3,400 files** indexed (mix of code, docs, configs, JSON, YAML, PDFs, logs)
- **Current chunking:** Fixed-size text splitting at 2,048 tokens with 256 overlap
- **Content extraction:** Only first 50,000 characters stored per file (500-char summary for catalog, full content for Qdrant chunks)

## The Problem

Our naive chunking treats all files the same. A 50-line Python file and a 200-page PDF both get split at 2,048-token boundaries regardless of structure. This causes:
- Code files: Functions split mid-body, imports separated from usage
- Config files: JSON/YAML broken at arbitrary points
- Docs: Section headers disconnected from their content
- Short files: Get only 1 chunk, losing all context

We need file-type-aware chunking that respects logical boundaries.

## What We've Already Tried
- Extension-specific chunk sizes (`.py`: 1000, `.md`: 800, `.json`: 1200 tokens) — helps marginally but still splits at arbitrary boundaries
- Fixed 2,048 tokens with 256 overlap — baseline, functional but low quality
- File-level embedding (one vector per file) — too coarse for search within files

## Constraints
- **OS:** Windows 11
- **Python:** 3.14
- **GPU:** RTX 3080 Ti (12GB VRAM) — embedding model uses ~2.5GB
- **RAM:** 32GB available
- **Scale:** 3,400 files now, target 50,000+
- **Latency budget:** Chunking happens during indexing (offline), so speed is secondary to quality
- **Dependencies:** Must work with sentence-transformers (PyTorch-based), no C compilation on Windows

## Specific Questions to Answer

1. **What are proven chunking strategies for code files?** (AST-aware, function-level, class-level)
2. **What works for config files (JSON, YAML, TOML)?** (key-level? section-level? full-file?)
3. **What works for documentation (Markdown, RST, PDF)?** (section headers? paragraphs? semantic boundaries?)
4. **Is there a unified chunking library that handles all these types?** (LangChain's splitters? LlamaIndex? Something else?)
5. **What chunk sizes do production semantic search systems actually use at 5K-50K file scale?**
6. **Does overlapping chunks help or hurt at our scale?** (We currently use 256 token overlap)
7. **Should small files (< chunk size) be embedded as one chunk or still split?**

## Expected Output

A structured answer covering:
1. **Recommended strategy per file type** (code, config, docs, data, media)
2. **Specific library recommendations** (with install commands, Python 3.14 compatibility)
3. **Chunk size recommendations** with reasoning
4. **Overlap strategy** (how much, when to use it, when to skip it)
5. **Implementation sketch** — Python code showing how to integrate with our existing `chunker.py`
6. **Trade-off analysis** — what we gain vs what we lose vs current approach
7. **Fallback plan** — if the recommended approach fails, what's the next-best option?

**OUTPUT FORMAT:** Save all findings as a `.md` file at `C:\AI_STATION\filemind\docs\RESEARCH_FINDINGS_YYYYMMDD_CHUNKING.md` so Qwen can read it directly in the next session.

## Decision Criteria

We'll consider the research actionable if it provides:
- At least one concrete library recommendation that works on Windows + Python 3.14
- Specific chunk size numbers (not just "it depends")
- Implementation code or pseudocode we can adapt
- A clear fallback path that doesn't break existing functionality

---

## Experimental + Reliable Backup Plan

**Experimental path:** AST-aware chunking for code, structure-aware for configs, semantic boundary chunking for docs  
**Reliable backup:** Current fixed-size chunking with extension-specific sizes (already working)  
**Switch mechanism:** `config.SMART_CHUNKING = True/False` in config.py  
**Verification test:** Search "FileMind configuration scan roots" — should return `config.py` at rank 1 with relevant snippet, not split mid-function
