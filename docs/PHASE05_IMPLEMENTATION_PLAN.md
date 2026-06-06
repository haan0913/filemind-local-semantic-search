# Phase 0.5 Implementation Plan — Final

## Research Status: COMPLETE ✅

All 7 gaps have been resolved through two rounds of targeted research. All four flagged uncertainties have been definitively answered with Python 3.14-compatible, production-tested implementations.

---

## Implementation Order

### 1. Switch Classifier to gemma3:4b (Gap 3) — Small (1-2h)
**Why first**: Frees 5.2GB VRAM, unblocks larger embedding batches downstream.
- `config.py`: `CLASSIFICATION_MODEL = "gemma3:4b"`
- Verify JSON schema format works (already confirmed in testing)
- Keep gemma4-e4b-json as fallback
- **Validation**: Run classification on 10 unknown files, verify JSON output parses

### 2. Enable FP16 + Dynamic Batch Sizing (Gap 7) — Small (1-2h)
**Why second**: Compounds VRAM savings from #1, maximizes indexing throughput.
- Load BGE-M3 with `torch_dtype=torch.float16` + `model.half()`
- Verify base model + dense head both FP16 via assert
- Implement dynamic batch sizing: try 32 → catch OOM → halve → cache working size
- FP16→FP32 fallback for edge-case OOM batches
- **Validation**: Compare FP16 vs FP32 embeddings on 50 files (cosine similarity > 0.99)

### 3. Implement BM25 Index + RRF Hybrid Search (Gap 1) — Medium (4-6h)
**Why third**: Restores the other half of hybrid search. Depends on clean chunk pipeline from #1-2.
- New module: `bm25_index.py` — `BM25HybridIndex` class using `rank_bm25`
- Smart tokenizer: `tokenize_for_bm25(text, file_ext)` — regex-based, preserves code identifiers
- Index builder: processes chunks during embedding pipeline, persists to disk
- RRF fusion: `rrf_fusion(bm25_results, qdrant_results, k=60)` — rank-based, not score-based
- Search integration: hybrid query path returns fused results
- **Validation**: Search "error log crash" — verify BM25 catches exact keywords that dense misses

### 4. Deploy Hybrid Critic for Agent Grounding (Gap 4) — Medium (4-6h)
**Why fourth**: Requires gemma3:4b from #1. Locks agent reliability.
- New module: `critic.py` — `hybrid_grounding_check(answer, evidence)`
- Step 1: Regex extraction of claimed file paths → deterministic match against evidence
- Step 2: LLM semantic check (gemma3:4b, temperature=0.0, forced-choice 3 labels)
- Step 3: Rule-based fallback if LLM output malformed
- Agent integration: wrap `_validate_answer()` with critic check
- System prompt update: add explicit refusal template for empty search results
- **Validation**: 50-sample evaluation — Precision >= 0.85, FPR <= 0.10

### 5. Diagnostic Audit + Index Noise Cleanup (Gap 2 + 5) — Small (2-3h)
**Why fifth**: Independent of other changes. Cleans data quality.
- Audit script: enumerate indexed files by extension, count chunkable vs non-chunkable
- Expand SKIP_SUBDIRS: add `/dist/`, `/build/`, `/out/`, `/node_modules/`, `/.venv/`, `/.git/`, `.idea/`, `.vscode/`, `Thumbs.db`, `.DS_Store`
- Verification script: re-scan with new patterns → query DB for noise pattern matches → report
- Tiered chunking: Tier 1 (smart chunking for code/docs/config), Tier 2 (`--deep-scan` flag for everything else)
- **Validation**: Re-scan produces zero files matching noise patterns

### 6. Reranker Verification (Gap 6) — Trivial (<1h)
**Why last**: Independent, quick check.
- Verify current reranker identity — check which library is actually imported
- If broken/unknown: switch to `sentence_transformers.CrossEncoder("BAAI/bge-reranker-v2-m3")`
- Add logging: log top-5 results before/after rerank to verify reordering occurs
- **Validation**: Search with reranking enabled — confirm result order changes vs. no-rerank baseline

---

## Post-Implementation: Force Rebuild
After all 6 items:
```bash
python -m filemind run.py scan --rebuild
```
This will:
- Re-index all files with clean SKIP_DIRS patterns
- Generate chunks with smart chunking (Tier 1 only)
- Build BM25 index alongside Qdrant dense vectors
- Embed with FP16 + optimized batch size
- Classify with gemma3:4b
- Result: full chunk coverage, hybrid search restored, clean index

---

## Dependencies Graph

```
#1 gemma3:4b switch ──→ #2 FP16 batch sizing ──→ #3 BM25 hybrid
                                      │
                                      └──→ #4 Critic (needs gemma3:4b)

#5 Index cleanup ──→ (independent, can run parallel to #1-4)

#6 Reranker check ──→ (independent, trivial)

All ──→ Force rebuild ──→ Validation tests
```

---

## Files to Create/Modify

| File | Action | Scope |
|------|--------|-------|
| `config.py` | Modify | CLASSIFICATION_MODEL, new BM25 config |
| `embedder.py` | Modify | FP16 loading, dynamic batch sizing |
| `bm25_index.py` | **Create** | BM25HybridIndex class, smart tokenizer |
| `search.py` | Modify | RRF fusion integration, hybrid query path |
| `agent/critic.py` | **Create** | Hybrid grounding check |
| `agent/run.py` | Modify | Integrate critic into validation loop |
| `classifier.py` | Modify | Verify gemma3:4b JSON schema path |
| `scanner.py` | Modify | Expand SKIP_SUBDIRS patterns |
| `nightly.py` | Modify | BM25 indexing step, tiered chunking |
| `audit_index.py` | **Create** | Diagnostic audit script |
| `verify_noise.py` | **Create** | Index noise verification script |

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| gemma3:4b classification accuracy lower than gemma4 | Low | Medium | Keep gemma4-e4b-json as fallback, compare on 50 samples |
| FP16 numerical instability on edge-case chunks | Very Low | Low | FP16→FP32 fallback pattern, assert verification |
| BM25 tokenizer misses code patterns | Low | Medium | Regex tested against `.py`, `.json`, `.yaml` samples |
| Critic false positives (valid answers flagged as hallucinated) | Medium | High | Rule-based fallback + manual 50-sample eval before deploy |
| Force rebuild takes too long (564s previous) | Medium | Low | Acceptable one-time cost; incremental re-indexing after |
