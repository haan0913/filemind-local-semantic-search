# Research Paper: From Hallucination to Grounding — gemma4-e4b Reliability Framework

> **Full Title**: From Hallucination to Grounding: A System-Level Framework for Building Reliable Local Agents with gemma4-e4b  
> **Applied to**: FileMind Agent — `C:\AI_STATION\filemind\agent\run.py`  
> **Date Analyzed**: 2026-04-08  
> **PDF Location**: `C:\AI_STATION\file_management_research\From Hallucination to Grounding_ A System-Level Framework for Building Reliable Local Agents with gemma4-e4b.pdf`

---

## Executive Summary

This paper directly diagnoses **why gemma4-e4b fails at agentic tool-calling** despite being capable at general chat and code generation. It confirms our findings and adds critical model-specific analysis: gemma4-e4b's architectural efficiency trade-offs (shared KV layers, sliding window attention) may limit its expressiveness for structured multi-step workflows. It prescribes a tiered model strategy and Ollama parameter tuning.

---

## Root Cause Analysis: Why gemma4-e4b Fails at Tool-Calling

### Three Interconnected Failure Areas

1. **Model Architecture & Training Weaknesses**
   - gemma4-e4b uses **18 of 42 layers with shared KV weights** — efficiency technique that may constrain reasoning
   - Sliding window attention (SWA=512) trades expressiveness for memory footprint
   - Training data likely skewed toward conversational/open-ended tasks, not sequential tool execution
   - Smaller models excel at general chat but struggle with ReAct (Reason-Act-Observe) workflows

2. **Prompt Limitations Alone**
   - Despite CORE MANDATE, decision flowcharts, examples, and explicit rules — model still skipped `search_filemind()`
   - Model prioritizes "satisfying user intent" over "following strict protocol"
   - Defaults to pre-trained knowledge when retrieval fails → fabrication about Kimi (Moonshot AI)
   - "Prompts alone are often insufficient to guarantee deterministic behavior, especially under conditions of ambiguity or cognitive load"

3. **Absence of Programmatic Enforcement**
   - No checks/balances to validate tool execution outcomes
   - After parsing error → retry loop instead of signaling retrieval failure
   - After `Out: None` → generated fabricated response instead of disclaimer
   - "The agent's logic is not structurally constrained to operate within a defined contract with its knowledge base"

### Key Quote
> "The combination of potential model limitations, the inherent fallibility of prompts, and a lack of architectural constraints creates a perfect storm, resulting in an agent that is unreliable for its primary mission of grounded, data-driven reasoning."

---

## Gemma 3 4B vs Gemma 4 4B for Agentic Tasks

### Why Gemma 3 4B May Be More Reliable Currently

| Factor | Gemma 3 4B | Gemma 4 4B (e4b) |
|--------|-----------|-------------------|
| **Shared KV Layers** | None (all layers independent) | 18 of 42 layers shared |
| **Community Tuning** | Mature, well-established patterns | New, configuration still being explored |
| **Tool-Calling Stability** | Proven reliable in deployments | Inconsistent, requires system-level fixes |
| **Architecture Trade-offs** | Standard attention | Sliding window + shared KV for efficiency |
| **VRAM Usage** | ~3-5 GB (q8_0/q4_K_M) | ~9 GB (Q8_0) |
| **Prompt Adherence** | Strong for structured tasks | Variable under cognitive load |

### Conclusion
Gemma 4's efficiency optimizations (shared KV, SWA) reduce memory footprint but may limit its expressiveness for highly specialized tasks like structured tool-calling. Until Gemma 4's configuration patterns are better established, Gemma 3 4B remains the more reliable choice for agentic workflows.

---

## Ollama Parameter Tuning Recommendations

### Parameters to Experiment With

| Parameter | Current | Recommended Range | Purpose |
|-----------|---------|-------------------|---------|
| `num_ctx` | Default (8192?) | 16384-32768 | Larger context → better tool memory, fewer loops |
| `temperature` | 0.2 | 0.0-0.1 | More deterministic → fewer creative deviations |
| `repeat_penalty` | Default (1.1?) | 1.2-1.5 | Escape repetitive failure loops |
| `stop` tokens | `<turn|>` | Verify no interference | Prevent premature termination corrupting code blocks |

### Testing Strategy
1. Incrementally increase `num_ctx` → observe if tool-calling improves
2. Reduce `temperature` to 0.1 or 0.0 → force most probable token selection
3. Adjust `repeat_penalty` → discourage flawed reasoning repetition
4. Verify `<turn|>` stop token doesn't interfere with `<code>` block generation

> "By systematically testing these Ollama parameters—num_ctx, temperature, repeat_penalty, and stop token handling—it is possible to decouple the issue from the model's inherent architecture and arrive at a more robust, locally-configured solution."

---

## Tiered Model Strategy

### Proposed Agent Stack (Fits in 12GB VRAM)

| Agent Role | Recommended Model | Ollama Tag | VRAM | Status |
|------------|------------------|------------|------|--------|
| **Primary Worker** | Gemma 3 4B | `gemma3:4b-q8_0` or `q4_K_M` | ~4-5 GB | 🔄 Not installed |
| **Critic/Validator** | Qwen 2.5 3B | `qwen2.5:3b-q4_K_M` | ~2.1 GB | 🔄 Not installed |
| **Fast Router** | Phi-4-mini 3.8B | `phi4:mini-q4_K_M` | ~2.0 GB | 🔄 Not installed |
| **Meta-Orchestrator** | Gemma 3 4B (CPU) | `gemma3:4b-q2_K` | ~0 GB VRAM | 🔄 Not installed |
| **Current (fallback)** | Gemma 4 E4B | `gemma4-e4b:latest` | ~9 GB | ✅ Installed |

**Total concurrent VRAM**: ~7.1 GB (leaves ~5 GB headroom for embeddings + Qdrant + OS)

---

## Multi-Layered Guardrails (Reinforces Previous Paper)

### Layer 1: Input Rails
- Classify query before LLM invocation
- Early refusal for out-of-scope queries
- "I am an agent designed exclusively to search my local knowledge base. I cannot provide information about external topics like 'kimi'."

### Layer 2: Pre-Execution Validation
- Dedicated XML/JSON parser (not brittle regex)
- Strict tool argument validation (absolute paths, etc.)
- Deterministic Python functions for counting, not LLM generation

### Layer 3: Mandatory Search-First Protocol
- ✅ Implemented: `_run_mandatory_search()` before agent loop
- ✅ Implemented: `_build_grounding_context()` injects evidence
- Agent structurally constrained to operate on retrieved evidence

### Implementation Status
| Layer | Paper 1 (Engineering Trust) | Paper 2 (Hallucination to Grounding) | Our Implementation |
|-------|----------------------------|-------------------------------------|-------------------|
| Input Rails | Recommended | Recommended | Partial (pre-search acts as input rail) |
| Pre-Execution | Recommended | Recommended | Partial (regex fix, needs XML parser) |
| Mandatory Search | Critical | Critical | ✅ Implemented |
| Empty Result Protocol | Required | Required | ✅ Implemented |
| Output Structuring | Day 1/Day 2 | Day 1/Day 2 | Partial (Day 1 grounding) |
| Critic Agent | Recommended | Recommended | ❌ Not implemented |
| Ollama Tuning | Not discussed | Recommended | ❌ Not tested |
| Tiered Models | Recommended | Recommended | ❌ Not deployed |

---

## Optimization Recommendations

1. **Aggressive quantization**: Use `q4_K_M` over `Q8_0` where quality is acceptable
2. **Asynchronous tool execution**: Wrap blocking I/O in thread pool executor
3. **Dynamic resource management**: Meta-agent monitors RAM/CPU, adjusts threads
4. **Parallel task processing**: Shared LLM instances handle concurrent requests

---

## Phased Implementation Roadmap

### Phase 1: Foundation ✅ COMPLETE
- [x] Fix brittle code parsing (code_block_tags regex)
- [x] Mandatory search-first protocol in code
- [x] Standardized empty result protocol
- [x] System prompt rewrite with explicit directives
- [x] Answer validation guardrail
- [x] Research paper analysis (both papers)

### Phase 2: Transparency & Tuning (Next)
- [ ] Ollama parameter tuning (num_ctx, temperature, repeat_penalty, stop tokens)
- [ ] Source-cited evidence in all tool outputs
- [ ] Formal separation: Evidence section + Reasoning section
- [ ] Consider switching to `gemma3:4b-q8_0` as primary worker

### Phase 3: Multi-Model Swarm (Future)
- [ ] Pull `gemma3:4b-q8_0`, `qwen2.5:3b-q4_K_M`, `phi4:mini-q4_K_M`
- [ ] Implement critic agent for output validation
- [ ] Implement fast router for intent classification
- [ ] Deploy tiered model architecture

### Phase 4: Automation (Long-term)
- [ ] Structural test suite (trace execution, validate state)
- [ ] KPI instrumentation per run
- [ ] Learning loop from logs → prompt refinement
- [ ] Dynamic resource management

---

## Key Quotes

> "Smaller language models, despite their efficiency, often exhibit a performance gap when tasked with structured, multi-step agentic workflows like ReAct (Reason-Act-Observe), compared to their larger counterparts."

> "The model may misinterpret the implicit context of the prompt, particularly after encountering errors."

> "Without these programmatic safeguards, even a technically functional component like the vector store becomes ineffective if the surrounding agentic logic is unrestrained and prone to deviation."

> "This approach embodies a control-theoretic mindset, designing the system to move from refusal to recovery, where a failed retrieval triggers a controlled status update rather than a catastrophic failure."

---

## References Worth Exploring

| # | Topic | Link |
|---|-------|------|
| 4 | Testing Local LLMs for Function Calling | https://www.linkedin.com/pulse/testing-local-llms-function-calling-from-llama-qwen-vishalkharjul-rba5e |
| 5 | Running DeepSeek/Llama 3/Qwen Locally (GPU Guide) | https://dev.to/maxvyaznikov/running-deepseek-llama-3-and-qwen-locally-complete-gpu-requirements-guide-6fd |
| 6 | Structured Output Parsing Improvement | https://www.linkedin.com/posts/philipp-schmid-a6a2bb196_how-i-improved-the-structured-output-parsing-activity-7260970826441584641-PcDl |
| 10 | Qwen 2.5: A Party of Foundation Models | https://qwenlm.github.io/blog/qwen2.5/ |
| 11 | DeepSeek-V3, GPT-4, Phi-4, LLaMA-3.3 Code Generation | https://arxiv.org/pdf/2502.14926 |

---

## Comparison with Previous Paper

| Aspect | "Engineering Trust" (Paper 1) | "Hallucination to Grounding" (Paper 2) |
|--------|------------------------------|---------------------------------------|
| **Focus** | General agentic trust framework | Gemma 4-specific diagnosis |
| **Model Analysis** | Generic LLM hallucination | gemma4-e4b architectural trade-offs |
| **Key Insight** | Prompts alone insufficient | Shared KV layers + SWA limit expressiveness |
| **Configuration** | Not discussed | Ollama parameter tuning (num_ctx, temp, repeat_penalty) |
| **Model Recommendation** | Gemma 3 4B, Qwen 2.5 3B, Phi-4-mini | Same, with reasoning |
| **Uniqueness** | 3-layer enforcement architecture | Model-specific optimization guide |

**Together these papers provide**: (1) architectural framework + (2) model-specific tuning = complete grounding solution.
