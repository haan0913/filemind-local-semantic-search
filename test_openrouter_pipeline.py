#!/usr/bin/env python3
"""Test full pipeline with OpenRouter for classification (bypasses Ollama gemma4 issues)."""
import sys, os, time, json
sys.path.insert(0, 'C:/AI_STATION/filemind')

from config import config
config.ollama_api_url = 'http://127.0.0.1:9999'  # Invalid port - force Ollama fallback
from catalog import Catalog
from extractor import extract_content
from classifier import Classifier
from chunker import TextChunker
from embedder import get_embedder
from vector_store import VectorStore
from scanner import FileScanner

print("=== Full Pipeline Test with OpenRouter ===\n")

# Phase 1: Scan - use filemind directory only (small test)
print("Phase 1: Scanning...")
config.scan_roots = ["C:/AI_STATION/filemind"]
scanner = FileScanner()
changes, deleted = scanner.scan()
print(f"  Found {len(changes)} changes, {len(deleted)} deleted")

# Limit to first 10 files for testing
test_files = changes[:10]
print(f"  Testing with {len(test_files)} files\n")

# Phase 2: Extract
print("Phase 2: Extracting content...")
catalog = Catalog()
catalog.init_db()
file_data = []
for change in test_files:
    try:
        content = extract_content(change.full_path, max_size=config.max_file_size)
        summary = content[:config.max_content_length]
        file_data.append({
            "path": change.path,
            "full_path": change.full_path,
            "size": change.size,
            "mtime": change.mtime,
            "content_hash": change.content_hash,
            "ext": change.ext,
            "content_summary": summary,
            "change_type": change.change_type,
        })
        catalog.upsert_file(
            path=change.path, full_path=change.full_path,
            size=change.size, mtime=change.mtime,
            content_hash=change.content_hash, ext=change.ext,
            content_summary=summary,
        )
        print(f"  Extracted: {change.path}")
    except Exception as e:
        print(f"  Error: {change.path} - {e}")

print(f"  Total extracted: {len(file_data)}\n")

# Phase 3: Classify (will fail Ollama -> fallback to OpenRouter)
print("Phase 3: Classifying (via OpenRouter)...")
classifier = Classifier()
classifications = classifier.classify(file_data)
class_map = {cls["path"]: cls for cls in classifications}
for cls in classifications:
    catalog.update_category(cls["path"], cls["category"], cls["confidence"])
    print(f"  {cls['path'][:60]} -> {cls['category']} ({cls['confidence']:.2f})")
print(f"  Total classified: {len(classifications)}\n")

# Phase 4: Chunk & Embed
print("Phase 4: Chunking and embedding...")
chunker = TextChunker()
vs = VectorStore()
total_chunks = 0
for fd in file_data:
    content = fd.get("content_summary", "")
    if not content.strip():
        continue
    try:
        chunks = chunker.chunk(content, fd["path"])
        if not chunks:
            continue
        embedder = get_embedder()
        texts = [c.content for c in chunks]
        encoded = embedder.encode(texts, return_dense=True, return_sparse=True)
        dense_vecs = encoded.get("dense_vecs", [])
        sparse_vecs = encoded.get("lexical_weights", [{}] * len(chunks))
        cls_info = class_map.get(fd["path"], {})
        category = cls_info.get("category", "unknown")
        chunk_records = []
        for i, chunk in enumerate(chunks):
            chunk_id = f"{fd['path']}::chunk_{i}"
            chunk_records.append({
                "id": chunk_id, "file_id": fd["path"],
                "chunk_index": i, "content": chunk.content,
                "vector": dense_vecs[i] if i < len(dense_vecs) else [],
                "sparse_vector": sparse_vecs[i] if i < len(sparse_vecs) else {},
                "file_type": fd.get("ext", ""), "category": category,
                "mtime": fd.get("mtime", 0),
            })
        vs.upsert_chunks(chunk_records)
        catalog.update_chunk_count(fd["path"], len(chunks))
        total_chunks += len(chunks)
        print(f"  Embedded: {fd['path']} ({len(chunks)} chunks)")
    except Exception as e:
        print(f"  Error: {fd['path']} - {e}")

print(f"\n  Total chunks created: {total_chunks}")

# Verify
print("\n=== VERIFICATION ===")
total = catalog.count()
categorized = catalog.conn.execute('SELECT COUNT(*) FROM file_index WHERE category != "unknown"').fetchone()[0]
emb = catalog.conn.execute('SELECT COUNT(*) FROM file_index WHERE chunk_count > 0').fetchone()[0]
print(f"Files indexed: {total}")
print(f"Files classified (non-unknown): {categorized}")
print(f"Files with embeddings: {emb}")
print(f"Chunks created: {total_chunks}")

if total > 0 and categorized > 0 and emb > 0:
    print("\n✅ PIPELINE TEST SUCCESSFUL!")
else:
    print("\n❌ PIPELINE TEST FAILED - check errors above")

catalog.close()
vs.close()