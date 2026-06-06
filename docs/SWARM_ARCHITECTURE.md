# FileMind — Swarm Architecture & Resource Optimization

> **Research Date**: April 8, 2026
> **Source**: Deep research on local agent swarm patterns
> **Status**: Documented for future implementation (Phase 4+)

---

## Hardware Reality Check

| Resource | Your Spec | Per-Agent Cost (Gemma 4 e4b) | Practical Max |
|----------|-----------|------------------------------|---------------|
| **VRAM** | 12 GB (RTX 3080 Ti) | ~4.2 GB (LLM) + ~0.8 GB (embeddings) | **2 LLM instances** (GPU + CPU fallback) |
| **RAM** | 32 GB DDR4 | ~2-3 GB (context + tools + Qdrant) | **8-10 agents** before swapping |
| **CPU** | 5950X (16c/32t) | ~1-2 cores when thinking | **12-16 agents** if well-parallelized |
| **Disk I/O** | NVMe | Low unless heavy file ops | Not a bottleneck |

---

## The Key Insight: Tasks ≠ LLM Instances

**Don't spawn 10 independent LLM processes** — that wastes VRAM and creates contention.

**Do this instead:**
```
[Orchestrator Agent] (GPU, PRIMARY Gemma instance — shared)
       │
       ├─→ [Worker Pool: 4-6 async tasks]
       │    ├─ Tool execution threads (shell, file I/O)
       │    ├─ Embedding queue (CPU-bound, batched)
       │    └─ Vector search (Qdrant local, in-process)
       │
       └─→ [Critic/Monitor Agent] (same LLM, low-priority queue)
            ├─ Validates outputs
            ├─ Logs KPIs + learnings
            └─ Triggers retries or fallbacks
```

✅ **4-6 concurrent intelligent tasks with 1 LLM instance** using async/await + thread pools
✅ **2 LLM instances max** (one GPU, one CPU fallback) if truly parallel reasoning needed

---

## Estimated Performance (Your Hardware)

| Configuration | Avg Latency | Throughput | VRAM | Notes |
|--------------|-------------|------------|------|-------|
| **1 agent** (current) | 8-12 sec | 5-7 tasks/min | ~5.0 GB | Baseline |
| **2 agents** (shared LLM) | 10-15 sec | 8-10 tasks/min | ~5.5 GB | Async tooling helps |
| **2 agents** (dual LLM) | 15-25 sec | 4-6 tasks/min | ~9.5 GB | CPU fallback slows one |
| **4 agents** (async pool) | 12-20 sec | 12-15 tasks/min | ~6.2 GB | Best balance |
| **6+ agents** | 25-45 sec | 8-10 tasks/min | ~8-10 GB | Diminishing returns |

> ⚠️ **Critical**: Qdrant local mode loads entire index into RAM. If vector corpus >15GB, RAM becomes bottleneck before VRAM.

---

## Optimization Tactics (Ranked by Impact)

### 1. Model Quantization (Biggest VRAM Win)
```bash
ollama pull gemma4:e4b-q4_K_M  # ~3.8GB vs ~5.2GB for default
```
→ Frees ~1.4GB VRAM → potentially enables 3rd agent instance

### 2. Shared Embedder + Batched Encoding
```python
# One forward pass for many agents' queries
def encode_batch(texts: list[str], batch_size=16) -> np.ndarray:
    return model.encode(texts, batch_size=batch_size, normalize_embeddings=True)
```
→ Reduces GPU memory fragmentation, speeds up swarm embedding ops

### 3. Async Tool Execution
```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(max_workers=4)

async def run_tool_async(tool_name: str, **kwargs):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, lambda: tools[tool_name].forward(**kwargs))
```
→ Keeps LLM unblocked while tools run → higher throughput

### 4. Priority Queuing
```python
from queue import PriorityQueue

task_queue = PriorityQueue()
task_queue.put((1, "urgent_fact_check", "Verify dependency X"))
task_queue.put((10, "background_index", "Scan new files"))
```
→ Critical agents get GPU time first

---

## Meta-Agent: Self-Optimizing Swarm

Once KPIs are logging (✅ now implemented), add a background optimizer:

```python
# meta_agent.py — runs in background thread
def swarm_optimizer():
    while True:
        kpi = load_latest_kpi()
        if kpi["ram_usage_gb"] > 28:
            reduce_worker_pool(by=2)
        if kpi["avg_latency_sec"] > 20:
            switch_to_lighter_model("gemma4:e4b-q2_K")
        time.sleep(300)  # Check every 5 minutes
```

---

## Implementation Phases

| Phase | What | When |
|-------|------|------|
| **Now** (✅ Done) | KPI logging, single agent, learnings | Session B |
| **Phase 2** | Async tool wrappers, thread pool executor | Next |
| **Phase 3** | Priority queue, task scheduling | After Phase 2 |
| **Phase 4** | Meta-agent optimizer, dynamic scaling | After Phase 3 |
| **Phase 5** | Dual LLM instances (GPU + CPU fallback) | When needed |

---

## Decision Rule

**Don't add complexity until a specific bottleneck appears 3+ times.**

Current state: 1 agent, 2-step tasks, ~12 sec latency. This is perfectly usable.

Add swarm features only when:
- You need to run multiple tasks simultaneously
- Latency becomes unacceptable (>30 sec per task)
- RAM/VRAM pressure causes failures
- You have a concrete multi-agent use case

---

*Documented: April 8, 2026 — KPI logging implemented, swarm architecture planned for Phase 4+*
