"""
FileMind Reality Check & Integration Tests

Run: python filemind/tests/test_reality.py
Tests are grouped into:
  1. Dependency audit      -- what's installed vs required
  2. DB integrity          -- indexed files still exist on disk
  3. FTS search quality    -- keyword search returns relevant results
  4. Classifier API        -- uses actual method names from current codebase
  5. Embedder degradation  -- fails gracefully when deps missing
  6. Vector store reality  -- reports actual embedding count honestly
  7. Pipeline E2E          -- scan temp dir, verify all stages
  8. Duplicate detection   -- finds known identical files
  9. Search relevance      -- known query -> expected file in results
 10. Category accuracy     -- spot-check .py files are "code", etc.
"""

import os
import sys
import sqlite3
import tempfile
import shutil
import hashlib
import importlib
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from filemind.config import config

# -- Test harness -------------------------------------------------------------

passed = 0
failed = 0
warnings = 0
_results = []

def ok(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        _results.append(("PASS", name, detail))
    else:
        failed += 1
        _results.append(("FAIL", name, detail))

def warn(name, detail=""):
    global warnings
    warnings += 1
    _results.append(("WARN", name, detail))

def section(title):
    print(f"\n{'-'*60}")
    print(f"  {title}")
    print(f"{'-'*60}")

def run_section(title, fn):
    section(title)
    try:
        fn()
    except Exception as e:
        _results.append(("ERRO", title, str(e)))
        global failed
        failed += 1


# -----------------------------------------------------------------------------
# 1. Dependency Audit
# -----------------------------------------------------------------------------

def test_dependencies():
    REQUIRED = {
        "qdrant_client": "vector store (semantic search)",
        "rank_bm25": "BM25 lexical retrieval",
        "sentence_transformers": "BGE-M3 embeddings + reranker",
        "fitz": "PDF extraction (PyMuPDF)",
        "docx": "DOCX extraction (python-docx)",
        "openpyxl": "Excel extraction",
        "pptx": "PowerPoint extraction (python-pptx)",
        "extract_msg": "Outlook MSG extraction",
        "gradio": "web dashboard",
        "torch": "embedding model backend",
        "requests": "Ollama / OpenRouter HTTP",
        "tqdm": "progress bars",
        "watchdog": "file system watcher",
    }
    missing = []
    for pkg, purpose in REQUIRED.items():
        try:
            importlib.import_module(pkg)
            ok(f"dep:{pkg}", True)
        except ImportError:
            missing.append(pkg)
            ok(f"dep:{pkg} ({purpose})", False, "NOT INSTALLED")

    ok("all required deps installed", len(missing) == 0,
       f"Missing: {missing}" if missing else "")
    if missing:
        warn("semantic search and some extraction unavailable until deps installed",
             f"pip install {' '.join(missing)}")


# -----------------------------------------------------------------------------
# 2. DB Integrity -- Indexed Files Still Exist on Disk
# -----------------------------------------------------------------------------

DB_PATH = Path(config.sqlite_db)

def test_db_integrity():
    ok("filemind.db exists", DB_PATH.exists())
    if not DB_PATH.exists():
        return

    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()

    # Sample 50 files and verify they exist on disk
    c.execute("SELECT COUNT(*) FROM file_index")
    total_rows = c.fetchone()[0]
    sample_size = min(50, total_rows)
    c.execute(f"SELECT full_path FROM file_index ORDER BY RANDOM() LIMIT {sample_size}")
    rows = c.fetchall()
    ok("DB has sampled rows", len(rows) == sample_size)

    missing_on_disk = [r[0] for r in rows if not os.path.exists(r[0])]
    ok(
        f"sampled files exist on disk ({len(rows) - len(missing_on_disk)}/{len(rows)})",
        len(missing_on_disk) == 0,
        f"Orphaned records: {missing_on_disk[:5]}" if missing_on_disk else "",
    )

    # Verify no NULL full_paths
    c.execute("SELECT COUNT(*) FROM file_index WHERE full_path IS NULL OR full_path = ''")
    null_count = c.fetchone()[0]
    ok("no NULL full_path entries", null_count == 0, f"{null_count} nulls found")

    # Verify content_hash is populated
    c.execute("SELECT COUNT(*) FROM file_index WHERE content_hash IS NULL OR content_hash = ''")
    no_hash = c.fetchone()[0]
    ok("all files have content_hash", no_hash == 0, f"{no_hash} files without hash")

    # Verify category distribution is sane (< 50% unknown)
    c.execute("SELECT COUNT(*) FROM file_index WHERE category = 'unknown' OR category IS NULL")
    unknown = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM file_index")
    total = c.fetchone()[0]
    pct = unknown / total if total else 1
    ok(f"unknown category < 50% ({pct:.0%} unknown)", pct < 0.5,
       f"{unknown}/{total} files are unknown")

    # Verify chunk_count > 0 for files with meaningful content (>100 bytes)
    # Files under 100 bytes may be all whitespace and produce no chunks legitimately
    c.execute("SELECT COUNT(*) FROM file_index WHERE chunk_count = 0 AND size > 100")
    no_chunks = c.fetchone()[0]
    ok("files >100 bytes have chunks", no_chunks == 0,
       f"{no_chunks} files >100 bytes have 0 chunks")

    conn.close()


# -----------------------------------------------------------------------------
# 3. FTS5 Search Quality -- Known Files, Known Queries
# -----------------------------------------------------------------------------

def test_fts_search_quality():
    from filemind.catalog import Catalog
    catalog = Catalog()

    # Query for a term that MUST appear in the codebase
    cases = [
        ("FileMind", "FILEMIND_MASTER_PLAN"),   # master plan doc
        ("Telegram", "bot"),                     # Telegram bot file
        ("classifier", "classifier"),            # classifier.py
        ("scanner", "scanner"),                  # scanner.py
        ("pytest", "test"),                      # test files
    ]

    for query, expected_substr in cases:
        results = catalog.fts_search(query, top_k=10)
        hit = any(expected_substr.lower() in r.get("path", "").lower()
                  or expected_substr.lower() in r.get("content_summary", "").lower()
                  for r in results)
        ok(f'fts "{query}" -> finds relevant file', hit,
           f"top paths: {[r.get('path','') for r in results[:3]]}" if not hit else "")

    catalog.close()


# -----------------------------------------------------------------------------
# 4. Classifier API -- Uses Actual Method Names
# -----------------------------------------------------------------------------

def test_classifier_api():
    from filemind.classifier import Classifier
    clf = Classifier()

    # Verify actual methods exist (not stale _parse_response)
    ok("classify() method exists", callable(getattr(clf, "classify", None)))
    ok("_parse_indexed_response() exists",
       callable(getattr(clf, "_parse_indexed_response", None)))
    ok("_parse_response() does NOT exist (stale API)",
       not hasattr(clf, "_parse_response"),
       "old method still present -- update tests/test_modules.py")

    files = [{"path": "test.py", "ext": ".py", "content_summary": "def foo(): pass"}]

    # Test _parse_indexed_response with valid index-keyed JSON (uses "i" field, not "path")
    raw = '[{"i":1,"category":"code","confidence":0.9}]'
    result = clf._parse_indexed_response(raw, files)
    ok("_parse_indexed_response: valid JSON", len(result) == 1 and result[0]["category"] == "code")

    # Markdown-fenced JSON
    fenced = '```json\n[{"i":1,"category":"code","confidence":0.9}]\n```'
    result = clf._parse_indexed_response(fenced, files)
    ok("_parse_indexed_response: strips markdown fences", len(result) == 1 and result[0]["category"] == "code")

    # Invalid JSON -> unknown fallback
    result = clf._parse_indexed_response("not json", files)
    ok("_parse_indexed_response: invalid JSON -> unknown", result[0]["category"] == "unknown")


# -----------------------------------------------------------------------------
# 5. Embedder Graceful Degradation
# -----------------------------------------------------------------------------

def test_embedder_degradation():
    """Embedder must fail cleanly, not crash the pipeline."""
    try:
        from filemind.embedder import Embedder
        e = Embedder()
        try:
            result = e.encode(["test text"], return_dense=True, return_sparse=True)
            has_dense_payload = (
                isinstance(result, dict)
                and "dense_vecs" in result
                and len(result["dense_vecs"]) == 1
            )
            ok("embedder encode returns structured payload", has_dense_payload, str(result)[:200])
        except Exception as embed_err:
            ok("embedder does NOT raise uncaught exception", False,
               f"raised: {embed_err}")
    except ImportError as e:
        warn("embedder module failed to import", str(e))


# -----------------------------------------------------------------------------
# 6. Vector Store Reality -- Embedding Count
# -----------------------------------------------------------------------------

def test_vector_store_reality():
    try:
        from filemind.vector_store import VectorStore
        vs = VectorStore()
        count = vs.count()
        expected_chunks = 0
        if DB_PATH.exists():
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()
            cursor.execute("SELECT COALESCE(SUM(chunk_count), 0) FROM file_index")
            expected_chunks = cursor.fetchone()[0] or 0
            conn.close()
        ok("vector store count() returns int", isinstance(count, int))

        if expected_chunks == 0:
            warn("vector store comparison skipped", "expected chunk count is 0 or rebuild is in progress")
        elif count == 0:
            ok(f"vector store has embeddings (FAIL: 0/{expected_chunks} chunks indexed)", False,
               "Qdrant is empty or the rebuild has not committed yet")
        elif count < expected_chunks * 0.5:
            warn(f"vector store partially populated ({count}/{expected_chunks})",
                 "some chunks may still be rebuilding -- re-run: python run.py scan --full")
        else:
            ok(f"vector store populated ({count}/{expected_chunks})", True)
        vs.close()
    except Exception as e:
        warn("vector store check failed", str(e))


# -----------------------------------------------------------------------------
# 7. Pipeline E2E -- Scan Temp Dir, Verify All Stages
# -----------------------------------------------------------------------------

def test_pipeline_e2e():
    from filemind.scanner import FileScanner
    from filemind.catalog import Catalog
    from filemind.extractor import extract_content
    from filemind.chunker import chunk_text

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create known test files
        files = {
            "alpha.py": "def greet():\n    return 'hello world'\n\nclass Bot:\n    pass",
            "beta.md": "# FileMind Test\n\nThis document tests the pipeline end to end.",
            "gamma.txt": "Plain text file with some content about Telegram bots and API keys.",
        }
        for name, content in files.items():
            with open(os.path.join(tmpdir, name), "w") as f:
                f.write(content)

        # Stage 1: Extract content
        for name, expected_word in [("alpha.py", "greet"), ("beta.md", "FileMind"), ("gamma.txt", "Telegram")]:
            content = extract_content(os.path.join(tmpdir, name))
            ok(f"extractor reads {name}", expected_word in content)

        # Stage 2: Chunk text
        py_content = extract_content(os.path.join(tmpdir, "alpha.py"))
        chunks = chunk_text(py_content, "alpha.py")
        ok("chunker produces chunks from .py file", len(chunks) >= 1)

        # Stage 3: Catalog insert + FTS search
        db_path = Path(tmpdir) / "e2e_test.db"
        cat = Catalog(db_path=db_path)
        cat.init_db()

        for name, content in files.items():
            full_path = os.path.join(tmpdir, name)
            cat.upsert_file(
                path=name,
                full_path=full_path,
                size=os.path.getsize(full_path),
                mtime=os.path.getmtime(full_path),
                content_hash=hashlib.md5(content.encode()).hexdigest(),
                ext=os.path.splitext(name)[1],
                content_summary=content,
                category="unknown",
                confidence=0.0,
                chunk_count=1,
            )

        ok("E2E: 3 files stored in catalog", cat.count() == 3)

        results = cat.fts_search("Telegram", top_k=5)
        ok("E2E: FTS finds 'Telegram' in gamma.txt",
           any("gamma" in r.get("path", "") for r in results))

        results = cat.fts_search("FileMind pipeline", top_k=5)
        ok("E2E: FTS finds 'FileMind' in beta.md",
           any("beta" in r.get("path", "") for r in results))

        # Stage 4: Scan log
        scan_id = cat.start_scan()
        cat.complete_scan(scan_id, 3, 3, 3, 0, 0)
        history = cat.get_scan_history(1)
        ok("E2E: scan log records run", len(history) == 1 and history[0]["status"] == "completed")

        cat.close()


# -----------------------------------------------------------------------------
# 8. Duplicate Detection -- Finds Known Identical Files
# -----------------------------------------------------------------------------

def test_duplicate_detection():
    from filemind.catalog import Catalog
    from filemind.duplicates import DuplicateDetector

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "dup_test.db"
        cat = Catalog(db_path=db_path)
        cat.init_db()

        same_hash = hashlib.md5(b"identical content").hexdigest()
        unique_hash = hashlib.md5(b"completely different").hexdigest()

        # Insert 2 files with same hash (exact duplicates)
        for i in range(2):
            cat.upsert_file(
                path=f"dup_{i}.txt",
                full_path=f"/tmp/dup_{i}.txt",
                size=100,
                mtime=1700000000.0,
                content_hash=same_hash,
                ext=".txt",
                content_summary="identical content",
                category="personal",
                confidence=0.9,
                chunk_count=1,
            )
        # Insert 1 unique file
        cat.upsert_file(
            path="unique.txt",
            full_path="/tmp/unique.txt",
            size=200,
            mtime=1700000000.0,
            content_hash=unique_hash,
            ext=".txt",
            content_summary="completely different",
            category="personal",
            confidence=0.9,
            chunk_count=1,
        )

        detector = DuplicateDetector(catalog=cat)
        exact = detector.find_exact()

        ok("duplicate detector finds the 2 identical files",
           same_hash in exact and len(exact[same_hash]) == 2)
        ok("duplicate detector does not flag unique file",
           unique_hash not in exact)
        ok("duplicate report returns dict",
           isinstance(detector.report(), dict))

        cat.close()


# -----------------------------------------------------------------------------
# 9. Search Relevance -- Real Index, Known Queries
# -----------------------------------------------------------------------------

def test_search_relevance():
    """Query the live production DB -- not a toy fixture."""
    from filemind.catalog import Catalog
    cat = Catalog()

    # bot.py must rank higher than unrelated files for "Telegram bot"
    results = cat.fts_search("Telegram bot", top_k=5)
    paths = [r.get("path", "") for r in results]
    has_bot = any("bot" in p.lower() or "telegram" in p.lower() for p in paths)
    ok("'Telegram bot' query returns bot-related files", has_bot,
       f"top paths: {paths[:3]}")

    # scanner.py must appear when searching for "file scanner directory walk"
    results = cat.fts_search("file scanner directory", top_k=10)
    paths = [r.get("path", "") for r in results]
    has_scanner = any("scanner" in p.lower() for p in paths)
    ok("'file scanner directory' query finds scanner.py", has_scanner,
       f"top paths: {paths[:3]}")

    # FileMind master plan must appear for "filemind architecture"
    results = cat.fts_search("filemind architecture", top_k=10)
    paths = [r.get("path", "") for r in results]
    has_plan = any("filemind" in p.lower() or "master" in p.lower() for p in paths)
    ok("'filemind architecture' query finds master plan", has_plan,
       f"top paths: {paths[:3]}")

    cat.close()


# -----------------------------------------------------------------------------
# 10. Category Accuracy -- Spot-Check Against File Extensions
# -----------------------------------------------------------------------------

def test_category_accuracy():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # .py files should be "code" (not unknown/config/personal)
    c.execute("SELECT COUNT(*) FROM file_index WHERE ext='.py' AND category='code'")
    py_code = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM file_index WHERE ext='.py'")
    py_total = c.fetchone()[0]
    pct = py_code / py_total if py_total else 0
    ok(f".py files classified as 'code' >= 70% ({pct:.0%})", pct >= 0.7,
       f"{py_code}/{py_total} .py files are code")

    # .md files should be documentation or ai_project
    c.execute("SELECT COUNT(*) FROM file_index WHERE ext='.md' AND category IN ('documentation','ai_project','research')")
    md_doc = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM file_index WHERE ext='.md'")
    md_total = c.fetchone()[0]
    pct = md_doc / md_total if md_total else 0
    ok(f".md files classified as doc/research/ai >= 60% ({pct:.0%})", pct >= 0.6,
       f"{md_doc}/{md_total} .md files are docs/research/ai_project")

    # .json files should NOT be classified as personal/finance (should be config/code)
    c.execute("SELECT COUNT(*) FROM file_index WHERE ext='.json' AND category IN ('config','code','ai_project')")
    json_ok = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM file_index WHERE ext='.json'")
    json_total = c.fetchone()[0]
    pct = json_ok / json_total if json_total else 0
    ok(f".json files classified as config/code/ai >= 80% ({pct:.0%})", pct >= 0.8,
       f"{json_ok}/{json_total} .json files in expected categories")

    conn.close()


# -----------------------------------------------------------------------------
# Runner
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("FileMind Reality Check & Integration Tests")
    print("=" * 60)

    run_section("1. Dependency Audit", test_dependencies)
    run_section("2. DB Integrity", test_db_integrity)
    run_section("3. FTS Search Quality", test_fts_search_quality)
    run_section("4. Classifier API Contracts", test_classifier_api)
    run_section("5. Embedder Graceful Degradation", test_embedder_degradation)
    run_section("6. Vector Store Reality", test_vector_store_reality)
    run_section("7. Pipeline E2E", test_pipeline_e2e)
    run_section("8. Duplicate Detection", test_duplicate_detection)
    run_section("9. Search Relevance (Live Index)", test_search_relevance)
    run_section("10. Category Accuracy", test_category_accuracy)

    print(f"\n{'='*60}")
    print(f"  RESULTS")
    print(f"{'='*60}")
    for status, name, detail in _results:
        marker = {"PASS": "OK", "FAIL": "FAIL", "WARN": "WARN", "ERRO": "ERR"}.get(status, "?")
        line = f"  [{marker}] {name}"
        if detail:
            line += f"\n       -> {detail}"
        print(line)

    print(f"\n  {passed} passed  |  {failed} failed  |  {warnings} warnings")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)
