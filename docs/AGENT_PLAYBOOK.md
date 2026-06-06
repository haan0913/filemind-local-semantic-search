# Agent Playbook — Local AI Model Guidelines

**Created:** 2026-04-08  
**Version:** 1.0  
**Applies to:** FileMind agent, Ollama models, AI_STATION automation

> Update notice: current FileMind defaults now favor `gemma3:4b` for classification and tool-driven retrieval reliability. Legacy `gemma4-e4b` guidance below is preserved as historical context and lessons learned, not as the current default.

> Documentation updates to this file must follow `C:\AI_STATION\hub\docs\AGENT_DOCUMENTATION_STANDARD.md`.

---

## 1. MODEL SELECTION GUIDE

### When to Use Each Model

| Task | Model | Why | Expected Latency |
|---|---|---|---|
| **File classification** | gemma4-e4b-json | JSON output enforcement, reliable structure | ~1.5s |
| **Agent tool-calling** | gemma4-e4b | Primary agent, 9 tools available | ~1.4-1.7s |
| **Complex reasoning** | gemma4-26b | Heavy analysis, 25.2B params | ~10s+ (RAM-spilled) |
| **Simple lookup** | llama3.2 | Fast, 3.2B, fits easily | ~0.5s |
| **Query routing** | phi4:mini (planned) | Intent classification, tiny | ~0.3s |
| **Output validation** | qwen2.5:3b (planned) | Catch hallucinations, JSON | ~0.8s |
| **Embeddings** | nomic-embed-text | Text embeddings only | ~0.1s |
| **Semantic search** | BGE-M3 (local) | Dense + sparse vectors | ~0.2s |

### Decision Tree

```
User Query
    ↓
Is it a simple factual question?
  ├─ Yes → llama3.2 (fast)
  └─ No ↓
Does it require tool use (search, read file, run command)?
  ├─ Yes → gemma4-e4b (agent mode)
  └─ No ↓
Is it complex reasoning (multi-step analysis, code review)?
  ├─ Yes → gemma4-26b (if VRAM allows, else gemma4-e4b)
  └─ No ↓
Is it file classification?
  ├─ Yes → gemma4-e4b-json (JSON mode)
  └─ No → gemma4-e4b (general)
```

---

## 2. PROMPTING GUIDELINES

### gemma4-e4b (Agent Mode)

**DO:**
- Provide explicit tool-use instructions in system prompt
- Set `max_steps=5` to prevent spiraling
- Use mandatory search-first protocol (code, not prompt)
- Validate outputs via `_validate_answer()`

**DON'T:**
- Rely on prompts alone for grounding — use architectural constraints
- Allow unlimited steps — agent will spiral
- Assume search results are populated — handle empty results explicitly
- Trust model output without validation

**System Prompt Template:**
```
You are FileMind, an AI assistant for file management and code understanding.

MANDATORY PROTOCOL:
1. ALWAYS search the index FIRST before answering any question about files
2. If search returns empty results, state "No files found matching [query]" — DO NOT guess
3. Source all answers from indexed file content — never use general knowledge
4. Validate your answer against search results before responding

Available tools: [list of 9 tools]
Maximum steps: 5
```

### gemma4-e4b-json (Classification Mode)

**DO:**
- Use `/api/chat` endpoint with JSON Schema `format` parameter
- Set `temperature: 0.1`, `num_predict: 4096+`, `repeat_penalty: 1.2`
- Batch 5-8 files max per request
- Parse with strict JSON validation

**DON'T:**
- Use `/api/generate` endpoint — JSON format constraints don't work
- Set `think=false` — breaks format constraint (bug #15260)
- Batch >8 files — causes JSON failures
- Accept responses with markdown code blocks — strip them

**Classification Prompt Template:**
```
Classify the following file. Respond ONLY with a valid JSON object.

Required format:
{
  "category": "one of: code, config, documentation, ai_project, finance, data, media, system, unknown",
  "confidence": <number between 0.0 and 1.0>,
  "reason": "<brief explanation>"
}

File: {filepath}
Content summary: {first 500 chars}
Extension: {ext}

Respond with JSON only. No explanations, no markdown, no code blocks.
```

### llama3.2 (Fast Fallback)

**DO:**
- Use for simple factual questions
- Keep queries short and direct
- Set `temperature: 0.7` for conversational responses

**DON'T:**
- Use for file classification — not fine-tuned for JSON output
- Expect tool-calling reliability — fewer training examples
- Use for complex reasoning — 3.2B params limited

---

## 3. OLLAMA API PATTERNS

### Chat Completion (Standard)
```python
import requests

response = requests.post("http://localhost:11434/api/chat", json={
    "model": "gemma4-e4b",
    "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What files match this query?"}
    ],
    "stream": False,
    "options": {
        "temperature": 0.1,
        "num_predict": 4096,
        "repeat_penalty": 1.2
    }
})

result = response.json()["message"]["content"]
```

### JSON-Constrained Output
```python
response = requests.post("http://localhost:11434/api/chat", json={
    "model": "gemma4-e4b-json",
    "messages": [{"role": "user", "content": prompt}],
    "format": {
        "type": "object",
        "properties": {
            "category": {"type": "string"},
            "confidence": {"type": "number"},
            "reason": {"type": "string"}
        },
        "required": ["category", "confidence", "reason"]
    },
    "stream": False,
    "options": {
        "temperature": 0.1,
        "num_predict": 4096,
        "repeat_penalty": 1.2
    }
})

# Parse with validation
import json
try:
    result = json.loads(response.json()["message"]["content"])
    assert "category" in result
    assert "confidence" in result
except (json.JSONDecodeError, AssertionError):
    # Retry with rule-based fallback
    result = rule_based_classifier(filepath)
```

### Embedding Generation
```python
response = requests.post("http://localhost:11434/api/embed", json={
    "model": "nomic-embed-text",
    "input": "Text to embed"
})

embedding = response.json()["embeddings"][0]  # 768-dim vector
```

### Model Management
```python
# List models
models = requests.get("http://localhost:11434/api/tags").json()["models"]

# Show model info
info = requests.post("http://localhost:11434/api/show", json={"name": "gemma4-e4b"}).json()

# Unload model
requests.post("http://localhost:11434/api/generate", json={
    "model": "gemma4-e4b",
    "keep_alive": 0
})
```

---

## 4. KNOWN FAILURES & WORKAROUNDS

### Failure Mode 1: Agent Skips Search

**Symptom:** Agent answers from general knowledge without searching FileMind index.

**Root Cause:** gemma4-e4b has 18/42 shared KV layers + sliding window attention (SWA=512). Trades expressiveness for memory efficiency → less reliable tool-calling vs gemma3:4b.

**Workaround:**
- `_run_mandatory_search()` in CODE (not prompt) runs before agent loop
- `_build_grounding_context()` injects evidence into agent context
- `_validate_answer()` checks if answer is grounded in search results
- Still fails ~5% of the time — monitor and fix

**Long-term Fix:** Replace with gemma3:4b for tool-calling (better reliability)

---

### Failure Mode 2: JSON Output Contains Thinking Tags

**Symptom:** Response starts with `<think>...</think>` before JSON.

**Root Cause:** gemma4 trained with chain-of-thought — emits thinking even when not requested.

**Workaround:**
```python
import re
content = response.json()["message"]["content"]
# Strip thinking tags
content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
# Strip markdown code blocks
content = re.sub(r'```(?:json)?\n(.*)\n```', r'\1', content, flags=re.DOTALL)
# Parse JSON
result = json.loads(content.strip())
```

---

### Failure Mode 3: Classification Returns Truncated JSON

**Symptom:** JSON response cuts off mid-object: `{"category": "code", "confid`

**Root Cause:** `num_predict` default is 128 tokens — too short for classification with reason.

**Workaround:**
- Set `num_predict: 4096` minimum
- If truncated, retry with `num_predict: 8192`
- If still truncated, use rule-based classifier

---

### Failure Mode 4: Ollama Server Not Running

**Symptom:** `ConnectionError: HTTPConnectionPool(host='localhost', port=11434)`

**Workaround:**
```python
import subprocess

def ensure_ollama():
    try:
        requests.get("http://localhost:11434/api/version", timeout=2)
    except requests.ConnectionError:
        # Start Ollama GUI app
        subprocess.Popen([
            r"C:\Users\amirk\AppData\Local\Programs\Ollama\ollama.exe"
        ])
        # Wait for startup
        time.sleep(5)
```

---

### Failure Mode 5: VRAM Out of Memory

**Symptom:** Model fails to load, error mentions "out of memory" or "CUDA out of memory"

**Workaround:**
1. Unload other models: `curl http://localhost:11434/api/generate -d '{"keep_alive": 0}'`
2. Check VRAM: `nvidia-smi`
3. Use smaller model (llama3.2 instead of gemma4-e4b)
4. Reduce `num_ctx` in request options

---

## 5. PERFORMANCE OPTIMIZATION

### VRAM Management

| Strategy | VRAM Saved | Impact |
|---|---|---|
| Unload unused models | 2-8GB per model | Must reload for next use |
| Reduce `num_ctx` | 0.5-1GB | Shorter context window |
| Use Q4 quantization | 3-4GB vs Q8 | Slight quality loss |
| Run on CPU only | All VRAM free | 10x slower inference |

### Batch Processing

| Task | Batch Size | Notes |
|---|---|---|
| File classification | 5-8 files | Larger batches cause JSON failures |
| Embedding generation | 32-64 texts | BGE-M3 handles large batches efficiently |
| Query expansion | 1 query | Single query, expand with sparse weights |

### Caching

**What to Cache:**
- Embeddings for static files (don't change often)
- Classification results for files with same mtime + hash
- Search results for identical queries (TTL: 5 minutes)

**What NOT to Cache:**
- Agent responses (context-dependent)
- Large file scans (expensive, but content changes)
- Tool execution results (side effects)

---

## 6. MULTI-MODEL SWARM DESIGN (PLANNED)

### Architecture

```
┌─────────────────────────────────────────────────────┐
│ User Query                                           │
└──────────────────────┬──────────────────────────────┘
                       ↓
              ┌─────────────────┐
              │ phi4:mini       │ ← Router (intent classification)
              │ VRAM: 1.5GB     │
              └────────┬────────┘
                       ↓
         ┌─────────────┼─────────────┐
         ↓             ↓             ↓
    ┌──────────┐ ┌──────────┐ ┌──────────┐
    │llama3.2  │ │gemma3:4b │ │gemma4-e4b│ ← Workers
    │VRAM: 2GB │ │VRAM: 3.5 │ │VRAM: 8.7 │
    └────┬─────┘ └────┬─────┘ └────┬─────┘
         ↓             ↓             ↓
         └─────────────┼─────────────┘
                       ↓
              ┌─────────────────┐
              │ qwen2.5:3b      │ ← Critic (validation)
              │ VRAM: 2GB       │
              └────────┬────────┘
                       ↓
              ┌─────────────────┐
              │ Final Response  │
              └─────────────────┘
```

### Router Logic (phi4:mini)

```python
def route_query(query: str) -> str:
    """Classify query intent and route to appropriate model."""
    
    # Fast path: rule-based routing
    if any(kw in query.lower() for kw in ['what is', 'define', 'explain']):
        return 'llama3.2'  # Simple factual question
    
    if any(kw in query.lower() for kw in ['search', 'find', 'locate']):
        return 'gemma3:4b'  # Tool-calling required
    
    if any(kw in query.lower() for kw in ['analyze', 'compare', 'review']):
        return 'gemma4-e4b'  # Complex reasoning
    
    if any(kw in query.lower() for kw in ['classify', 'categorize']):
        return 'gemma4-e4b-json'  # JSON output required
    
    # Default: use phi4:mini for classification
    response = ollama_chat('phi4:mini', f'''
    Route this query to the appropriate model. Choose one:
    - "fast": Simple factual question (llama3.2)
    - "agent": Requires tool use (gemma3:4b)
    - "reasoning": Complex analysis (gemma4-e4b)
    - "json": Structured output (gemma4-e4b-json)
    
    Query: {query}
    
    Respond with one word only: fast, agent, reasoning, or json
    ''')
    
    routing = {
        'fast': 'llama3.2',
        'agent': 'gemma3:4b',
        'reasoning': 'gemma4-e4b',
        'json': 'gemma4-e4b-json'
    }
    return routing.get(response.strip().lower(), 'gemma4-e4b')
```

### Critic Logic (qwen2.5:3b)

```python
def validate_response(query: str, response: str, search_results: list) -> dict:
    """Validate that response is grounded in search results."""
    
    prompt = f'''
    Validate this response against the search results.
    
    QUERY: {query}
    
    SEARCH RESULTS:
    {chr(10).join([f"- {r['filepath']}: {r['content'][:200]}" for r in search_results])}
    
    RESPONSE:
    {response[:1000]}
    
    Check:
    1. Is every factual claim supported by search results?
    2. Are there any hallucinations or unsupported claims?
    3. Is the response relevant to the query?
    
    Respond with JSON:
    {{
      "valid": true/false,
      "issues": ["list of issues or empty array"],
      "confidence": 0.0-1.0
    }}
    '''
    
    result = ollama_chat_json('qwen2.5:3b', prompt)
    return result
```

### VRAM Budget for Swarm

| Model | Base VRAM | Loaded When | Unloaded When |
|---|---|---|---|
| phi4:mini | 1.5GB | Always (router) | Never |
| gemma3:4b | 3.5GB | Agent queries | After 10min idle |
| gemma4-e4b | 8.7GB | Reasoning queries | After 5min idle (large) |
| qwen2.5:3b | 2GB | Validation only | After 5min idle |
| BGE-M3 | 2.5GB | Embedding/semantic search | Never (always needed) |
| **Peak** | **10.2GB** | | |

---

## 7. VERSION HISTORY

| Version | Date | Changes |
|---|---|---|
| 1.0 | 2026-04-08 | Initial creation — consolidated from session extracts |

---

*This playbook is versioned. Update after every session that discovers new failure modes, optimization patterns, or model configurations.*

---
Documentation Signature
Updated by: Codex (GPT-5)
Timestamp: 2026-04-13T06:40:53.5558960-04:00
Change summary: Marked the playbook's gemma4 guidance as historical and linked the signed-documentation standard.
