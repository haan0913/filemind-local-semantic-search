# Research Paper: Engineering Trust in Agentic Systems

> **Full Title**: Engineering Trust in Agentic Systems: A Multi-Layered Framework for Enforcing Grounding in Local AI Agents  
> **Applied to**: FileMind Agent — `C:\AI_STATION\filemind\agent\run.py`  
> **Date Analyzed**: 2026-04-08  
> **PDF Location**: `C:\AI_STATION\file_management_research\Engineering Trust in Agentic Systems_ A Multi-Layered Framework for Enforcing Grounding in Local AI Agents.pdf`

---

## Executive Summary

This paper directly diagnoses the "kimi query" failure we experienced: agent skips search, falls back to parametric knowledge, returns ungrounded answer. It prescribes a **3-layer enforcement architecture** — input rails, pre-execution validation, and mandatory search-first protocol — implemented at the **code level**, not via prompts.

> "The agent's logic appears to default to its parametric knowledge when its primary retrieval mechanism fails, creating a false sense of success. This phenomenon is a classic example of an agent hallucinating."

---

## Root Cause Analysis (Paper's Diagnosis)

### Failure Cascade Identified
1. **First breakdown**: Code parsing failure — `<code >` with trailing space → parser rejects → tool never executes → `Out: None`
2. **Second breakdown**: Agent receives `None`, doesn't interpret as "no results" — enters retry loop with more malformed code
3. **Final breakdown**: Agent falls back to general knowledge base → returns ungrounded response about Kimi (Moonshot AI) → appears successful but is fabricated

> "This is a **silent failure mode**, where the system produces an output that appears plausible but is factually incorrect in the context of its designated purpose."

### Key Insight
> "Simply instructing an agent to 'use files' is insufficient; the system must be architecturally constrained to operate within a defined contract with its knowledge base."

**This confirms our suspicion: prompts alone cannot enforce grounding. Code must enforce it.**

---

## 3-Layer Enforcement Architecture

### Layer 1: Input Rails (Before LLM)
- Validate query falls within agent's operational domain
- For FileMind: if query is clearly external-topic, refuse immediately
- Framework reference: NVIDIA NeMo Guardrails

**Implementation status**: Partial — `_run_mandatory_search()` acts as input rail by running search before agent loop

### Layer 2: Pre-Execution Validation (During Generation)
- Validate code blocks before execution (use XML/JSON parser, not brittle regex)
- Strict tool argument validation (e.g., absolute paths only)
- Deterministic fallbacks: use Python functions for counting, not LLM generation

**Implementation status**: Partial — `code_block_tags` regex fix applied; tool validation still basic

### Layer 3: Mandatory Search-First Protocol (Core Logic)
- **Most critical layer**: Agent MUST execute `query_filemind` as first step for ANY query
- Only after search completes should agent proceed to other actions
- Explicit protocol for empty results: standardized message, NOT fabrication
- "This architectural constraint ensures that the agent's output is always, by design, built upon a foundation of retrieved evidence."

**Implementation status**: ✅ Implemented in `_run_mandatory_search()` + `_build_grounding_context()`

---

## Output Structuring Framework

### Day 1 (Immediate) — What We Need Now
1. Every response begins with clear statement: "Searching your local knowledge base for 'X'..."
2. Empty results → standardized disclaimer: "I searched for 'X' in your local files but found no relevant content."
3. All retrieved info must be cited: `[vector_store.py]: snippet...`
4. Source metadata for every piece of evidence

### Day 2 (Future) — Formal Separation
```
## Retrieved Evidence
[file_id=142, type=.py]: content snippet...
[file_id=287, type=.md]: content snippet...

## Reasoning & Synthesis
Based on the evidence above: [conclusion]
```

**Implementation status**: Day 1 partial — `_build_grounding_context()` provides evidence-first structure; Day 2 not yet implemented

---

## Multi-Model Swarm Architecture

The paper recommends specialized models per role, not one general-purpose model:

| Agent Role | Recommended Model | Ollama Tag | VRAM | Purpose |
|------------|------------------|------------|------|---------|
| **Primary Worker** | Gemma 3 4B | `gemma3:4b-q8_0` or `q4_K_M` | ~3-5 GB | Strong reasoning, code generation |
| **Critic/Validator** | Qwen 2.5 3B | `qwen2.5:3b-q4_K_M` | ~2.1 GB | Syntax checking, schema validation |
| **Fast Router** | Phi-4-mini 3.8B | `phi4:mini-q4_K_M` | ~2.0 GB | Intent classification, tool routing |
| **Meta-Orchestrator** | Gemma 3 4B (CPU) | `gemma3:4b-q2_K` | ~0 GB VRAM | Log parsing, rule generation |

**Total concurrent VRAM**: ~7.1 GB (fits in 12 GB RTX 3080 Ti with headroom)

**Key insight for our setup**: We're using `gemma4-e4b` (7.5B Q8_0, ~9GB) as our only agent model. The paper suggests this is over-provisioned for routing but under-performing for reasoning vs. the Gemma 3 4B. Consider pulling `gemma3:4b-q8_0` and `qwen2.5:3b-q4_K_M` for specialized roles.

---

## Automated Testing & Governance

### Structural Testing (Not Just Output Testing)
> "Instead of only testing the final output string, the tests must instrument the agent to log its internal state at each step of its reasoning process."

For the kimi query, a test should assert:
1. Agent generates `search_filemind` tool call (or search ran before agent)
2. Search returns expected result (or empty)
3. Final answer contains evidence from search OR standardized disclaimer

### Governance Process
- All changes to agent core logic → PR with justification
- PR must include tests proving groundedness is maintained
- Auditable trail of architectural decisions

---

## Performance Optimization Recommendations

1. **Aggressive quantization**: Use `q4_K_M` over `Q8_0` where quality is acceptable
2. **Asynchronous tool execution**: Wrap blocking I/O in thread pool executor
3. **Dynamic resource management**: Meta-agent monitors RAM/CPU, adjusts threads

---

## Phased Implementation Roadmap (From Paper)

### Phase 1: Foundation (DONE in this session)
- [x] Fix brittle code parsing (code_block_tags regex)
- [x] Mandatory search-first protocol in code (`_run_mandatory_search`)
- [x] Standardized empty result protocol (`_build_grounding_context`)
- [x] System prompt rewrite with explicit directives
- [x] Answer validation guardrail (`_validate_answer`)

### Phase 2: Transparency (Next Session)
- [ ] Source-cited evidence in all tool outputs
- [ ] Formal separation: Evidence section + Reasoning section
- [ ] Critic agent for output validation
- [ ] Input rail classifier (detect out-of-scope queries)

### Phase 3: Automation (Future)
- [ ] Structural test suite (trace execution, validate state at each step)
- [ ] KPI instrumentation per run
- [ ] Learning loop from logs → prompt refinement
- [ ] Multi-model swarm deployment

---

## Key Quotes for Reference

> "The failure occurs because the system lacks the necessary mechanisms to detect when a retrieval step has failed and to respond appropriately, instead opting for a fabricated answer."

> "This defense-in-depth strategy draws upon principles from AI safety, control theory, and robust software engineering to create a resilient framework."

> "By combining these layers of enforcement, the FileMind agent can be transformed into a system that is not merely prompted to be grounded, but is structurally compelled to be so."

> "A robust guardrail system is incomplete without a corresponding framework for automated testing and governance."

---

## References Worth Exploring (From Paper's Bibliography)

| # | Topic | Link |
|---|-------|------|
| 4 | Control-Theoretic Guardrails | https://arxiv.org/html/2510.13727v1 |
| 49 | Automated Structural Testing of LLM Agents | https://arxiv.org/html/2601.18827v1 |
| 52 | A Knowledge-Grounded Cognitive Runtime | https://arxiv.org/html/2603.25097v1 |
| 77 | GaRAGe Benchmark (Grounding Annotations) | https://arxiv.org/html/2506.07671v1 |
| 120 | Keyword Search Is All You Need (RAG Alternative) | https://arxiv.org/html/2602.23368v1 |
| 141 | RAGShield: Provenance-Verified Defense | https://arxiv.org/html/2604.00387v1 |
| 151 | MemMachine: Ground-Truth-Preserving Memory | https://arxiv.org/html/2604.04853v1 |
| 152 | Decision-Centric Design for LLM Systems | https://arxiv.org/html/2604.00414v1 |
