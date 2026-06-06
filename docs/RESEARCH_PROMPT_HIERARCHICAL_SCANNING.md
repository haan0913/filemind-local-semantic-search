# Research Prompt â€” Hierarchical Context-Directed Multi-Drive File Scanning

**Priority:** Phase 3+ (Future Enhancement â€” NOT for current implementation)
**Date:** 2026-04-08 (updated with full session context)
**Delegated by:** Qwen Code (coding agent â€” FileMind project)
**Research type:** Architecture/Algorithm Design, Multi-Pass File Discovery, Heuristic Scoring
**Status:** Ready for deep research agent

---

## 1. PROJECT CONTEXT

### What FileMind Is
FileMind is a PC-wide **semantic file search engine** running on Windows 11. It indexes files across multiple directories, chunks their content intelligently (AST for Python, headers for Markdown, structure for JSON/YAML), embeds chunks via BGE-M3 (1024-dim vectors), and stores them in Qdrant for semantic + keyword hybrid search.

### Current Architecture (Working)
- **Index:** 3,987 files indexed, 5,896 chunks in Qdrant (67.70 MB vectors)
- **Catalog:** SQLite at `C:\AI_STATION\.index\filemind.db` (13.96 MB)
- **Embedding:** BGE-M3 via sentence-transformers on CUDA (RTX 3080 Ti, 12GB VRAM)
- **Search:** Semantic (dense vectors) + keyword (FTS5) + reranking (CrossEncoder)
- **Smart Chunking:** File-type-aware dispatch (AST, structure, headers, layout)
- **Classification:** Rule-based first pass (instant for known extensions) + LLM fallback (gemma4-e4b-json, 8.25s per 5 unknown-ext files)
- **Safety:** 3-tier classification (IMMUTABLE/PROTECTED/MOVABLE) â€” 99.3% coverage on 8,679 scanned files

### The Problem We're Solving
The user has **apps, games, and projects scattered across multiple drives** (C:, D:, potentially more). The current system requires explicit scan roots configured in `config.py` â€” it doesn't discover what to scan. A full blind scan of all drives would be extremely slow and could accidentally process system directories.

The goal: an **intelligent hierarchical scanning system** that discovers applications and projects across an entire multi-drive system WITHOUT blind one-by-one scanning.

---

## 2. THE METHOD â€” 4-Pass Hierarchical Context-Directed Scanning

This is the user's vision. We need research to validate, refine, and make it practical.

### Pass 1: Top-Level Discovery
**Goal:** Build a map of the entire system at minimum depth.
**Approach:**
- Scan ONLY the highest-level folders across all drives (C:\, D:\, E:\, etc.)
- List immediate subdirectories at depth 1-2
- For each folder, collect metadata ONLY (no content reading):
  - Total folder size
  - File count by type distribution
  - Presence of "signature files" (package.json, .git, requirements.txt, etc.)
  - Depth of the folder tree
- Assess each folder: is it likely an "app root," "project," "system noise," or "user data"?
- Output: scored list of top-level candidates for deeper scanning

**Key question:** What's the optimal depth for Pass 1? Depth 1 (fastest but least info) vs depth 2-3 (more info but slower)?

### Pass 2: Context-Directed Descent
**Goal:** Selectively descend into promising folders, skip system noise.
**Approach:**
- Based on Pass 1 scores, choose which folders to descend into
- High-priority: folders with app/project signatures
  - Presence of manifest files (package.json, requirements.txt, Cargo.toml, .csproj, CMakeLists.txt)
  - Subdirectory patterns (src/, bin/, lib/, config/, Data/, Assets/)
  - File type distribution skewed toward code/config/docs (not temp/cache/log)
- Low-priority (skip): Windows directories, AppData caches, temp folders, browser profiles
- Medium-priority: user documents, downloads (needs deeper assessment)
- For each descended folder, repeat the metadata collection + scoring
- Output: refined tree of promising application/project roots

**Key question:** What heuristic scoring model best separates "real app" from "system folder" at this depth?

### Pass 3: File-Level Prioritized Analysis
**Goal:** Within each targeted folder, understand what it contains by reading key files.
**Approach:**
- Sort files within each folder by "information value" BEFORE reading:
  - **Priority 1 (read first):** Large config files, manifests, entry points (main.py, index.js, Program.cs, .uproject)
  - **Priority 2 (read second):** README files, documentation, package manifests
  - **Priority 3 (read if needed):** Source code samples, config files
  - **Deprioritized:** Logs, caches, temp files, compiled binaries, node_modules, __pycache__
- Use file size + type + naming patterns to assess information value
- Read content snippets (first 1-5KB) of priority files to determine folder purpose
- Entropy detection: distinguish compiled binary vs text vs config vs data
- Output: confident classification of each folder's purpose and contents

**Key question:** How many files need to be read to reach 95%+ confidence about a folder's purpose?

### Pass 4: Root Isolation and Boundary Detection
**Goal:** Identify exactly where each application/project starts and ends.
**Approach:**
- Trace BACK UP the tree from confirmed app files to find the root boundary
- Detect the boundary between "this app's files" and "generic system directories"
  - Example: `C:\Games\MyGame\` is the root, not `C:\Games\` or `C:\`
  - Example: `C:\Users\amirk\Projects\myapp\` is the root, not `C:\Users\amirk\`
- Extract only the application root folder as a scan candidate
- Verify: does this root contain a self-contained project? (manifest + source + docs)
- Output: clean list of application/project roots ready for FileMind indexing

**Key question:** How to algorithmically detect the "root boundary" between an app and its parent system folder?

---

## 3. RESEARCH QUESTIONS (Detailed)

### RQ1: Multi-Pass Scanning Algorithms
What algorithms and techniques exist for hierarchical/context-directed file discovery?

- **Bloom filter signatures:** Can we use bloom filters to quickly assess whether a folder contains files of interest without full enumeration?
- **Heuristic descent:** What features should a folder scoring function use? (size, file count, type distribution, depth, naming patterns, presence of signature files)
- **ML-based folder scoring:** Has anyone trained a model to classify folders by purpose based on metadata alone? What features would it need?
- **Entropy-based classification:** Can file entropy distinguish compiled binary vs text vs config vs data fast enough to be useful?
- **Information retrieval techniques:** What IR techniques apply to folder prioritization?

**Specifically research:**
- How do code search engines (Sourcegraph, OpenGrok) handle repository discovery?
- How do IDE project import wizards detect project types and roots?
- How do game launchers (Steam, GOG, Epic) discover installed games across drives?

### RQ2: File Prioritization Within Folders
How to sort files by "information value" before scanning?

- **File size as proxy:** Is file size a reliable indicator of importance? (Large configs are informative, large binaries are noise)
- **File type hierarchy:** What's the definitive priority order for file types when assessing a folder?
  - Tier 1: Manifest files (package.json, requirements.txt, Cargo.toml, pom.xml, .csproj, CMakeLists.txt, .uproject, .godot)
  - Tier 2: Entry points (main.py, index.js, app.js, Program.cs, Game.cpp)
  - Tier 3: Documentation (README.md, README.txt, docs/, CHANGELOG)
  - Tier 4: Config files (.env, config.json, settings.py, service manifests)
  - Tier 5: Source code samples (any .py, .js, .ts, .cs, .cpp)
  - Deprioritized: .log, .cache, .tmp, node_modules/, __pycache__/, .git/, dist/, build/
- **Naming patterns:** What naming conventions indicate importance? (Project names, version numbers, dates)
- **File density:** Does the ratio of code files to other file types indicate a "real project"?

### RQ3: Application Root Detection
What signals definitively identify "this is where the app starts"?

**For software projects:**
- Presence of manifest + source + tests + docs in the same directory tree
- Version control root (.git folder at top level)
- Build system configuration (Makefile, build.gradle, webpack.config.js)

**For games:**
- Unity: Assets/, Library/, ProjectSettings/ folders + .sln file
- Unreal: .uproject file + Source/ + Config/ + Content/
- Godot: project.godot file at root
- Custom engines: executable + data files + config

**For general applications:**
- Installation manifests (unins000.exe for Inno Setup, uninstall.exe)
- Registry entries (Windows installer database)
- Configuration directories with application-specific names

**Key question:** How to distinguish between:
- A folder that IS an application (MyGame/)
- A folder that CONTAINS applications (Games/)
- A folder that is part of an application (Games/MyGame/Data/)

### RQ4: Existing Tools Comparison
How do existing tools approach multi-drive file discovery?

| Tool | Approach | Strengths | Weaknesses |
|------|----------|-----------|------------|
| TreeSize | Full directory enumeration + size calculation | Complete, accurate | Slow, no content awareness |
| WinDirStat | Full scan + visual treemap | Visual, complete | Very slow on large drives |
| Everything (voidtools) | NTFS USN Journal parsing | Instant results | No content analysis, no cross-drive correlation |
| Steam Library | Folder scanning for appmanifest_*.acf files | Fast, game-specific | Only Steam games |
| Windows Search | Indexing Service + content crawling | Integrated, content-aware | Slow setup, incomplete coverage |
| IDE project import | Pattern matching for known project types | Accurate for known types | Misses custom setups |

**Research specifically:**
- What approach does Everything use for instant file discovery? (USN Journal?)
- How does Steam's library system discover games across multiple drives?
- How do IDE project import wizards (VS Code, IntelliJ, Visual Studio) detect projects?
- How does Windows "Apps & Features" enumerate installed applications?

### RQ5: Optimal Pass Structure
What's the most efficient algorithm for discovering apps across drives?

- **Pass 1 depth:** Depth 1 vs 2 vs 3? What's the sweet spot between speed and information gain?
- **Pass 2 scoring:** What's the minimum feature set for a reliable folder scoring function?
- **Pass 3 sampling:** How many files need to be read to reach confidence? Is there a stopping criterion?
- **Pass 4 boundary:** What algorithm traces back up the tree to find the root?

**Hypotheses to validate:**
- H1: Pass 1 at depth 2 covers 90%+ of discoverable apps with <5% of full scan cost
- H2: A scoring function with 5 features (manifest presence, file type ratio, folder size, depth, naming pattern) achieves 95%+ precision
- H3: Reading 3-5 priority files per folder is sufficient for 90%+ classification accuracy
- H4: Root boundary detection can be solved by finding the highest directory containing a manifest file

### RQ6: Safety Guarantees
How to prevent the scanner from doing harmful things?

- **Immutable directories:** How to guarantee NO scanning of active venvs, node_modules, .git, Windows system dirs?
- **Permission handling:** How to handle access denied errors gracefully without crashing or hanging?
- **Encrypted directories:** How to detect and skip BitLocker-encrypted or EFS-encrypted folders?
- **False positive prevention:** How to avoid misidentifying system directories as applications?
- **False negative prevention:** How to avoid missing actual apps in unusual locations?
- **Rate limiting:** How to prevent the scanner from overwhelming the disk I/O?

---

## 4. TECHNICAL CONSTRAINTS

### Hardware
- **CPU:** AMD Ryzen 9 5950X (16 cores, 32 threads)
- **GPU:** NVIDIA RTX 3080 Ti (12GB VRAM)
- **RAM:** 64GB DDR4
- **Storage:** NVMe SSD (C:), potentially additional drives (D:, E:)
- **OS:** Windows 11

### Software
- **Python:** 3.14
- **Current stack:** Qdrant (local), SQLite, sentence-transformers (BGE-M3), CrossEncoder
- **Ollama:** 7 models installed (gemma4-e4b, gemma4-e4b-json, gemma3:4b, gemma4-26b, llama3.2, llama3, nomic-embed-text)

### Current FileMind Capabilities
- Smart chunking (AST, structure, headers, layout)
- Semantic search (dense vectors)
- Keyword search (FTS5)
- Hybrid RRF fusion
- Reranking (CrossEncoder)
- Safety classification (3-tier)
- Pre-scan backups
- Scan logging with JSON reports

### What This Research Should NOT Assume
- This is NOT about replacing FileMind's current indexing â€” it's about DISCOVERING what to index
- This is NOT about content analysis â€” FileMind already does semantic search well
- This IS about efficient, safe, intelligent discovery across multi-drive systems

---

## 5. DELIVERABLES

1. **Algorithm design document** with detailed pseudocode for each of the 4 passes
2. **Heuristic scoring model** with specific features, weights, and thresholds
   - What features to score on? (manifest presence, file type ratio, folder size, depth, naming, entropy)
   - What threshold for "descend vs skip"?
   - What threshold for "this is an app root" vs "keep searching"?
3. **Comparison table** of existing tools with specific strengths/weaknesses for our use case
4. **Risk assessment** with specific false positive/negative scenarios and mitigations
5. **Recommended implementation path** for Python on Windows 11
   - Which Python libraries to use? (os, pathlib, scandir, ctypes for USN Journal?)
   - How to handle Windows-specific features (USN Journal, registry queries)?
6. **Phased approach** â€” Phase 1 MVP through full implementation
   - MVP: What's the minimum that works? (Pass 1 + basic scoring?)
   - Phase 2: Add Pass 3 content analysis
   - Phase 3: Add Pass 4 boundary detection
   - Phase 4: ML-based scoring (if warranted)
7. **Estimated complexity** and timeline
8. **Integration plan** â€” how would this plug into FileMind's existing architecture?

---

## 6. OUTPUT FORMAT

Structured markdown with:
- Executive summary (1 page)
- Sections for each research question with evidence, analysis, and recommendations
- Pseudocode for each pass algorithm
- Decision tables (if X then Y, else Z)
- Comparison tables with existing tools
- Clear "Phase 1 MVP" section with specific implementation steps
- References to papers, tools, and documentation consulted

**Do NOT** provide generic advice. Be specific, cite sources, provide pseudocode, and give actionable recommendations for a Python developer on Windows 11.

---

## 7. CRITICAL CONTEXT: SKIP_DIRS Audit Discovery

During the full system scan (2026-04-08), we discovered that the **current SKIP_DIRS configuration is too aggressive** and excludes valuable content:

### Root Cause Analysis Results
```
Total files on disk (matching INDEX_EXTENSIONS): 167,406
  Excluded by SKIP_DIRS/SKIP_SUBDIRS:           158,713 (94.8%)
  Scannable but NOT in vector index:              8,693
  Already in index:                               3,987 (but gap analysis shows 0 overlap due to path format)
```

### What's Being Excluded (and Why It Matters)
| Skip Rule | Files Excluded | What's Lost |
|-----------|---------------|-------------|
| `.kimi` (entire directory) | 113,252 | **Plans, subagent conversations, memory files, project context** â€” this is the Kimi AI agent's working memory and planning data |
| `node_modules` | 35,984 | Correct to skip (framework code, not user content) |
| `.venv` | 4,720 | Correct to skip (Python dependencies) |
| `playwright` | 1,742 | Probably safe to skip (browser automation) |
| `.windsurf` | 822 | IDE config â€” mostly noise but may have user settings |
| `tools` | 585 | May contain user scripts and utilities |
| `.next` | 564 | Build artifacts â€” safe to skip |
| `vault` | 429 | FileMind backups â€” duplicates, safe to skip |
| `.local` | 258 | Local config â€” may have user preferences |
| `backups` | 93 | Safe to skip |

### The Problem
The current approach is **binary**: either include an entire scan root or skip it entirely. The `.kimi` directory alone has 113,252 files, and we're skipping ALL of them. But inside `.kimi` are:
- Project plans and task definitions
- Subagent conversation contexts
- Memory files and knowledge artifacts
- Tool results with important discoveries

### The Needed Solution
Replace blanket SKIP_DIRS with **fine-grained SKIP_SUBDIRS patterns**:
- **Include:** `.kimi/projects/*/subagents/`, `.kimi/config.toml`, `.kimi/credentials/`
- **Exclude:** `.kimi/owl-agent/.venv/`, `.kimi/logs/`, `.kimi/model_store/`

This research should consider how the hierarchical scanning method (4-pass approach) can also be applied **within currently-skipped directories** to selectively extract valuable content while maintaining noise exclusion.

---

## 8. RELATED RESEARCH PROMPTS

This prompt complements:
- `RESEARCH_PROMPT_SPARSE_VECTORS.md` â€” BGE-M3 sparse vector extraction for hybrid search
- `RESEARCH_PROMPT_CHUNKING_STRATEGY.md` â€” Smart chunking for heterogeneous file types
- `RESEARCH_PROMPT_PROJECT_ORCHESTRATION.md` â€” Project planning and orchestration

---

*Research prompt generated by Qwen Code during FileMind session 2026-04-08. Delegate to dedicated research agent.*

---
Documentation Signature
Updated by: Codex (GPT-5.5)
Timestamp: 2026-05-18T15:08:12-04:00
Change summary: Replaced obsolete container-specific config example during Task 191 cleanup.
