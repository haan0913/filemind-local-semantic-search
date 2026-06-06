"""
Comprehensive tests for FileMind modules.
Tests core functionality without requiring full scan.
"""

import os
import sys
import tempfile
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from filemind.config import config, ensure_dirs
from filemind.chunker import TextChunker, chunk_text
from filemind.extractor import extract_content, get_supported_extensions

print("=" * 60)
print("FileMind — Comprehensive Test Suite")
print("=" * 60)

errors = 0
passed = 0


def report_test(name, condition):
    global errors, passed
    if condition:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        errors += 1
        print(f"  [FAIL] {name}")


# ── Config Tests ────────────────────────────────────────────────────
print("\n--- Config ---")
try:
    ensure_dirs()
    report_test("ensure_dirs() creates directories", config.index_dir.exists())
    report_test("scan_roots has entries", len(config.scan_roots) > 0)
    report_test("categories has 10 entries", len(config.categories) == 10)
    report_test("embedding_dim is 1024", config.embedding_dim == 1024)
    report_test("chunk_size is 2048", config.chunk_size == 2048)
    report_test("chunk_overlap is 256", config.chunk_overlap == 256)
except Exception as e:
    print(f"  [ERRO] Config tests failed: {e}")
    errors += 10

# ── Chunker Tests ───────────────────────────────────────────────────
print("\n--- Chunker ---")
try:
    chunker = TextChunker(chunk_size=10, overlap=2)

    # Empty text
    result = chunker.chunk("")
    report_test("Empty text returns empty list", len(result) == 0)

    # Small text (under chunk size)
    result = chunker.chunk("hello world test")
    report_test("Small text returns 1 chunk", len(result) == 1)
    report_test("Chunk has correct content", result[0].content == "hello world test")

    # Large text
    text = " ".join([f"word{i}" for i in range(100)])
    result = chunker.chunk(text)
    report_test("Large text returns multiple chunks", len(result) > 1)
    report_test("First chunk has content", len(result[0].content) > 0)

    # Overlap test
    chunker2 = TextChunker(chunk_size=5, overlap=2)
    text2 = " ".join([f"w{i}" for i in range(20)])
    result2 = chunker2.chunk(text2)
    report_test("Overlap creates expected chunks", len(result2) > 1)

    # Convenience function
    result = chunk_text("test text here", "test.txt", chunk_size=5, overlap=1)
    report_test("chunk_text() function works", len(result) > 0)
except Exception as e:
    print(f"  [ERRO] Chunker tests failed: {e}")
    errors += 10

# ── Extractor Tests ─────────────────────────────────────────────────
print("\n--- Extractor ---")
try:
    # Create temp file and test extraction
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("Hello, this is a test file for extraction.")
        temp_path = f.name

    content = extract_content(temp_path)
    report_test("Text file extraction works", "Hello" in content)
    os.unlink(temp_path)

    # Test nonexistent file
    result = extract_content("/nonexistent/path/file.txt")
    report_test("Nonexistent file returns empty string", result == "")

    # Test supported extensions
    exts = get_supported_extensions()
    report_test("Has supported extensions", len(exts) > 0)
    report_test(".txt in extensions", ".txt" in exts)
    report_test(".py in extensions", ".py" in exts)
    report_test(".md in extensions", ".md" in exts)

except Exception as e:
    print(f"  [ERRO] Extractor tests failed: {e}")
    errors += 10

# ── Catalog Tests ───────────────────────────────────────────────────
print("\n--- Catalog ---")
try:
    from filemind.catalog import Catalog

    # Use temp database for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        catalog = Catalog(db_path=db_path)
        catalog.init_db()

        # Insert test file
        catalog.upsert_file(
            path="test/file.md",
            full_path="/tmp/test/file.md",
            size=1000,
            mtime=1700000000.0,
            content_hash="abc123",
            ext=".md",
            content_summary="Test content",
            category="documentation",
            confidence=0.9,
            chunk_count=1,
        )

        report_test("File stored in catalog", catalog.count() == 1)

        # Retrieve file
        file = catalog.get_file("test/file.md")
        report_test("Can retrieve stored file", file is not None)
        assert file is not None
        report_test("File has correct category", file["category"] == "documentation")

        # Category filter
        files = catalog.get_files_by_category("documentation")
        report_test("Category filter works", len(files) == 1)

        # Extension filter
        files = catalog.get_files_by_type(".md")
        report_test("Extension filter works", len(files) == 1)

        # Update category
        catalog.update_category("test/file.md", "research", 0.8)
        file = catalog.get_file("test/file.md")
        assert file is not None
        report_test("Category update works", file["category"] == "research")

        # FTS search
        catalog2 = Catalog(db_path=Path(tmpdir) / "test2.db")
        catalog2.init_db()
        catalog2.upsert_file(
            path="search_test.py",
            full_path="/tmp/search_test.py",
            size=500,
            mtime=1700000000.0,
            content_hash="def456",
            ext=".py",
            content_summary="This is a Python script for testing search functionality",
            category="code",
            confidence=0.9,
            chunk_count=1,
        )
        results = catalog2.fts_search("Python script", top_k=5)
        report_test("FTS search returns results", len(results) > 0)

        # Scan logging
        scan_id = catalog2.start_scan()
        report_test("Scan log created", scan_id > 0)
        catalog2.complete_scan(scan_id, 100, 5, 3, 1, 0)
        history = catalog2.get_scan_history(5)
        report_test("Scan history works", len(history) > 0)

        # Stats
        stats = catalog2.get_stats()
        report_test("Stats returns total_files", stats["total_files"] > 0)
        report_test("Stats has categories", len(stats["categories"]) > 0)

        # Delete file
        catalog2.delete_file("search_test.py")
        report_test("File deleted", catalog2.count() == 0)

        catalog.close()
        catalog2.close()

except Exception as e:
    print(f"  [ERRO] Catalog tests failed: {e}")
    import traceback

    traceback.print_exc()
    errors += 10

# ── Classifier Tests ────────────────────────────────────────────────
print("\n--- Classifier ---")
try:
    from filemind.classifier import Classifier

    classifier = Classifier()

    # Test _parse_indexed_response with good JSON (index-based format)
    json_input = """[
        {"i": 1, "category": "code", "confidence": 0.9},
        {"i": 2, "category": "documentation", "confidence": 0.8}
    ]"""
    files = [{"path": "test.py"}, {"path": "readme.md"}]
    result = classifier._parse_indexed_response(json_input, files)
    report_test("Parses valid JSON array (index-based)", len(result) == 2)
    report_test("Category matches", result[0]["category"] == "code")

    # Test _parse_indexed_response with markdown fences
    fenced_input = """```json
[{"i": 1, "category": "code", "confidence": 0.9}]
```"""
    result = classifier._parse_indexed_response(fenced_input, [{"path": "test.py"}])
    report_test("Handles markdown fences", len(result) == 1)
    report_test("Category correct with fences", result[0]["category"] == "code")

    # Test _parse_indexed_response with dict wrapper
    dict_input = '{"files": [{"i": 1, "category": "code", "confidence": 0.9}]}'
    result = classifier._parse_indexed_response(dict_input, [{"path": "test.py"}])
    report_test("Handles dict wrapper with 'files' key", len(result) == 1)

    # Test fallback for invalid JSON
    result = classifier._parse_indexed_response(
        "not json at all", [{"path": "test.py"}]
    )
    report_test("Invalid JSON returns unknown", result[0]["category"] == "unknown")

except Exception as e:
    print(f"  [ERRO] Classifier tests failed: {e}")
    errors += 10

# ── Scanner Tests ───────────────────────────────────────────────────
print("\n--- Scanner ---")
try:
    from filemind.scanner import FileScanner

    scanner = FileScanner()
    report_test("Scanner created", scanner is not None)
    report_test("Has correct skip dirs", ".git" in scanner.cfg.skip_dirs)

except Exception as e:
    print(f"  [ERRO] Scanner tests failed: {e}")
    errors += 5

# ── Summary ──────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print(f"Results: {passed} passed, {errors} failed")
if errors == 0:
    print("All tests passed!")
else:
    print(f"WARNING: {errors} test(s) failed")
print("=" * 60)
