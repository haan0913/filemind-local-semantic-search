# FileMind — Quick Start (What Works RIGHT NOW)

## ✅ Working Today (Phase 0)

### Scan & Index
```bash
cd C:\AI_STATION\filemind

# Quick scan (detects changes, ~2 seconds for 3000+ files)
python -m filemind run.py scan

# Full pipeline (extract + chunk + embed + classify — takes longer)
python -m filemind run.py scan --full
```

### Search
```bash
# Hybrid search (keyword + semantic)
python -m filemind run.py "Python script for Telegram bot"

# Keyword only (FTS5)
python -m filemind run.py "configuration" --keyword

# Semantic only (vector)
python -m filemind run.py "machine learning" --semantic

# Filter by extension
python -m filemind run.py "test" --type .py
```

### System Info
```bash
# Index statistics
python -m filemind run.py stats

# Find duplicates
python -m filemind run.py duplicates

# Health check (Ollama, GPU, DB)
python -m filemind run.py health

# Verify index completeness
python -m filemind run.py verify
```

### Web UI
```bash
# Gradio dashboard (port 7860)
python -m filemind run.py dashboard

# FastAPI server (port 8000)
python -m filemind api.py
```

## 🚧 Agent (Session A — WORKING)

### Run Agent Commands
```bash
# Simple file operations
python agent/run.py "Count all .py files in C:\AI_STATION\filemind"
python agent/run.py "Find all config files in C:\AI_STATION"
python agent/run.py "Show me the FileMind index statistics"

# Search your knowledge base
python agent/run.py "Search for files about the Telegram bot"

# File system exploration
python agent/run.py "List files in C:\AI_STATION\filemind\tests"
python agent/run.py "Find all markdown files in C:\AI_STATION"
```

### Available Agent Tools
| Tool | What It Does |
|------|-------------|
| `find_files` | Find files by glob pattern (*.py, *.md, etc.) |
| `list_directory` | List files in a directory |
| `read_file` | Read file contents (up to 5KB) |
| `search_filemind` | Search the knowledge base |
| `shell_command` | Run safe shell commands |
| `filemind_stats` | Get index statistics |
| `python_interpreter` | Execute Python code |

## 📊 Current Index Stats
- **Files indexed**: ~3,254
- **Chunks in Qdrant**: 405
- **Top categories**: code (1291), config (652), ai_project (567), docs (357)
- **Top types**: .json (1169), .py (943), .js (337), .md (209)
- **Duplicates found**: 1,205 groups (needs cleanup)

## 🔧 If Something Breaks
```bash
# Restore from vault backup
xcopy "C:\AI_STATION\vault\filemind_2026-04-08_phase0-dense-only\src" "C:\AI_STATION\filemind" /E /I /H /Y

# Or restore database backup
xcopy "C:\AI_STATION\backups\filemind_20260408_pre_phase0" "C:\AI_STATION\filemind" /E /I /H /Y
```

---
*Last updated: April 8, 2026 — Phase 0 Complete*
