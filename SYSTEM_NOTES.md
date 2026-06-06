# System Notes

## Internet Access Limitation
- **No general internet search access** - cannot browse Google, DuckDuckGo, etc.
- Can still make HTTP requests to specific APIs (OpenRouter, Ollama localhost)
- Cannot rely on external free models being available (they rotate/deprecated)
- **Primary strategy should always be LOCAL Ollama first**

## Key Learnings
1. gemma4-e4b JSON issues fixed by using `/api/chat` + `format` parameter
2. Free OpenRouter models rotate frequently - many return 404
3. OpenRouter free tier limited to 50 requests/day (not viable for 3200 files)
4. Local Ollama is the reliable, offline-only solution
5. Batch size of 5 files = 100% classification success rate

## Local Models (as of 2026-04-08)
6. **6 models installed** via Ollama — see `docs/LOCAL_MODEL_REGISTRY.md` for full details
7. `gemma4-e4b:latest` — primary agent model, 7.5B Q8_0, ~9GB VRAM, has `tools` capability
8. `gemma4-e4b-json:latest` — same weights + JSON-only system prompt
9. `gemma4-26b:latest` — 25.2B Q3_K_M, ~12GB+ VRAM ⚠️ barely fits RTX 3080 Ti
10. `llama3.2:latest` — 3.2B Q4_K_M, ~2GB VRAM, fast fallback
11. `llama3:latest` — 8.0B Q4_0, ~5GB VRAM, legacy
12. `nomic-embed-text:latest` — 137M F16 embedding model
13. Ollama executable NOT in PATH — lives at `C:\Program Files\Ollama\` — use API at `http://localhost:11434`
14. Ollama server runs as 2 processes + 1 app process (~1.87GB RAM idle)

## Model Versioning Strategy
15. Maintain versioned agent+prompt+model pairings (see registry doc section 9)
16. Always keep at least 1 fallback model configured
17. Different models process code differently — may need model-specific prompt/code variants
18. Backup SDKs and working configs must be preserved when upgrading

## Governance Rules (MANDATORY for ALL agents)
19. **FileMind FIRST**: Use FileMind tools as PRIMARY method for file/codebase exploration
20. **Native tools as FALLBACK only**: grep/glob/read_file only when FileMind is broken
21. See `docs/LOCAL_MODEL_REGISTRY.md` section 10 for full governance rules

## Research Paper Applied (2026-04-08)
22. "Engineering Trust in Agentic Systems: A Multi-Layered Framework for Enforcing Grounding in Local AI Agents" — FULLY ANALYZED
23. Key finding: "Simply instructing an agent to 'use files' is insufficient; the system must be architecturally constrained"
24. 3-layer enforcement implemented: Input rails (pre-search), Pre-execution validation (code parser fix), Mandatory search-first protocol (code-level)
25. Multi-model swarm recommended: Worker (gemma3:4b), Critic (qwen2.5:3b), Router (phi4:mini), Orchestrator (gemma3:4b-q2_K CPU)
26. See `docs/RESEARCH_PAPER_GROUNDING_FRAMEWORK.md` for full analysis
27. Phases 1-3 roadmap defined in research doc — Phase 1 complete, Phase 2 (transparency) next
28. **NEW**: "From Hallucination to Grounding: A System-Level Framework for Building Reliable Local Agents with gemma4-e4b" — FULLY ANALYZED
29. Key finding: gemma4-e4b's 18/42 shared KV layers + sliding window attention trade expressiveness for memory, making it less reliable for structured tool-calling vs gemma3:4b
30. Ollama parameter tuning recommended: num_ctx 16384+, temperature 0.0-0.1, repeat_penalty 1.2-1.5
31. See `docs/RESEARCH_PAPER_GEMMA4_RELIABILITY.md` for gemma4-specific analysis
32. Gemma 3 4B recommended as primary worker over Gemma 4 E4B until Gemma 4 patterns are better established

## PDF Reader Status
33. pypdf installed (`pip install pypdf`) — can extract PDF text from research papers
34. Consider adding PDF reader utility to FileMind tools for future paper processing

## Session Learning Extractor — AUTOMATED
35. MANDATORY: Every session MUST end with complete 16-section learning extraction
36. Output: `docs/SESSION_LEARNING_EXTRACT_[YYYYMMDD].md` + copy to `vault/` + update SYSTEM_NOTES.md
37. Template: `docs/SESSION_LEARNING_EXTRACT_TEMPLATE.md` (includes post-extraction chat appendix)
38. Guide: `docs/SESSION_LEARNING_EXTRACTOR_GUIDE.md`
39. First extraction: `docs/SESSION_LEARNING_EXTRACT_20260408.md` (this session)
40. User directive: "set a systemwide prompt, first and foremost just for you and then for every prompt and especially documentation of it in AI_STATION automating this process"

## Meta-Learning Loop — PLANNED (Workstream G)
41. Two paths: (1) Prompt automation via frontier model weekly, (2) Fine-tuning local model in 3-6 months
42. Session extracts → frontier model reads patterns → suggests improvements → user approves → deploy with version tag
43. Key files planned: prompt_optimizer.py, cli_review.py, generate_playbook.py, AGENT_PLAYBOOK.md
44. Governance: user approves every change, justification logged in PROJECT_PLAN.md
45. DO NOT START yet — planned for next session per user instruction

## Research-First Protocol (2026-04-08)
46. Before non-trivial changes: evaluate knowledge → identify gaps → generate research prompt → deep research → implement with experimental+backup pattern
47. Research prompts go in `docs/RESEARCH_PROMPT_*.md` — see `docs/RESEARCH_FIRST_PROTOCOL.md` for format
48. Every experimental change MUST have: reliable backup, config switch, verification test

## Force Rebuild Success (2026-04-08)
49. Root cause of 405 chunks: interrupted scans + OOM from 32-thread ThreadPoolExecutor
50. Fix: batch embedding (8 files/batch, sequential) + torch.cuda.empty_cache() between batches
51. Force rebuild completed: 3,383 files, 3,383 chunks, 0 errors
52. `--rebuild` flag added to `python run.py scan` for full re-chunk+re-embed

## Search Quality
53. Search returns relevant results after rebuild (config.py, upgrade plan, run.py in top 5)
54. Some noise remains from old scan roots — delta scan will clean
55. Reranking implemented but disabled by default (ENABLE_RERANKING=false)
56. HyDE implemented but disabled by default (HYDE_ENABLED=false)

## GitHub Integration
57. GitHub skill built: hub/agents/skills/github/ — 13 commands, all JSON output
58. PAT configured in hub/.env, auth verified (user: haan0913)
59. FileMind pushed to https://github.com/haan0913/filemind (private repo, 69 files)
60. Scripts: github_tool.py (CLI dispatcher), github_auth.py (PAT loader), github_local.py (git ops)

## Safety Features Added
61. Deleted file verification: os.path.exists() check before removing from index
62. Mass deletion cap: 100+ files triggers warning in nightly.py
63. Backup strategy: vault/backups/ with timestamped index/code/docs snapshots

## First Research Priority
64. Chunking strategy for heterogeneous files — see docs/RESEARCH_PROMPT_CHUNKING_STRATEGY.md
65. BGE-M3 sparse vector extraction alternatives — needed for full hybrid search

## Smart Chunking Implemented (2026-04-08)
66. Research PDF received and integrated: "Beyond Fixed-Size Chunks" provides complete blueprint
67. Implemented file-type-aware chunking in chunker.py with dispatcher pattern:
    - Python: AST-based (ast module) — chunks by functions, classes
    - JSON: Structure-aware — chunks by keys, nested blocks
    - YAML: Structure-aware (PyYAML) — chunks by sections
    - TOML: Structure-aware (tomllib) — chunks by [section] headers
    - Markdown: Header-based hierarchical — chunks by # headings
    - PDF: Multi-stage via PyMuPDF — extract, infer structure, chunk
    - Other: Fixed-size fallback with extension-specific sizes
68. Config flag: USE_SMART_CHUNKING = True (default), False reverts to old behavior
69. Always falls back to fixed-size on any error — zero breaking changes
70. Verified: Python AST chunking separates functions/classes correctly

## Second Research Priority
71. BGE-M3 sparse vector extraction — sentence-transformers returns empty dicts, killing half of hybrid search
72. Research prompt created: docs/RESEARCH_PROMPT_SPARSE_VECTORS.md
73. Plan B defined: standalone BM25 as sparse replacement if BGE-M3 sparse extraction proves impossible on Windows Python 3.14
74. Smart chunk rebuild running — re-chunking all files with type-aware strategy

## Full System Scan & Safety Classification (2026-04-08 14:40)
75. Full system scan completed: 8,679 files, 362.4 MB, 267s duration
76. Safety config created: safety_config.py with 3 tiers (IMMUTABLE/PROTECTED/MOVABLE)
77. Classification coverage: 99.3% (84 immutable, 6,160 protected, 2,376 movable, 59 unclassified)
78. Pre-scan backup: vault/index_backup_20260408_143450 (81.66 MB — SQLite + Qdrant)
79. Scan logger: scan_logger.py — outputs JSON report + console summary
80. 60 "unknown" files in index — all .log files (expected, not a problem)
81. Consolidated knowledge report: docs/CONSOLIDATED_KNOWLEDGE_REPORT.md

## Classification Model Switch (2026-04-08 14:34)
82. CLASSIFICATION_MODEL changed from "gemma4-e4b-json" to "gemma3:4b" in config.py
83. INITIAL BENCHMARK: gemma3:4b returned empty `{}` with `format: "json"` (string)
84. TROUBLESHOOT: gemma3:4b works with JSON schema format, not plain string
85. FIX APPLIED: classifier.py `_ollama_call()` now detects gemma3 and uses schema
86. FIXED BENCHMARK: gemma3:4b 7.43s vs gemma4-e4b-json 8.25s (1.11x faster)
87. Both models 100% accuracy on unknown extensions
88. KEPT gemma4-e4b-json as default (more reliable, JSON system prompt baked in)
89. gemma3:4b now viable fallback — half VRAM, 10% faster
90. Ollama path: C:\Users\amirk\AppData\Local\Programs\Ollama\ (not C:\Program Files\Ollama\)

## STRICT RULE: No Deep Research by Qwen (2026-04-08)
85. Qwen MUST NOT conduct deep research autonomously. For complex research, Qwen generates a comprehensive research prompt and delegates to user's dedicated research agent.
86. Qwen may use internet for simple lookups (web_search for quick facts) but NOT for deep analysis, trend research, state-of-the-art comparisons, or comprehensive reports.
87. All research prompts go to user for delegation. This is a permanent governance rule.

## SKIP_DIRS Audit + Re-index (2026-04-08 16:11)
91. T-INDEX-001 COMPLETE: Replaced blanket ".kimi" skip with fine-grained SKIP_SUBDIRS (27 patterns) + HIGH_VALUE_INCLUDE_PATTERNS (15 patterns). scanner.py now detects symlinks/junctions to prevent infinite recursion (.kimi/.kimi). .jsonl extension added to INDEX_EXTENSIONS.
92. T-INDEX-002 COMPLETE: Full re-scan: 842 files scanned, 619 indexed, 1585 chunks, 0 errors, 564.5s. Catalog: 3,987 → 4,804 files (+817). Categories: config(1638), documentation(1218), code(1015), ai_project(647), research(107), personal(92), unknown(79), finance(5), archive(3).
93. 20+ large session files (>500KB) skipped by MAX_FILE_SIZE — Kimi context.jsonl, wire.jsonl, Claude session files. These contain valuable conversation data but exceed size limit.
94. Hierarchical scanning architecture saved to docs/HIERARCHICAL_SCANNING_ARCHITECTURE.md — full 4-pass design with pseudocode, ML scoring model, phased roadmap. DO NOT re-research.
95. Next session tasks (priority order): T-NEXT-001 MOVABLES decision (2,376 files), T-NEXT-002 Obsidian Vault path, T-NEXT-003 59 unclassified files, T-NEXT-004 Hierarchical scanning research (delegate), T-NEXT-005 Sparse vectors research (delegate), T-NEXT-006 Push to GitHub.
## Architecture Research Session (2026-04-13)
96. COMPREHENSIVE RESEARCH: Dual-engine Windows watcher (watchdog + USN Journal) confirmed as production-grade design. USN Journal requires 500-800 lines ctypes code, admin privileges, per-volume. Used by Everything (voidtools).
97. macOS NATIVE PORT MANDATORY: VM rejected. FSEvents + Metal/MPS + ANE. Unified memory (16GB) > 12GB VRAM for ML workloads. VM = CPU-only = 10x slower.
98. PLATFORM-SPECIFIC BUILDS: Performance > unified abstraction. Windows hybrid (RDCW+USN) and macOS FSEvents can't be elegantly abstracted.
99. QUEUE-BASED PIPELINE: Replace sequential nightly.py with SQLite-backed queue. 3-5x speedup (2min → 30sec for 4K files). SELECT FOR UPDATE for atomic job claiming.
100. SCALABILITY NUMBERS: 4K=30s, 50K=3min, 200K=12min, 1M=60min with 8-worker queue. Sequential: 2min, 25min, 100min, 500min.
101. ENTERPRISE = ARCHITECTURAL PIVOT: Local-first → centralized client-server. Kafka ingestion, distributed Qdrant/ES, RBAC, multi-tenancy. Different product, not incremental.
102. WATCHDOG BUFFER: Default 2048 bytes → increase to 1MB. Overflow detection should auto-trigger USN Journal catch-up (self-correcting).
103. VECTOR COMPACTION: Qdrant doesn't auto-delete stale vectors. Weekly vacuum: check disk existence → delete orphans → COMPACT if fragmentation >20%.

## Phase 0.5 — Outstanding Technical Debt (2026-04-13)
104. SPARSE VECTORS BROKEN: sentence-transformers returns empty dicts for BGE-M3 lexical weights. Hybrid search = dense-only + FTS5. Research prompt created.
105. LOW CHUNK COVERAGE: ~405-1585 chunks for 3838-4804 files (~10%). Needs --rebuild after fixes.
106. CLASSIFIER MODEL: gemma4-e4b-json default (8.7GB VRAM, worse tool-calling). gemma3:4b viable (3.5GB, better reliability) — should become default.
107. AGENT SEARCH SKIPPING: gemma4-e4b can still bypass mandatory search-first and answer from parametric knowledge.
108. INDEX NOISE: Browser cache / build artifacts / node_modules partially cleaned via SKIP_DIRS audit but not verified complete.
109. RERANKER UNKNOWN: FlagEmbedding removed (Python 3.14). Alternative in use but identity + functionality not verified.
110. DYNAMIC BATCHING: Current batch size 8 is static workaround. Needs optimization per hardware.

## STRICT RULE: No Deep Research by Qwen (REINFORCED 2026-04-13)
111. Qwen MUST NOT conduct deep research autonomously. For complex research, Qwen generates a comprehensive research prompt and delegates to user's dedicated research agent.
112. All research prompts go to user for delegation. This is a permanent governance rule.

## MANDATORY SYSTEM RULE — READ BEFORE WRITING (ALL AGENTS, ALL PROJECTS)
113. BEFORE making ANY code change, agent MUST read the actual existing code, configuration, and documentation in the project. NEVER assume invocation patterns, import conventions, API signatures, architectural decisions, or dependency availability from training data.
114. Training data expires — local files are the SINGLE SOURCE OF TRUTH. Always read the files you're about to modify and their dependencies first.
115. Check existing patterns: imports, error handling, naming conventions, config format, CLI invocation, module structure — follow them exactly.
116. If agent catches itself thinking "I think the pattern is X" — STOP and read the file instead.
117. This rule applies to EVERY project, EVERY agent, EVERY change. No exceptions.
118. Real-world failure example: 2026-04-13 — agent wrote `from .bm25_index import BM25HybridIndex` (bare relative import) in nightly.py without checking that the project uses try/except pattern for dual invocation support (`python -m filemind` vs `python run.py`). Pipeline crashed with "attempted relative import with no known parent package". Root cause: agent assumed import pattern from training data instead of reading the existing 20+ successful import patterns in the codebase.
119. Correct workflow: (1) Read target file, (2) Read 2-3 related files to understand patterns, (3) Check existing imports for convention, (4) THEN write code that matches the established pattern.

## Ollama Service Note (2026-04-13)
120. ALL models are installed (gemma4-e4b, gemma4-e4b-json, gemma3:4b, llama3, llama3.2, nomic-embed-text). If audit says "cannot find models", Ollama service is just DOWN — run `ollama serve` or restart Ollama. Models ARE installed, just not accessible when service is stopped.
121. Ollama path: C:\Users\amirk\AppData\Local\Programs\Ollama\ — API at http://localhost:11434

## File Consolidation Goal (2026-04-13)
122. User wants to consolidate ALL AI content, knowledge, projects, files into ONE unified directory in file explorer. This is a MAJOR reorganization — DO NOT act on this until FileMind is fully capable and reliable. Plan: (1) Complete Phase 0.5 fixes, (2) Run --rebuild for 100% coverage, (3) Design consolidation plan with user approval, (4) Execute reorganization, (5) Rescan new unified directory.

## Phase 0.5 Implementation (2026-04-13) — ALL ACTIONS COMPLETE
116. ACTION 1 DONE: CLASSIFICATION_MODEL switched from "gemma4-e4b-json" to "gemma3:4b" in config.py. Saves ~5.2GB VRAM. OPENROUTER_AS_PRIMARY set to False.
117. ACTION 2 DONE: BM25 hybrid search implemented. New file: bm25_index.py (BM25HybridIndex class + smart tokenizer + RRF fusion). search.py integrates BM25 as 3rd leg of RRF fusion. nightly.py builds BM25 index during embed phase.
118. ACTION 3 DONE: FP16 enabled in embedder.py — model.half() on GPU load, ~65% throughput gain, ~50% VRAM savings. Dynamic batch sizing: tries configured size, halves on OOM, caches working size.
119. ACTION 4 DONE: Critic loop implemented. New file: agent/critic.py (hybrid grounding: regex path extraction + gemma3:4b semantic check + rule-based fallback). Integrated into agent/run.py _validate_answer() as Layer 3b.
120. ACTION 5 DONE: Reranker logging added to search.py — logs top-5 pre-rerank and post-rerank file names, reports when order changes.
121. Force rebuild scan runs but times out at 10 min (needs ~15-20 min for full 4,800+ file reindex). FP16 confirmed working, gemma3:4b classifier confirmed, BM25 building confirmed.

## CRITICAL LESSON: Dual Invocation Pattern (2026-04-13)
122. FileMind supports TWO invocation modes: (a) `python -m filemind scan` (package context), (b) `python run.py scan` (standalone script). ALL imports in project files MUST use `try: from .module import X / except ImportError: from module import X` pattern. NEVER use bare relative imports (`from .module`) — they only work in mode (a). This pattern is used throughout config.py, nightly.py, search.py, classifier.py, etc. Always check existing import patterns before adding new modules.
123. Correct CLI invocation: `python -m filemind scan --rebuild` (NOT `python -m filemind run.py scan --rebuild` — run.py is not a subcommand, it's the script entry point for mode b).
124. SyntaxWarning in Python 3.14: "\A" is invalid escape sequence. Found in <unknown> files during rebuild — likely in tokenizer/regex code. Should use raw strings (r"\A") but NOT breaking anything yet.