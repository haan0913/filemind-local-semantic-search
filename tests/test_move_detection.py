"""Focused regression tests for rename-aware move handling."""

import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from filemind.catalog import Catalog
from filemind.config import config
from filemind.scanner import FileScanner
from filemind.vector_store import VectorStore


class MoveDetectionTests(unittest.TestCase):
    def test_catalog_move_file_preserves_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "catalog.db"
            catalog = Catalog(db_path=db_path)
            catalog.init_db()
            try:
                catalog.upsert_file(
                    path="old/report.txt",
                    full_path="C:/tmp/old/report.txt",
                    size=123,
                    mtime=100.0,
                    content_hash="hash-123",
                    ext=".txt",
                    content_summary="Quarterly report",
                    category="documentation",
                    confidence=0.95,
                    chunk_count=3,
                    tags=["finance"],
                    tier="user",
                )

                moved = catalog.move_file(
                    old_path="old/report.txt",
                    new_path="archive/report.txt",
                    new_full_path="C:/tmp/archive/report.txt",
                    size=123,
                    mtime=200.0,
                    content_hash="hash-123",
                    ext=".txt",
                )

                self.assertTrue(moved)
                self.assertIsNone(catalog.get_file("old/report.txt"))
                record = catalog.get_file("archive/report.txt")
                self.assertIsNotNone(record)
                assert record is not None
                self.assertEqual(record["category"], "documentation")
                self.assertEqual(record["chunk_count"], 3)
                self.assertEqual(record["full_path"], "C:/tmp/archive/report.txt")
                self.assertEqual(record["mtime"], 200.0)
            finally:
                catalog.close()

    def test_scanner_detects_rename_as_move(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "scanroot"
            old_dir = root / "old"
            new_dir = root / "new"
            old_dir.mkdir(parents=True)
            new_dir.mkdir(parents=True)

            source = old_dir / "notes.txt"
            source.write_text("Move me without changing content.", encoding="utf-8")

            scan_cfg = replace(config, scan_roots=[str(root)])
            scanner = FileScanner(config_obj=scan_cfg)

            db_path = Path(tmpdir) / "scanner.db"
            catalog = Catalog(db_path=db_path)
            catalog.init_db()
            try:
                stat = source.stat()
                catalog.upsert_file(
                    path="old/notes.txt",
                    full_path=str(source.resolve()).replace("\\", "/"),
                    size=stat.st_size,
                    mtime=stat.st_mtime,
                    content_hash=scanner._compute_hash(str(source)),
                    ext=".txt",
                    content_summary=source.read_text(encoding="utf-8"),
                    category="documentation",
                    confidence=0.8,
                    chunk_count=1,
                )
                catalog.conn.commit()

                renamed = new_dir / "notes.txt"
                os.replace(source, renamed)

                changes, deleted = scanner.scan(catalog=catalog)
                self.assertEqual(deleted, set())
                self.assertEqual(len(changes), 1)
                self.assertEqual(changes[0].change_type, "moved")
                self.assertEqual(changes[0].previous_path, "old/notes.txt")
                self.assertEqual(
                    changes[0].path, scanner._make_index_path(str(renamed), root)
                )
            finally:
                catalog.close()

    def test_scanner_dedupes_overlapping_roots(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "scanroot"
            root.mkdir(parents=True)
            target = root / "note.txt"
            target.write_text("Same file through duplicate roots.", encoding="utf-8")

            scan_cfg = replace(config, scan_roots=[str(root), str(root)])
            scanner = FileScanner(config_obj=scan_cfg)

            db_path = Path(tmpdir) / "scanner.db"
            catalog = Catalog(db_path=db_path)
            catalog.init_db()
            try:
                changes, deleted = scanner.scan(catalog=catalog)

                self.assertEqual(deleted, set())
                self.assertEqual(len(changes), 1)
                self.assertEqual(changes[0].change_type, "new")
                self.assertEqual(
                    changes[0].path, scanner._make_index_path(str(target), root)
                )
            finally:
                catalog.close()

    def test_vector_store_move_file_rekeys_chunks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            local_vector_config = replace(
                config,
                qdrant_mode="local",
                qdrant_url="",
                qdrant_collection="test_file_chunks_move_detection",
            )
            with patch("filemind.vector_store.config", local_vector_config):
                vs = VectorStore(db_path=Path(tmpdir) / "qdrant")
            try:
                old_file_id = "docs/old.txt"
                new_file_id = "archive/new.md"
                vs.upsert_chunks(
                    [
                        {
                            "id": f"{old_file_id}::chunk_0",
                            "file_id": old_file_id,
                            "chunk_index": 0,
                            "chunk_hash": "chunk-hash",
                            "content": "Move-aware vector reuse",
                            "vector": [0.0] * config.embedding_dim,
                            "sparse_vector": {"move": 1.0},
                            "file_type": ".txt",
                            "category": "documentation",
                            "mtime": 10.0,
                        }
                    ]
                )

                moved = vs.move_file(
                    old_file_id=old_file_id,
                    new_file_id=new_file_id,
                    new_mtime=20.0,
                    new_file_type=".md",
                )

                self.assertEqual(moved, 1)
                self.assertEqual(vs.get_file_chunks(old_file_id), [])
                new_chunks = vs.get_file_chunks(new_file_id)
                self.assertEqual(len(new_chunks), 1)
                self.assertEqual(new_chunks[0]["id"], f"{new_file_id}::chunk_0")
                self.assertEqual(new_chunks[0]["file_id"], new_file_id)
                self.assertEqual(new_chunks[0]["file_type"], ".md")
                self.assertEqual(new_chunks[0]["mtime"], 20.0)
            finally:
                vs.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
