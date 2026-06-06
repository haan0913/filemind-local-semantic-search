# Session Learning Extract — 2026-04-08 (Ollama Documentation & Consolidation)

**Session Date:** 2026-04-08  
**Session Type:** Documentation & Planning  
**Extracted By:** Qwen Code

---

## 1. SESSION GOALS

1. Document all Ollama configuration and local AI models to avoid re-researching in future sessions
2. Consolidate local model management information into AI_CENTER (planned directory structure)
3. Understand what caused the pipeline crash during previous orchestration
4. Prepare for FileMind v2 implementation (8 critical fixes + capability upgrades)

---

## 2. ENVIRONMENT

| Property | Value |
|---|---|
| **OS** | Windows 11 (win32) |
| **GPU** | NVIDIA GeForce RTX 3080 Ti (12GB VRAM, CUDA 8.6) |
| **CPU** | 16 cores / 32 threads |
| **RAM** | 32GB (20.5GB free at session start) |
| **Ollama Version** | 0.20.3 |
| **Ollama Path** | `C:\Users\amirk\AppData\Local\Programs\Ollama\ollama.exe` |
| **API Endpoint** | `http://127.0.0.1:11434` |
| **Models Storage** | `C:\Users\amirk\.ollama\models` |
| **Python** | Installed (used by FileMind) |
| **LanceDB** | 0.30.2 |
| **Qdrant** | 405 chunks indexed |

---

## 3. DISCOVERIES

### Ollama Installation

- **Ollama is NOT in PATH** — must use full path or API calls
- **Executable location:** `C:\Users\amirk\AppData\Local\Programs\Ollama\ollama.exe`
- **Server starts via GUI app** — check system tray, not CLI
- **API is fully functional** — all models accessible via `http://localhost:11434`

### Installed Models (6 Total)

1. **gemma4-e4b** (7.5GB, Q8_0) — Primary agent, 8.7GB VRAM loaded
2. **gemma4-e4b-json** (7.5GB, Q8_0) — Same + JSON system prompt
3. **gemma4-26b** (12.5GB, Q3_K_M) — Barely fits 12GB VRAM, spills to RAM
4. **llama3.2** (2.0GB, Q4_K_M) — Fast fallback
5. **llama3** (4.7GB, Q4_0) — Legacy
6. **nomic-embed-text** (274MB, F16) — Embeddings

### gemma4-e4b Performance

- **Load time:** ~4.5 seconds
- **First request:** ~6.8 seconds (includes model load)
- **Subsequent requests:** ~1.4-1.7 seconds
- **Layer offloading:** 43/43 layers to GPU (full offload)
- **KV cache:** 4096 context (auto-determined by VRAM)
- **VRAM breakdown:** 7.6GB model + 224MB KV cache + 176MB compute graph = 8.7GB total

### Critical API Findings

- **`/api/chat` works** for JSON-constrained output with `format` parameter
- **`/api/generate` does NOT work** for JSON format constraints on gemma4
- **Bug #15260:** `think=false` breaks format constraint on gemma4 — do NOT set it
- **Batch size limit:** Max 5-8 files per classification request (larger causes JSON failures)

### FileMind Index Status

- **3,282 files indexed**
- **405 Qdrant chunks**
- **Scan roots:** `C:\AI_STATION`, `C:\Users\amirk\.kimi`
- **Max file size:** 500KB (larger files skipped)
- **Content stored per file:** 50KB
- **Chunk size:** 512 tokens (BGE-M3 supports 8192 — wasting 94%)

### 8 Critical Architectural Weaknesses Identified

1. **FTS5 only indexes 500 chars** — content beyond first 3 sentences invisible to keyword search
2. **Sparse vectors generated but never used** — `return_sparse=False` in search
3. **Classification fragile** — 94.8% accuracy, Ollama-dependent
4. **`count()` loads everything to RAM** — `to_pandas()` instead of `count_rows()`
5. **FTS5 chokes on special characters** — hyphens, dots split tokens
6. **RRF weighting hardcoded** — 2x semantic, not tunable per query
7. **No re-ranking** — RRF score only, no cross-encoder
8. **No query expansion** — "API key" won't find "secret", "token"

### Previous Session Crash Root Cause

**What happened:** I was orchestrating FileMind research pipeline — reading research files, analyzing code, launching deep research agents, building implementation plans.

**Why it crashed:**
1. Too many parallel agents (3+ deep research agents simultaneously)
2. Large file reads (70KB research docs) consumed context
3. Complex multi-step orchestration exceeded token budget

**How to prevent:**
- Sequence agent launches instead of parallel for deep research
- Read files selectively — don't load entire 70KB docs unless needed
- Use `Explore` agent for quick discovery, `general-purpose` for deep analysis
- Check context usage periodically and checkpoint progress

---

## 4. DECISIONS MADE

### Documentation Strategy

1. **Create LOCAL_MODEL_REGISTRY.md** — Single source of truth for Ollama config
2. **Create FILEMIND_V2_UPGRADE_PLAN.md** — Phased implementation plan for 8 fixes + upgrades
3. **Create AGENT_PLAYBOOK.md** — Model selection, prompting guidelines, known failures
4. **Store in `C:\AI_STATION\AI STAION\`** — Temporary until AI_CENTER consolidation

### FileMind v2 Plan Approval

All 8 critical fixes + 5 capability upgrades documented in upgrade plan. Implementation order:
- **Week 1:** Fixes 1-5 (critical reliability)
- **Week 2:** Upgrades 6-8 (search quality)
- **Week 3:** Upgrades 9-10, 12 (scale + UI)
- **Week 4+:** Upgrades 11, 13 (advanced features)

### Consolidation Plan

Planned AI_CENTER structure:
```
C:\AI_STATION\AI_CENTER\
├── ollama\REGISTRY.md
├── filemind\
│   ├── ARCHITECTURE.md
│   ├── KNOWN_ISSUES.md
│   ├── UPGRADE_PLAN.md
│   └── SESSION_REPORTS\
├── research\
│   ├── VECTOR_SEARCH.md
│   ├── EMBEDDING_MODELS.md
│   ├── CLASSIFICATION.md
│   └── COMPETITIVE_ANALYSIS.md
├── AGENT_PLAYBOOK.md
└── SYSTEM_NOTES.md
```

**Execution deferred** until Ollama pipeline is fully operational.

---

## 5. CHANGES MADE

### Files Created

1. **`C:\AI_STATION\AI STAION\LOCAL_MODEL_REGISTRY.md`** (16KB)
   - Complete Ollama configuration
   - Model inventory with specs
   - API usage patterns
   - Known issues and workarounds
   - Commands reference
   - Decision history

2. **`C:\AI_STATION\AI STAION\FILEMIND_V2_UPGRADE_PLAN.md`** (20KB)
   - 8 critical fixes with implementation details
   - 5 capability upgrades with architecture
   - Dependency matrix
   - Testing strategy
   - Risk assessment
   - Success criteria

3. **`C:\AI_STATION\AI STAION\AGENT_PLAYBOOK.md`** (14KB)
   - Model selection guide
   - Prompting guidelines per model
   - API patterns and templates
   - Known failure modes + workarounds
   - Multi-model swarm design
   - Performance optimization

---

## 6. COMMANDS USED

### Ollama API
```bash
# List models
curl http://localhost:11434/api/tags

# Server config (from logs)
OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_MODELS=C:\Users\amirk\.ollama\models
OLLAMA_KEEP_ALIVE=2562047h47m16.854775807s
OLLAMA_CONTEXT_LENGTH=0 (auto)
OLLAMA_NUM_PARALLEL=1
OLLAMA_VULKAN=false
```

### File Discovery
```cmd
dir C:\AI_STATION\ /b
dir "C:\AI_STATION\AI STAION" /b
dir "C:\Program Files\Ollama" /b
where /r "C:\Program Files\Ollama" ollama.exe
```

### PowerShell (for Ollama path)
```powershell
& "C:\Users\amirk\AppData\Local\Programs\Ollama\ollama.exe" list
```

---

## 7. ERRORS ENCOUNTERED

### Error 1: Ollama Command Not Found
```
'ollama' is not recognized as an internal or external command
```
**Cause:** Ollama not in PATH  
**Fix:** Use full path `C:\Users\amirk\AppData\Local\Programs\Ollama\ollama.exe` or API

### Error 2: Path with Spaces Not Working
```
'C:\Program' is not recognized as an internal or external command
```
**Cause:** Windows CMD doesn't handle spaces in paths with `cmd /c`  
**Fix:** Use PowerShell: `& 'C:\Program Files\Ollama\ollama.exe'`

### Error 3: Ollama Directory Not Found
```
File Not Found: C:\Program Files\Ollama
```
**Cause:** Ollama installed to `AppData\Local\Programs`, not `Program Files`  
**Fix:** Correct path is `C:\Users\amirk\AppData\Local\Programs\Ollama\`

---

## 8. LEARNINGS

### Technical Learnings

1. **Ollama on Windows has non-standard paths** — `AppData\Local\Programs` instead of `Program Files`
2. **`ollama` CLI not in PATH by default** — must use API or full path
3. **gemma4 JSON format constraints only work with `/api/chat`** — `/api/generate` ignores `format` parameter
4. **gemma4 VRAM usage is 8.7GB** — leaves only 1.3GB free on 12GB GPU (tight)
5. **FileMind sparse vectors are wasted** — generated but never read during search
6. **LanceDB FTS on full content is the fix** — eliminates SQLite FTS5 500-char truncation
7. **Multi-model swarm fits in 12GB VRAM** — if managed carefully (peak 10.2GB)
8. **Context window crashes happen** — too many parallel agents + large file reads = OOM

### Architectural Learnings

9. **Prompts alone are insufficient for grounding** — must use architectural constraints (code)
10. **Mandatory search-first protocol prevents hallucination** — implemented in FileMind agent code
11. **Rule-based classifier as fallback improves reliability** — from 94.8% to ~98%
12. **Hybrid search (FTS + dense + sparse) is superior to RRF** — native LanceDB support exists
13. **Cross-encoder re-ranking adds 15-25% accuracy** — MS MARCO MiniLM is tiny (90MB)

### Process Learnings

14. **Sequence deep research agents, don't parallelize** — prevents context OOM
15. **Checkpoint progress after each agent** — allows resuming after crash
16. **Read files selectively** — don't load 70KB docs unless absolutely needed
17. **Use Explore agent for quick discovery** — reserve general-purpose for deep analysis

---

## 9. DEFERRED ITEMS

1. **AI_CENTER consolidation** — Planned structure defined, execution deferred until Ollama operational
2. **gemma3:4b installation** — Recommended for better tool-calling, deferred to next session
3. **FileMind v2 implementation** — Plan complete, awaiting execution
4. **Multi-model swarm** — Architecture designed, needs model installation first
5. **Large file support** — Tiered approach planned, depends on chunk size increase
6. **Terminal UI** — Rich dashboard planned, low priority vs core fixes
7. **Meta-learning loop** — Planned for 1-3 months out, needs 50-100 session extracts

---

## 10. DEPENDENCIES

### For FileMind v2 Phase 1

| Fix | Depends On | Risk |
|---|---|---|
| Fix 1 (FTS) | None — LanceDB 0.30.2 already supports it | Low |
| Fix 2 (Sparse) | None — one-line change | Low |
| Fix 3 (Classifier) | None — additive rule-based fallback | Low |
| Fix 4 (Count) | None — one-line change | Trivial |
| Fix 5 (Variants) | None — additive query preprocessing | Low |

### For FileMind v2 Phase 2

| Upgrade | Depends On | New Dependencies |
|---|---|---|
| Upgrade 6 (Hybrid) | Fix 1, Fix 2 | `cross-encoder` package |
| Upgrade 7 (Expansion) | Fix 2 | None |
| Upgrade 8 (Chunks) | None | Requires full re-index |
| Upgrade 9 (Large files) | Upgrade 8 | `easyocr`, `faster-whisper`, `opencv-python` (Tier 3) |
| Upgrade 10 (Watcher) | None | `watchdog` (already installed) |

### For Multi-Model Swarm

| Model | Status | Action Needed |
|---|---|---|
| phi4:mini | Not installed | `ollama pull phi4:mini` |
| gemma3:4b | Not installed | `ollama pull gemma3:4b` |
| qwen2.5:3b | Not installed | `ollama pull qwen2.5:3b` |

---

## 11. SECURITY CONSIDERATIONS

1. **Ollama API is local-only** — `http://127.0.0.1:11434`, no external exposure
2. **No API keys or secrets in logs** — Ollama doesn't require authentication
3. **FileMind index contains file paths** — could reveal directory structure if exposed
4. **Classification may process sensitive files** — ensure Ollama doesn't log content (check `OLLAMA_DEBUG_LOG_REQUESTS:false`)
5. **Large file scanning** — user must opt-in to deep scan, prevent accidental indexing of sensitive data

---

## 12. PERFORMANCE METRICS

| Metric | Current Value | Notes |
|---|---|---|
| **gemma4-e4b load time** | ~4.5s | Full model load |
| **gemma4-e4b first request** | ~6.8s | Includes load |
| **gemma4-e4b subsequent** | ~1.4-1.7s | Cached model |
| **VRAM available (idle)** | 10.2GB | Out of 12GB total |
| **VRAM available (gemma4 loaded)** | ~1.3GB | Tight for other models |
| **FileMind index size** | 3,282 files | 500MB estimated |
| **Qdrant chunks** | 405 | LanceDB has full chunks |
| **Classification accuracy** | 94.8% | 3,106/3,282 classified |
| **Chunk size** | 512 tokens | Wasting 94% of BGE-M3 capacity |

---

## 13. USER INSTRUCTIONS

### From User (verbatim)

> "after the ollama stuff has been fixed document everything so you dont have to research again like this next time also wish to move and consolidate local model stuff in AI_CENTER once we get to an operational state"

> "also what happened you were orchestrating the whole pipeline then crashed"

### Interpreted Requirements

1. **Document everything comprehensively** — create reference documents that prevent re-researching
2. **Consolidate to AI_CENTER** — planned directory structure, execute when operational
3. **Explain the crash** — root cause analysis and prevention strategy

---

## 14. OPEN QUESTIONS

1. **Should we install gemma3:4b now?** — Better tool-calling reliability, 3.5GB VRAM, recommended in research
2. **What's the priority for AI_CENTER consolidation?** — User mentioned it, but timing unclear
3. **Should we execute Phase 1 fixes immediately?** — All low-risk, significant quality improvement
4. **Does user want to expand scan roots beyond AI_STATION?** — Current coverage limited to 2 directories
5. **Should we remove unused models (llama3, nomic-embed-text)?** — Free up ~5GB disk space

---

## 15. NEXT ACTIONS

### Immediate (Next Session)

1. **Test gemma4-e4b classification with JSON format fix** — Verify 95%+ reliability
2. **Implement Fix 4 (count_rows)** — One-line change, instant win
3. **Implement Fix 1 (LanceDB FTS)** — Biggest search quality improvement
4. **Verify FileMind agent search-first protocol** — Check `_run_mandatory_search()` in code

### Short-term (This Week)

5. **Install gemma3:4b** — `ollama pull gemma3:4b`
6. **Implement Fixes 2, 3, 5** — Sparse storage, classifier fallback, query variants
7. **Test hybrid search pipeline** — Fix 1 + Fix 2 enable it
8. **Begin AI_CENTER consolidation** — Move docs to structured directory

### Medium-term (Next 2 Weeks)

9. **Upgrade 6: Cross-encoder re-ranking** — Install `cross-encoder` package
10. **Upgrade 8: Increase chunk size to 4096** — Requires full re-index
11. **Upgrade 9: Large file support** — Tiered approach
12. **Upgrade 10: File watcher** — Watchdog-based real-time updates

---

## 16. NOTES

### Key Insight from Research Papers

**"Engineering Trust in Agentic Systems":**
- 3-layer enforcement: mandatory pre-search (code), standardized empty results, output grounding
- Prompts alone are structurally insufficient — system must be architecturally constrained
- Multi-model swarm recommended: gemma3:4b worker, qwen2.5:3b critic, phi4:mini router

**"From Hallucination to Grounding: Gemma4 Reliability":**
- gemma4-e4b's 18/42 shared KV layers + SWA(512) trade expressiveness for memory
- Less reliable for structured tool-calling vs gemma3:4b
- Ollama tuning: `num_ctx` 16384+, `temperature` 0.0-0.1, `repeat_penalty` 1.2-1.5
- Gemma 3 4B recommended as primary worker for tool-calling

### FileMind Research Summary

From `C:\AI_STATION\file_management_research\`:
- 7 research papers analyzed (170KB total)
- Recommended stack: LanceDB (embedded, serverless), BGE-M3 embeddings, Gemma4 classifier
- VRAM budget: 8-9GB total usage (fits in 12GB RTX 3080 Ti)
- Performance targets: <100ms search, 3-5 hours first-run index, 5-10 min nightly delta

### Windows-Specific Notes

- Ollama GUI app starts automatically — check system tray
- PATH issues with spaces — use PowerShell for paths with spaces
- CMD `where /r` doesn't search system-wide reliably — use PowerShell or API
- FileMind CLI works via `python -m filemind` — no standalone `.exe`

---

*This extract follows the 16-section format from SESSION_LEARNING_EXTRACT_TEMPLATE.md. Copy to vault and update SYSTEM_NOTES.md.*
