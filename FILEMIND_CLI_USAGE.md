# FileMind - Using Existing CLI Tools

> Key insight: you do not need the lazy-start UI or agent loop to use FileMind. The CLI already supports search, rebuild, verification, and system inspection directly.

---

## What You Can Do Right Now

### Search Your Files
```bash
python C:\AI_STATION\filemind\run.py search "query text"
python C:\AI_STATION\filemind\run.py search "query" --keyword
python C:\AI_STATION\filemind\run.py search "query" --semantic
python C:\AI_STATION\filemind\run.py search "query" --type .py
```

### Refresh and Verify the Index
```bash
python C:\AI_STATION\filemind\run.py scan
python C:\AI_STATION\filemind\run.py scan --full
python C:\AI_STATION\filemind\run.py scan --rebuild
python C:\AI_STATION\filemind\run.py scan --prune-excluded
python C:\AI_STATION\filemind\run.py verify
```

### Inspect System State
```bash
python C:\AI_STATION\filemind\run.py stats
python C:\AI_STATION\filemind\run.py duplicates
python C:\AI_STATION\filemind\run.py health
```

### Read Actual File Content
```bash
type "C:\path\to\file.py"
```

---

## What This Enables

| Task | How | Example |
|------|-----|---------|
| **Find files by topic** | Search index plus read results | "Find all files about the Telegram bot" |
| **Identify duplicates** | Run duplicates command | "Show duplicate files and suggest which to keep" |
| **Analyze categories** | Run stats plus search | "What percent of my files are code vs config?" |
| **Check index health** | Run verify and health | "Did the rebuild fully cover the current scan scope?" |
| **Organize suggestions** | Combine search plus categorization | "Suggest a folder structure for my AI projects" |
| **Cleanup planning** | Duplicates plus search plus analysis | "Create a plan to clean up temp or backup files" |
| **Project inventory** | Stats plus search plus filters | "List all projects in C:/AI_STATION" |
| **Code analysis** | Search by type plus shell reads | "Find all files that import requests" |

---

## Current Index Stats (as of April 16, 2026)

| Metric | Value |
|--------|-------|
| Effective files on disk | 2,909 |
| Catalog entries | 2,909 |
| Files with extracted content | 2,818 |
| Files with embeddings | 2,818 |
| Chunks in shared Qdrant | 23,121 |
| BM25 chunks | 23,121 |
| Verification status | 100.0% completeness, chunk parity OK |
| Top categories | documentation (1238), config (790), code (511), ai_project (267), research (80) |
| Top extensions | .md (1102), .json (747), .py (492), .txt (205), .log (108) |
| Duplicate files marked | 30 |

---

## Current Limitations

| What the CLI can do | What still is not built |
|---------------------|-------------------------|
| Search the live index and return ranked results | First-prompt lazy-start / switchboard UI |
| Rebuild and verify the corpus on demand | Real-time file watching |
| Read file contents through normal shell tools | Autonomous file operations without an explicit command |
| Suggest cleanup or organization plans | Fully automated execution plans |

---

## Go-To Commands

```bash
# Search the indexed corpus
python C:\AI_STATION\filemind\run.py search "what am I looking for"

# Check the current corpus shape
python C:\AI_STATION\filemind\run.py stats

# Verify scan completeness and chunk parity
python C:\AI_STATION\filemind\run.py verify

# Confirm system health
python C:\AI_STATION\filemind\run.py health
```

---
*The CLI is the stable path today. The later lazy-start model is intended to sit on top of this command surface, not replace it.*
