# Session Learning Extract — 2026-04-13

## 1. Session Goal
Conduct comprehensive research-driven architecture review of FileMind covering: real-time file watching (Windows + macOS), cross-platform strategy, scalability path to 100K users, and gap analysis between current state (Phase 1.5) and production-ready system.

## 2. Environment / System
- **OS**: Windows (win32), planning macOS migration
- **Hardware (Windows)**: RTX 3080 Ti (12GB VRAM), Ryzen 9 5900X, 32GB RAM
- **Hardware (macOS target)**: M1 Pro MacBook Pro, 16GB unified memory, 1TB SSD
- **Python**: 3.14 (FlagEmbedding fails C compilation)
- **Ollama models**: gemma4-e4b:latest, gemma4-e4b-json:latest, gemma4-26b:latest, llama3.2:latest, llama3:latest, nomic-embed-text:latest, gemma3:4b (added this session)
- **Index state**: ~3,838-4,804 files in SQLite catalog, ~405-1,585 chunks in Qdrant (~10% coverage)
- **Scan roots**: 8 directories (C:\AI_STATION, .kimi, Obsidian Vault, pc-focus, .cline, .claude, .openclaw, .agents)
- **Total PC data**: ~2TB mixed personal data (media + projects)

## 3. Key Decisions Made
1. **VM approach definitively rejected** for macOS — native port only
2. **Platform-specific builds** over unified abstraction layer — prioritize performance over compatibility
3. **Dual-engine Windows watcher**: watchdog (low-latency) + USN Journal (reliability/catch-up)
4. **Queue-based pipeline** over sequential processing — SQLite-backed queue (not Redis/RabbitMQ) for current scale
5. **Enterprise requires architectural pivot** — local-first → centralized client-server is a different product, not incremental
6. **USN Journal complexity acknowledged** — 500-800 lines of ctypes code minimum
7. **Phase 0.5 needed** — current technical debt must be fixed before Phase 1 architecture work

## 4. Changes Made
- Session learning extract document created (this file)
- SYSTEM_NOTES.md to be updated with new numbered items
- No code changes in this session — research/analysis only

## 5. Errors / Failures Encountered
- None (research session, no code execution)

## 6. Commands Executed
- None (research session)

## 7. Technical Learnings

### Real-Time File Watching
- **ReadDirectoryChangesW (watchdog)**: Kernel-level, millisecond latency, but fixed buffer (default 2048 bytes in watchdog) silently drops events on overflow. Recursive watch funnels ALL subdirectory events into single buffer.
- **USN Journal**: NTFS volume-level append-only log of all metadata changes. Survives reboots, enables catch-up after offline periods. Requires admin privileges (raw disk access). No mature Python libraries — requires ctypes with DeviceIoControl + FSCTL_QUERY_USN_JOURNAL + FSCTL_READ_USN_JOURNAL. USN_RECORD_V3 struct has variable-length fields. Journal wraps on full volumes (overwrites oldest entries). Each NTFS volume has separate journal.
- **Hybrid architecture**: watchdog as front-line (ms latency) + USN Journal as periodic catch-up (minutes/hours) + shared "dirty file" queue with dedup = production-grade design. Used by Everything (voidtools), docFetcher.

### macOS File Watching
- **FSEvents**: High-performance, permission-free, batches change events via GCD queue. Can stall if event stream not consumed quickly enough. No admin privileges required.
- **Metal/MPS acceleration**: sentence-transformers supports MPS backend for BGE-M3 on Apple Silicon. Ollama uses Apple Neural Engine. Unified memory means full 16GB available to ML workloads (vs 12GB dedicated VRAM on RTX 3080 Ti).
- **VM performance**: No GPU passthrough → CPU-only inference is order of magnitude slower. 16GB split → VM gets 6-8GB max. Not viable for always-on indexing.

### Linux File Watching
- **inotify**: Watch count limits (kernel resource), no native recursive support (must manually traverse and watch every subdirectory). Less scalable than USN Journal or FSEvents for 2TB scope.

### Architecture Critique
- **Sequential pipeline is primary bottleneck**: scan → extract → classify → embed → store blocks at each stage. GPU idle while CPU extracts, CPU idle while GPU embeds.
- **Queue-based pipeline**: SQLite-backed queue with SELECT FOR UPDATE pattern sufficient for current scale. Multiple workers pull jobs, process independently. Survives process crashes (jobs stay in queue).
- **Single point of failure**: nightly.py crashes halt entire system. Queue model solves this.
- **Concurrent write risk**: SQLite + Qdrant writes need atomic transactions (update metadata + vector together or not at all).
- **Vector index compaction**: Qdrant doesn't auto-delete stale vectors. Weekly vacuum needed: query all chunk file_ids → check disk existence → delete orphans → COMPACT if fragmentation > 20%.
- **Search telemetry**: Track zero-result queries, click patterns, query latency. Store in local SQLite for analysis.

### Scalability Numbers
| File Count | Sequential Pipeline | Queue-Based (8 workers) |
|-----------|-------------------|----------------------|
| 4,000 | ~2 min | ~30 sec |
| 50,000 | ~25 min | ~3 min |
| 200,000 | ~100 min (unacceptable) | ~12 min |
| 1,000,000 | ~500 min (broken) | ~60 min |

### Enterprise Architecture (100K users)
- Centralized index on server cluster
- Lightweight client watchers send events to Kafka ingestion
- Distributed Qdrant/Elasticsearch backend
- Multi-tenancy + RBAC
- CLI/dashboard become thin clients over network API
- Monumental undertaking — different product entirely

## 8. Patterns / Best Practices Identified
- **Verify don't trust labels**: "No real-time watcher yet" in README read like scope decision, not a gap. Agents moved on without asking why.
- **Platform-specific > unified abstraction** when performance is the priority. Complex patterns (Windows hybrid, FSEvents stall handling) can't be elegantly abstracted.
- **Queue-backed workers** for any pipeline with independent stages. Decouples CPU/IO/GPU work, enables parallelism, provides crash recovery.
- **Atomic transactions** for any multi-store update (SQLite + Qdrant).
- **Self-correcting systems**: watchdog overflow detection → auto-triggers USN Journal catch-up. Don't just log errors, act on them.

## 9. Deferred Items
- Phase 0.5 implementation (fix current gaps) — planned for next session
- Phase 1-4 implementation plan — approved conceptually, not yet started
- USN Journal ctypes implementation — complex, needs dedicated session
- macOS FSEvents native implementation — requires macOS hardware
- Enterprise architecture design document — long-term vision only
- Backup/restore strategy for index — mentioned but not designed
- FlagEmbedding replacement verification — unknown which alternative is in use

## 10. Dependencies
- **New**: SQLite-backed queue (no new dependency needed — uses existing sqlite3)
- **New**: ctypes for USN Journal (built-in Python)
- **Future**: Kafka for enterprise ingestion
- **Future**: OpenTelemetry for search telemetry
- **Current gap**: sentence-transformers returns empty dicts for BGE-M3 sparse vectors

## 11. Security Considerations
- USN Journal requires admin privileges — user must explicitly grant for full PC scanning
- Multi-tenancy/RBAC needed for enterprise version (currently zero auth)
- Raw disk access (USN Journal) has security implications — must be carefully scoped

## 12. Performance Optimizations Identified
- Dynamic batching for embedding workers (current batch size 8 is static)
- Metal multi-buffer model for macOS (CPU prepares buffer n while GPU processes n-1)
- GPU utilization profiling via Xcode Metal Performance HUD
- Watchdog buffer increase from 2048 bytes → 1MB
- Queue-based parallelism: 3-5x speedup on current hardware

## 13. User Instructions / Preferences
- Prioritize maximum performance over cross-platform compatibility
- Willing to maintain completely different builds for Windows vs macOS
- End goal: enterprise tool for 100K employees (dream version for sale)
- Current scope: personal workstation with 2TB data, tech enthusiast pushing boundaries
- Research-first protocol: Qwen generates prompts, delegates to dedicated research agent
- No deep research by Qwen autonomously — permanent governance rule

## 14. Open Questions
- Which FlagEmbedding replacement is currently in use for reranking? Is it working?
- What's the actual USN Journal wrap-around rate on a 2TB drive with heavy use?
- How to handle non-NTFS drives (exFAT, FAT32 USB drives) in scan roots?
- What's the optimal worker count for queue pipeline on Ryzen 9 5900X (12C/24T)?
- Should BGE-M3 be replaced with a newer embedding model?

## 15. Next Actions (Priority Order)
1. **Phase 0.5**: Fix current technical debt (sparse vectors, chunk coverage, classifier model, index noise, reranker verification)
2. **Phase 1A**: SQLite-backed queue-based pipeline refactoring
3. **Phase 1B**: Watchdog buffer fix (1MB + overflow detection)
4. **Phase 2A**: USN Journal ctypes implementation
5. **Phase 2B**: macOS FSEvents + Metal native implementation
6. **Phase 3**: Vector compaction + search telemetry + dead-letter queues
7. **Phase 4**: Enterprise architecture design document

## 16. Key Numbered Items for SYSTEM_NOTES.md
- Add items 96-110 covering: dual-engine watcher decision, queue-based pipeline, platform-specific builds, macOS native port, enterprise pivot acknowledgment, Phase 0.5 gap list, scalability numbers, research delegation protocol reinforced
