# Research-First Development Protocol

**Created:** 2026-04-08  
**Version:** 1.0

---

## Principle

Before implementing any non-trivial change, Qwen MUST:
1. **Evaluate current knowledge** — What do we actually know vs assume?
2. **Identify knowledge gaps** — What would change the design decision?
3. **Generate a precise research prompt** — Specific, answerable, actionable
4. **Run deep research** (via separate agent) OR ask user to approve the research
5. **Implement with backup** — Every experimental change has a reliable fallback

## Decision Framework

| If the problem is... | Then... | Example |
|---|---|---|
| **Architecture choice** | Research first | "Which vector DB for 50K files?" |
| **Algorithm/strategy** | Research first | "Best chunking for code+text?" |
| **Library/API selection** | Research first | "How to extract BGE-M3 sparse vectors?" |
| **Config toggle** | Just do it | Enable reranking |
| **Bug fix** | Just fix it | Deleted file safety check |
| **Cosmetic** | Just do it | CLI output formatting |

## Experimental + Reliable Backup Pattern

Every experimental implementation MUST have:
- **Experimental path** — The researched, optimized approach
- **Reliable backup** — The known-working fallback that keeps the system functional
- **Switch mechanism** — Config flag to toggle between them
- **Verification test** — A search query or metric that proves the experimental path works

Example:
```
Experimental: BGE-M3 sparse vectors via transformers library
Backup: Dense-only search (current behavior)
Switch: config.ENABLE_SPARSE_VECTORS = True/False
Test: Search "API key authentication" — should find config files with exact terms
```

## Research Prompt Format

Every research prompt MUST include:
1. **Context** — What system we're working with, what's been tried
2. **Question** — Specific, answerable question (not "tell me about X")
3. **Constraints** — Hardware, OS, Python version, VRAM limits
4. **What we've already tried** — Prevents re-researching solved problems
5. **Expected output** — What format the research should return
6. **Decision criteria** — How we'll know if the research is good enough to implement
7. **Output requirement** — Research agent MUST save findings as a `.md` file in `C:\AI_STATION\filemind\docs\RESEARCH_FINDINGS_YYYYMMDD.md` so Qwen can read it directly in the next session

## Session Integration

At the start of each session, Qwen:
1. Reads this protocol
2. Reviews SYSTEM_NOTES.md for numbered decisions
3. Checks FILEMIND_V2_UPGRADE_PLAN.md for current priorities
4. Identifies which items need research vs just coding
5. Generates research prompts for items that need investigation

---

*This protocol is versioned. Update after every session that refines the research process.*
