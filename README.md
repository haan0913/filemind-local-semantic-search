# FileMind — Local Semantic File Search

A local-first semantic file search engine for Windows. Indexes your PC with hybrid Qdrant vector search (dense + sparse), BGE-M3 embeddings, and local LLM classification via Ollama. Zero cloud dependency.

**Status:** v2 — Clean rebuild verified
**Last Updated:** 2026-04-16

---

## What It Does

- **Scan** your directories for files (configurable roots, noise filtering)
- **Extract** content from PDFs, DOCX, code, text, JSON, YAML, and more
- **Classify** files into categories (code, config, documentation, ai_project, etc.) using local Ollama LLM with rule-based fallback
- **Chunk & Embed** with BGE-M3 (dense + sparse vectors, CUDA accelerated)
- **Search** with hybrid RRF fusion of semantic + keyword + sparse signals
- **Rerank** with cross-encoder for improved relevance
- **Deduplicate** exact and near-duplicate files

---

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│   Scanner   │────▶│  Extractor   │────▶│  Classifier  │
│  os.walk()  │     │  PyMuPDF     │     │  Ollama LLM  │
│  + change   │     │  python-docx │     │  + rule-base │
└─────────────┘     └──────────────┘     └──────────────┘
                                                  │
                                                  ▼
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  Search API │◀────│ Vector Store │◀────│  Chunker     │
│  RRF fusion │     │  Qdrant      │     │  TextSplitter│
│  + rerank   │     │  dense+sparse│     │  chunk_size  │
└─────────────┘     └──────────────┘     └──────────────┘
```

### Key Components

| Component | File | Purpose |
|---|---|---|
| **Scanner** | `scanner.py` | Directory walk, change detection (mtime + MD5) |
| **Extractor** | `extractor.py` | Multi-format content extraction (PDF, DOCX, text) |
| **Classifier** | `classifier.py` | Ollama LLM + RuleBasedClassifier fallback |
| **Chunker** | `chunker.py` | Text splitting with configurable sizes |
| **Embedder** | `embedder.py` | BGE-M3 dense + sparse vector generation |
| **Vector Store** | `vector_store.py` | Qdrant with hybrid search (RRF fusion) |
| **Search Engine** | `search.py` | Hybrid search + cross-encoder reranking + HyDE |
| **Index Pipeline** | `nightly.py` | `run_index_pipeline()` implementation plus compatibility aliases for the on-demand CLI pipeline |
| **CLI** | `run.py` | Command-line interface |

---

## Installation

### Prerequisites

- **Python 3.12** via the AI_STATION `semantic-core` venv (`C:\AI_STATION\venvs\semantic-core\Scripts\python.exe`)
- **NVIDIA GPU with CUDA** (tested on RTX 3080 Ti, 12GB VRAM) — CPU fallback works but is intentionally slow
- **CUDA-enabled PyTorch** in `semantic-core`; bootstrap enforces `torch==2.11.0+cu130` from `https://download.pytorch.org/whl/cu130` when `nvidia-smi` is available
- **Ollama** (optional, for LLM classification and HyDE query expansion)

### Setup

```powershell
# Clone the repo
git clone https://github.com/YOUR_USERNAME/filemind.git
cd filemind

# Install/update the AI_STATION semantic runtime
powershell -ExecutionPolicy Bypass -File C:\AI_STATION\projects\source\ai_station_context\scripts\bootstrap_semantic_core.ps1

# Verify installation
C:\AI_STATION\venvs\semantic-core\Scripts\python.exe C:\AI_STATION\filemind\run.py runtime
```

### Ollama Setup (Optional)

Ollama is only needed for LLM classification and HyDE query expansion. The search engine works without it.

1. Install [Ollama for Windows](https://ollama.com/download)
2. Pull required models:
   ```
   ollama pull gemma4-e4b-json   # File classification
   ollama pull llama3             # HyDE query expansion
   ```
3. Verify: `curl http://localhost:11434/api/tags`

### Environment Variables (Optional)

Copy `.env.template` to `.env` and configure:

```env
OLLAMA_API_URL=http://localhost:11434
ENABLE_RERANKING=false
HYDE_ENABLED=false
LOG_LEVEL=INFO
DASHBOARD_PORT=7860
```

---

## Usage

### Scan & Index

```powershell
# Quick scan (detect changes only)
python run.py scan

# Full pipeline (extract, embed, classify)
python run.py scan --full

# Clean full rebuild from source (shared Qdrant recommended)
python run.py scan --rebuild
```

`scan --rebuild` now resets the live FileMind chunk collection and repopulates it from retained catalog files so stale vector payloads do not survive across full rebuilds.

### Search

```powershell
# Hybrid search (default)
python run.py search "authentication API configuration"

# Keyword only
python run.py search "database connection" --keyword

# Semantic only
python run.py search "file management architecture" --semantic

# With filters
python run.py search "config" --type .py --category config

# With reranking
python run.py search "embeddings" --rerank

# With HyDE query expansion (Ollama required)
python run.py search "vector search pipeline" --hyde

# Interactive REPL mode
python run.py interactive
```

### Statistics & Health

```powershell
# View index statistics
python run.py stats

# System health check
python run.py health

# Verify effective scan scope vs catalog/vector parity
python run.py verify

# Find duplicates
python run.py duplicates

# Launch web dashboard
python run.py dashboard
```

### Classify Unclassified Files

```powershell
# Run classification on files with "unknown" category
python run.py classify
```

---

## Configuration

Edit `config.py` or set environment variables.

### Key Settings

| Setting | Default | Description |
|---|---|---|
| `SCAN_ROOTS` | AI_STATION + more | Directories to scan |
| `SKIP_DIRS` | .git, __pycache__, etc. | Directories to skip |
| `CHUNK_SIZE` | 2048 | Tokens per chunk |
| `CHUNK_OVERLAP` | 256 | Overlap between chunks |
| `MAX_FILE_SIZE` | 500KB | Max file for content extraction |
| `TIER1_MAX_SIZE` | 1MB | Tier 1 file size limit |
| `TIER2_MAX_SIZE` | 10MB | Tier 2 file size limit |
| `ENABLE_RERANKING` | false | Cross-encoder reranking |
| `HYDE_ENABLED` | false | HyDE query expansion |
| `CATEGORIES` | 10 categories | Classification categories |

### Scan Roots

By default, FileMind scans:
- `C:\AI_STATION` (primary workspace)
- `C:\Users\amirk\.kimi` (agent directory)
- `C:\Users\amirk\Obsidian Vault` (personal notes)
- `C:\Users\amirk\pc-focus` (personal project)
- `C:\Users\amirk\.cline`, `.claude`, `.openclaw`, `.agents` (agent configs)

**Add your own:** Edit `SCAN_ROOTS` in `config.py`. Add directories to `SKIP_DIRS` to exclude them.

---

## Project Structure

```
filemind/
├── agent/                  # Smolagents CodeAgent (Ollama integration)
├── docs/                   # Documentation
│   ├── LOCAL_MODEL_REGISTRY.md
│   ├── FILEMIND_V2_UPGRADE_PLAN.md
│   ├── AGENT_PLAYBOOK.md
│   ├── BACKUP_VERSION_STRATEGY.md
│   └── ...
├── tests/                  # Test suite
├── ui/                     # Dashboard UI
├── vault/                  # Session vault (not in repo)
│
├── catalog.py              # SQLite file index with FTS5
├── vector_store.py         # Qdrant vector store (hybrid search)
├── search.py               # Search engine (RRF fusion, reranking, HyDE)
├── scanner.py              # Directory scanner with change detection
├── extractor.py            # Multi-format content extraction
├── chunker.py              # Text chunking
├── embedder.py             # BGE-M3 embeddings (CUDA)
├── classifier.py           # Ollama LLM + rule-based classification
├── nightly.py              # Index pipeline implementation and compatibility aliases
├── duplicates.py           # Exact + semantic duplicate detection
├── run.py                  # CLI entry point
├── config.py               # Central configuration
│
├── requirements.txt
├── pyproject.toml
├── .gitignore
└── README.md
```

---

## Current Status (2026-04-16)

### What's Working ✅
- Hybrid search over shared Qdrant plus BM25, with `run.py verify` confirming catalog/vector parity
- Clean `scan --rebuild` behavior that resets the live FileMind collection and rebuilds it from source files
- Force reindex safety for deleted and out-of-scope paths, including stale chunk cleanup when extraction is empty
- Longer catalog summaries (up to the configured content budget) so rebuilds are not poisoned by stale short text
- Automatic offline Hugging Face loading when `BAAI/bge-m3` is already cached locally
- Query operators (`type:` and `in:`), reranking support, HyDE support, duplicate detection, and interactive REPL mode

### Verified Corpus Snapshot
- Effective files on disk: 2,909
- Catalog entries: 2,909
- Files with extracted content: 2,818
- Files with embeddings: 2,818
- Shared Qdrant chunks: 23,121
- BM25 chunks: 23,121
- Verification status: 100.0% completeness, chunk parity OK

### Known Limitations ⚠️
- The current `sentence-transformers` BGE-M3 path returns empty lexical weights, so Qdrant's sparse prefetch is effectively inactive; BM25 still provides the lexical leg, but true BGE sparse retrieval is not live yet
- No real-time file watcher yet; indexing is still operator-triggered
- The first-prompt lazy-start / switchboard UI is not built yet
- Some deeper historical docs still use older "nightly" wording

### Planned Next 📋
1. Resolve the lexical retrieval plan explicitly: either restore true BGE-M3 sparse weights in the live stack or formalize BM25 as the supported lexical leg and simplify the Qdrant path accordingly
2. Move `scan --rebuild` to an alias-backed shadow rebuild so full reindexes can swap atomically with fast rollback
3. Build the lazy-start / switchboard UI layer on top of the stable on-demand pipeline
4. Continue doc cleanup for older "nightly" references outside the main user-facing guides
5. Revisit default reranking and HyDE behavior after more retrieval QA on the corrected lexical path

See [FILEMIND_V2_UPGRADE_PLAN.md](docs/FILEMIND_V2_UPGRADE_PLAN.md) for the full roadmap.

---

## Backup & Version Strategy

FileMind follows a strict backup policy before any destructive operation:
- Pre-scan index backup → `vault/backups/index_YYYYMMDD_HHMMSS/`
- Pre-config-change code backup → `vault/backups/code_YYYYMMDD_HHMMSS/`
- Post-session docs backup → `vault/backups/docs_YYYYMMDD_HHMMSS/`

See [BACKUP_VERSION_STRATEGY.md](docs/BACKUP_VERSION_STRATEGY.md) for details.

---

## License

[TODO — add your license]

---

*Built for local-first AI-powered file management. No cloud, no API keys (except optional OpenRouter fallback), all data stays on your machine.*
