# Chunking Strategy Research — Findings Summary

**Source:** "Beyond Fixed-Size Chunks: A Modular Framework for Semantically Coherent Indexing in FileMind" (PDF)  
**Date:** 2026-04-08  
**Status:** ACTIONABLE — Implementation ready

---

## Key Findings

### Problem Confirmed
Fixed-size 2,048-token chunking with 256 overlap fragments logical units:
- **Code:** Functions split mid-body, imports separated from usage
- **Config:** Key-value pairs broken, nested blocks split
- **Docs:** Section headers disconnected from content

### Recommended Strategy

| File Type | Strategy | Library | Key Unit |
|---|---|---|---|
| `.py` | AST-based | Built-in `ast` module | Functions, classes |
| `.json` | Parse → chunk by keys | Built-in `json` | Key-value pairs, nested blocks |
| `.yaml`, `.yml` | Parse → chunk by keys | `PyYAML` (pure Python) | Key-value pairs, sections |
| `.toml` | Parse → chunk by keys | Built-in `tomllib` (Python 3.11+) | Key-value pairs, sections |
| `.md` | Header-based hierarchical | Custom regex logic | Sections by `#` headers |
| `.rst` | Structural chunking | `docutils` | Sections by underline |
| `.pdf` | Multi-stage: extract → infer structure → chunk | `PyMuPDF` (fitz) | Layout-aware paragraphs |
| Other | Fallback to fixed-size | Existing chunker | 2,048 tokens, 256 overlap |

### Implementation Pattern
- Dispatcher pattern in `chunker.py` — routes by extension
- `config.USE_SMART_CHUNKING = True/False` toggle
- Always fallback to fixed-size on error
- Variable chunk sizes — semantic coherence over fixed limits
- Retain 256-token overlap as safety net

### Libraries (Windows + Python 3.14 compatible)
- `ast` — standard library, no install needed
- `json` — standard library
- `tomllib` — standard library (Python 3.11+)
- `PyYAML` — `pip install pyyaml` (pure Python, no C deps)
- `PyMuPDF` — pre-compiled wheel for Windows
- `markdown-it-py` — pure Python Markdown parser (optional)

---

## Implementation Plan

1. Add `USE_SMART_CHUNKING = True` to config.py
2. Refactor `chunker.py` with dispatcher pattern
3. Implement `chunk_python_file()` using `ast` module
4. Implement `chunk_json_file()` using `json` module
5. Implement `chunk_yaml_file()` using `PyYAML`
6. Implement `chunk_toml_file()` using `tomllib`
7. Implement `chunk_markdown_file()` using header regex
8. Implement `chunk_pdf_file()` using `PyMuPDF`
9. Retain existing `fixed_size_chunker()` as fallback
10. Test with `--rebuild` flag on a small subset first

---

*Research integrated into SYSTEM_NOTES.md items 66-70.*
