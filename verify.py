# pyright: reportMissingParameterType=false, reportMissingTypeArgument=false, reportPrivateUsage=false, reportUnknownParameterType=false
"""
Verification - compare FileMind's live scan scope against the current index.

Answers: "Did we index every file FileMind currently intends to track?"
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, cast

try:
    from .config import config
    from .catalog import Catalog
    from .scanner import FileScanner
    from .scan_lock import (
        SCAN_LOCK_PATH,
        _process_exists,
        heartbeat_scan_lock,
        raise_if_scan_cancel_requested,
        read_scan_lock,
    )
    from .vector_store import VectorStore
except ImportError:
    from config import config
    from catalog import Catalog
    from scanner import FileScanner
    from scan_lock import (
        SCAN_LOCK_PATH,
        _process_exists,
        heartbeat_scan_lock,
        raise_if_scan_cancel_requested,
        read_scan_lock,
    )
    from vector_store import VectorStore


_UNSET = object()


def _safe_console_text(value) -> str:
    """Return text that will not fail on legacy Windows console encodings."""
    text = "" if value is None else str(value)
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding, errors="replace")


def _print_line(value=""):
    print(_safe_console_text(value))


def _is_link_or_junction(path: str) -> bool:
    """Return whether a directory is a symlink or Windows junction."""
    is_junction = getattr(os.path, "isjunction", None)
    return os.path.islink(path) or (is_junction(path) if is_junction else False)


def collect_indexable_disk_paths(
    roots: list[str] | None = None,
    scanner: FileScanner | None = None,
) -> tuple[set[str], set[str]]:
    """Collect the effective in-scope file set using the same scanner rules as indexing."""
    scanner = scanner or FileScanner()
    roots = roots or scanner.cfg.scan_roots

    indexed_paths: set[str] = set()
    scanned_real_paths: set[str] = set()

    for root_dir in roots:
        root_path = Path(root_dir)
        if not root_path.exists():
            continue

        for dirpath, dirnames, filenames in os.walk(str(root_path)):
            kept_dirnames = []
            for dirname in dirnames:
                full_dir = os.path.join(dirpath, dirname)
                if _is_link_or_junction(full_dir):
                    continue
                if scanner._should_skip_dir(dirname):
                    continue
                if scanner._should_skip_subdir(dirname, dirpath):
                    continue
                kept_dirnames.append(dirname)
            dirnames[:] = kept_dirnames

            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                ext = scanner._index_extension(filename)
                if ext not in scanner.cfg.index_extensions:
                    continue

                rel_from_root = os.path.relpath(filepath, str(root_path)).replace(
                    "\\", "/"
                )
                if not scanner._should_include_file(rel_from_root):
                    continue

                real_path = scanner._canonical_fs_path(filepath)
                if real_path in scanned_real_paths:
                    continue

                try:
                    stat = os.stat(filepath)
                except (OSError, PermissionError):
                    continue

                if stat.st_size > scanner.cfg.tier2_max_size:
                    continue

                scanned_real_paths.add(real_path)
                indexed_paths.add(scanner._make_index_path(filepath, root_path))

    return indexed_paths, scanned_real_paths


def _classify_catalog_only_record(
    record: dict, scanner: FileScanner, scanned_real_paths: set[str]
) -> str:
    """Explain why a catalog entry is no longer part of the live in-scope file set."""
    full_path = record.get("full_path", "")
    size = int(record.get("size") or 0)

    if full_path and os.path.exists(full_path):
        real_path = scanner._canonical_fs_path(full_path)
        if real_path in scanned_real_paths:
            return "alias_overlap"
        in_scope, reason = scanner._evaluate_existing_path_scope(full_path, size=size)
        if not in_scope:
            return reason
        return "path_key_mismatch"

    rel_path = record.get("path", "")
    if rel_path and os.path.exists(rel_path):
        in_scope, reason = scanner._evaluate_existing_path_scope(rel_path, size=size)
        if not in_scope:
            return f"fallback:{reason}"
        return "fallback:path_key_mismatch"

    return "missing_on_disk"


def get_vector_store_status() -> tuple[int | None, str | None, str]:
    """Return the live vector-store chunk count and target details when available."""
    store = None
    try:
        store = VectorStore()
        count = store.client.count(collection_name=store.collection_name).count
        if getattr(store, "connection_mode", "").lower() == "http":
            target = f"shared:{getattr(config, 'qdrant_url', '') or 'http://127.0.0.1:6333'} [{store.collection_name}]"
        else:
            target = f"local:{store.db_path} [{store.collection_name}]"
        return count, None, target
    except Exception as exc:
        return None, str(exc), "unavailable"
    finally:
        if store is not None:
            store.close()


def _canonical_qdrant_url() -> str:
    qdrant_url = getattr(config, "qdrant_url", "").strip()
    if qdrant_url:
        return qdrant_url.rstrip("/")
    qdrant_host = getattr(config, "qdrant_host", "127.0.0.1")
    qdrant_port = getattr(config, "qdrant_port", 6333)
    return f"http://{qdrant_host}:{qdrant_port}".rstrip("/")


def _vector_store_target_label(vector_store: VectorStore) -> str:
    collection = getattr(
        vector_store,
        "collection_name",
        getattr(config, "qdrant_collection", "file_chunks"),
    )
    mode = str(getattr(vector_store, "connection_mode", "") or "").lower()
    if mode == "http":
        return f"shared:{str(getattr(vector_store, 'qdrant_url', _canonical_qdrant_url())).rstrip('/')} [{collection}]"
    return f"local:{getattr(vector_store, 'db_path', 'unknown')} [{collection}]"


def _validate_canonical_chunk_repair_target(vector_store: VectorStore) -> str | None:
    mode = str(getattr(vector_store, "connection_mode", "") or "").lower()
    collection = str(getattr(vector_store, "collection_name", ""))
    expected_collection = str(getattr(config, "qdrant_collection", "file_chunks"))
    target_label = _vector_store_target_label(vector_store)

    if mode != "http":
        return (
            "Refused chunk-count repair because the vector target is not the canonical "
            f"shared HTTP Qdrant target: {target_label}."
        )
    if collection != expected_collection:
        return (
            "Refused chunk-count repair because the Qdrant collection does not match "
            f"the canonical FileMind collection {expected_collection!r}: {target_label}."
        )

    actual_url = str(
        getattr(vector_store, "qdrant_url", _canonical_qdrant_url())
    ).rstrip("/")
    expected_url = _canonical_qdrant_url()
    if actual_url != expected_url:
        return (
            "Refused chunk-count repair because the shared Qdrant URL drifted from "
            f"{expected_url!r} to {actual_url!r}."
        )
    return None


def _repair_progress(phase: str, **progress: int) -> None:
    heartbeat_scan_lock(phase=phase, progress=progress)
    raise_if_scan_cancel_requested()


def get_vector_file_chunk_counts(
    vector_store: VectorStore | None = None,
    *,
    batch_size: int = 1000,
    progress_callback=None,
) -> dict[str, int]:
    """Return current Qdrant chunk counts grouped by FileMind file_id."""
    owns_store = vector_store is None
    store = vector_store or VectorStore()
    counts: dict[str, int] = {}
    offset = None
    batch_number = 0
    points_seen = 0
    batch_size = max(int(batch_size), 1)
    try:
        while True:
            batch_number += 1
            if progress_callback:
                progress_callback(
                    "repair_chunk_counts_scroll",
                    batch=batch_number,
                    points_seen=points_seen,
                )
            points, next_offset = store.client.scroll(
                collection_name=store.collection_name,
                limit=batch_size,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            points_seen += len(points)
            for point in points:
                payload = point.payload or {}
                file_id = payload.get("file_id")
                if not file_id:
                    continue
                key = str(file_id)
                counts[key] = counts.get(key, 0) + 1
            if next_offset is None:
                break
            offset = next_offset
        return counts
    finally:
        if owns_store:
            close = getattr(store, "close", None)
            if callable(close):
                close()


def repair_catalog_chunk_counts_from_vectors(
    catalog: Catalog | None = None,
    vector_store: VectorStore | None = None,
    *,
    scroll_batch_size: int = 1000,
    update_batch_size: int = 500,
) -> dict:
    """Synchronize catalog chunk_count metadata from the shared vector store.

    This is a metadata repair for interrupted scans that reset catalog chunk_count
    values before Qdrant upserts finished. It does not create or delete vectors.
    """
    owns_catalog = catalog is None
    catalog = catalog or Catalog()
    if owns_catalog:
        catalog.init_db()
    owns_vector_store = vector_store is None
    vector_store = vector_store or VectorStore()
    try:
        target_error = _validate_canonical_chunk_repair_target(vector_store)
        if target_error:
            return {
                "success": False,
                "updated": 0,
                "extra_vector_paths": [],
                "message": target_error,
                "vector_target": _vector_store_target_label(vector_store),
            }

        records = catalog.get_all_files()
        catalog_paths = {record["path"] for record in records}
        vector_counts = get_vector_file_chunk_counts(
            vector_store=vector_store,
            batch_size=scroll_batch_size,
            progress_callback=_repair_progress,
        )
        extra_vector_paths = sorted(set(vector_counts) - catalog_paths)
        if extra_vector_paths:
            return {
                "success": False,
                "updated": 0,
                "extra_vector_paths": extra_vector_paths,
                "message": "Refused chunk-count repair because Qdrant has file_ids missing from the catalog.",
                "vector_target": _vector_store_target_label(vector_store),
            }

        updates: list[tuple[str, int, int]] = []
        for record in records:
            path = record["path"]
            current = int(record.get("chunk_count") or 0)
            actual = int(vector_counts.get(path, 0))
            if current != actual:
                updates.append((path, current, actual))

        update_batch_size = max(int(update_batch_size), 1)
        total_update_batches = max(
            (len(updates) + update_batch_size - 1) // update_batch_size, 1
        )
        for batch_start in range(0, len(updates), update_batch_size):
            batch_number = (batch_start // update_batch_size) + 1
            _repair_progress(
                "repair_chunk_counts_update",
                batch=batch_number,
                total_batches=total_update_batches,
                rows_updated=batch_start,
            )
            for path, _current, actual in updates[
                batch_start : batch_start + update_batch_size
            ]:
                catalog.update_chunk_count(path, actual)
            catalog.conn.commit()

        return {
            "success": True,
            "updated": len(updates),
            "updates": updates[:50],
            "extra_vector_paths": [],
            "message": f"Synchronized {len(updates)} catalog chunk_count row(s) from Qdrant.",
            "vector_target": _vector_store_target_label(vector_store),
        }
    finally:
        if owns_vector_store:
            close = getattr(vector_store, "close", None)
            if callable(close):
                close()
        if owns_catalog:
            catalog.close()


def _classify_vector_target(vector_target: str | None) -> str:
    """Classify the vector target label used in verification output."""
    target = (vector_target or "").strip().lower()
    if target.startswith("shared:"):
        return "shared"
    if target.startswith("local:"):
        return "local"
    if target == "unavailable":
        return "unavailable"
    return "unknown"


def _get_vector_target_note(vector_target_kind: str, chunk_parity: bool | None) -> str:
    """Return an operator-facing note for non-canonical vector targets."""
    if vector_target_kind == "local":
        if chunk_parity is False:
            return (
                "Local embedded Qdrant is legacy/scratch for AI_STATION and may be stale; "
                "use the shared HTTP target before treating this chunk mismatch as corruption."
            )
        return "Local embedded Qdrant is legacy/scratch for AI_STATION; shared HTTP is the default target."
    if vector_target_kind == "shared":
        return "Shared HTTP Qdrant is the AI_STATION default FileMind target."
    if vector_target_kind == "unavailable":
        return (
            "Vector store is unavailable; verify is limited to catalog/disk completeness "
            "until qdrant-shared is healthy."
        )
    return ""


def _get_scan_lock_status() -> dict | None:
    """Return current scan lock status, including whether its PID is alive."""
    lock = read_scan_lock()
    if not lock:
        return None

    raw_pid = lock.get("pid")
    try:
        pid = int(raw_pid) if raw_pid is not None else None
    except (TypeError, ValueError):
        pid = None

    active = pid is not None and _process_exists(pid)
    return {
        "path": str(SCAN_LOCK_PATH),
        "pid": pid,
        "mode": lock.get("mode", "unknown"),
        "started_at": lock.get("started_at"),
        "command": lock.get("command", ""),
        "active": active,
    }


def _get_scan_activity(catalog: Catalog) -> dict:
    """Summarize live/stale scan state without relying on FileMind search."""
    lock_status = _get_scan_lock_status()
    lock_active = bool(lock_status and lock_status.get("active"))

    stale_scans: list[dict] = []
    running_scans: list[dict] = []

    reconcile = cast(Any, getattr(catalog, "reconcile_running_scans", None))
    if callable(reconcile):
        reconciled = reconcile(stale_legacy=not lock_active)
        stale_scans = reconciled if isinstance(reconciled, list) else []

    get_running_scans = cast(Any, getattr(catalog, "get_running_scans", None))
    if callable(get_running_scans):
        running = get_running_scans(reconcile=False)
        running_scans = running if isinstance(running, list) else []

    return {
        "scan_in_progress": bool(lock_active or running_scans),
        "scan_lock": lock_status,
        "running_scans": running_scans,
        "stale_scans": stale_scans,
    }


def build_verification_report(
    roots: list[str] | None = None,
    catalog: Catalog | None = None,
    scanner: FileScanner | None = None,
    vector_chunk_count=_UNSET,
    vector_chunk_error=_UNSET,
    vector_target=_UNSET,
) -> dict:
    """Build a completeness report against FileMind's effective live scan scope."""
    scanner = scanner or FileScanner()

    owns_catalog = catalog is None
    catalog = catalog or Catalog()
    if owns_catalog:
        catalog.init_db()

    try:
        scan_activity = _get_scan_activity(catalog)
        disk_paths, scanned_real_paths = collect_indexable_disk_paths(
            roots=roots, scanner=scanner
        )
        records = catalog.get_all_files()
        catalog_paths = {record["path"] for record in records}
        missing_paths = sorted(disk_paths - catalog_paths)
        indexed_in_scope = disk_paths & catalog_paths

        catalog_only_records = [
            record for record in records if record["path"] not in disk_paths
        ]
        catalog_only_breakdown: dict[str, int] = {}
        for record in catalog_only_records:
            reason = _classify_catalog_only_record(record, scanner, scanned_real_paths)
            catalog_only_breakdown[reason] = catalog_only_breakdown.get(reason, 0) + 1

        files_with_content = sum(
            1 for record in records if (record.get("content_summary") or "").strip()
        )
        files_with_embeddings = sum(
            1 for record in records if int(record.get("chunk_count") or 0) > 0
        )
        catalog_chunk_count = sum(
            int(record.get("chunk_count") or 0) for record in records
        )

        if (
            vector_chunk_count is _UNSET
            or vector_chunk_error is _UNSET
            or vector_target is _UNSET
        ):
            live_vector_chunk_count, live_vector_chunk_error, live_vector_target = (
                get_vector_store_status()
            )
            if vector_chunk_count is _UNSET:
                vector_chunk_count = live_vector_chunk_count
            if vector_chunk_error is _UNSET:
                vector_chunk_error = live_vector_chunk_error
            if vector_target is _UNSET:
                vector_target = live_vector_target

        disk_count = len(disk_paths)
        catalog_count = len(records)
        indexed_in_scope_count = len(indexed_in_scope)
        missing_count = len(missing_paths)
        catalog_only_count = len(catalog_only_records)

        completeness_pct = (
            (indexed_in_scope_count / disk_count * 100.0) if disk_count else 100.0
        )
        embedding_coverage_pct = (
            (files_with_embeddings / catalog_count * 100.0) if catalog_count else 100.0
        )

        chunk_parity = None
        if vector_chunk_count is not None:
            chunk_parity = vector_chunk_count == catalog_chunk_count

        drift_detected = (
            missing_count > 0 or catalog_only_count > 0 or chunk_parity is False
        )
        vector_target_text = vector_target if isinstance(vector_target, str) else None
        vector_target_kind = _classify_vector_target(vector_target_text)
        vector_target_note = _get_vector_target_note(vector_target_kind, chunk_parity)
        local_vector_mismatch_only = (
            vector_target_kind == "local"
            and chunk_parity is False
            and missing_count == 0
            and catalog_only_count == 0
        )
        vector_unavailable = vector_target_kind == "unavailable" or (
            vector_chunk_count is None and bool(vector_chunk_error)
        )

        if scan_activity["scan_in_progress"]:
            status = "IN_PROGRESS"
            if drift_detected:
                status_message = (
                    "A FileMind scan is in progress; catalog/vector/BM25 state may be staged. "
                    "Rerun verify after the scan completes before treating mismatches as corruption."
                )
            else:
                status_message = (
                    "A FileMind scan is in progress; current snapshot is consistent, "
                    "but rerun verify after completion for a final result."
                )
        elif vector_unavailable and missing_count == 0 and catalog_only_count == 0:
            status = "WARN"
            status_message = (
                "Catalog matches the scan scope, but vector parity is degraded because "
                "the FileMind vector store is unavailable."
            )
        elif (
            missing_count == 0 and catalog_only_count == 0 and chunk_parity is not False
        ):
            status = "OK"
            status_message = "Catalog matches the current FileMind scan scope."
        elif local_vector_mismatch_only:
            status = "WARN"
            status_message = (
                "The catalog matches the scan scope, but the local legacy/scratch Qdrant "
                "target is out of sync. Use the shared HTTP target before treating this as index corruption."
            )
        elif completeness_pct >= 95.0 and chunk_parity is not False:
            status = "WARN"
            status_message = "Catalog is mostly current, but drift remains to review."
        else:
            status = "FAIL"
            status_message = (
                "Catalog drift detected; rebuild or cleanup review is needed."
            )

        return {
            "disk_file_count": disk_count,
            "catalog_file_count": catalog_count,
            "indexed_in_scope_count": indexed_in_scope_count,
            "missing_from_catalog_count": missing_count,
            "catalog_only_count": catalog_only_count,
            "catalog_only_breakdown": catalog_only_breakdown,
            "missing_paths": missing_paths,
            "catalog_only_paths": [record["path"] for record in catalog_only_records],
            "files_with_content": files_with_content,
            "files_with_embeddings": files_with_embeddings,
            "catalog_chunk_count": catalog_chunk_count,
            "vector_chunk_count": vector_chunk_count,
            "vector_chunk_error": vector_chunk_error,
            "vector_target": vector_target,
            "vector_target_kind": vector_target_kind,
            "vector_target_note": vector_target_note,
            "completeness_pct": completeness_pct,
            "embedding_coverage_pct": embedding_coverage_pct,
            "chunk_parity": chunk_parity,
            "scan_in_progress": scan_activity["scan_in_progress"],
            "scan_lock": scan_activity["scan_lock"],
            "running_scans": scan_activity["running_scans"],
            "running_scan_count": len(scan_activity["running_scans"]),
            "stale_scans": scan_activity["stale_scans"],
            "stale_scan_count": len(scan_activity["stale_scans"]),
            "status": status,
            "status_message": status_message,
        }
    finally:
        if owns_catalog:
            catalog.close()


def render_verification_report(report: dict) -> str:
    """Render an ASCII-only verification summary suitable for Windows consoles."""
    lines = [
        "=" * 60,
        "FileMind Completeness Verification",
        "=" * 60,
        "",
        f"Effective files on disk: {report['disk_file_count']:,}",
        f"Catalog entries:         {report['catalog_file_count']:,}",
        f"Indexed in scope:        {report['indexed_in_scope_count']:,}",
        f"Missing from catalog:    {report['missing_from_catalog_count']:,}",
        f"Catalog-only entries:    {report['catalog_only_count']:,}",
        "",
        f"Files with content:      {report['files_with_content']:,}",
        f"Files with embeddings:   {report['files_with_embeddings']:,}",
        f"Catalog chunk count:     {report['catalog_chunk_count']:,}",
        f"Vector target:           {report['vector_target']}",
    ]

    vector_target_note = report.get("vector_target_note")
    if vector_target_note:
        lines.append(f"Vector target note:      {vector_target_note}")

    if report["vector_chunk_count"] is None:
        lines.append("Vector chunk count:      unavailable")
    else:
        lines.append(f"Vector chunk count:      {report['vector_chunk_count']:,}")

    lines.extend(
        [
            "",
            f"Completeness:            {report['completeness_pct']:.1f}%",
            f"Embedding coverage:      {report['embedding_coverage_pct']:.1f}%",
        ]
    )

    if report["chunk_parity"] is True:
        lines.append("Chunk parity:            OK")
    elif report["chunk_parity"] is False:
        lines.append("Chunk parity:            MISMATCH")
    else:
        lines.append("Chunk parity:            UNKNOWN")

    scan_lock = report.get("scan_lock")
    if report.get("scan_in_progress"):
        lines.append("")
        lines.append("Scan state:              IN PROGRESS")
        if scan_lock:
            lock_state = "active" if scan_lock.get("active") else "stale"
            lines.append(
                f"Scan lock:               {lock_state} pid={scan_lock.get('pid')} mode={scan_lock.get('mode')}"
            )
        for scan in report.get("running_scans", [])[:3]:
            lines.append(
                f"Running scan_log row:    id={scan.get('id')} pid={scan.get('pid')} mode={scan.get('mode', 'unknown')}"
            )
    elif report.get("stale_scan_count", 0):
        lines.append("")
        lines.append(f"Stale scan rows cleaned: {report['stale_scan_count']}")

    if report["catalog_only_breakdown"]:
        lines.append("")
        lines.append("Catalog-only breakdown:")
        for reason, count in sorted(report["catalog_only_breakdown"].items()):
            lines.append(f"  {reason}: {count}")

    if report["missing_paths"]:
        lines.append("")
        lines.append("Sample missing paths:")
        for path in report["missing_paths"][:5]:
            lines.append(f"  {path}")

    if report["vector_chunk_error"]:
        lines.append("")
        lines.append(f"Vector count note: {report['vector_chunk_error']}")

    lines.extend(
        [
            "",
            f"Status: {report['status']}",
            report["status_message"],
            "=" * 60,
        ]
    )
    return "\n".join(lines)


def verify() -> dict:
    """Run the verification report and print it safely."""
    report = build_verification_report()
    _print_line(render_verification_report(report))
    return report
