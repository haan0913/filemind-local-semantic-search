# BGE-M3 Embedding Research Notes

## Key Findings — April 2026

FlagEmbedding's BGE-M3 provides both dense (1024-dim) and sparse lexical weights,
enabling hybrid BM25+vector search with Reciprocal Rank Fusion (RRF).

### Performance on AI_STATION corpus (3254 files)
- Indexing speed: ~45 files/min on CPU, ~320 files/min on CUDA
- Top search categories: code (1291), config (652), ai_project (567)

### Chunking strategy
- chunk_size=512 tokens, overlap=64
- Files >8K tokens split into overlapping segments
- Classification uses first 8K tokens only (sufficient for category detection)

## Next Steps
- Integrate Telegram bot for remote search queries
- Add nightly re-embedding for modified files
- Benchmark nomic-embed-text vs BGE-M3 on this corpus
