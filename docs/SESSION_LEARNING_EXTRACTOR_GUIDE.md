# Session Learning Extractor — Automation Guide

> **Purpose**: Every Qwen Code session on this project MUST end with a complete retrospective extraction of the conversation, saved as a structured document.
> **Trigger**: End of every session (when user signals wrap-up or session naturally concludes).
> **Format**: 16-section structured markdown (see template below).
> **Output**: `docs/SESSION_LEARNING_EXTRACT_[YYYYMMDD].md` + copy to `vault/` + update `SYSTEM_NOTES.md`.

---

## How It Works

### 1. Qwen automatically runs the extraction
At session end, Qwen reads the entire conversation top-to-bottom and produces a structured markdown document covering:
- Goals & scope (with DONE/PARTIAL/NOT DONE/DEFERRED status)
- System & environment details (versions, paths, configs)
- Architecture & design decisions (with CONFIRMED/UNVERIFIED status)
- Files changed (with paths and reasons)
- Every error encountered (with root cause and fix status)
- All commands run (with outcomes)
- Technical learnings (self-contained, out-of-context readable)
- Project-specific patterns & conventions
- Incomplete/deferred/known issues (with resume context)
- Dependencies & external services
- Security considerations
- Performance notes
- User instructions & preferences (verbatim)
- Open questions
- Recommended next actions
- Notes & miscellaneous

### 2. File is saved to two locations
- `C:\AI_STATION\filemind\docs\SESSION_LEARNING_EXTRACT_[YYYYMMDD].md`
- `C:\AI_STATION\filemind\vault\SESSION_LEARNING_EXTRACT_[YYYYMMDD].md` (backup copy)

### 3. SYSTEM_NOTES.md is updated
- Key learnings appended as numbered items
- Model registry entries updated if new models were discovered/configured
- Research paper references added

### 4. Post-Extraction Chat Appendix (if applicable)
- If the user continues chatting after the extraction is produced, the full record of that conversation is captured in the APPENDIX section of the extract
- This ensures nothing is lost if the session extends beyond the formal wrap-up
- The extract file is re-saved with the appendix appended (updated timestamp on file)

### 5. "Chicken Out" Tracking (Agent Reliability Monitoring)
- During the conversation, Qwen MUST identify and record any instances where the agent "chickens out" — i.e., hesitates, skips mandatory tool use, or answers from parametric knowledge instead of searching the local index first
- These instances are recorded in a dedicated **APPENDIX B: Agent Reliability Record** section at the end of the extract
- Each instance includes:
  - **What was asked**: the user's query or command
  - **What should have happened**: mandatory search-first protocol, tool invocation, etc.
  - **What actually happened**: agent answered from general knowledge, skipped search, partial execution, etc.
  - **Model running**: which model was active (e.g., `gemma4-e4b:latest`, `llama3.2`, etc.)
  - **Severity**: `HIGH` (fabrication/hallucination), `MEDIUM` (partial search, incomplete results), `LOW` (correct but incomplete, missed optimization)
  - **Context**: any guardrails that were in place but failed, or that were absent
- This creates a structured failure dataset that powers the meta-learning loop (Workstream G) — the `prompt_optimizer.py` will specifically target these patterns for improvement
- Example format:
  ```
  ### Chicken-Out Instance #1
  - **Query**: "kimi"
  - **Expected**: search_filemind(query="kimi") → return results or empty
  - **Actual**: Answered from parametric knowledge: "Kimi is an AI assistant by Moonshot AI..."
  - **Model**: gemma4-e4b:latest
  - **Severity**: HIGH (fabrication — skipped mandatory search)
  - **Guardrails**: None yet (mandatory pre-search not implemented in code)
  ```

---

## Template

The extraction template is defined in `docs/SESSION_LEARNING_EXTRACT_20260408.md` — use that as the canonical reference.

Key rules:
- Do not summarize. Do not compress. Preserve technical specificity verbatim.
- Capture failures as carefully as successes.
- If something was "not done," "skipped," "deferred," or "will do later" — capture it under section 9 (Incomplete/Deferred).
- Preserve user's exact wording for requirements, constraints, and preferences.
- Where chronological order matters (debugging sequences), preserve it.

---

## Automation Commands

To manually trigger the extraction at any point:
```
Run the Session Learning Extractor on this conversation and save to docs/ and vault/.
```

Or simply signal session end — Qwen should auto-trigger.

---

## Quality Checklist

After extraction, verify:
- [ ] All 16 sections present and populated
- [ ] Verbatim error messages preserved
- [ ] All commands listed with outcomes
- [ ] User instructions captured verbatim
- [ ] Deferred items have resume context
- [ ] File saved to both docs/ and vault/
- [ ] SYSTEM_NOTES.md updated
