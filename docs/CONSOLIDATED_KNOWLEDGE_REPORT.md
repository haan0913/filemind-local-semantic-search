# Consolidated Knowledge Report
**Date:** 2026-04-08  
**Source:** Full system scan via FileMind (scan_report_20260408_144212.json)  
**Method:** 8 scan roots, 33 file types, safety-classified

---

## 1. SYSTEM OVERVIEW

### What AI_STATION Contains
| Item | Count | Size |
|------|-------|------|
| Total files on disk | 8,679 | 362.4 MB |
| Files in vector index | 3,987 | 134.7 MB (5,896 chunks) |
| Files NOT yet indexed | ~4,692 | — |
| Safety-classified | 8,620 (99.3%) | — |

### File Type Breakdown
| Type | Count | What It Is |
|------|-------|-----------|
| .md | 4,244 | Documentation, READMEs, agent specs, commands, prompts |
| .json | 1,953 | Configs, agent metadata, tool results, settings |
| .sh | 866 | Shell scripts (mostly OWL community use cases) |
| .py | 863 | Python code (FileMind, OWL, MemMachine, projects) |
| .txt | 492 | Requirements, notes, tool output captures |
| .ts/.tsx | 102 | TypeScript (Next.js dashboard, web UIs) |
| .log | 56 | Runtime logs (expected unknowns) |
| .html | 48 | Web pages (eval viewers, report templates) |
| .pdf | 5 | Research papers |

---

## 2. DIRECTORY MAP

### AI_STATION Top-Level (what exists)
```
C:\AI_STATION\
├── .index/              # FileMind vector DB (Qdrant + SQLite) — IMMUTABLE
├── agents/              # Agent specification markdown files (system-architect, etc.)
├── claude_config/       # Backup copy of Claude configs — MOVABLE (not active)
├── commands/            # Command specs (/sc:design, /sc:build, etc.)
├── config/              # API keys, .env files, profiles — PROTECTED
├── filemind/            # FileMind source code — PROTECTED (the tool itself)
├── filemind-deep/       # FileMind deep variant — PROTECTED
├── hub/                 # AI Hub project (Next.js dashboard, models, agents)
├── owl-agent/           # OWL multi-agent framework source
├── plugins/             # Claude plugins marketplace
├── projects/            # Project folders (pc-focus, turboquant, etc.)
├── security/            # API keys, credentials — PROTECTED
├── source/              # MemMachine source code
├── xmcp/                # X/Twitter API integration
├── README.md            # AI_STATION overview
├── CONSOLIDATION_PLAN.md # Original consolidation mission
└── vault/               # FileMind backups — MOVABLE
```

### External Scan Roots (outside AI_STATION)
```
C:\Users\amirk\.kimi\          # Kimi AI agent (configs, logs, owl-agent venv)
C:\Users\amirk\.cline\         # Cline AI agent
C:\Users\amirk\.claude\        # Claude Code agent
C:\Users\amirk\.openclaw\      # OpenClaw AI agent
C:\Users\amirk\.agents\        # Agent specifications
C:\Users\amirk\pc-focus\       # Personal project (Python)
C:\Users\amirk\Obsidian Vault  # NOT FOUND — may have been moved
```

---

## 3. SAFETY CLASSIFICATION

### IMMUTABLE (84 files — NEVER touch)
- Python venvs (.venv, site-packages, __pycache__)
- Ollama installation (C:\Users\amirk\AppData\Local\Programs\Ollama)
- Node modules
- Git repositories
- FileMind core infrastructure (run.py, config.py, .index)
- Active agent configs (.kimi/kimi.json, .kimi/config.toml, device_id)

### PROTECTED (6,160 files — needs approval to move)
- FileMind source code (excluding core files)
- OWL framework source
- Hub project (Next.js dashboard, models, agents)
- Plugin marketplace
- Agent specifications and commands
- User home config (.kimi, .cline, .claude, .openclaw, .agents)
- pc-focus personal project
- Source code (MemMachine)
- Config and security directories

### MOVABLE (2,376 files — safe to reorganize)
**By extension:**
| Type | Count | What |
|------|-------|------|
| .md | 1,348 | Vault backup copies, nested plugin duplicates |
| .json | 484 | Subagent metadata (agent-*.meta.json), claude_config copies |
| .sh | 272 | OWL community use case scripts (in nested copies) |
| .py | 126 | Backup copies of FileMind code in vault |
| .txt | 110 | Tool result captures, requirements in nested dirs |
| .ts | 24 | Dashboard copies in nested plugin dirs |
| .html | 12 | Eval viewer copies |

**Main MOVABLE sources:**
1. `filemind/vault/` — 6 timestamped backup sessions (run.py, SYSTEM_NOTES.md copies)
2. `claude_config/` — Full copy of Claude configs (not active, just backup)
3. `plugins/plugins/` — Double-nested plugin copies
4. `commands/commands/` — Double-nested command copies
5. `agents/agents/` — Double-nested agent spec copies

### UNCLASSIFIED (59 files — edge cases)
These are paths that don't match any safety pattern. Likely subdirectories of known roots
that the glob patterns don't catch. Low priority — can be addressed in Phase 2.

---

## 4. KEY PROJECTS DISCOVERED

### Active Projects
| Project | Location | Purpose |
|---------|----------|---------|
| **FileMind** | `C:\AI_STATION\filemind\` | PC-wide semantic file search (the tool we're using) |
| **AI Hub** | `C:\AI_STATION\hub\` | Next.js dashboard, model management, agent bridge |
| **OWL Agent** | `C:\AI_STATION\owl-agent\` | Multi-agent framework (Camel-AI based) |
| **MemMachine** | `C:\AI_STATION\source\memmachine\` | Memory system (episodic + semantic) |
| **pc-focus** | `C:\Users\amirk\pc-focus\` | Personal Python project |
| **Plugins** | `C:\AI_STATION\plugins\` | Claude Code plugin marketplace |

### Community/Example Projects (in owl-agent/)
- A-Share Investment Agent (Chinese stock analysis)
- Excel Analyzer (data analysis with OWL)
- Notion MCP integration
- Interview Preparation Assistant
- PHI Sanitization & Article Writing

### Research/Analysis Files
- Grounding framework research (RESEARCH_PAPER_GROUNDING_FRAMEWORK.md)
- Gemma4 reliability analysis (RESEARCH_PAPER_GEMMA4_RELIABILITY.md)
- Session learning extracts (SESSION_LEARNING_EXTRACT_20260408.md)
- System notes (74+ numbered items in SYSTEM_NOTES.md)

---

## 5. MODELS & INFRASTRUCTURE

### Ollama Models (7 installed)
| Model | Size | Purpose |
|-------|------|---------|
| gemma3:4b | 3.3 GB | **New classification model** (half VRAM of gemma4) |
| gemma4-e4b:latest | 8.2 GB | Primary agent model |
| gemma4-e4b-json:latest | 8.2 GB | JSON-optimized variant |
| gemma4-26b:latest | 12 GB | Heavy model (barely fits 12GB VRAM) |
| llama3.2:latest | 2.0 GB | Fast fallback |
| llama3:latest | 4.7 GB | Legacy |
| nomic-embed-text:latest | 274 MB | Embeddings |

### Key Infrastructure
- **Python runtime:** `C:\Users\amirk\.kimi\owl-agent\.venv\Scripts\python.exe`
- **Ollama:** `C:\Users\amirk\AppData\Local\Programs\Ollama\` (API at localhost:11434)
- **Vector DB:** Qdrant at `C:\AI_STATION\.index\qdrant\`
- **Catalog:** SQLite at `C:\AI_STATION\.index\filemind.db`
- **GPU:** RTX 3080 Ti (12GB VRAM)
- **CPU:** Ryzen 9 5950X

---

## 6. NOISE SOURCES IDENTIFIED

1. **Vault backups** — 6 session snapshots duplicating all FileMind files
2. **Nested directories** — `plugins/plugins/`, `commands/commands/`, `agents/agents/` (double/triple nesting)
3. **Subagent metadata** — JSON files like `agent-a3320572fb1cdae49.meta.json`
4. **Tool result captures** — `.txt` files from agent tool outputs
5. **Runtime logs** — 56 .log files (expected unknowns)
6. **Claude config backup** — `claude_config/` is a copy, not active configs

---

## 7. RECOMMENDED ACTIONS (Phase 1 — Safe Only)

### Immediate (MOVABLES only, zero risk)
1. **Archive vault backups** — Move 6 session snapshots to D: drive or compress
2. **Archive claude_config** — Move backup copy to archive (not active)
3. **Fix nested directories** — Remove double-nested `plugins/plugins/`, `commands/commands/`, `agents/agents/`
4. **Clean tool results** — Archive or delete `**/tool-results/*.txt` and `**/subagents/agent-*.meta.json`

### Requires Verification (PROTECTED)
5. **Reclassify .log files** — Add "log" as a category or accept as "unknown"
6. **Verify Obsidian Vault** — Path `C:/Users/amirk/Obsidian Vault` not found — locate or remove from scan roots
7. **Index missing files** — ~4,692 files found by scan but not in vector index

### Future (Phase 2-3 — Intelligent Migration)
8. Dependency-aware file movement (scan for references before moving)
9. Automated deduplication across all scan roots
10. Full re-index after cleanup to remove stale chunks

---

## 8. FILEMIND CAPABILITIES (Current State)

### Working
- [x] Smart chunking (AST for Python, structure for JSON, headers for Markdown)
- [x] Semantic search (BGE-M3 embeddings, CUDA accelerated)
- [x] Keyword search (FTS5 with custom tokenchars)
- [x] Hybrid RRF fusion (dense + keyword ranking)
- [x] Reranking (sentence_transformers CrossEncoder)
- [x] Dependency validation (check_deps.py auto-startup)
- [x] Safety classification (IMMUTABLE/PROTECTED/MOVABLE)
- [x] Pre-scan backups (backup_index.py)
- [x] Scan logging (scan_logger.py with JSON reports)

### Pending
- [ ] Sparse vectors (BGE-M3 lexical weights not extractable on Windows/Python 3.14)
- [ ] PDF text extraction (implemented, needs testing)
- [ ] YAML/TOML smart chunking (implemented, needs testing)
- [ ] gemma3:4b classification verification on unknown files

---

*Report generated by FileMind scan_logger.py — Session 20260408_144212*
