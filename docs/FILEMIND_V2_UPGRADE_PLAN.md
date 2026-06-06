# FileMind v2 Upgrade Plan

**Created:** 2026-04-08  
**Last Updated:** 2026-04-16 (Clean rebuild verified; sparse-path review and benchmark gate added)  
**Status:** Rebuild integrity fixed and verified; retrieval path review active  
**Priority:** Retrieval correctness → zero-downtime rebuilds → startup UX

---

## ADDENDUM STATUS (2026-04-16)

**This addendum supersedes the older 2026-04-08 assumptions below where they conflict.**

**Verified current state:**
- **2,909 effective files** on disk and in the catalog
- **23,121 chunks** in shared Qdrant with **23,121 BM25 chunks**
- **Clean `scan --rebuild`** now resets and repopulates the live FileMind collection coherently
- **`run.py verify`** now reports real scan scope, chunk parity, and the active vector target
- **Offline Hugging Face loading** is automatic when `BAAI/bge-m3` is already cached locally

**Critical retrieval caveat:**
- **Dense vectors are live; BGE lexical weights are not.** The current `sentence-transformers` embedder path returns empty `lexical_weights` for BGE-M3 in this stack, which means Qdrant's sparse prefetch branch is effectively skipped today.
- **Search is still functional** because BM25 is built from the same chunk corpus and fused into the final ranking path, but this is not the same as having true BGE-M3 sparse retrieval active end to end.
- **Plan impact:** treat sparse restoration or lexical-path simplification as a first-class retrieval task, not a later polish item.

**Recommended near-term order:**
1. Decide the supported lexical path: restore true BGE sparse weights or bless BM25 as the supported lexical engine
2. Move rebuilds to an alias-backed shadow collection with verify-then-swap
3. Build the lazy-start / switchboard layer so model load cost is paid once per session
4. Only then revisit default reranking and HyDE policy

**Experimental sparse benchmark gate:**
- Before promoting the experimental FlagEmbedding backend beyond this session, run a stable-vs-experimental benchmark pass.
- Record at minimum: search quality on a fixed query set, rebuild duration, warm/cold search latency, completeness, embedding coverage, and chunk parity.
- Treat the live shared rebuild as readiness evidence, not final promotion evidence, until those KPIs are captured side by side.

**Benchmark decision (2026-04-16):**
- The medium benchmark gate is now complete. See `docs/EMBEDDING_BACKEND_EVALUATION_20260416.md`.
- Experimental `FlagEmbedding` is faster and slightly stronger without reranking, but reranked quality is mixed and the runtime story is still split across environments.
- Decision: keep `sentence_transformers` as the default supported backend, keep `flagembedding_experimental` opt-in, and treat BM25 as the supported lexical engine in the stable stack for now.
- Next implementation priority: alias-backed shadow rebuilds for shared Qdrant so future backend comparisons can verify then swap safely.

---

## POST-AUDIT STATUS (2026-04-08)

**Audit revealed: Most planned fixes were ALREADY IMPLEMENTED in the codebase.** The upgrade plan was based on outdated assumptions. Here's the real status:

**Current State:**
- **Historical baseline only.** See the 2026-04-16 addendum above for the current verified corpus size and chunk counts.
- **Qdrant** (not LanceDB) as vector store
- **BGE-M3 dense embeddings** are live via `sentence-transformers`
- **Sparse lexical weights are currently empty** in the active embedder path, so true BGE sparse retrieval is not active end to end
- **Hybrid search** currently means dense retrieval plus BM25 fusion, with optional Qdrant sparse prefetch only if lexical weights become available
- **Cross-encoder reranking** is implemented and currently enabled via `sentence-transformers` `CrossEncoder`
- **Query expansion** — HyDE via llama3 implemented, disabled by default (`HYDE_ENABLED = False`)
- **Query operators** — `type:` and `in:` parsing in `search.py`
- **RuleBasedClassifier** — implemented with extension map + directory heuristics
- **Tiered file sizes** — `TIER1_MAX_SIZE=1MB`, `TIER2_MAX_SIZE=10MB`
- **Chunk size** — `CHUNK_SIZE=2048` (up from 512), extension-specific overrides
- **Classification** — OpenRouter as primary fallback, gemma4-e4b-json local
- **Special character FTS** — Migration 3 applied (`tokenchars '-_./'`)

**What's actually broken:**
1. **Index noise:** `antigravity-browser-profile` and browser cache files polluting search results
2. **Lexical-path mismatch:** the code advertises BGE-M3 sparse/hybrid behavior, but the active embedder returns empty lexical weights
3. **Startup cost:** each fresh CLI search process still pays model-load cost
4. **Historical docs drift:** older docs still describe earlier pipeline assumptions

---

## PHASE 1: INDEX QUALITY (Immediate — This Session)

### Fix 1: Remove Browser/Agent Noise from Index ✅ DONE

**Problem:** `antigravity-browser-profile` and browser cache files dominate search results.

**Fix Applied:** Added `"antigravity-browser-profile"` to `SKIP_DIRS` in `config.py`.

**Next:** Re-run scan to clean index. Delete existing noise chunks from Qdrant.

---

### Fix 2: Expand Chunk Coverage (405 → all eligible files)

**Problem:** Only 405 chunks for 3,838 files. Most files have metadata but no vector chunks.

**Root Cause:** Chunking/embedding pipeline not running for all indexed files. Likely:
- Scanner indexes file metadata but skips chunking for certain file types
- Embedding step fails silently for some files
- Previous scans didn't run the full pipeline (metadata-only scan)

**Investigation needed:** Check `scanner.py`, `nightly.py`, and `run.py` to trace why chunks aren't being created for most files.

**Target:** At least 2,000+ chunks (one per eligible file minimum, more for large files).

---

### Fix 3: Tune Scan Roots — Remove Low-Value Directories

**Problem:** Scan roots expanded to include `.ollama`, `.gemini`, `.cline`, `.claude`, `.agents` — these contain mostly model binaries, caches, and framework internals. Not user content.

**Recommendation:**
- Keep: `AI_STATION`, `.kimi`, Obsidian Vault, `pc-focus` (user content)
- Remove from SCAN_ROOTS: `.ollama`, `.gemini`, `.node-llama-cpp`, `.cline`, `.claude`, `.agents` (framework internals)
- Or: Keep them but add more aggressive noise filtering (e.g., skip `*_store/`, `model_store/`, `extensions_crx_cache/`)

**Decision needed from user.**

---

### Fix 4: Enable Reranking for Better Result Quality

**Problem:** `ENABLE_RERANKING = False` in config. Hybrid RRF scores alone don't understand query-document relevance.

**Fix:** Set `ENABLE_RERANKING = True`. `FlagReranker` with `BAAI/bge-reranker-v2-m3` is implemented and ready.

**Impact:** ~15-25% accuracy improvement on technical queries.
**Cost:** ~200ms additional latency per search (runs on CPU).

---

### Fix 5: Enable HyDE Query Expansion

**Problem:** `HYDE_ENABLED = False` in config. Query expansion could improve recall on conceptual searches.

**Fix:** Set `HYDE_ENABLED = True`. Uses llama3 (fast, 4.7GB) to generate hypothetical document.

**Impact:** Better recall for abstract queries like "file management system architecture".
**Cost:** ~1-2s additional latency (Ollama llama3 inference).

---

## PHASE 2: SEARCH QUALITY TUNING (After Phase 1)

### Upgrade 6: Improve Search Result Relevance ✅ PARTIALLY DONE

**Current State:** Qdrant native hybrid with `Fusion.RRF` is implemented. Cross-encoder reranker (`FlagReranker`) is implemented but **disabled by default** (`ENABLE_RERANKING = False`).

**Issue:** Search results return browser profile noise instead of relevant FileMind files. This is an index quality problem, not a search algorithm problem.

**Action Items:**
1. ✅ Fix index noise first (Phase 1) — remove browser profiles
2. Enable `ENABLE_RERANKING = True` after index is clean
3. Test reranking latency impact (BAAI/bge-reranker-v2-m3 on CPU)

---

### Upgrade 7: HyDE Query Expansion ✅ IMPLEMENTED, DISABLED

**Current State:** `_hyde_expand()` method exists in `search.py`, uses llama3 via Ollama. Disabled by default (`HYDE_ENABLED = False`, `HYDE_WEIGHT = 0.5`).

**Action:** Enable after index is clean. Test on abstract queries vs direct search.

---

### Upgrade 8: Chunk Size Tuning ✅ DONE

**Current State:** `CHUNK_SIZE = 2048` (already upgraded from 512), with extension-specific overrides:
- `.py`, `.js`: 1000 tokens
- `.md`: 800 tokens  
- `.json`: 1200 tokens
- `.txt`: 500 tokens
- Default: 2048 tokens

**Assessment:** 2048 is a good sweet spot. BGE-M3 supports 8192 but 2048 gives better granularity for search results. No change needed.

---

### Upgrade 9: Large File Support ✅ PARTIALLY IMPLEMENTED

**Current State:** `TIER1_MAX_SIZE = 1MB`, `TIER2_MAX_SIZE = 10MB` in config. `MAX_FILE_SIZE = 500KB` for standard content extraction.

**Issue:** Files 500KB-10MB are indexed as metadata but may not be chunked/embedded (same root cause as Fix 2 — chunking pipeline not running for all files).

**Action:** Fix chunking pipeline first (Phase 1, Fix 2), then large file support comes for free.

---

### Upgrade 10: Real-Time File Watching

**Status:** `watchdog` v6.0 is installed. No `watcher.py` module exists yet.

**Action:** Implement after index quality is solid.

---

## PHASE 3: ADVANCED FEATURES (After Phase 1-2)

### Upgrade 11: Terminal UI

**Current:** CLI only (`python run.py search "query"`). Rich is installed.

**Target:** Rich dashboard with search interface, results display, category filters.

---

### Upgrade 12: Multi-Model Swarm

**Current:** Single gemma4-e4b for agent + classification. llama3 available as fallback.

**Planned:** Router (phi4:mini) → Worker (gemma3:4b) → Critic (qwen2.5:3b) pipeline.

**Action:** Install new models after current pipeline is stable.

---

### Upgrade 13: Meta-Learning Loop

**Concept:** Weekly review of session extracts → prompt improvements → user approves → deploy with version tag.

**Action:** After 10+ session extracts accumulated.

---

## IMPLEMENTATION ORDER

### Right Now (This Session)
1. ✅ Add antigravity-browser-profile to SKIP_DIRS
2. ⏳ Decide on scan root cleanup (user decision needed)
3. ⏳ Investigate why only 405 chunks for 3,838 files
4. ⏳ Re-scan with clean config to expand chunk coverage

### Next Session
5. Enable reranking (`ENABLE_RERANKING = True`)
6. Enable HyDE for abstract queries
7. Test search quality on real queries
8. Install gemma3:4b if needed for better tool-calling

### Later
9. Terminal UI (Rich dashboard)
10. File watcher (watchdog)
11. Multi-model swarm
12. Meta-learning loop

---

## DEPENDENCIES MATRIX

| Upgrade | Depends On | Status |
|---|---|---|
| Fix 1 (Noise removal) | None | ✅ DONE |
| Fix 2 (Chunk coverage) | Investigate scanner pipeline | ⏳ NEXT |
| Fix 3 (Scan roots) | User decision | ⏳ WAITING |
| Fix 4 (Reranking) | Fix 1, Fix 2 | Ready to enable |
| Fix 5 (HyDE) | Fix 1, Fix 2 | Ready to enable |
| Upgrade 8 (Chunks) | Already done | ✅ DONE |
| Upgrade 9 (Large files) | Fix 2 | Blocked |
| Upgrade 10 (Watcher) | None | Planned |
| Upgrade 11 (TUI) | None | Planned |
| Upgrade 12 (Swarm) | None | Planned |
| Upgrade 13 (Meta) | 10+ session extracts | Planned |

---

## SUCCESS CRITERIA

### Phase 1 (Index Quality) ✅
- [ ] Browser profile noise removed from index
- [ ] Chunk count increases from 405 to 2,000+
- [ ] Search for "FileMind configuration" returns `config.py`, not browser files

### Phase 2 (Search Tuning) ✅
- [ ] Reranking enabled and tested
- [ ] HyDE enabled and tested on abstract queries
- [ ] 80%+ of test queries return relevant results in top 5

### Phase 3 (Advanced) ✅
- [ ] Terminal UI provides intuitive search experience
- [ ] Multi-model swarm routes queries correctly 90%+ of time
- [ ] Meta-learning loop suggests 2+ improvements/week

---

*This plan was AUDITED against the actual codebase on 2026-04-08. Most originally planned fixes were already implemented. Current focus: index quality, not algorithm changes.*
