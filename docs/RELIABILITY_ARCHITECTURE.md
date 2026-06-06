# FileMind — Local Agent Reliability Architecture

> **Core Insight**: You don't need a bigger model. You need a **100% reliable system** around a 70% model.
> **Date**: April 8, 2026
> **Source**: Research on local agentic AI engineering patterns

---

## The Stack (All Local, No Cloud)

| Component | What It Is | Running Where |
|-----------|------------|---------------|
| **LLM** | `gemma4-e4b:latest` | Ollama (`localhost:11434`) |
| **Agent Framework** | `smolagents` 1.24.0 (Hugging Face) | Python 3.14 |
| **Embeddings** | `BAAI/bge-m3` via `sentence-transformers` | Local CPU/GPU |
| **Vector Store** | Qdrant (local mode) | In-process |
| **Knowledge Base** | SQLite + FTS5 + Qdrant vectors | `C:/AI_STATION/.index/` |
| **Tools** | 7 custom tools (filesystem, search, shell) | Your filesystem + subprocess |

✅ **Zero external API calls** — all local after model download
✅ **No data leaves your machine**
✅ **Full code execution** — agent writes and runs Python

---

## The Reliability Problem

Small models (4B parameters) are:
- ✅ Fast, private, cheap to run
- ❌ Inconsistent at following complex instructions
- ❌ Prone to spiraling when confused
- ❌ Bad at knowing when they're done

**Solution**: Engineer reliability at the SYSTEM level, not the MODEL level.

---

## Four Reliability Pillars

### 1. Tool Grounding + Output Validation
Don't trust the model's words — trust the tool outputs.

```python
# Every tool validates its own inputs and outputs
def forward(self, dirpath: str) -> str:
    # Input validation
    path = Path(dirpath)
    if not path.is_absolute():
        path = Path.cwd() / path  # Auto-fix, don't fail
    if not path.exists():
        return f"Directory not found: {dirpath}"  # Clear error for agent
    
    # Output is always structured, never raw
    return structured_output  # Agent can parse this
```

### 2. Self-Correction Loop (Already Working)
The agent already retries when tools fail:
- Tool returns error → Agent sees error → Agent tries different approach
- We reinforce this with system prompt rules

### 3. Deterministic Fallbacks
For precision operations, bypass the LLM:
```python
# Instead of asking model to count files:
# Use rglob directly (100% accurate)
len(list(Path("C:/AI_STATION/filemind").rglob("*.py")))
```

### 4. Prompt as Code (Versioned, Dynamic)
System prompt is the most critical piece:
- Custom prompt fixed the spiraling problem
- Should be versioned and testable
- Should inject context-specific instructions

---

## Memory Architecture (Future — Phase 4+)

### Three Memory Layers

| Layer | Storage | Purpose | When to Build |
|-------|---------|---------|---------------|
| **Session Memory** | JSON file | What happened in this conversation | Phase 2 |
| **Learning Log** | JSONL | Patterns from past tasks | ✅ **Done (Session B)** |
| **KPI Metrics** | `logs/kpi.jsonl` | Latency, throughput, resource usage | ✅ **Done (Session B)** |
| **User Preferences** | Config file | "Always use absolute paths" | Phase 2 |

### What's Implemented Now
- ✅ `learnings.jsonl` — Agent logs what works/doesn't after each task
- ✅ `logs/kpi.jsonl` — Latency, throughput, RAM, CPU per task
- ✅ `get_learnings` tool — Retrieve past learnings before new tasks
- ✅ `log_learning` tool — Record insights during task completion
- ✅ KPI report printed after each agent run

---

## What We Built Today (Session A)

### Working
- ✅ Agent loop with smolagents + Ollama
- ✅ Custom system prompt prevents spiraling
- ✅ 7 tools: find_files, list_directory, read_file, search_filemind, shell_command, filemind_stats, python_interpreter
- ✅ max_steps=5 prevents infinite loops
- ✅ Tool output validation (absolute path auto-resolution, error messages)
- ✅ Test passed: "Count .py files" → "49 files" in 2 steps

### Next Reliability Improvements (Session B)
1. **LearningLogger tool** — Log what works/doesn't after each task
2. **Prompt versioning** — Save prompt versions, track which works best
3. **Error pattern detection** — If agent repeats same error, force different approach
4. **Deterministic counters** — For "count files" type queries, use rglob directly

---

## Key Decision: When to Add Complexity

| Pattern | Complexity | Impact | When to Add |
|---------|-----------|--------|-------------|
| Custom system prompt | Low | High | ✅ Done |
| Tool input validation | Low | High | ✅ Partially done |
| max_steps limit | Low | High | ✅ Done |
| Learning log | Medium | Medium | Phase 2 |
| Critic agent | Medium | Medium | Phase 3 |
| Prompt versioning | Medium | Low | Phase 3 |
| Memory retrieval | High | Low | Phase 4 |

**Rule**: Add complexity only when a specific failure pattern appears 3+ times.

---

## Next Sessions Plan

### Session B: Reliability Hardening
- Test agent with diverse tasks
- Identify failure patterns
- Add LearningLogger tool
- Improve tool descriptions based on what agent misunderstands

### Session C: Real Cleanup Task
- "Analyze indexed files, find duplicates, suggest cleanup"
- This is the first real test of multi-step reasoning
- Will reveal what reliability patterns we actually need

---

*Documented: April 8, 2026 — Agent Loop Working, Reliability Patterns Identified*
