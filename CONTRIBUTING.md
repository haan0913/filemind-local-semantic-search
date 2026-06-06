# Contributing to FileMind

## Development Setup

```powershell
# Clone and install
git clone https://github.com/YOUR_USERNAME/filemind.git
cd filemind
pip install -r requirements.txt

# Run tests
cd tests
python -m pytest
```

## Code Style

- Follow existing patterns in the codebase
- Docstrings on all public functions
- Logging instead of print statements
- Type hints where practical
- Try/except with logger.error, not silent failures

## Before Submitting Changes

1. **Backup the index** — any config change can affect scan results
   ```powershell
   robocopy C:\AI_STATION\.index C:\AI_STATION\vault\backups\index_$(Get-Date -Format yyyyMMdd_HHmmss) /E
   ```

2. **Run health check** — verify dependencies are functional
   ```powershell
   python run.py health
   ```

3. **Test search** — run a quick query to verify the pipeline
   ```powershell
   python run.py search "test" --top-k 3
   ```

## Architecture Decisions

- **Qdrant over LanceDB** — serverless local mode, native hybrid search with RRF fusion
- **BGE-M3 via sentence-transformers** — avoids Python 3.14 C-compilation issues with FlagEmbedding
- **Ollama for LLM** — local-first, no API keys, optional cloud fallback (OpenRouter)
- **Batch embedding** — sequential batches of 8 files to avoid VRAM OOM on 12GB GPU
- **Rule-based classifier fallback** — deterministic fast-path when Ollama is unavailable
- **Force reindex (`--rebuild`)** — recovers from interrupted scans without full rescan

See [docs/FILEMIND_V2_UPGRADE_PLAN.md](docs/FILEMIND_V2_UPGRADE_PLAN.md) for the full roadmap.
