# FileMind Agentic OS — Master Project Plan

> **Vision**: Transform FileMind from a semantic search engine into a modular, local-first agentic AI operating system.
> **Hardware**: RTX 3080 Ti (12GB VRAM), Ryzen 9 5900X (12 cores), 32GB RAM, Windows 11
> **Runtime**: Python 3.14.3, Ollama (Gemma 4 e4b), Qdrant vector DB, SQLite + FTS5
> **Strategy**: Start small, establish a stable knowledge base, scale incrementally, monetize when viable, expand with more compute.

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Current State Assessment](#current-state-assessment)
3. [Architecture Blueprint](#architecture-blueprint)
4. [Workstream Breakdown](#workstream-breakdown)
5. [Phased Implementation Roadmap](#phased-implementation-roadmap)
6. [Milestone Definitions](#milestone-definitions)
7. [Testing Strategy](#testing-strategy)
8. [Dependency & Requirements Plan](#dependency--requirements-plan)
9. [Security & Privacy Framework](#security--privacy-framework)
10. [Research Topics](#research-topics)
11. [Checklists & Agendas](#checklists--agendas)
12. [Risk Register](#risk-register)
13. [Appendix: File Structure](#appendix-file-structure)

---

## Executive Summary

### Problem Statement
FileMind's indexing pipeline is **critically blocked** due to a C-compilation failure in the `FlagEmbedding` library under Python 3.14.3. Without a working index, no agent can reason over the user's files.

### Strategic Decision
Replace `FlagEmbedding` with `sentence-transformers` (pure PyTorch, no native compilation). This aligns with the project's commitment to **lightweight, compatible, pure-PyTorch** technologies and sets the foundation for a code-based agent framework (`smolagents`).

### Phased Approach
| Phase | Name | Goal | Deliverable |
|-------|------|------|-------------|
| **0** | Foundation & Stabilization | Unblock indexing pipeline, verify end-to-end pipeline | Working `nightly.py` with sentence-transformers |
| **1** | Agent Runtime | Establish smolagents-based orchestrator loop | Agent can receive commands, plan, execute Python code |
| **2** | Core Tooling | Provision essential tools | FileSystemTool, ShellTool, QueryFileMindTool |
| **3** | Secure Delegation | External model API pipeline | Sanitized, HITL-gated external model calls |
| **4** | Modular Expansion | Plugin-based architecture | Dynamic tool/agent loading from YAML registry |
| **5** | Multi-Agent System | Research sub-agent + collaboration | Dedicated research agent with network access |

---

## Current State Assessment

### What Works
- **Scanner** (`scanner.py`): mtime+MD5 change detection, ~2s for 3000+ files
- **Extractor** (`extractor.py`): PDF, DOCX, XLSX, PPTX, EML, text/code extraction
- **Catalog** (`catalog.py`): SQLite + FTS5, 3,254+ files indexed, schema migrations working
- **Vector Store** (`vector_store.py`): Qdrant with dense+sparse vectors, hybrid RRF search
- **Search** (`search.py`): Hybrid search (keyword + semantic), HyDE expansion, reranking
- **Classifier** (`classifier.py`): gemma4-e4b-json via Ollama, batch size 5, rule-based fallback
- **CLI** (`run.py`): 9 subcommands functional
- **UI**: Gradio dashboard + Vite-based web frontend
- **Deep Scan Variant** (`filemind-deep/`): Full-file MD5, 3,326 files indexed

### What's Broken
- **Embedder** (`embedder.py`): `FlagEmbedding` fails to install on Python 3.14.3 (C compilation, missing zlib.h)
- **Tests**: `test_modules.py` references stale `_parse_response()` method
- **Documentation**: Inconsistencies (LanceDB references vs Qdrant implementation)
- **OpenRouter Fallback**: Free models rotate frequently

### What's Missing
- Agent orchestration loop (no smolagents integration)
- Tool provisioning (no FileSystemTool, ShellTool, etc.)
- Secure delegation pipeline (no data sanitization, API gateway, HITL)
- Plugin-based architecture (tools hardcoded, not dynamically loadable)
- Multi-agent system (no research sub-agent)

---

## Architecture Blueprint

### Target Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    FileMind Agentic OS                       │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────┐   │
│  │                  User Interface Layer                 │   │
│  │  CLI (run.py)  │  Gradio Dashboard  │  Web UI (Vite) │   │
│  └──────────────────────────┬───────────────────────────┘   │
│                             │                                │
│  ┌──────────────────────────▼───────────────────────────┐   │
│  │              Orchestrator Agent Loop                  │   │
│  │         (smolagents CodeAgent + Gemma 4 e4b)          │   │
│  │                                                       │   │
│  │  Plan → Act → Observe → Iterate                      │   │
│  └───┬──────────┬──────────┬──────────┬─────────────────┘   │
│      │          │          │          │                      │
│  ┌───▼───┐  ┌───▼────┐  ┌─▼─────┐  ┌▼──────────────┐      │
│  │ FileSystem│  │Shell │  │Query  │  │External Model │      │
│  │Tool     │  │Tool  │  │FileMind│  │Delegation     │      │
│  │         │  │      │  │Tool    │  │Pipeline       │      │
│  └────────┘  └──────┘  └────────┘  └┬──────────────┘      │
│                                     │                      │
│  ┌──────────────────────────────────▼──────────────────┐   │
│  │              Knowledge Base Layer                    │   │
│  │  ┌──────────────┐  ┌─────────────┐  ┌────────────┐  │   │
│  │  │ SQLite + FTS5│  │ Qdrant      │  │ Classifier │  │   │
│  │  │ (file catalog│  │ (chunk vecs │  │ (gemma4    │  │   │
│  │  │  + metadata) │  │  dense+sparse│  │  e4b-json) │  │   │
│  │  └──────────────┘  └─────────────┘  └────────────┘  │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Security & Privacy Layer                │   │
│  │  Sandboxing │ RBAC │ HITL │ Data Sanitization │ MCP │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Embedding Library | `sentence-transformers` | Pure PyTorch, no C/Rust compilation, Python 3.14 compatible |
| Agent Framework | `smolagents` | Lightweight, HuggingFace-native, code-based (not schema-based), aligns with PyTorch ecosystem |
| Agent Paradigm | Code generation (not JSON schema) | Local models (Gemma) excel at code generation, more flexible, expressive |
| Model Target | Gemma 4 e4b (4B active, Q4_K_M) | Fits 12GB VRAM, ~2.4GB weights + 1.5GB KV cache + 0.7GB overhead = ~4.6GB total |
| Context Window | 8,192 tokens | Prevents OOM, 4B models degrade past 12K anyway |
| External Delegation | LiteLLM proxy + data sanitization + HITL | Centralized control, privacy preservation, human oversight |

---

## Workstream Breakdown

### Workstream A: Core Infrastructure & Indexing Pipeline
**Owner**: Primary Developer
**Priority**: P0 (Critical — blocks everything else)

| Task | File(s) | Description | Status |
|------|---------|-------------|--------|
| A1 | `embedder.py` | Replace FlagEmbedding with sentence-transformers | Pending |
| A2 | `embedder.py` | Adapt API interface (maintain `encode()`, `encode_with_normalization()`) | Pending |
| A3 | `requirements.txt` | Remove FlagEmbedding, ensure sentence-transformers pinned | Pending |
| A4 | `pyproject.toml` | Update dependencies | Pending |
| A5 | `nightly.py` | Test end-to-end pipeline with new embedder | Pending |
| A6 | `tests/test_modules.py` | Fix stale `_parse_response()` reference | Pending |
| A7 | `config.py` | Validate embedding config (model name, batch size, device) | Pending |
| A8 | Full pipeline | Run full scan on test subset, verify index population | Pending |

**Deliverable**: Working indexing pipeline that can scan, extract, chunk, classify, and embed files without compilation errors.

---

### Workstream B: Agent Framework Integration
**Owner**: Primary Developer
**Priority**: P1 (High — core agentic capability)

| Task | File(s) | Description | Status |
|------|---------|-------------|--------|
| B1 | `requirements.txt` | Add `smolagents` dependency | Pending |
| B2 | New: `agent/orchestrator.py` | Create smolagents CodeAgent wrapper for Ollama/Gemma | Pending |
| B3 | New: `agent/loop.py` | Implement Plan→Act→Observe loop with step limits | Pending |
| B4 | New: `agent/config.py` | Agent configuration (max steps, temperature, context window) | Pending |
| B5 | New: `agent/prompts.py` | System prompts for code generation, tool invocation | Pending |
| B6 | New: `agent/state.py` | Agent state management (history, observations, errors) | Pending |
| B7 | `api.py` | Replace /api/chat RAG endpoint with agent loop endpoint | Pending |
| B8 | `dashboard.py` | Add agent interaction tab to Gradio UI | Pending |

**Deliverable**: Agent can receive natural language commands, plan actions, generate Python code, execute it, and observe results.

---

### Workstream C: Tool Provisioning
**Owner**: Primary Developer
**Priority**: P1 (High — agent capabilities)

| Task | File(s) | Description | Status |
|------|---------|-------------|--------|
| C1 | New: `agent/tools/filesystem.py` | FileSystemTool (read, write, list, delete files) | Pending |
| C2 | New: `agent/tools/shell.py` | ShellTool (safe subprocess execution) | Pending |
| C3 | New: `agent/tools/search.py` | QueryFileMindTool (wraps SearchEngine.search) | Pending |
| C4 | New: `agent/tools/__init__.py` | Tool registry and base class | Pending |
| C5 | New: `agent/sandbox.py` | Code execution sandbox (restricted eval/os/subprocess) | Pending |
| C6 | `config.py` | Add tool permission configuration | Pending |
| C7 | New: `agent/modes.py` | Dual-mode system (Plan Mode = read-only, Normal Mode = full access) | Pending |

**Deliverable**: Agent has access to filesystem, shell, and search tools with sandboxed execution and dual-mode access control.

---

### Workstream D: Secure Delegation Pipeline
**Owner**: Primary Developer
**Priority**: P2 (Medium — external model augmentation)

| Task | File(s) | Description | Status |
|------|---------|-------------|--------|
| D1 | New: `agent/delegation.py` | External model delegation orchestrator | Pending |
| D2 | New: `agent/sanitization.py` | Data sanitization (PII detection, pseudonymization, redaction) | Pending |
| D3 | New: `agent/gateway.py` | AI Gateway/Proxy (LiteLLM integration) | Pending |
| D4 | New: `agent/hitl.py` | Human-in-the-Loop approval mechanism | Pending |
| D5 | `config.py` | Add external model configuration (API keys, models, rate limits) | Pending |
| D6 | New: `agent/audit_log.py` | Delegation audit trail (query, response, rationale) | Pending |

**Deliverable**: Agent can securely delegate complex tasks to external models with data sanitization, HITL approval, and full audit logging.

---

### Workstream E: Plugin-Based Architecture
**Owner**: Primary Developer
**Priority**: P3 (Lower — long-term extensibility)

| Task | File(s) | Description | Status |
|------|---------|-------------|--------|
| E1 | New: `agent/plugins/registry.py` | Plugin registry (YAML-based tool/agent definitions) | Pending |
| E2 | New: `agent/plugins/loader.py` | Dynamic plugin loader from `plugins/` directory | Pending |
| E3 | New: `agent/plugins/base.py` | Base plugin interface (ToolPlugin, AgentPlugin) | Pending |
| E4 | New: `plugins/` directory | Plugin directory structure | Pending |
| E5 | Refactor: `agent/tools/` | Convert existing tools to plugin format | Pending |
| E6 | New: `agent/plugins/schema.py` | Plugin schema validation and documentation | Pending |

**Deliverable**: Tools and sub-agents can be added by creating YAML configuration files and Python modules in `plugins/` directory.

---

### Workstream F: Multi-Agent System
**Owner**: Primary Developer
**Priority**: P4 (Lowest — future expansion)

| Task | File(s) | Description | Status |
|------|---------|-------------|--------|
| F1 | New: `agent/research_agent.py` | Dedicated research sub-agent | Pending |
| F2 | New: `agent/coordinator.py` | Multi-agent coordinator (task delegation, collaboration) | Pending |
| F3 | New: `agent/rbac.py` | Role-Based Access Control for agents | Pending |
| F4 | `config.py` | Agent role definitions and permissions | Pending |
| F5 | New: `agent/communication.py` | Inter-agent communication protocol | Pending |

**Deliverable**: Dedicated research agent with network access, governed by RBAC, collaborating with main orchestrator.

---

## Phased Implementation Roadmap

### Phase 0: Foundation & Stabilization (IMMEDIATE)

**Objective**: Unblock the indexing pipeline and establish a stable foundation.

#### Sprint 0.1: Dependency Resolution
**Duration**: 1 session
**Tasks**:
- [ ] A1: Refactor `embedder.py` to use `SentenceTransformer("BAAI/bge-m3")`
- [ ] A2: Maintain existing API (`encode()`, `encode_with_normalization()`, `get_embedder()`)
- [ ] A3: Update `requirements.txt` — remove `FlagEmbedding`, pin `sentence-transformers>=4.0.0`
- [ ] A4: Update `pyproject.toml` dependencies
- [ ] A5: Test import — `python -c "from sentence_transformers import SentenceTransformer; print('OK')"`

#### Sprint 0.2: Pipeline Verification
**Duration**: 1-2 sessions
**Tasks**:
- [ ] A6: Run `nightly.py` on small test subset (50-100 files)
- [ ] A7: Verify Qdrant population (check vector counts)
- [ ] A8: Verify SQLite catalog updates (check file_index table)
- [ ] A9: Run hybrid search, confirm results returned
- [ ] A10: Fix any runtime errors

#### Sprint 0.3: Test Suite Repair
**Duration**: 1 session
**Tasks**:
- [ ] A11: Fix `test_modules.py` — replace `_parse_response()` with `_parse_indexed_response()`
- [ ] A12: Run full test suite, document any remaining failures
- [ ] A13: Create `tests/test_embedder.py` for new sentence-transformers embedder

**Phase 0 Exit Criteria**:
- ✅ `python -m filemind run.py scan --full` completes without errors
- ✅ Qdrant vector count > 0 after indexing
- ✅ Hybrid search returns relevant results
- ✅ All tests pass (or documented known failures)
- ✅ Backup created of working state

---

### Phase 1: Agent Runtime Foundation

**Objective**: Establish the smolagents-based orchestrator loop.

#### Sprint 1.1: Framework Setup
**Duration**: 1-2 sessions
**Tasks**:
- [ ] B1: Install `smolagents`, verify compatibility with Python 3.14
- [ ] B2: Configure Ollama connection (model: `gemma4:e4b`, base: `http://localhost:11434`)
- [ ] B3: Create minimal agent that prints planned action and terminates
- [ ] B4: Test agent with simple command: `"list all .py files in C:/AI_STATION/filemind"`

#### Sprint 1.2: Agent Loop Implementation
**Duration**: 2-3 sessions
- [ ] B5: Implement full Plan→Act→Observe loop with max_steps=5
- [ ] B6: Add error handling (syntax errors, execution timeouts, retries)
- [ ] B7: Add observation capture and context accumulation
- [ ] B8: Add stop conditions (task complete, max steps, user interrupt)
- [ ] B9: Integrate with existing `api.py` /api/chat endpoint

**Phase 1 Exit Criteria**:
- ✅ Agent receives command, outputs Python code, executes it, returns result
- ✅ Agent handles errors gracefully (no crashes)
- ✅ Agent loop terminates within max_steps
- ✅ API endpoint `/api/chat` returns agent response

---

### Phase 2: Core Tooling

**Objective**: Provision the agent with essential tools.

#### Sprint 2.1: File System & Shell Tools
**Duration**: 2-3 sessions
- [ ] C1: Implement FileSystemTool (read_file, write_file, list_dir, delete_file)
- [ ] C2: Implement ShellTool (run_command with timeout, output capture)
- [ ] C3: Implement sandbox (restricted subprocess, no `eval()` with arbitrary code)
- [ ] C4: Test FileSystemTool: agent reads file, lists directory, writes file
- [ ] C5: Test ShellTool: agent runs `dir`, `python --version`, `git status`

#### Sprint 2.2: Search Tool & Integration
**Duration**: 1-2 sessions
- [ ] C6: Implement QueryFileMindTool (wraps `SearchEngine().search`)
- [ ] C7: Test search tool: agent queries index, receives results
- [ ] C8: End-to-end test: `"find all project reports from last quarter"`
- [ ] C9: Add dual-mode access control (Plan Mode = read-only)

**Phase 2 Exit Criteria**:
- ✅ Agent can read/write/list files via FileSystemTool
- ✅ Agent can run shell commands via ShellTool (with timeout)
- ✅ Agent can search knowledge base via QueryFileMindTool
- ✅ Plan Mode restricts to read-only operations
- ✅ Sandbox prevents dangerous operations

---

### Phase 3: Secure Delegation

**Objective**: Enable secure external model augmentation.

#### Sprint 3.1: Data Sanitization
**Duration**: 1-2 sessions
- [ ] D1: Implement PII detection (regex for emails, phones, IPs, API keys)
- [ ] D2: Implement pseudonymization (replace identifiers with fake data)
- [ ] D3: Implement field-level redaction (remove sensitive fields)
- [ ] D4: Test sanitization on sample data with known PII

#### Sprint 3.2: Gateway & HITL
**Duration**: 2-3 sessions
- [ ] D5: Integrate LiteLLM proxy for external model routing
- [ ] D6: Implement HITL approval flow (pause, present sanitized query, await approval)
- [ ] D7: Implement audit logging (query, response, timestamp, rationale)
- [ ] D8: End-to-end test: complex query → sanitize → HITL → external model → result

**Phase 3 Exit Criteria**:
- ✅ PII is detected and sanitized before external API call
- ✅ HITL approval required for external delegation
- ✅ All delegations logged to audit trail
- ✅ Agent can augment local reasoning with external model results

---

### Phase 4: Modular Expansion

**Objective**: Refactor to plugin-based architecture.

#### Sprint 4.1: Plugin Infrastructure
**Duration**: 2-3 sessions
- [ ] E1: Create plugin registry with YAML-based definitions
- [ ] E2: Implement dynamic plugin loader from `plugins/` directory
- [ ] E3: Define base plugin interface (ToolPlugin, AgentPlugin)
- [ ] E4: Convert FileSystemTool, ShellTool, QueryFileMindTool to plugins

#### Sprint 4.2: Universal Parser Development
**Duration**: 3-4 sessions
- [ ] Research: LLM-driven universal parsing (parse any format via LLM)
- [ ] Implement parser plugin for PDF, DOCX, XLSX beyond current extractor
- [ ] Test parser on diverse file types
- [ ] Document parser limitations and fallback strategies

**Phase 4 Exit Criteria**:
- ✅ New tools can be added via YAML config + Python module in `plugins/`
- ✅ Universal parser handles common formats with LLM assistance
- ✅ Plugin registry is queryable and documented

---

### Phase 5: Multi-Agent System

**Objective**: Introduce research sub-agent and multi-agent collaboration.

#### Sprint 5.1: Research Agent
**Duration**: 3-4 sessions
- [ ] F1: Implement research agent with web search and academic database access
- [ ] F2: Define RBAC roles (main agent vs research agent permissions)
- [ ] F3: Implement inter-agent communication protocol
- [ ] F4: Test research agent: `"research latest trends in agentic AI security"`

#### Sprint 5.2: Collaboration & Monetization
**Duration**: Ongoing
- [ ] F5: Implement task delegation between main agent and research agent
- [ ] F6: Explore monetization strategies (API access, premium features, consulting)
- [ ] F7: Evaluate compute expansion needs and plan accordingly

**Phase 5 Exit Criteria**:
- ✅ Research agent can perform web searches and return findings
- ✅ Main agent can delegate research tasks and receive results
- ✅ RBAC enforced for agent permissions
- ✅ Monetization strategy identified and initial revenue stream established

---

## Milestone Definitions

### M0: Pipeline Unblocked
**Trigger**: `nightly.py` completes full scan without errors
**Validation**:
```bash
python -m filemind run.py scan --full
# Output shows: Pipeline SUCCESS, Indexed: X files, Chunks: Y chunks
```
**Artifacts**: Modified `embedder.py`, updated `requirements.txt`, working Qdrant index

### M1: Agent Can Act
**Trigger**: Agent receives command, generates code, executes it, returns result
**Validation**:
```bash
# API call to /api/chat
# Command: "list all Python files in the project"
# Expected: Agent outputs Python code using FileSystemTool/ShellTool, returns file list
```
**Artifacts**: `agent/orchestrator.py`, `agent/loop.py`, tool base classes

### M2: Tools Operational
**Trigger**: Agent successfully uses all 3 core tools
**Validation**:
- FileSystemTool: reads/writes files correctly
- ShellTool: executes commands with timeout protection
- QueryFileMindTool: returns search results from index
**Artifacts**: All 3 tool implementations, sandbox, dual-mode access control

### M3: Secure Delegation Working
**Trigger**: External model call with sanitization + HITL + audit log
**Validation**:
- PII detected in sample query → sanitized → presented to user → approved → sent to external model → response received → logged
**Artifacts**: Delegation pipeline, sanitization module, HITL mechanism, audit log

### M4: Plugin Architecture Live
**Trigger**: New tool added via YAML config, loaded dynamically, functional in agent
**Validation**:
- Create `plugins/example_tool.yaml` + `plugins/example_tool.py`
- Agent can use example tool without code changes to core
**Artifacts**: Plugin registry, loader, base classes, converted tools

### M5: Multi-Agent System Operational
**Trigger**: Research agent performs web search, returns results to main agent
**Validation**:
- Command: `"research the latest developments in agentic AI"` → Main agent delegates to Research agent → Research agent searches → Results returned → Main agent synthesizes
**Artifacts**: Research agent, coordinator, RBAC, inter-agent protocol

---

## Testing Strategy

### Test Pyramid

```
                    ┌─────────────┐
                    │  E2E Tests  │    ← Full pipeline, agent workflows
                   ├───────────────┤
                  │ Integration   │    ← Tool testing, delegation pipeline
                 ├──────────────────┤
                │    Unit Tests     │  ← Individual modules, embedder, classifier
               ├──────────────────────┤
              │     Smoke Tests       │← Import checks, CLI commands, health checks
              └──────────────────────┘
```

### Testing Periods

| Period | When | What | Duration |
|--------|------|------|----------|
| **T0** | After Phase 0 | Embedder unit tests, pipeline integration tests | 1 session |
| **T1** | After Phase 1 | Agent loop unit tests, basic integration tests | 1-2 sessions |
| **T2** | After Phase 2 | Tool unit tests, sandbox penetration tests, E2E agent workflows | 2 sessions |
| **T3** | After Phase 3 | Sanitization tests, HITL flow tests, audit log verification | 1-2 sessions |
| **T4** | After Phase 4 | Plugin loading tests, dynamic registration tests | 1 session |
| **T5** | After Phase 5 | Multi-agent coordination tests, RBAC tests | 2 sessions |
| **Regression** | Every phase | Re-run all previous tests | 1 session |

### Test Categories

#### Unit Tests
- `tests/test_embedder.py`: sentence-transformers encode, batch processing, error handling
- `tests/test_orchestrator.py`: Agent initialization, prompt generation, step limiting
- `tests/test_tools.py`: Each tool's interface, input validation, output formatting
- `tests/test_sandbox.py`: Restricted operations, timeout enforcement, error handling
- `tests/test_sanitization.py`: PII detection accuracy, pseudonymization correctness

#### Integration Tests
- `tests/test_pipeline.py`: Full scan → extract → classify → embed pipeline
- `tests/test_agent_loop.py`: Agent receives command → plans → acts → observes
- `tests/test_delegation.py`: Sanitize → HITL → external call → response → audit
- `tests/test_plugins.py`: YAML config → load → register → agent can use

#### E2E Tests
- `tests/test_e2e.py`: Real-world scenarios:
  - "Find all Python files that import requests"
  - "Summarize the contents of my project directory"
  - "Research agentic AI security trends" (with delegation)

#### Smoke Tests
- Import all modules
- Run CLI commands (`scan`, `search`, `stats`, `health`)
- Verify Ollama connection
- Verify Qdrant connection
- Check GPU availability

---

## Dependency & Requirements Plan

### Immediate Dependency Changes

#### Remove
```
FlagEmbedding>=1.2.0  # Fails on Python 3.14 (C compilation, missing zlib.h)
                      # Also: BGE-M3 sparse/lexical weights NOT exposed via
                      # sentence-transformers — we ship dense-only for now
```

#### Add

**Phase 0 (Now):**
```
sentence-transformers>=4.0.0  # Pure PyTorch embedding library
```

**Phase 1+ (Agent Framework):**
```
smolagents>=1.0.0             # Lightweight agent framework (code-based, HuggingFace-native)
pydantic>=2.0.0               # Tool interface definitions, input/output validation
```

**Phase 3+ (Secure Delegation):**
```
litellm>=1.0.0                # AI Gateway/proxy for external model routing
```

#### Keep
```
qdrant-client>=1.10.0    # Vector database
torch>=2.1.0             # PyTorch backend for sentence-transformers
ollama>=0.1.0            # Local model runtime
pymupdf>=1.23.0          # PDF extraction
python-docx>=1.1.0       # DOCX extraction
openpyxl>=3.1.0          # XLSX extraction
python-pptx>=0.6.23      # PPTX extraction
extract-msg>=0.48.0      # EML/MSG extraction
gradio>=4.0.0            # Web dashboard
fastapi>=0.100.0         # REST API
uvicorn>=0.22.0          # ASGI server
watchdog>=3.0.0          # File watching (future)
pyyaml>=6.0              # YAML configs
tqdm>=4.66.0             # Progress bars
requests>=2.31.0         # HTTP client
pandas>=2.0.0            # Data manipulation
```

### Python Version Strategy

**Current**: Python 3.14.3 (experimental, causes compilation failures)
**Recommended**: Maintain Python 3.14.3 for now (sentence-transformers works), but prepare fallback to Python 3.12 LTS if additional compatibility issues arise.

**Rationale**: sentence-transformers uses pure PyTorch, which is compatible with Python 3.14. If future dependencies break on 3.14, we can create a Python 3.12 venv and maintain both.

### Hardware Resource Budget

| Component | VRAM (GB) | RAM (GB) | Notes |
|-----------|-----------|----------|-------|
| Gemma 4 e4b (Q4_K_M) | 2.4 | 0.5 | Quantized weights |
| KV Cache (8K context) | 1.5 | 0.3 | PagedAttention |
| Ollama Runtime | 0.7 | 0.5 | CUDA buffers |
| sentence-transformers | 2.0 | 1.0 | BGE-M3 model |
| Qdrant (in-memory) | 0.0 | 2.0 | Depends on index size |
| Python Runtime | 0.0 | 1.0 | FileMind processes |
| OS + Overhead | 0.0 | 4.0 | Windows + background |
| **Total** | **6.6 / 12** | **9.3 / 32** | **~55% VRAM, ~29% RAM** |

**Available Headroom**: ~5.4GB VRAM, ~22.7GB RAM — sufficient for agent loops, file operations, and multitasking.

---

## Security & Privacy Framework

### TRiSM Implementation Plan

| Pillar | Mechanism | Phase | Status |
|--------|-----------|-------|--------|
| **Trust** | Code-based tool invocation (not schema) | Phase 1 | Pending |
| **Risk** | Dual-mode access (Plan/Normal) | Phase 2 | Pending |
| **Security** | Sandboxed code execution | Phase 2 | Pending |
| **Privacy** | PII sanitization before external calls | Phase 3 | Pending |
| **Accountability** | Audit logging for all delegations | Phase 3 | Pending |
| **Transparency** | User-visible agent reasoning and actions | Phase 1 | Pending |

### Security Controls Matrix

| Control Area | Mechanism | Implementation | Phase |
|-------------|-----------|----------------|-------|
| Execution Isolation | Sandboxed subprocess | Restricted `os`/`subprocess`, no `eval()` | Phase 2 |
| Privilege Management | Dual-mode (Plan/Normal) | Read-only vs full access toggle | Phase 2 |
| Access Control | Tool-level permissions | Each tool declares required permissions | Phase 2 |
| External Communication | LiteLLM proxy | Centralized API routing, auth, rate limiting | Phase 3 |
| Privacy Protection | PII sanitization | Regex-based detection + pseudonymization | Phase 3 |
| Auditing | Delegation log | JSON audit trail with timestamps | Phase 3 |
| HITL | Approval flow | Pause → present → await → resume | Phase 3 |

---

## Research Topics

### Active Research Areas

| Topic | Question | Priority | Notes |
|-------|----------|----------|-------|
| **smolagents Compatibility** | Does smolagents work with Python 3.14? | P0 | Must verify before Phase 1 |
| **Gemma 4 e4b Tool Calling** | What's the optimal prompt format for tool calling? | P1 | Research prompt engineering |
| **Sandbox Design** | Best approach for Windows sandboxing? | P1 | Docker not ideal on Windows |
| **Universal Parsing** | Can LLMs reliably parse arbitrary file formats? | P3 | Explore for Phase 4 |
| **Multi-Agent Coordination** | How do agents collaborate without conflicts? | P4 | Research for Phase 5 |
| **Monetization Models** | What services can FileMind offer? | P4 | API, consulting, premium features |

### Research Artifacts to Create

1. `research/smolagents_compatibility.md` — Python 3.14 compatibility report
2. `research/gemma4_tool_calling.md` — Optimal prompt formats, benchmarking
3. `research/sandbox_design.md` — Windows sandboxing approaches, trade-offs
4. `research/security_threat_model.md` — Threat model for agentic OS
5. `research/monetization.md` — Revenue models, market analysis
6. `research/embedding_strategy.md` — Dense-only decision, when to add sparse/BM25

### Key Research Decision (2026-04-08): Dense-Only Embeddings

**Finding**: `sentence-transformers` does NOT expose BGE-M3's sparse/lexical weights.
These are learned model outputs — a tokenizer-based fallback would produce non-comparable
weight distributions and break hybrid ranking quality.

**Decision**: Ship with **dense-only vector search**. The Qdrant vector store already
handles this gracefully (`if sparse_dict:` check in `search_hybrid`). Dense cosine
similarity with BGE-M3 1024-dim vectors is high-quality on its own.

**When to add sparse**: Only if search relevance measurements show a clear gap that
sparse vectors would fill. Options then: FlagEmbedding (if Python 3.14 wheels exist),
BM25/SPLADE pipeline, or hybrid with Elasticsearch.

---

## Checklists & Agendas

### Pre-Session Checklist
Before each work session:
- [ ] Ollama running (`ollama list` shows models)
- [ ] Qdrant accessible
- [ ] GPU available (`nvidia-smi` shows RTX 3080 Ti)
- [ ] Virtual environment active
- [ ] Current code backed up (git commit or backup)
- [ ] Session goals defined (pick 1-3 tasks from plan)

### Phase 0 Session Agenda

#### Session 1: Fix Embedder
1. Read current `embedder.py`
2. Implement sentence-transformers replacement
3. Maintain existing API (`encode()`, `encode_with_normalization()`, `get_embedder()`)
4. Update `requirements.txt` and `pyproject.toml`
5. Test: `python -c "from filemind.embedder import get_embedder; e = get_embedder(); print(e.encode(['test']))"`
6. Commit changes

#### Session 2: Verify Pipeline
1. Run: `python -m filemind run.py scan --full`
2. Monitor output for errors
3. Check Qdrant: `python -c "from filemind.vector_store import VectorStore; vs = VectorStore(); print(vs.count())"`
4. Check SQLite: `python -c "from filemind.catalog import Catalog; c = Catalog(); print(c.count())"`
5. Run search: `python -m filemind run.py search "Python script"`
6. Fix any errors found

#### Session 3: Fix Tests & Backup
1. Fix `test_modules.py` stale method reference
2. Create `test_embedder.py` for new embedder
3. Run: `pytest tests/`
4. Document remaining failures
5. Create backup/archive of working state

#### Session 4+: Meta-Learning Loop & Prompt Automation (Workstream G)
**Status**: PLANNED — Do not start until session after current one is over
1. Create `prompt_optimizer.py` — reads recent session extracts, calls frontier model (Claude/GPT-4) for prompt/code improvement suggestions
2. Add `review_prompt_suggestions()` CLI — interactive approve/reject workflow with comments
3. Tag prompt versions in `agent/run.py`: `PROMPT_VERSION = "v1.3"` with date + justification
4. Add "Prompt Evolution" section to `PROJECT_PLAN.md` — log every change with session extract references
5. Create `generate_playbook.py` — auto-extract "Common failure patterns", "Guardrail recipes", "Model-specific quirks", "Tool usage examples" → `AGENT_PLAYBOOK.md`
6. **Session Learning Extract Enhancement**: Add logic to track "chicken out" moments — when the agent hesitates, skips search, or answers from parametric knowledge instead of using tools. Record these in the appendix of each session extract report with:
   - What the agent was asked
   - What it should have done (search first)
   - What it actually did (answered from knowledge / skipped tool)
   - Which model was running (e.g., `gemma4-e4b`)
   - Severity: high (fabrication), medium (partial search), low (correct but incomplete)
   - This creates a structured failure dataset for the meta-learning loop to optimize against

### Code Review Checklist
For each code change:
- [ ] Imports are correct (no missing, no unused)
- [ ] Error handling present (try/except with logging)
- [ ] Type hints added (function signatures, return types)
- [ ] Docstrings added (purpose, args, returns)
- [ ] Tests added or updated
- [ ] No hardcoded paths (use `config.py`)
- [ ] GPU memory managed (clear cache after large operations)
- [ ] Backward compatible (existing code not broken)

---

## Risk Register

| Risk | Probability | Impact | Mitigation | Owner |
|------|------------|--------|------------|-------|
| sentence-transformers fails on Python 3.14 | Low | High | Fallback to Python 3.12 venv | Primary |
| smolagents incompatible with Python 3.14 | Medium | High | Test before Phase 1, consider custom agent loop | Primary |
| Gemma 4 e4b poor tool calling quality | Medium | Medium | Optimize prompts, increase context window, use frontier model fallback | Primary |
| GPU OOM during embedding | Low | Medium | Reduce batch size, use CPU fallback, clear VRAM | Primary |
| Qdrant corruption on Windows | Low | High | Regular backups, WAL mode, fsync | Primary |
| External API costs (OpenRouter) | Medium | Low | Set budget caps, use free models, cache responses | Primary |
| Scope creep (too many features) | High | Medium | Strict phase gating, no feature creep within phases | Primary |
| Burnout (solo developer) | Medium | High | Sustainable pace, celebrate milestones, document progress | Primary |

---

## Appendix: File Structure

### Planned Directory Structure

```
C:\AI_STATION\filemind\
├── __init__.py
├── __main__.py
├── config.py                    # Central configuration
├── run.py                       # CLI entry point
├── scanner.py                   # File scanner
├── extractor.py                 # Content extractor
├── chunker.py                   # Text chunker
├── embedder.py                  # [MODIFY] sentence-transformers embedder
├── catalog.py                   # SQLite catalog
├── vector_store.py              # Qdrant vector store
├── classifier.py                # Ollama classifier
├── search.py                    # Hybrid search engine
├── duplicates.py                # Duplicate detection
├── nightly.py                   # Pipeline orchestrator
├── dashboard.py                 # Gradio dashboard
├── api.py                       # FastAPI REST API
├── memmachine_sync.py           # MemMachine integration
├── verify.py                    # Completeness verification
├── requirements.txt             # [MODIFY] Dependencies
├── pyproject.toml               # [MODIFY] Project metadata
│
├── agent/                       # [NEW] Agent framework
│   ├── __init__.py
│   ├── orchestrator.py          # smolagents CodeAgent wrapper
│   ├── loop.py                  # Plan→Act→Observe loop
│   ├── config.py                # Agent configuration
│   ├── prompts.py               # System prompts
│   ├── state.py                 # Agent state management
│   ├── sandbox.py               # Code execution sandbox
│   ├── modes.py                 # Dual-mode access control
│   ├── delegation.py            # External model delegation
│   ├── sanitization.py          # PII sanitization
│   ├── gateway.py               # AI Gateway (LiteLLM)
│   ├── hitl.py                  # Human-in-the-Loop
│   ├── audit_log.py             # Delegation audit trail
│   ├── coordinator.py           # Multi-agent coordinator
│   ├── rbac.py                  # Role-Based Access Control
│   ├── communication.py         # Inter-agent protocol
│   │
│   ├── tools/                   # [NEW] Tool implementations
│   │   ├── __init__.py          # Tool registry
│   │   ├── base.py              # Base tool class
│   │   ├── filesystem.py        # FileSystemTool
│   │   ├── shell.py             # ShellTool
│   │   └── search.py            # QueryFileMindTool
│   │
│   └── plugins/                 # [NEW] Plugin infrastructure
│       ├── __init__.py
│       ├── registry.py          # Plugin registry
│       ├── loader.py            # Dynamic plugin loader
│       ├── base.py              # Base plugin interface
│       └── schema.py            # Plugin schema validation
│
├── plugins/                     # [NEW] Plugin directory
│   └── (YAML configs + Python modules)
│
├── tests/
│   ├── __init__.py
│   ├── test_modules.py          # [MODIFY] Fix stale references
│   ├── test_reality.py          # Integration tests
│   ├── test_cli_behaviors.py    # CLI tests
│   ├── test_embedder.py         # [NEW] Embedder unit tests
│   ├── test_orchestrator.py     # [NEW] Agent loop tests
│   ├── test_tools.py            # [NEW] Tool tests
│   ├── test_sandbox.py          # [NEW] Sandbox tests
│   ├── test_sanitization.py     # [NEW] Sanitization tests
│   └── test_e2e.py              # [NEW] End-to-end tests
│
├── research/                    # [NEW] Research documentation
│   ├── smolagents_compatibility.md
│   ├── gemma4_tool_calling.md
│   ├── sandbox_design.md
│   ├── security_threat_model.md
│   └── monetization.md
│
├── researchapr8/                # Existing research
│   ├── Architecting FileMind_...pdf
│   └── Architecting FileMind_...txt
│
├── ui/                          # Existing web frontend
│   └── ...
│
├── .env                         # Environment variables
├── .env.template                # Template
├── README.md                    # Project overview
├── SYSTEM_NOTES.md              # Key learnings
└── PROJECT_PLAN.md              # THIS FILE — Master project plan
```

### Backup Strategy

Before any major changes:
1. Copy entire `filemind/` directory to `C:\AI_STATION\vault\filemind_YYYYMMDD_description\`
2. Export SQLite database: `sqlite3 C:/AI_STATION/.index/filemind.db ".backup backup.db"`
3. Export Qdrant collection state (if applicable)
4. Update `C:\AI_STATION\filemind\vault\MANIFEST.md` with new checkpoint

**Current backups:**
| Checkpoint | Path |
|-----------|------|
| Phase 0 (dense-only, all tests pass) | `C:\AI_STATION\vault\filemind_2026-04-08_phase0-dense-only\` |

---

## Workstream G: Meta-Learning Loop & Prompt Automation
**Owner**: Primary Developer
**Priority**: P2 (Medium — turns session data into systematic improvement)
**Status**: PLANNED — Do not start until next session

| Task | File(s) | Description | Status |
|------|---------|-------------|--------|
| G1 | New: `prompt_optimizer.py` | Weekly frontier model review of session extracts → suggests prompt/code improvements | Planned |
| G2 | New: `cli_review.py` | Interactive CLI to approve/reject suggestions with comments | Planned |
| G3 | `agent/run.py` | Add `PROMPT_VERSION` constant, version tracking | Planned |
| G4 | `PROJECT_PLAN.md` | Add "Prompt Evolution" section — log every change with justification | Planned |
| G5 | New: `generate_playbook.py` | Auto-generate AGENT_PLAYBOOK.md from accumulated extracts | Planned |
| G6 | Future: `fine_tune/` | Convert successful sessions into supervised fine-tuning examples (50-100+ examples needed) | Deferred (3-6 months) |

**Meta-Learning Loop Architecture**:
```
[Session Ends] → [Extract Saved to docs/ + vault/] → [learnings.jsonl updated]
   ↓
[Weekly: prompt_optimizer.py reads last 5-10 extracts]
   ↓
[Frontier model (Claude/GPT-4) analyzes patterns, suggests improvements]
   ↓
[User reviews via CLI — approve/reject with comments]
   ↓
[Approved changes deployed → new prompt version tagged]
   ↓
[PROJECT_PLAN.md updated with justification (governance)]
   ↓
[Next session runs with improvements]
```

**Design Principles**:
- Every automated suggestion requires explicit user approval before deployment
- Never overfit to recent sessions — weight older successful patterns
- Frontier suggestions always validated in sandbox before production deploy
- Fine-tuning requires careful eval — hold out test set
- Extracts remain human-readable — user is final arbiter

**Key Output Files** (planned):
- `AGENT_PLAYBOOK.md` — Living reference: failure patterns, guardrail recipes, model quirks, tool examples
- `prompt_versions.json` — Version history with diffs, justifications, outcomes
- `fine_tune/training_examples.jsonl` — Accumulated supervised examples for eventual LoRA fine-tuning

**Deliverable**: Self-improving agent system that learns from its own experience, with user firmly in governance loop.

---

## Glossary

| Term | Definition |
|------|-----------|
| **Agentic OS** | An operating system paradigm where an LLM acts as the "brain," orchestrating tools and tasks autonomously |
| **CodeAgent** | An agent that generates and executes Python code to accomplish tasks (smolagents paradigm) |
| **HITL** | Human-in-the-Loop: requiring human approval before certain actions |
| **MCP** | Model Context Protocol: emerging standard for secure tool use with LLMs |
| **PII** | Personally Identifiable Information: data that can identify individuals |
| **RBAC** | Role-Based Access Control: permissions assigned by role, not individually |
| **RAG** | Retrieval-Augmented Generation: augmenting LLM responses with retrieved context |
| **RRF** | Reciprocal Rank Fusion: combining ranked results from multiple search methods |
| **TRiSM** | Trust, Risk, and Security Management: framework for AI system governance |
| **Q4_K_M** | GGUF quantization format: 4-bit quantization, medium quality, small size |

---

*This document is a living artifact. Update as the project evolves.*
*Last updated: April 8, 2026*
*Next review: After Phase 0 completion*
