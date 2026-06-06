# Local AI Model Registry & Ollama Configuration

**Last Updated:** 2026-04-08  
**Status:** Operational (Ollama v0.20.3 running)  
**Hardware:** NVIDIA GeForce RTX 3080 Ti (12GB VRAM) | 32GB RAM | 16-core/32-thread CPU

---

## 1. OLLAMA INSTALLATION

| Property | Value |
|---|---|
| **Version** | 0.20.3 |
| **Executable** | `C:\Users\amirk\AppData\Local\Programs\Ollama\ollama.exe` |
| **API Endpoint** | `http://127.0.0.1:11434` |
| **Models Storage** | `C:\Users\amirk\.ollama\models` |
| **Server Log** | See console output (no file logging configured) |
| **PATH Status** | ❌ NOT in PATH — must use full path or API |

### Key Environment Variables

| Variable | Value | Notes |
|---|---|---|
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Default bind address |
| `OLLAMA_MODELS` | `C:\Users\amirk\.ollama\models` | Model storage location |
| `OLLAMA_KEEP_ALIVE` | `2562047h47m16.854775807s` | Models stay loaded indefinitely |
| `OLLAMA_CONTEXT_LENGTH` | `0` (auto) | Default 4096 for 12GB VRAM |
| `OLLAMA_NUM_PARALLEL` | `1` | Single request at a time |
| `OLLAMA_VULKAN` | `false` | CUDA only, Vulkan disabled |
| `OLLAMA_NO_CLOUD` | `false` | Cloud access enabled |

### GPU Detection

```
Device 0: NVIDIA GeForce RTX 3080 Ti
  Compute Capability: 8.6
  CUDA Driver: 13.2
  Total VRAM: 12.0 GiB
  Available: 10.2 GiB (idle)
  CUDA Architectures: 750,800,860,870,890,900,1000,1030,1100,1200,1210
  VMM: Yes
  Use Graphs: Yes
```

### Starting Ollama

```powershell
# GUI app starts automatically — check system tray
# If not running:
& "C:\Users\amirk\AppData\Local\Programs\Ollama\ollama.exe"

# Verify it's running:
curl http://localhost:11434/api/version
```

---

## 2. INSTALLED MODELS

### Model Inventory

| # | Model Name | Size | Quant | Purpose | Status |
|---|---|---|---|---|---|
| 1 | `gemma4-e4b` | 7.5GB | Q8_0 | **Primary agent** — FileMind AI, general tasks | ✅ Loaded |
| 2 | `gemma4-e4b-json` | 7.5GB | Q8_0 | Same + JSON system prompt (structured output) | ✅ Ready |
| 3 | `gemma4-26b` | 12.5GB | Q3_K_M | Heavy reasoning (barely fits 12GB VRAM) | ⚠️ Marginal |
| 4 | `llama3.2` | 2.0GB | Q4_K_M | Fast fallback, lightweight tasks | ✅ Ready |
| 5 | `llama3` | 4.7GB | Q4_0 | Legacy, compatibility | ✅ Ready |
| 6 | `nomic-embed-text` | 274MB | F16 | Text embeddings (FileMind semantic search) | ✅ Ready |

**Total disk usage:** ~35GB in `C:\Users\amirk\.ollama\models`

### Model Details

#### gemma4-e4b (Primary Agent)
- **Digest:** `6a46c9241b50c6398c1b3825454950093a6cf5200b94017d1935151a6de7c375`
- **Architecture:** Gemma-4-E4B-It (43 layers)
- **VRAM Usage:** 8.7GB (7.6GB model + 224MB KV cache + 176MB compute graph)
- **CPU Fallback:** 680MB (weights) + 5MB (compute graph)
- **Load Time:** ~4.5 seconds
- **Inference Speed:** ~1.4-1.7s per chat request (short responses)
- **Layer Offloading:** 43/43 layers to GPU (full offload)
- **KV Cache:** 4096 context (auto-determined by VRAM)

#### gemma4-e4b-json (JSON Output Variant)
- **Digest:** `b05067ad03d86cd9b97657ca037d268cdd037c9cf0914b0c843e29b069174557`
- **Same base model** with custom JSON enforcement system prompt
- **Use when:** Structured output required (FileMind classification, API responses)

#### gemma4-26b (Heavy Model)
- **Digest:** `3577c90d2e1f5c32831e1ed9ad3b9177f2ddaae08ea469c7fd3618d9787749ef`
- **Parameter Size:** 25.2B (Q3_K_M quantization)
- **⚠️ WARNING:** 12.5GB size exceeds 12GB VRAM — will spill to RAM, very slow
- **Use case:** Complex reasoning only when gemma4-e4b fails, accept 10x slowdown

#### llama3.2 (Fast Fallback)
- **Digest:** `a80c4f17acd55265feec403c7aef86be0c27983ab279d83f3bcd3abbcb5b8b72`
- **Parameter Size:** 3.2B (Q4_K_M)
- **VRAM:** ~2GB — fits easily, fast inference
- **Use when:** gemma4-e4b unavailable, need quick answers

#### llama3 (Legacy)
- **Digest:** `365c0bd3c000a25d28ddbf732fe1c6add414de7275464c4e4d1c3b5fcb5d8ad1`
- **Parameter Size:** 8.0B (Q4_0)
- **VRAM:** ~4.5GB
- **Status:** Kept for compatibility, not actively used

#### nomic-embed-text (Embeddings)
- **Digest:** `0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f`
- **Parameter Size:** 137M (F16 — no quantization)
- **Use:** FileMind semantic search embeddings only
- **Not a chat model**

---

## 3. OLLAMA API USAGE

### List Models
```bash
curl http://localhost:11434/api/tags
```

### Chat Completion
```bash
curl http://localhost:11434/api/chat -d '{
  "model": "gemma4-e4b",
  "messages": [{"role": "user", "content": "Hello"}],
  "stream": false
}'
```

### Show Model Info
```bash
curl http://localhost:11434/api/show -d '{"name": "gemma4-e4b"}'
```

### Generate (Non-Chat)
```bash
curl http://localhost:11434/api/generate -d '{
  "model": "gemma4-e4b",
  "prompt": "What is Python?",
  "stream": false
}'
```

### Critical API Notes

1. **`/api/chat` vs `/api/generate`:**
   - Use `/api/chat` for conversational tasks (FileMind agent)
   - Use `/api/generate` for single-prompt completion
   - **BUG:** gemma4 JSON format constraints ONLY work with `/api/chat`, NOT `/api/generate`
   - See "Gemma JSON Issue" section below

2. **Streaming:**
   - `stream: false` → single JSON response
   - `stream: true` → newline-delimited JSON chunks
   - FileMind uses `stream: false` for reliability

3. **Response Format:**
```json
{
  "model": "gemma4-e4b",
  "created_at": "2026-04-08T14:16:11.000Z",
  "message": {"role": "assistant", "content": "Response text"},
  "done": true,
  "total_duration": 6797992900,
  "load_duration": 4450000000,
  "prompt_eval_count": 128,
  "eval_count": 64,
  "eval_duration": 2347992900
}
```

---

## 4. GEMMA4 JSON OUTPUT ISSUE (CRITICAL FOR FILEMIND)

### The Problem
FileMind classifier needs JSON output from gemma4. Raw model often returns:
- Thinking tags `<think>...</think>` before answer
- Markdown code blocks around JSON
- Extra text before/after JSON
- Truncated responses

### The Solution (95%+ Reliability)

**1. Use `/api/chat` endpoint, NOT `/api/generate`**
```python
response = requests.post("http://localhost:11434/api/chat", json={
    "model": "gemma4-e4b-json",
    "messages": [{"role": "user", "content": prompt}],
    "format": {
        "type": "object",
        "properties": {
            "category": {"type": "string"},
            "confidence": {"type": "number"}
        },
        "required": ["category", "confidence"]
    },
    "options": {
        "temperature": 0.1,
        "num_predict": 4096,
        "repeat_penalty": 1.2
    },
    "stream": false
})
```

**2. Critical parameters:**
- `format`: JSON Schema — forces structured output
- `temperature: 0.1`: Reduces randomness
- `num_predict: 4096+`: Prevents truncation (default 128 is too short)
- `repeat_penalty: 1.2`: Prevents loops

**3. System prompt for JSON mode:**
```
You MUST respond with ONLY a valid JSON object. No explanations, no markdown, no code blocks.
Required format: {"category": "string", "confidence": 0.0-1.0}
```

**4. Known Bug:** `think=false` parameter breaks format constraint on gemma4 (bug #15260 in Ollama tracker). Do NOT set it.

**5. Batch size limit:** Max 5-8 files per classification request. Larger batches cause JSON failures.

---

## 5. FILEMIND INTEGRATION

### How FileMind Uses Ollama

**FileMind agent architecture:**
- `smolagents` CodeAgent framework
- Ollama via `OpenAIServerModel` (compatible with OpenAI API format)
- 9 tools available: PythonInterpreterTool, SearchFileMindTool, ReadFileTool, ListDirTool, FindFilesTool, ShellTool, FileStatsTool, LogLearningTool, GetLearningsTool
- Custom system prompt prevents spiraling, max_steps=5

**Key files:**
- `C:\AI_STATION\filemind\agent\run.py` — Main agent runner
- `C:\AI_STATION\filemind\classifier.py` — LLM file classifier
- `C:\AI_STATION\filemind\vector_store.py` — LanceDB embeddings
- `C:\AI_STATION\filemind\embedder.py` — BGE-M3 embedding model
- `C:\AI_STATION\filemind\config.py` — Configuration (SCAN_ROOTS, SKIP_DIRS)

**Agent Model Config:**
```python
model = OpenAIServerModel(
    model_id="gemma4-e4b",
    api_key="ollama",
    base_url="http://localhost:11434/v1"
)
```

**Mandatory Search-First Protocol:**
- `_run_mandatory_search()` runs before agent loop
- `_build_grounding_context()` injects evidence into agent context
- Prevents agent from answering from parametric knowledge
- Per research: "prompts alone are structurally insufficient — system must be architecturally constrained"

### Model Tuning for FileMind

| Parameter | Recommended | Why |
|---|---|---|
| `num_ctx` | 16384+ | BGE-M3 supports 8192, but agent needs more for tool results |
| `temperature` | 0.0-0.1 | Classification needs deterministic output |
| `repeat_penalty` | 1.2-1.5 | Prevents loops in long responses |
| `num_predict` | 4096+ | Prevents truncation on classification batches |
| `top_p` | 0.9 | Standard |
| `top_k` | 40 | Standard |

---

## 6. KNOWN ISSUES & LIMITATIONS

### gemma4-e4b Reliability

**Issue:** Agent sometimes skips `search_filemind` tool and answers from general knowledge.

**Root cause:** gemma4 has 18/42 shared KV layers + sliding window attention (SWA=512). This trades expressiveness for memory efficiency, making it less reliable for structured tool-calling vs gemma3:4b.

**Mitigation:**
- Mandatory search-first protocol in CODE (not just prompt)
- Standardized empty results handling
- Output grounding via `_validate_answer()`
- Still have occasional failures — monitor and fix

### Model Loading Performance

| Model | Load Time | First Request | Subsequent |
|---|---|---|---|
| gemma4-e4b | ~4.5s | ~6.8s | ~1.4-1.7s |
| llama3.2 | ~1.5s | ~3s | ~0.5s |
| gemma4-26b | ~15s+ | ~30s+ | ~10s+ (RAM-spilled) |

### VRAM Management

- **12GB total, ~10GB available** (system reserves ~2GB for display)
- **gemma4-e4b:** 8.7GB → leaves ~1.3GB (tight)
- **gemma4-26b:** Needs ~15GB → spills 3GB to RAM (very slow)
- **Running 2 models simultaneously:** Not recommended — will OOM
- **KEEP_ALIVE indefinite:** Models stay loaded until manually unloaded or Ollama restart

### Unload Model
```bash
curl http://localhost:11434/api/generate -d '{
  "model": "gemma4-e4b",
  "keep_alive": 0
}'
```

---

## 7. RECOMMENDED MODEL UPGRADES

### Priority 1: gemma3:4b (Worker Model)
- **Why:** Better tool-calling reliability, smaller footprint (~3GB), faster
- **VRAM:** ~3.5GB → can run alongside embedding model
- **Use:** Primary FileMind worker, replace gemma4-e4b for tool calls
- **Install:** `ollama pull gemma3:4b`

### Priority 2: qwen2.5:3b (Critic Model)
- **Why:** Excellent at validation, code review, JSON output
- **VRAM:** ~2GB → lightweight critic
- **Use:** Validate gemma4 outputs, catch hallucinations
- **Install:** `ollama pull qwen2.5:3b`

### Priority 3: phi4:mini (Router)
- **Why:** Tiny (~1.5GB), fast, good at intent classification
- **Use:** Route queries to appropriate model
- **Install:** `ollama pull phi4:mini`

### Multi-Model Swarm Architecture

```
User Query
    ↓
phi4:mini (Router) — "What does the user need?"
    ↓
├─ Simple lookup → llama3.2 (fast)
├─ Tool calling → gemma3:4b (reliable)
├─ Complex reasoning → gemma4-e4b (capable)
└─ Validation → qwen2.5:3b (critic)
```

**Total VRAM with swarm:** ~10GB (fits in 12GB)

---

## 8. FILEMIND INDEX STATUS

**Current State (as of 2026-04-08):**
- **Files indexed:** 3,282
- **Qdrant chunks:** 405
- **Scan roots:** `C:\AI_STATION`, `C:\Users\amirk\.kimi`
- **Max file size:** 500KB
- **Content stored per file:** 50KB
- **Chunk size:** 512 tokens

**Skipped directories:**
`.git`, `__pycache__`, `node_modules`, `venv`, `.venv`, `Lib`, `site-packages`, `.claude`, `.obsidian`, `.telegram_bot`, `backups`, `tools`, `memmachine_data`, `playwright`

---

## 9. CRITICAL COMMANDS REFERENCE

### Ollama Management
```powershell
# Start Ollama (GUI app — check system tray)
& "C:\Users\amirk\AppData\Local\Programs\Ollama\ollama.exe"

# List models
curl http://localhost:11434/api/tags

# Pull new model
ollama pull <model-name>
# OR (if ollama not in PATH):
Invoke-WebRequest -Uri http://localhost:11434/api/pull -Method POST -Body '{"name":"model-name"}'

# Remove model
ollama rm <model-name>

# Check server status
curl http://localhost:11434/api/version

# Unload all models
curl http://localhost:11434/api/generate -d '{"keep_alive": 0}'
```

### FileMind Operations
```powershell
cd C:\AI_STATION\filemind

# Search
python -m filemind run.py search "query" [--keyword|--semantic|--type .ext]

# Stats
python -m filemind run.py stats

# Health check
python -m filemind run.py health

# Verify index
python -m filemind run.py verify

# Scan (full)
python -m filemind run.py scan --full

# Agent (smolagents)
python agent/run.py "your question"
```

### Troubleshooting

| Problem | Solution |
|---|---|
| Ollama not responding | Check system tray, restart GUI app |
| Model won't load | Check VRAM: `nvidia-smi`, unload other models |
| JSON output fails | Use `/api/chat` with `format` parameter, not `/api/generate` |
| Classification returns "unknown" | Check Ollama is running, increase `num_predict` |
| Agent skips search | Check `_run_mandatory_search()` in `agent/run.py` |
| "ollama" command not found | Use full path: `C:\Users\amirk\AppData\Local\Programs\Ollama\ollama.exe` |
| VRAM OOM | Unload large models, use llama3.2 instead |

---

## 10. DECISION HISTORY

### Why gemma4-e4b as primary?
- Best balance of capability (7.5B params) and VRAM fit (8.7GB)
- Q8_0 quantization preserves quality
- Supports multimodal (text, image, audio)
- **Tradeoff:** Less reliable tool-calling than gemma3:4b due to shared KV layers

### Why not larger models?
- gemma4-26b (25.2B) barely fits 12GB VRAM, spills to RAM
- Inference 10x slower when RAM-spilled
- Only use for complex reasoning when gemma4-e4b fails

### Why keep llama3.2?
- Tiny (2GB), fast, reliable for simple queries
- Perfect fallback when gemma4 unavailable
- Legacy compatibility with llama3 ecosystem

### Why nomic-embed-text?
- FileMind uses BGE-M3 for embeddings, NOT nomic
- nomic kept for compatibility/testing
- Consider removing if space needed

### Why 6 models total?
- From previous session work — installed incrementally
- Some are legacy/unused (llama3, nomic-embed-text)
- Can prune when consolidating to AI_CENTER

---

## 11. WHAT HAPPENED: PIPELINE CRASH

**Context:** I was orchestrating a FileMind research and implementation pipeline — reading research files, analyzing code modules, launching deep research agents, and building implementation plans.

**What happened:** Multiple parallel agent launches + deep research tool + file reads consumed context window. The system hit resource limits and the session crashed mid-orchestration.

**Root causes:**
1. Too many parallel agents launched simultaneously (3+ deep research agents)
2. Large file reads (70KB research docs) consumed context
3. Complex multi-step orchestration exceeded token budget

**How to prevent:**
- Sequence agent launches instead of parallel when doing deep research
- Read files selectively — don't load entire 70KB docs unless needed
- Use `Explore` agent for quick file discovery, reserve `general-purpose` for deep analysis
- Check context usage periodically and checkpoint progress

---

## 12. CONSOLIDATION PLAN FOR AI_CENTER

**Current state:**
- Documentation scattered across:
  - `C:\AI_STATION\AI STAION\` (obsidian notes, session reports)
  - `C:\AI_STATION\filemind\docs\` (technical docs)
  - `C:\AI_STATION\file_management_research\` (research papers)
  - `C:\AI_STATION\CONSOLIDATION_PLAN.md` (exists but not executed)
  - QWEN.md memories (session memory fragments)

**Goal:** Single source of truth at `C:\AI_STATION\AI_CENTER\`

**Proposed structure:**
```
C:\AI_STATION\AI_CENTER\
├── ollama\
│   ├── REGISTRY.md              ← This document (moved here)
│   ├── MODEL_CONFIGS\           ← Per-model Ollama configs
│   └── PERFORMANCE_LOGS\        ← Load times, inference speeds
├── filemind\
│   ├── ARCHITECTURE.md          ← System design, data flow
│   ├── KNOWN_ISSUES.md          ← Bug tracker, workarounds
│   ├── UPGRADE_PLAN.md          ← 8 critical fixes + enhancements
│   └── SESSION_REPORTS\         ← Timestamped session summaries
├── research\
│   ├── VECTOR_SEARCH.md         ← Qdrant vs LanceDB comparison
│   ├── EMBEDDING_MODELS.md      ← BGE-M3, alternatives
│   ├── CLASSIFICATION.md        ← LLM classifier patterns
│   └── COMPETITIVE_ANALYSIS.md  ← Raycast, DEVONthink insights
├── AGENT_PLAYBOOK.md            ← Model selection, prompting patterns
└── SYSTEM_NOTES.md              ← Numbered key decisions (global)
```

**When to execute:** After Ollama pipeline is fully operational and stable

---

## 13. NEXT ACTIONS

### Immediate (This Session)
1. ✅ Document Ollama configuration (this document)
2. ⏳ Move to `C:\AI_STATION\AI_CENTER\ollama\REGISTRY.md`
3. ⏳ Test gemma4-e4b classification with JSON format fix
4. ⏳ Verify FileMind agent search-first protocol

### Short-term (Next Session)
1. Add gemma3:4b for reliable tool-calling
2. Implement mandatory search-first protocol if not already in code
3. Fix FTS5 500-char truncation (migrate to LanceDB FTS)
4. Enable sparse vector usage in semantic search
5. Add classification fallback (rule-based classifier)

### Medium-term (1-2 weeks)
1. Implement multi-model swarm (gemma3 worker, qwen2.5 critic, phi4 router)
2. Increase chunk size from 512 to 4096+ (BGE-M3 supports 8192)
3. Add large file handling (>500KB with deep scan option)
4. Consolidate all docs to AI_CENTER
5. Build terminal UI for FileMind (rich/textual)

### Long-term (1-3 months)
1. Meta-learning loop: Weekly review of session extracts → prompt improvements
2. Fine-tune small local model with accumulated extracts
3. Add image/video processing for large files
4. Expand scan roots beyond AI_STATION
5. Build web UI (FastAPI + Gradio)

---

## 14. REFERENCES

### Key Files
- `C:\AI_STATION\filemind\QWEN_SKILL_FILEMIND.md` — FileMind skill reference
- `C:\AI_STATION\filemind\docs\SESSION_LEARNING_EXTRACT_TEMPLATE.md` — Session extraction template
- `C:\AI_STATION\filemind\docs\SESSION_LEARNING_EXTRACTOR_GUIDE.md` — Extraction guide
- `C:\AI_STATION\filemind\SYSTEM_NOTES.md` — Numbered key decisions
- `C:\AI_STATION\CONSOLIDATION_PLAN.md` — Existing consolidation plan

### Research Papers Analyzed
- "Engineering Trust in Agentic Systems" — Grounding framework, 3-layer enforcement
- "From Hallucination to Grounding: A System-Level Framework for Building Reliable Local Agents with gemma4-e4b" — Gemma4 reliability, Ollama tuning

### External Resources
- Ollama API docs: https://github.com/ollama/ollama/blob/main/docs/api.md
- LanceDB docs: https://lancedb.github.io/lancedb/
- BGE-M3 model: https://huggingface.co/BAAI/bge-m3
- Gemma 4: https://huggingface.co/google/gemma-4

---

*This document is the single source of truth for Ollama configuration and local AI models. Update after every session that modifies models, configs, or discovers new issues.*
