# FileMind — Cloud API Swarm Architecture

> **Date**: April 8, 2026
> **Status**: Planned for Phase 4+
> **Goal**: Hybrid local + cloud agent swarm for cost-effective scaling

---

## The Concept

**Local agents** (Gemma 4 e4b on RTX 3080 Ti) handle 80% of tasks:
- File operations, search, organization
- Knowledge base queries
- Routine reasoning tasks

**Cloud agents** (free/paid API models) handle the 20% that need it:
- Complex multi-step reasoning (Claude Sonnet, GPT-4o-mini)
- Large document summarization (free tier models)
- Specialized tasks (code review, research, creative writing)
- Tasks where local model quality is insufficient

## Architecture

```
[FileMind Orchestrator] (local Gemma 4 e4b)
       │
       ├─→ Can I handle this locally?
       │    ├─ YES → Use local tools (9 tools available)
       │    └─ NO  → Route to cloud swarm
       │
       └─→ [Cloud Swarm Router]
            ├─ Free tier: OpenRouter free models (Qwen, etc.)
            ├─ Paid tier: Claude, GPT-4, Gemini (when needed)
            └─ Results sanitized, validated, returned to local
```

## Cost Optimization Strategy

| Task Type | Model | Cost | When to Use |
|-----------|-------|------|-------------|
| File operations | Local Gemma 4 e4b | $0 | 80% of tasks |
| Simple reasoning | Local Gemma 4 e4b | $0 | Quick answers |
| Complex analysis | OpenRouter free (Qwen) | $0 | Multi-step reasoning |
| High-quality output | Claude Sonnet | ~$0.01/task | Important documents |
| Code generation | GPT-4o-mini | ~$0.005/task | Complex code tasks |
| Research | Gemini Pro (free tier) | $0 | Web search + synthesis |

## Implementation Plan (Phase 4+)

1. **API Key Registry**: Encrypted local store for provider keys
   - OpenRouter (free models)
   - Anthropic (Claude)
   - OpenAI (GPT-4o-mini)
   - Google (Gemini)

2. **Routing Rules**:
   ```python
   def route_task(task: str, complexity: int) -> str:
       if complexity <= 3:
           return "local"  # Gemma 4 e4b
       elif complexity <= 6:
           return "openrouter_free"  # Qwen free tier
       else:
           return "claude_sonnet"  # Paid, high quality
   ```

3. **Data Sanitization**: Before any cloud call:
   - Remove PII, API keys, sensitive paths
   - Replace with placeholders
   - Log what was sent for audit

4. **Result Validation**:
   - Cloud results come back → local critic validates
   - If valid → use result
   - If invalid → retry with different model

## Key Decision
**Don't build this until you have a concrete task that fails locally 3+ times.**
KPI logging will tell you when local model isn't enough.

---

*Documented: April 8, 2026 — Architecture planned, implementation deferred to Phase 4*
