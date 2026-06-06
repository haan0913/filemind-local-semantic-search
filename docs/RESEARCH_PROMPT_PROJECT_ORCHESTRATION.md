# Research Prompt 3: Dual-Audience Project Planning — JSON Orchestration Prompts vs Human-Readable Plans

**Priority:** HIGH — addresses session amnesia, lost context, scattered priorities  
**Date:** 2026-04-08  
**Status:** Ready for deep research agent

---

## Context

We maintain a local-first AI development environment on Windows 11 with:
- **FileMind** — semantic file search engine being actively developed
- **Qwen 3.6 Plus** via OpenRouter as the primary agent (user-facing CLI)
- **Ollama gemma4-e4b** for local classification (switching to gemma3:4b soon)
- **Session-based development** — work happens in discrete 1-2 hour sessions, then context is lost
- **GitHub repo** — https://github.com/haan0913/filemind (private, 3 commits so far)

## The Problem

Our current planning documentation is scattered across 14+ markdown files in `C:\AI_STATION\filemind\docs\`:
- `FILEMIND_V2_UPGRADE_PLAN.md` — 241 lines of phased implementation plan
- `LOCAL_MODEL_REGISTRY.md` — 16KB of Ollama configuration
- `AGENT_PLAYBOOK.md` — 14KB of model guidelines
- `BACKUP_VERSION_STRATEGY.md` — backup policy
- `RESEARCH_FIRST_PROTOCOL.md` — research methodology
- `RESEARCH_PROMPT_CHUNKING_STRATEGY.md` — research prompt #1
- `RESEARCH_PROMPT_SPARSE_VECTORS.md` — research prompt #2
- `SYSTEM_NOTES.md` — 74 numbered decision items
- `SESSION_LEARNING_EXTRACT_20260408.md` — session extraction
- `RESEARCH_NOTES_CHUNKING.md` — research findings summary
- `SESSION_REPORT_20260408.md` — session report
- Plus session extracts, research papers, and more

**The core issue:** At the start of each session, the agent reads all this, tries to reconstruct the current state, figure out what's done vs. not done, and decide what to work on next. This takes time, often misses critical items (like the FlagReranker crash we just found), and the agent frequently forgets important context between sessions.

**What actually happened in our last session:**
1. Agent started by trying to research Ollama models (already documented)
2. Built documentation (good, but duplicated existing research)
3. Crashed mid-orchestration due to context overload
4. Next session: had to re-research everything from scratch
5. Only through user prompting discovered the FlagReranker crash that would have taken down search

**The gap:** We need a structured, machine-parseable project state document that tells the agent EXACTLY: what's done, what's broken, what's next, what constraints exist, what to watch for. Plus a parallel human-readable version for the user to review and approve plans.

## What We've Already Tried

1. **SYSTEM_NOTES.md** — Numbered decision items (1-74). Useful for reference but not actionable. Agent reads them but doesn't systematically check off completed items or prioritize next actions.

2. **FILEMIND_V2_UPGRADE_PLAN.md** — Phased plan with checkboxes. Agent updated it but doesn't actually USE it to decide what to work on. It's a reference doc, not an orchestration document.

3. **QWEN_SKILL_FILEMIND.md** — Skill reference for search/index operations. Agent reads it but doesn't use it for project management — it's task-oriented, not state-oriented.

4. **Research-first protocol** — Requires agent to evaluate knowledge before implementing. Good principle but not enforced — agent still implemented things without research when it should have.

5. **Session learning extracts** — 16-section extraction format captures what happened. But these are post-hoc — they don't guide the NEXT session.

6. **Dependency checker (check_deps.py)** — NEW, just created. Validates Python package dependencies at startup. This is a good model for what we need — but we need it at the PLANNING level, not just the dependency level.

## Specific Questions to Answer

1. **What's the optimal structure for a JSON orchestration prompt** that forces an LLM to maintain project state across sessions? What fields, what nesting, what constraints?

2. **How should the JSON be structured** so the LLM MUST:
   - Check off completed items before starting new work
   - Identify gaps and risks before implementing
   - Follow a defined priority (not jump to whatever seems interesting)
   - Remember critical warnings (like "don't switch models mid-rebuild")
   - Validate dependencies before enabling features
   - Report status to the user at session end

3. **What JSON schema constraints** prevent the LLM from:
   - Ignoring the document and answering from parametric knowledge
   - Skipping validation steps
   - Forgetting to save state at session end
   - Making changes without user approval

4. **How should the human-readable version mirror the JSON** — same structure, same priorities, same status? Or a different view of the same data (e.g., rendered from the JSON)?

5. **What existing frameworks exist for this?** Are there established patterns for "LLM project orchestration prompts"? JSON task schemas? State management protocols for agentic systems?

6. **How to enforce the JSON prompt** — should it be:
   - A system prompt prefix that the agent reads at session start?
   - A file that the agent MUST parse and respond to with a JSON action plan?
   - A checklist the agent fills out and saves at session end?
   - All of the above in a specific sequence?

7. **What's the right level of detail** for each field? Too coarse → not actionable. Too fine → overwhelms the LLM. Where's the sweet spot for a ~50-100 item project state?

## Constraints

- **LLM:** Qwen 3.6 Plus via OpenRouter (strong JSON following, 32K context window)
- **Session length:** 1-2 hours typical — document must be scannable in <30 seconds
- **Update frequency:** Every session — must be quick to update, not a burden
- **Two audiences:** AI agent (JSON, structured, constraint-enforced) + human user (markdown, reviewable, approving)
- **Must be file-based** — stored in `C:\AI_STATION\filemind\docs\` so it persists between sessions
- **Must be parseable by the agent** at startup — the agent reads it, extracts current state, and acts accordingly

## Expected Output

A structured answer covering:

1. **JSON schema design** — Complete field definitions with types, constraints, and descriptions for every field
2. **Human-readable template** — Markdown version that mirrors the JSON structure, designed for user review
3. **Orchestration sequence** — Exactly what the agent does at session start, during work, and at session end
4. **Enforcement mechanism** — How to make the LLM actually follow the JSON (system prompt design, output constraints, validation)
5. **Implementation code** — Python script or agent logic that loads the JSON, validates the agent's planned actions against it, and saves updates
6. **Migration plan** — How to convert our current scattered docs (SYSTEM_NOTES.md, UPGRADE_PLAN.md, etc.) into the new unified structure
7. **Trade-off analysis** — What we gain vs. what we lose vs. current approach

**OUTPUT FORMAT:** Save all findings as a `.md` file at `C:\AI_STATION\filemind\docs\RESEARCH_FINDINGS_YYYYMMDD_PROJECT_ORCHESTRATION.md` so Qwen can read it directly in the next session.

## Decision Criteria

We'll consider the research actionable if it provides:
- A complete JSON schema that an LLM can parse and act on without ambiguity
- A clear enforcement mechanism that prevents the LLM from ignoring the document
- A migration path from our current 14+ scattered docs to a unified dual-audience system
- An implementation that adds <5 minutes of overhead per session (loading + updating)

---

## Experimental + Reliable Backup Plan

**Experimental path:** Full JSON orchestration prompt with structured state, priority queue, validation rules, and session-end checkpointing  
**Reliable backup:** Enhanced SYSTEM_NOTES.md with mandatory section headers (DONE/TODO/RISKS/REMINDERS) — simple, readable, works today  
**Switch mechanism:** We can adopt the JSON approach incrementally — start with the markdown version, then add JSON parsing as the enforcement layer  
**Verification test:** At session start, agent reads project state document. At session end, agent updates it. Next session, agent reads the UPDATE (not re-discovers the state).
