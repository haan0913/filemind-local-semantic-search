from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

from filemind import verify as verify_module
from filemind.catalog import Catalog
from filemind.scan_lock import (
    acquire_scan_lock,
    heartbeat_scan_lock,
    raise_if_scan_cancel_requested,
    release_scan_lock,
    request_scan_cancel,
)


class ScanLockTests(unittest.TestCase):
    def test_active_lock_raises_clear_error(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        lock_path = Path(temp_dir.name) / "scan_full.lock"
        lock_path.write_text('{"pid": 12345, "mode": "full"}\n', encoding="utf-8")

        with patch("filemind.scan_lock._process_exists", return_value=True):
            with self.assertRaises(RuntimeError) as exc:
                acquire_scan_lock("full", lock_path)

        self.assertIn("already running", str(exc.exception))

    def test_stale_lock_is_replaced(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        lock_path = Path(temp_dir.name) / "scan_full.lock"
        lock_path.write_text('{"pid": 12345, "mode": "full"}\n', encoding="utf-8")
        old_timestamp = time.time() - 120
        os.utime(lock_path, (old_timestamp, old_timestamp))

        with patch("filemind.scan_lock._process_exists", return_value=False):
            payload = acquire_scan_lock("rebuild", lock_path, stale_after_seconds=60)
            self.addCleanup(lambda: release_scan_lock(lock_path))

        self.assertEqual(payload["pid"], os.getpid())
        self.assertTrue(lock_path.exists())

    def test_dead_pid_lock_is_retryable_until_old_enough(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        lock_path = Path(temp_dir.name) / "scan_full.lock"
        original = '{"pid": 12345, "mode": "full"}\n'
        lock_path.write_text(original, encoding="utf-8")

        with patch("filemind.scan_lock._process_exists", return_value=False):
            with self.assertRaises(RuntimeError) as exc:
                acquire_scan_lock("rebuild", lock_path, stale_after_seconds=60)

        self.assertIn("dead pid", str(exc.exception))
        self.assertEqual(lock_path.read_text(encoding="utf-8"), original)

    def test_cancel_request_survives_competing_scan_start(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        lock_path = Path(temp_dir.name) / "scan_full.lock"
        cancel_path = lock_path.with_suffix(".cancel")
        lock_path.write_text('{"pid": 12345, "mode": "full"}\n', encoding="utf-8")
        request_scan_cancel(
            "stop the active scan", requested_by="codex", lock_path=lock_path
        )

        with patch("filemind.scan_lock._process_exists", return_value=True):
            with self.assertRaises(RuntimeError):
                acquire_scan_lock("rebuild", lock_path)

        self.assertTrue(cancel_path.exists())
        self.assertIn("stop the active scan", cancel_path.read_text(encoding="utf-8"))

    def test_recent_partial_lock_is_retryable_and_preserved(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        lock_path = Path(temp_dir.name) / "scan_full.lock"
        partial = '{"pid": '
        lock_path.write_text(partial, encoding="utf-8")

        with self.assertRaises(RuntimeError) as exc:
            acquire_scan_lock("full", lock_path, stale_after_seconds=60)

        self.assertIn("unreadable or incomplete", str(exc.exception))
        self.assertEqual(lock_path.read_text(encoding="utf-8"), partial)

    def test_old_corrupt_lock_is_replaced(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        lock_path = Path(temp_dir.name) / "scan_full.lock"
        lock_path.write_text('{"pid": ', encoding="utf-8")
        old_timestamp = time.time() - 120
        os.utime(lock_path, (old_timestamp, old_timestamp))

        payload = acquire_scan_lock("full", lock_path, stale_after_seconds=60)
        self.addCleanup(lambda: release_scan_lock(lock_path))

        self.assertEqual(payload["pid"], os.getpid())
        self.assertIn('"mode": "full"', lock_path.read_text(encoding="utf-8"))

    def test_lock_heartbeat_records_phase_and_progress(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        lock_path = Path(temp_dir.name) / "scan_full.lock"
        acquire_scan_lock("full", lock_path)
        self.addCleanup(lambda: release_scan_lock(lock_path))

        updated = heartbeat_scan_lock(
            lock_path=lock_path,
            phase="embed",
            progress={"batch": 2, "total_batches": 5},
        )

        self.assertIsNotNone(updated)
        assert updated is not None
        self.assertEqual(updated["phase"], "embed")
        self.assertEqual(updated["progress"]["batch"], 2)

    def test_lock_heartbeat_requires_current_process_owner(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        lock_path = Path(temp_dir.name) / "scan_full.lock"
        original = '{"pid": 12345, "mode": "full", "phase": "walk"}\n'
        lock_path.write_text(original, encoding="utf-8")

        updated = heartbeat_scan_lock(lock_path=lock_path, phase="embed")

        self.assertIsNone(updated)
        self.assertEqual(lock_path.read_text(encoding="utf-8"), original)

    def test_scan_cancel_request_is_cooperative(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        lock_path = Path(temp_dir.name) / "scan_full.lock"
        acquire_scan_lock("full", lock_path)
        self.addCleanup(lambda: release_scan_lock(lock_path))

        request_scan_cancel(
            "operator timeout", requested_by="codex", lock_path=lock_path
        )

        with self.assertRaises(RuntimeError) as exc:
            raise_if_scan_cancel_requested(lock_path)
        self.assertIn("operator timeout", str(exc.exception))

    def test_release_removes_only_owned_lock_and_cancel(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        lock_path = Path(temp_dir.name) / "scan_full.lock"
        cancel_path = lock_path.with_suffix(".cancel")

        acquire_scan_lock("full", lock_path)
        request_scan_cancel("done", lock_path=lock_path)
        release_scan_lock(lock_path)

        self.assertFalse(lock_path.exists())
        self.assertFalse(cancel_path.exists())

        other_lock = '{"pid": 12345, "mode": "full"}\n'
        lock_path.write_text(other_lock, encoding="utf-8")
        request_scan_cancel("still running", lock_path=lock_path)
        release_scan_lock(lock_path)

        self.assertEqual(lock_path.read_text(encoding="utf-8"), other_lock)
        self.assertTrue(cancel_path.exists())

    def test_release_preserves_unreadable_lock(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        lock_path = Path(temp_dir.name) / "scan_full.lock"
        partial = '{"pid": '
        lock_path.write_text(partial, encoding="utf-8")

        release_scan_lock(lock_path)

        self.assertEqual(lock_path.read_text(encoding="utf-8"), partial)

    def test_catalog_reconciles_legacy_running_rows(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        catalog = Catalog(Path(temp_dir.name) / "filemind.db")
        catalog.init_db()
        self.addCleanup(catalog.close)
        catalog_api = cast(Any, catalog)

        catalog.conn.execute(
            "INSERT INTO scan_log (started_at, status) VALUES (?, 'running')",
            (1.0,),
        )
        catalog.conn.commit()

        stale: list[dict[str, Any]] = catalog_api.reconcile_running_scans(
            stale_legacy=True
        )
        rows = catalog.conn.execute("SELECT status FROM scan_log").fetchall()

        self.assertEqual(len(stale), 1)
        self.assertEqual(rows[0]["status"], "stale")

    def test_catalog_keeps_live_pid_running(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        catalog = Catalog(Path(temp_dir.name) / "filemind.db")
        catalog.init_db()
        self.addCleanup(catalog.close)
        catalog_api = cast(Any, catalog)

        scan_id: int = catalog_api.start_scan(
            mode="full", command="test", pid=os.getpid()
        )
        rows: list[dict[str, Any]] = catalog_api.get_running_scans()
        catalog.complete_scan(scan_id, 0, 0, 0, 0, 0)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["pid"], os.getpid())
        self.assertEqual(rows[0]["mode"], "full")

    def test_verify_reports_in_progress_instead_of_corruption(self) -> None:
        class RunningCatalog:
            def get_all_files(self) -> list[dict[str, Any]]:
                return [
                    {
                        "path": "docs/a.md",
                        "full_path": "C:/docs/a.md",
                        "content_summary": "alpha",
                        "chunk_count": 1,
                        "size": 100,
                    }
                ]

            def reconcile_running_scans(self, **_kwargs: Any) -> list[dict[str, Any]]:
                return []

            def get_running_scans(self, reconcile: bool = True) -> list[dict[str, Any]]:
                return [{"id": 7, "pid": os.getpid(), "mode": "full"}]

        def canonical_path(path: str) -> str:
            return path.lower()

        def evaluate_path_scope(path: str, size: int = 0) -> tuple[bool, str]:
            return (True, "in_scope")

        fake_scanner = SimpleNamespace(
            _canonical_fs_path=canonical_path,
            _evaluate_existing_path_scope=evaluate_path_scope,
        )

        with (
            patch(
                "filemind.verify.collect_indexable_disk_paths",
                return_value=({"docs/a.md"}, {"c:/docs/a.md"}),
            ),
            patch("filemind.verify._get_scan_lock_status", return_value=None),
        ):
            report = cast(
                dict[str, Any],
                verify_module.build_verification_report(
                    catalog=cast(Any, RunningCatalog()),
                    scanner=cast(Any, fake_scanner),
                    vector_chunk_count=99,
                    vector_chunk_error=None,
                    vector_target="shared:http://127.0.0.1:6333 [file_chunks]",
                ),
            )

        self.assertFalse(report["chunk_parity"])
        self.assertEqual(report["status"], "IN_PROGRESS")
        self.assertIn("scan is in progress", cast(str, report["status_message"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
