# FileMind — Roadmap to Usable Agent

> **Question**: When can we actually USE this thing for real work?
> **Answer**: Below is the honest assessment. No fluff.

---

## Current State (Phase 0 — ✅ DONE)

**What we have:**
- ✅ Working indexing pipeline (sentence-transformers, dense-only)
- ✅ 405 chunks in Qdrant, 3000+ files in SQLite catalog
- ✅ Hybrid search works (dense vector + keyword)
- ✅ CLI: scan, search, stats, duplicates, health
- ✅ Gradio dashboard + web UI
- ✅ 39/39 unit tests pass, 8/8 E2E tests pass

**What we DON'T have:**
- ❌ No agent loop — can't plan, execute, reason over tasks
- ❌ No tool execution — can't manage files, run commands
- ❌ Can't use it to clean up folders or do system-wide tasks autonomously

**Current capability**: You give it a search query, it returns relevant files. That's it.

---

## What's Needed for "Actually Useful" (Your 3 Goals)

### Goal 1: Clean Up Currently Indexed Folders
**What this means**: Agent finds old/duplicate/stale files, suggests deletions, organizes by category.
**What's needed**:
- Agent loop (can reason: "this file hasn't been modified in 2 years, it's a temp file, suggest delete")
- FileSystemTool (can list, move, delete files)
- Duplicate detection integration (we already have `duplicates.py`)
- HITL approval (you confirm before any deletion)

**Estimated sessions**: 2-3 sessions (Phase 1 + Phase 2 core tools)

### Goal 2: Full System Scan
**What this means**: Agent re-indexes everything, verifies completeness, reports gaps.
**What's needed**:
- This actually WORKS right now via `nightly.py` — just needs to run
- BUT: it'll take a while (3000+ files, extraction + embedding on CPU)
- Agent can monitor progress, report issues, restart if interrupted

**Estimated sessions**: 1 session (just run it, monitor, fix any issues)

### Goal 3: General Memory/Document/File Management
**What this means**: You say "find me all project notes about X" or "organize my downloads folder" and it does it.
**What's needed**:
- Full agent loop with planning
- FileSystemTool + ShellTool + QueryFileMindTool
- Some prompt engineering for natural language understanding
- HITL for destructive operations

**Estimated sessions**: 3-4 sessions (Phase 1 + Phase 2 + hardening)

---

## Fastest Path to "Usable Basic Agent"

I'm going to skip the full enterprise architecture and build the **minimum viable agent** first. Here's the streamlined plan:

### Session A: Agent Loop (1 session) — PRIORITY #1
**Goal**: Agent can receive a command, reason about it, execute Python code, return results.

```
What: Install smolagents, wire up Ollama/Gemma 4 e4b, create basic CodeAgent loop
Test: "list all .py files in C:/AI_STATION/filemind"
Output: Agent runs code, returns file list
```

### Session B: Core Tools (1-2 sessions) — PRIORITY #2
**Goal**: Agent has FileSystemTool, ShellTool, QueryFileMindTool.

```
What: Build 3 tools with sandbox, test each one
Test: "find all files mentioning 'telegram' and show me the top 5"
Output: Agent searches index, returns results with file paths + previews
```

### Session C: Real Task (1 session) — YOUR FIRST GOAL
**Goal**: Agent cleans up indexed folders.

```
What: Command agent with "analyze my indexed files, find duplicates, 
       identify stale temp files, suggest cleanup actions"
Test: Agent produces a cleanup plan, you approve, it executes
Output: Cleaner file structure, duplicates resolved
```

### Session D: Full Scan (0.5 session) — YOUR SECOND GOAL
**Goal**: Run full system scan with monitoring.

```
What: Run nightly.py on full index, agent monitors progress
Test: Scan completes, reports indexed count, any errors
Output: Fresh, complete index of all your files
```

---

## When Each Goal Is Ready

| Goal | Sessions Needed | Status | Confidence |
|------|----------------|--------|------------|
| **Full system scan** | 0 (works now) | ✅ READY NOW | 95% |
| **Agent loop + basic tools** | 2-3 sessions | ✅ DONE (Session A) | 90% |
| **Clean up indexed folders** | 3-4 sessions | After Session C | 70% |
| **General file management** | 3-4 sessions | After Session C | 70% |

### Session A Results (Completed April 8, 2026)
- ✅ smolagents 1.24.0 installed and working on Python 3.14
- ✅ Ollama `gemma4-e4b:latest` connected via `OpenAIServerModel`
- ✅ Agent loop: Plan → Act → Observe → Final Answer working
- ✅ 7 tools: PythonInterpreterTool, SearchFileMindTool, ReadFileTool, ListDirTool, FindFilesTool, ShellTool, FileStatsTool
- ✅ Custom system prompt prevents spiraling
- ✅ Test: "Count all .py files in C:\AI_STATION\filemind" → "There are 49 .py files" (2 steps)

### The Honest Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Gemma 4 e4b produces bad code for tool calls | Medium | High | Optimize prompts, add retry logic |
| Agent gets stuck in loops | Medium | Medium | Max steps=5, timeout guards |
| smolagents incompatible with Python 3.14 | Low | High | Custom agent loop fallback (not hard) |
| Ollama hangs on format:"json" | Low | Medium | Already fixed this issue |
| GPU OOM during full scan | Low | Medium | Batch size reduction, CPU fallback |

---

## My Recommendation

**Start with Session A immediately.** Why:
1. Agent loop is the gatekeeper — everything else depends on it
2. smolagents is lightweight, should install cleanly
3. If it doesn't work with Python 3.14, I'll write a custom 100-line agent loop (the concept is simple)
4. Once the loop works, adding tools is straightforward

**Realistic timeline if we focus:**
- Session A (agent loop): Tomorrow
- Session B (core tools): Day after
- Session C (cleanup task): Day 3-4
- Session D (full scan): Day 4-5

That's ~5 sessions to a working basic agent that can actually help you manage files. Not weeks, sessions. Some sessions might be same-day if things go smoothly.

---

## What I'll Do Next (If You Approve)

1. Check if `smolagents` installs on Python 3.14
2. If yes → build agent loop
3. If no → write custom lightweight agent loop (~100 lines)
4. Test with a simple file listing command
5. Report back with results

**Say the word and I'll start.**
