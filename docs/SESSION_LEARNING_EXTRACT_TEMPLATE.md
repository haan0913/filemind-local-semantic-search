# Session Learning Extract — Template

> Copy this template and fill it at the end of every session. Replace [brackets] with actual values.

```md
# Session Learning Extract
Date: [YYYY-MM-DD]
Project: [project name or brief descriptor — infer from context]
Session Summary: [2–3 sentence plain-language description of what this session was about and what state things are in at the end]

---

## 1. GOALS & SCOPE
> What the user set out to accomplish this session. One line per goal. Mark each:
> [DONE] | [PARTIAL] | [NOT DONE] | [DEFERRED]

- [STATUS] Goal description here

---

## 2. SYSTEM & ENVIRONMENT
> All technical environment details confirmed or used during this session.
> Include OS, runtime versions, package manager, key dependencies and their versions,
> relevant environment variables (keys redacted), config file paths, deployment target,
> database type/version, cloud provider, ports, and anything env-specific that affected behavior.

- Key: Value
- Tool/lib: version

---

## 3. ARCHITECTURE & DESIGN DECISIONS
> Decisions made about how things are built. For each: what was decided, why, and what alternatives were explicitly considered or rejected.
> One entry per decision. Mark CONFIRMED if the approach was validated in this session.

### [Decision title]
- What: [what was decided]
- Why: [reasoning given]
- Alternatives rejected: [if any]
- Status: [CONFIRMED | UNVERIFIED | REVISIT]

---

## 4. WHAT WAS BUILT OR CHANGED
> A precise record of every file, function, component, schema, config, script, or system that was created or modified.
> Include: file path, what changed, and why. Group by feature or concern if helpful.

### [Feature / concern name]
- File: `path/to/file`
  - Change: [description]
  - Reason: [why this change was made]

---

## 5. ERRORS, BUGS & DEBUGGING SEQUENCES
> Every error encountered. For each: the exact error message or behavior, what caused it, and how it was resolved (or not).
> Preserve verbatim error text where possible. Mark unresolved issues clearly.

### [Short error label]
- Error: `[exact error message or behavior description]`
- Root cause: [cause]
- Fix applied: [what was done]
- Outcome: [RESOLVED | WORKAROUND | UNRESOLVED | NEEDS FOLLOW-UP]
- Notes: [any relevant context — environment-specific, timing-related, etc.]

---

## 6. COMMANDS, SCRIPTS & OPERATIONS RUN
> Every terminal command, script, migration, query, or manual operation executed.
> Include the full command exactly as run. Note outcome (success / failure / partial).

```bash
# [purpose]
[exact command]
# outcome: [success | failed | produced warning | etc.]
```

---
Documentation Signature
Updated by: Codex (GPT-5)
Timestamp: 2026-04-13T06:40:53.5558960-04:00
Change summary: Added the required signature section to the session learning extract template.

---

## 7. TECHNICAL LEARNINGS
> Things that were learned or confirmed that are broadly reusable — not just for this project.
> Includes: language behaviors, framework quirks, API gotchas, tooling nuances,
> performance insights, security implications, and patterns that apply more widely.
> Write each as a self-contained insight — assume no other context.

### [Learning title]
- Insight: [the learning, written to be fully understood out of context]
- Context: [what in this session surfaced this]
- Applies to: [language / framework / tool / general concept]
- Severity: [gotcha | best practice | fundamental | nice-to-know]

---

## 8. PROJECT-SPECIFIC PATTERNS & CONVENTIONS
> Conventions, naming rules, architectural patterns, or team-specific norms that were established,
> discovered, or reinforced during this session. These are rules that apply to this codebase specifically.

- [Pattern or convention — written as an actionable rule]

---

## 9. INCOMPLETE, DEFERRED & KNOWN ISSUES
> Everything that was identified but not finished, explicitly deferred, or known to be broken at session end.
> Include the exact state it was left in and any context needed to pick it up.

### [Item title]
- Status: [NOT STARTED | IN PROGRESS | BLOCKED | DEFERRED BY USER]
- Description: [what needs to be done]
- Blocking reason (if any): [dependency, decision needed, unclear requirement, etc.]
- Context to resume: [everything a future agent needs to pick this up cold]
- Priority: [HIGH | MEDIUM | LOW | UNKNOWN]

---

## 10. DEPENDENCIES, INTEGRATIONS & EXTERNAL SERVICES
> Any third-party libraries, APIs, services, or tools that were introduced, configured, or found to be relevant.
> Include version, purpose, any auth/config requirements, and any known limitations encountered.

- Name: [dependency/service]
  - Version: [x.y.z]
  - Purpose: [why it's used]
  - Config required: [env vars, keys, setup steps]
  - Limitations/gotchas: [anything discovered]

---

## 11. SECURITY & DATA CONSIDERATIONS
> Any security-relevant decisions, data handling requirements, or sensitive areas touched.
> Includes: auth logic, secret handling, input validation, permissions, PII handling, rate limiting, etc.
> Flag anything that needs review even if it seems fine now.

- [Security or data consideration — with NEEDS REVIEW flag if unvalidated]

---

## 12. PERFORMANCE & SCALABILITY NOTES
> Anything relevant to how the system behaves under load, at scale, or over time.
> Include: identified bottlenecks, optimizations applied, profiling results, known scaling limits.

- [Performance note]

---

## 13. USER INSTRUCTIONS & STATED PREFERENCES
> Anything the user said that amounts to a rule, constraint, or strong preference for how work should be done.
> Preserve the user's exact words wherever possible. These inform how future sessions should behave.

- "[verbatim or near-verbatim user instruction]"

---

## 14. OPEN QUESTIONS & UNRESOLVED AMBIGUITIES
> Questions that came up and were not answered, decisions that couldn't be made due to missing information,
> and areas where requirements were unclear or conflicting.

- Question: [the open question]
  - Context: [why it came up]
  - Impact: [what it blocks or affects]
  - Needs input from: [user | external service | team | documentation]

---

## 15. WHAT TO DO NEXT — RECOMMENDED ACTIONS
> A prioritized, opinionated list of next steps based on everything extracted above.
> Written as if handing off to a fresh agent starting a new session.
> Include enough context in each item to act without reading the full extract.

1. [Most critical next action] — [why, and what context is needed]
2. [Next action]
3. ...

---

## 16. NOTES & MISCELLANEOUS
> Anything that doesn't fit the above categories but should not be lost.
> Includes: things the user mentioned in passing, interesting observations, potential future ideas,
> references to external docs or resources, and any other signal worth preserving.

- [Note]

---

## APPENDIX: Post-Extraction Chat Log
> If the user continues chatting AFTER the extraction is produced, this appendix captures
> the full record of that post-extraction conversation. This ensures nothing is lost even
> if the session extends beyond the formal wrap-up.
> 
> Include: user messages, assistant responses, any decisions made, any new information shared.
> Preserve verbatim where possible. This section is appended to the extract when post-extraction
> chat occurs.

### Post-Extraction Exchange 1
- User: [verbatim or summary of user message]
- Assistant: [verbatim or summary of assistant response]

### Post-Extraction Exchange 2
- User: [verbatim or summary]
- Assistant: [verbatim or summary]

[Add more exchanges as needed. If no post-extraction chat occurred, leave this section empty or omit.]

---

## 17. DOCUMENTATION SIGNATURE
> Required by `C:\AI_STATION\hub\docs\AGENT_DOCUMENTATION_STANDARD.md`.

- Updated by: [agent name]
- Timestamp: [YYYY-MM-DDTHH:MM:SS±HH:MM]
- Change summary: [one-line summary of what changed or what this extract captured]
```
