# pyright: reportMissingTypeArgument=false, reportPrivateUsage=false, reportUnknownParameterType=false
"""
FileMind index pipeline orchestration.

Chains all phases: scan -> extract -> chunk -> embed -> classify -> store.
Resumable, with progress tracking, error handling, and health checks.
"""

import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, cast

try:
    from .config import config
    from .catalog import Catalog
    from .vector_store import VectorStore
    from .scanner import FileScanner, FileChange
    from .extractor import extract_content
    from .chunker import TextChunker
    from .embedder import get_embedder
    from .classifier import Classifier
    from .check_deps import validate_all
    from .scan_lock import heartbeat_scan_lock, raise_if_scan_cancel_requested
except ImportError:
    from config import config
    from catalog import Catalog
    from vector_store import VectorStore
    from scanner import FileScanner, FileChange
    from extractor import extract_content
    from chunker import TextChunker
    from embedder import get_embedder
    from classifier import Classifier
    from check_deps import validate_all
    from scan_lock import heartbeat_scan_lock, raise_if_scan_cancel_requested

# Validate dependencies at pipeline start — auto-disables missing features
_missing = validate_all(config)

logger = logging.getLogger(__name__)

PROGRESS_FILE = Path(config.progress_file)


@dataclass
class PipelineResult:
    """Result of a pipeline run."""

    success: bool = False
    files_scanned: int = 0
    files_new: int = 0
    files_modified: int = 0
    files_moved: int = 0
    files_deleted: int = 0
    files_pruned: int = 0
    files_excluded_retained: int = 0
    files_indexed: int = 0
    chunks_created: int = 0
    files_classified: int = 0
    errors: int = 0
    duration_seconds: float = 0.0
    error_messages: list[str] = field(default_factory=list)


class NightlyOrchestrator:
    """Orchestrates the full indexing pipeline."""

    def __init__(self):
        self.catalog = Catalog()
        self.catalog.init_db()
        self.vector_store = VectorStore()
        self.scanner = FileScanner()
        self.chunker = TextChunker(
            chunk_size=config.chunk_size,
            overlap=config.chunk_overlap,
        )
        self.errors: list[str] = []
        self._progress = self._load_progress()
        self._active_scan_id: int | None = None

    def _heartbeat(self, phase: str, **progress: int | float | str) -> None:
        """Refresh SQLite and lock-file heartbeats and honor cooperative cancels."""
        active_scan_id = getattr(self, "_active_scan_id", None)
        if active_scan_id is not None:
            self.catalog.heartbeat_scan(active_scan_id)
        heartbeat_scan_lock(phase=phase, progress=progress)
        raise_if_scan_cancel_requested()

    def _summarize_content(self, content: str) -> str:
        """Trim extracted content to the configured indexing budget."""
        return content[: config.max_content_length]

    def _ensure_force_reindex_target(self):
        """Prevent full rebuilds from silently writing to a local scratch Qdrant."""
        if getattr(self.vector_store, "connection_mode", "").lower() == "http":
            return
        raise RuntimeError(
            "Force reindex requires the shared Qdrant HTTP target. "
            "Current FileMind config is using local Qdrant. "
            "Unset FILEMIND_QDRANT_MODE or set FILEMIND_QDRANT_MODE=http before running --rebuild."
        )

    def _reset_force_reindex_target(self):
        """Start force reindex from a clean collection and zeroed chunk metadata."""
        self._ensure_force_reindex_target()
        logger.info("  Resetting FileMind vector collection before full rebuild...")
        self.vector_store.reset_collection()
        self.catalog.reset_all_chunk_counts()
        self.catalog.conn.commit()

    def _get_record_index_text(
        self, record: dict, *, refresh_from_source: bool = False
    ) -> str:
        """Return the best available text to chunk for a record."""
        if refresh_from_source:
            full_path = str(record.get("full_path") or "")
            if full_path and os.path.exists(full_path):
                extracted = extract_content(full_path, max_size=config.max_file_size)
                return self._summarize_content(extracted) if extracted else ""
            return ""
        return str(record.get("content_summary") or "")

    def _existing_chunk_indices(self, path: str) -> list[int]:
        """Return chunk indexes currently stored for a file."""
        indices: list[int] = []
        for chunk in self.vector_store.get_file_chunks(path):
            raw_index = chunk.get("chunk_index")
            if raw_index is None:
                continue
            try:
                indices.append(int(raw_index))
            except (TypeError, ValueError):
                continue
        return sorted(set(indices))

    def _delete_file_chunk_indices(self, path: str, chunk_indices: list[int]) -> int:
        """Delete specific vector chunks and raise if Qdrant does not accept the write."""
        if not chunk_indices:
            return 0

        delete_chunks = cast(
            Callable[[str, list[int]], int] | None,
            getattr(self.vector_store, "delete_file_chunks", None),
        )
        if callable(delete_chunks):
            deleted = int(delete_chunks(path, chunk_indices))
        else:
            # Legacy fallback for test doubles: delete all chunks only when a
            # specific chunk-delete API is unavailable.
            deleted = int(self.vector_store.delete_by_file(path))

        if deleted < len(set(chunk_indices)):
            raise RuntimeError(
                f"Vector delete for {path} removed {deleted}/{len(set(chunk_indices))} expected chunk(s)."
            )
        return deleted

    def _upsert_chunk_records(self, path: str, chunk_records: list[dict]) -> int:
        """Upsert vector chunks and raise if Qdrant does not accept every record."""
        if not chunk_records:
            return 0
        upserted = int(self.vector_store.upsert_chunks(chunk_records))
        if upserted != len(chunk_records):
            raise RuntimeError(
                f"Vector upsert for {path} wrote {upserted}/{len(chunk_records)} expected chunk(s)."
            )
        return upserted

    def _clear_file_chunks(self, path: str):
        """Remove stale vector chunks for a file that no longer yields text."""
        existing_indices = self._existing_chunk_indices(path)
        self._delete_file_chunk_indices(path, existing_indices)
        self.catalog.update_chunk_count(path, 0)
        self.catalog.conn.commit()

    def _path_is_within(self, path: Path, root: Path) -> bool:
        """Return whether ``path`` is inside ``root`` using filesystem casing rules."""
        path_abs = os.path.normcase(os.path.abspath(str(path)))
        root_abs = os.path.normcase(os.path.abspath(str(root)))
        return path_abs == root_abs or path_abs.startswith(root_abs + os.sep)

    def _candidate_paths_for_index_path(self, index_path: str) -> list[Path]:
        """Return likely absolute filesystem paths for a FileMind index key."""
        normalized = index_path.replace("\\", "/").lstrip("/")
        candidates: list[Path] = []

        for base_name in ("ai_station_root", "user_home"):
            base = getattr(self.scanner.cfg, base_name, None)
            if base:
                candidates.append(Path(base) / normalized)

        for root_dir in self.scanner.cfg.scan_roots:
            candidates.append(Path(root_dir) / normalized)

        deduped: list[Path] = []
        seen: set[str] = set()
        for candidate in candidates:
            key = os.path.normcase(os.path.abspath(str(candidate)))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(candidate)
        return deduped

    def _missing_change_for_index_path(self, index_path: str) -> FileChange | None:
        """Resolve a missing catalog key to a focused ``FileChange`` without a full walk."""
        normalized = index_path.replace("\\", "/").lstrip("/")

        for candidate in self._candidate_paths_for_index_path(normalized):
            if not candidate.is_file():
                continue

            try:
                stat = os.stat(candidate)
            except (OSError, PermissionError):
                continue

            in_scope, _reason = self.scanner._evaluate_existing_path_scope(
                str(candidate),
                size=stat.st_size,
            )
            if not in_scope:
                continue

            matched_scan_root: Path | None = None
            for root_dir in self.scanner.cfg.scan_roots:
                root = Path(root_dir)
                if not root.exists() or not self._path_is_within(candidate, root):
                    continue
                if self.scanner._make_index_path(str(candidate), root) == normalized:
                    matched_scan_root = root
                    break

            if matched_scan_root is None:
                continue

            return FileChange(
                path=normalized,
                full_path=os.path.abspath(str(candidate)).replace("\\", "/"),
                change_type="new",
                size=stat.st_size,
                mtime=stat.st_mtime,
                content_hash=self.scanner._compute_hash(str(candidate)),
                ext=candidate.suffix.lower(),
            )

        return None

    def repair_missing_index_entries(
        self,
        missing_paths: list[str],
        *,
        max_files: int = 25,
    ) -> PipelineResult:
        """Targeted repair for small verify drift sets missing from the catalog.

        This intentionally avoids ``scanner.scan()`` and ``scan --full``.  The
        caller supplies the missing index keys from ``verify``; each key is
        resolved back to an in-scope file, then passed through the normal
        extract/classify/embed phases for only those files.
        """
        result = PipelineResult()
        start_time = time.time()

        normalized_missing = sorted(
            {
                path.replace("\\", "/").lstrip("/")
                for path in missing_paths
                if path and path.strip()
            }
        )

        try:
            if max_files < 1:
                raise ValueError("max_files must be at least 1")

            if len(normalized_missing) > max_files:
                message = (
                    f"Targeted repair refused {len(normalized_missing)} missing files; "
                    f"limit is {max_files}. Run a scoped review or raise --repair-limit intentionally."
                )
                result.errors += 1
                result.error_messages.append(message)
                self.errors.append(message)
                logger.warning(message)
                return result

            existing_paths = {record["path"] for record in self.catalog.get_all_files()}
            changes: list[FileChange] = []
            unresolved: list[str] = []

            for path in normalized_missing:
                if path in existing_paths:
                    logger.info(
                        f"  Missing repair skipped already-cataloged path: {path}"
                    )
                    continue

                change = self._missing_change_for_index_path(path)
                if change is None:
                    unresolved.append(path)
                    continue
                changes.append(change)

            if unresolved:
                message = (
                    "Targeted repair could not resolve these missing paths in the current "
                    f"FileMind scan scope: {', '.join(unresolved[:5])}"
                )
                if len(unresolved) > 5:
                    message += f" ... and {len(unresolved) - 5} more"
                result.errors += len(unresolved)
                result.error_messages.append(message)
                self.errors.append(message)
                logger.warning(message)

            result.files_scanned = len(changes)
            result.files_new = len(changes)

            if changes:
                logger.info(
                    f"Targeted missing-file repair: indexing {len(changes)} files"
                )
                file_data = self._phase_extract(result, changes)
                classifications = self._phase_classify(result, file_data)
                self._phase_embed(result, file_data, classifications)
                self.vector_store.build_fts_index()
                self._rebuild_bm25_index()
                self.catalog.conn.commit()
            else:
                logger.info(
                    "Targeted missing-file repair: no resolvable files to index"
                )

            result.success = result.errors == 0

        except Exception as e:
            result.errors += 1
            result.error_messages.append(str(e))
            self.errors.append(str(e))
            logger.error(f"Targeted missing-file repair failed: {e}")

        finally:
            result.duration_seconds = time.time() - start_time

        return result

    def _load_progress(self) -> dict:
        """Load saved progress for resume."""
        if PROGRESS_FILE.exists():
            try:
                with open(PROGRESS_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_progress(self, data: dict):
        """Save progress for resume."""
        PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(PROGRESS_FILE, "w") as f:
            json.dump(data, f, indent=2)

    def _clear_progress(self):
        """Clear saved progress."""
        if PROGRESS_FILE.exists():
            PROGRESS_FILE.unlink()

    def _rebuild_bm25_index(self):
        """Rebuild BM25 from the full Qdrant corpus to keep lexical search complete."""
        try:
            from .bm25_index import BM25HybridIndex
        except ImportError:
            from bm25_index import BM25HybridIndex

        logger.info("Phase 6: Rebuilding BM25 index from full vector store...")
        bm25_chunks = self.vector_store.export_bm25_chunks()
        if not bm25_chunks:
            logger.warning("  No chunks available for BM25 rebuild; skipping.")
            return

        bm25 = BM25HybridIndex()
        bm25.add_chunks(bm25_chunks)
        bm25.save(str(config.bm25_index_path))
        logger.info(f"  BM25 rebuild complete ({len(bm25)} chunks)")

    def health_check(self) -> dict:
        """Run health checks on dependencies."""
        checks = {}

        # Check Ollama
        try:
            import requests

            r = requests.get(f"{config.ollama_api_url}/api/tags", timeout=5)
            checks["ollama"] = {"status": "ok", "code": r.status_code}
        except Exception as e:
            checks["ollama"] = {"status": "error", "error": str(e)}

        # Check catalog
        try:
            count = self.catalog.count()
            checks["catalog"] = {"status": "ok", "count": count}
        except Exception as e:
            checks["catalog"] = {"status": "error", "error": str(e)}

        # Check vector store
        try:
            count = self.vector_store.count()
            checks["vector_store"] = {"status": "ok", "count": count}
        except Exception as e:
            checks["vector_store"] = {"status": "error", "error": str(e)}

        # Check GPU
        try:
            import torch

            if torch.cuda.is_available():
                checks["gpu"] = {
                    "status": "ok",
                    "device": torch.cuda.get_device_name(0),
                    "vram_used_gb": torch.cuda.memory_allocated() / 1e9,
                    "vram_total_gb": torch.cuda.get_device_properties(0).total_memory
                    / 1e9,
                }
            else:
                checks["gpu"] = {"status": "not available (CPU only)"}
        except Exception as e:
            checks["gpu"] = {"status": "error", "error": str(e)}

        # Check embedder selection/device without forcing a full encode.
        try:
            try:
                from .embedder import get_embedder
            except ImportError:
                from embedder import get_embedder

            embedder = get_embedder()
            checks["embedding"] = {
                "status": "ok",
                "backend": getattr(
                    config, "embedding_backend", "sentence_transformers"
                ),
                "requested_device": getattr(
                    embedder,
                    "requested_device",
                    getattr(config, "embedding_device", "cuda"),
                ),
                "device": embedder.get_device_info(),
            }
        except Exception as e:
            checks["embedding"] = {"status": "error", "error": str(e)}

        return checks

    def run(self, force_reindex: bool = False) -> PipelineResult:
        """Run the full indexing pipeline.

        Args:
            force_reindex: If True, re-chunk and re-embed ALL cataloged files
                          regardless of mtime. Use when pipeline was interrupted
                          or chunk coverage is low.
        """
        result = PipelineResult()
        start_time = time.time()
        scan_id = self.catalog.start_scan(
            mode="rebuild" if force_reindex else "full",
            command=" ".join(sys.argv),
        )
        self._active_scan_id = scan_id

        logger.info("=" * 60)
        logger.info("FileMind Index Pipeline — Starting")
        logger.info("=" * 60)

        try:
            if force_reindex:
                self._ensure_force_reindex_target()
            self._heartbeat("start")

            # Phase 1: Scan
            logger.info("Phase 1: Scanning directories...")
            changes, deleted, prunable_excluded = self._phase_scan(result)
            self._heartbeat("scan", files_scanned=result.files_scanned)

            # Phase 2: Extract
            logger.info("Phase 2: Extracting content...")
            file_data = self._phase_extract(result, changes)
            self._heartbeat("extract", files_extracted=len(file_data))

            # Phase 3: Classify
            logger.info("Phase 3: Classifying files...")
            classifications = self._phase_classify(result, file_data)
            self._heartbeat("classify", files_classified=result.files_classified)

            # Phase 4: Chunk & Embed
            logger.info("Phase 4: Chunking and embedding...")
            self._phase_embed(
                result, file_data, classifications, force_reindex=force_reindex
            )
            self._heartbeat(
                "embed",
                files_indexed=result.files_indexed,
                chunks_created=result.chunks_created,
            )

            # Force reindex: rebuild all retained catalog files against shared Qdrant
            if force_reindex:
                logger.info(
                    "Phase 4b: Force reindex — rebuilding all retained catalog files..."
                )
                self._reset_force_reindex_target()
                self._phase_force_reindex(
                    result,
                    classifications,
                    skip_paths=set(deleted) | set(prunable_excluded),
                )
                self._heartbeat(
                    "force_reindex",
                    files_indexed=result.files_indexed,
                    chunks_created=result.chunks_created,
                )

            logger.info("Phase 4b: Rebuilding Qdrant indexes...")
            self.vector_store.build_fts_index()
            self._heartbeat("qdrant_indexes")

            # Phase 5: Cleanup
            logger.info("Phase 5: Cleaning up deleted files...")
            self._phase_cleanup(result, deleted, prunable_excluded)
            self._heartbeat(
                "cleanup",
                files_deleted=result.files_deleted,
                files_pruned=result.files_pruned,
            )

            # Phase 6: Rebuild lexical index from the complete corpus
            self._rebuild_bm25_index()
            self._heartbeat("bm25_rebuild")
            self._reconcile_catalog_chunk_counts()
            self._heartbeat("chunk_count_reconcile")

            # Safety cap: warn if mass deletion detected
            cleanup_total = result.files_deleted + result.files_pruned
            if cleanup_total > 100:
                logger.warning(
                    f"SAFETY CAP: {cleanup_total} files marked for index removal. "
                    f"Review log before trusting this result."
                )

            # Save
            self.catalog.conn.commit()
            self._clear_progress()
            result.success = True

        except Exception as e:
            self.errors.append(str(e))
            result.errors += 1
            logger.error(f"Pipeline failed: {e}")
            self._save_progress(self._progress)

        finally:
            result.duration_seconds = time.time() - start_time

            # Log scan completion
            self.catalog.complete_scan(
                scan_id,
                files_scanned=result.files_scanned,
                files_changed=result.files_new
                + result.files_modified
                + result.files_moved,
                files_new=result.files_new,
                files_deleted=result.files_deleted + result.files_pruned,
                errors=result.errors,
                status="completed" if result.success else "failed",
            )

            # Summary
            logger.info("=" * 60)
            logger.info(f"Pipeline {'SUCCESS' if result.success else 'FAILED'}")
            logger.info(f"  Scanned: {result.files_scanned}")
            logger.info(f"  New: {result.files_new}")
            logger.info(f"  Modified: {result.files_modified}")
            logger.info(f"  Moved: {result.files_moved}")
            logger.info(f"  Deleted: {result.files_deleted}")
            logger.info(f"  Pruned Excluded: {result.files_pruned}")
            logger.info(f"  Excluded Retained: {result.files_excluded_retained}")
            logger.info(f"  Indexed: {result.files_indexed}")
            logger.info(f"  Chunks: {result.chunks_created}")
            logger.info(f"  Classified: {result.files_classified}")
            logger.info(f"  Errors: {result.errors}")
            logger.info(f"  Duration: {result.duration_seconds:.1f}s")
            logger.info("=" * 60)

            self.catalog.close()
            self.vector_store.close()
            self._active_scan_id = None

        return result

    def _reconcile_catalog_chunk_counts(self):
        """Synchronize catalog chunk_count metadata from the vector store after success."""
        try:
            try:
                from .verify import repair_catalog_chunk_counts_from_vectors
            except ImportError:
                from verify import repair_catalog_chunk_counts_from_vectors
            repaired = repair_catalog_chunk_counts_from_vectors(
                catalog=self.catalog,
                vector_store=self.vector_store,
            )
            if repaired.get("success"):
                logger.info("  Chunk-count reconciliation: %s", repaired.get("message"))
            else:
                logger.warning(
                    "  Chunk-count reconciliation skipped: %s", repaired.get("message")
                )
        except Exception as exc:
            logger.warning("  Chunk-count reconciliation failed: %s", exc)

    def _phase_scan(self, result: PipelineResult):
        """Phase 1: Scan directories for changes."""
        changes, deleted = self.scanner.scan()
        summary = self.scanner.get_changes_summary(changes, deleted)
        prunable_excluded = self.scanner.prunable_excluded_paths
        retained_excluded = self.scanner.retained_excluded_paths

        result.files_new = summary["new"]
        result.files_modified = summary["modified"]
        result.files_moved = summary.get("moved", 0)
        result.files_deleted = summary["deleted"]
        result.files_excluded_retained = len(retained_excluded)
        result.files_scanned = summary["total_changes"]

        logger.info(f"  Changes: {summary}")
        if prunable_excluded:
            logger.info(
                f"  Excluded entries eligible for pruning: {len(prunable_excluded)}"
            )
        if retained_excluded:
            logger.info(
                f"  Excluded entries retained for manual review: {len(retained_excluded)}"
            )
        return changes, deleted, prunable_excluded

    def prune_excluded(self) -> PipelineResult:
        """Maintenance run: prune intentionally excluded entries from the live index."""
        result = PipelineResult()
        start_time = time.time()
        scan_id = self.catalog.start_scan(
            mode="prune_excluded",
            command=" ".join(sys.argv),
        )

        logger.info("=" * 60)
        logger.info("FileMind Index Hygiene — Pruning Excluded Entries")
        logger.info("=" * 60)

        try:
            _, deleted, prunable_excluded = self._phase_scan(result)
            self.catalog.heartbeat_scan(scan_id)

            logger.info("Phase 2: Cleaning up deleted and excluded entries...")
            self._phase_cleanup(result, deleted, prunable_excluded)
            self.catalog.heartbeat_scan(scan_id)

            logger.info("Phase 3: Rebuilding BM25 index from remaining corpus...")
            self._rebuild_bm25_index()
            self.catalog.heartbeat_scan(scan_id)

            self.catalog.conn.commit()
            result.success = True

        except Exception as e:
            self.errors.append(str(e))
            result.errors += 1
            logger.error(f"Excluded-entry prune failed: {e}")

        finally:
            result.duration_seconds = time.time() - start_time
            self.catalog.complete_scan(
                scan_id,
                files_scanned=result.files_scanned,
                files_changed=result.files_deleted + result.files_pruned,
                files_new=0,
                files_deleted=result.files_deleted + result.files_pruned,
                errors=result.errors,
                status="completed" if result.success else "failed",
            )
            logger.info("=" * 60)
            logger.info(f"Index Hygiene {'SUCCESS' if result.success else 'FAILED'}")
            logger.info(f"  Deleted: {result.files_deleted}")
            logger.info(f"  Pruned Excluded: {result.files_pruned}")
            logger.info(f"  Excluded Retained: {result.files_excluded_retained}")
            logger.info(f"  Duration: {result.duration_seconds:.1f}s")
            logger.info("=" * 60)
            self.catalog.close()
            self.vector_store.close()

        return result

    def _phase_extract(
        self, result: PipelineResult, changes: list[FileChange]
    ) -> list[dict]:
        """Phase 2: Extract content from changed files."""
        file_data = []
        moved_without_reindex = 0
        for index, change in enumerate(changes, start=1):
            if index == 1 or index % 25 == 0:
                self._heartbeat("extract", files_seen=index, total_files=len(changes))
            if change.change_type == "deleted":
                continue
            if change.change_type == "moved":
                try:
                    self._process_move(change)
                    moved_without_reindex += 1
                except Exception as e:
                    self.errors.append(
                        f"Move reconciliation error: {change.path} — {e}"
                    )
                    result.errors += 1
                continue

            try:
                content = extract_content(
                    change.full_path,
                    max_size=config.max_file_size,
                )
                summary = self._summarize_content(content)

                file_data.append(
                    {
                        "path": change.path,
                        "full_path": change.full_path,
                        "size": change.size,
                        "mtime": change.mtime,
                        "content_hash": change.content_hash,
                        "ext": change.ext,
                        "content_summary": summary,
                        "change_type": change.change_type,
                    }
                )

                # Update catalog
                self.catalog.upsert_file(
                    path=change.path,
                    full_path=change.full_path,
                    size=change.size,
                    mtime=change.mtime,
                    content_hash=change.content_hash,
                    ext=change.ext,
                    content_summary=summary,
                )
            except Exception as e:
                self.errors.append(f"Extract error: {change.path} — {e}")
                result.errors += 1

        logger.info(f"  Extracted: {len(file_data)} files")
        if moved_without_reindex:
            logger.info(
                f"  Re-keyed moved files without re-embedding: {moved_without_reindex}"
            )
        self.catalog.conn.commit()  # Commit all upserts so DB sees the files
        return file_data

    def _process_move(self, change: FileChange):
        """Re-key a moved file in the catalog and vector store without re-embedding."""
        if not change.previous_path:
            raise ValueError("Missing previous_path for move event")

        previous = self.catalog.get_file(change.previous_path)
        if previous is None:
            raise ValueError(
                f"Original catalog record not found: {change.previous_path}"
            )

        moved_chunks = self.vector_store.move_file(
            old_file_id=change.previous_path,
            new_file_id=change.path,
            new_mtime=change.mtime,
            new_file_type=change.ext,
        )
        if moved_chunks < 0:
            raise RuntimeError("Vector store move failed")
        if moved_chunks == 0 and int(previous.get("chunk_count") or 0) > 0:
            logger.warning(
                f"Move detected for {change.path}, but no stored chunks were found to re-key"
            )

        moved = self.catalog.move_file(
            old_path=change.previous_path,
            new_path=change.path,
            new_full_path=change.full_path,
            size=change.size,
            mtime=change.mtime,
            content_hash=change.content_hash,
            ext=change.ext,
        )
        if not moved:
            raise RuntimeError(
                f"Catalog move failed for {change.previous_path} -> {change.path}"
            )

    def _phase_classify(
        self, result: PipelineResult, file_data: list[dict]
    ) -> dict[str, dict]:
        """Phase 3: Classify files using local LLM (gemma4-e4b-json)."""
        if not file_data:
            return {}

        classifier = Classifier()
        classifications = classifier.classify(file_data)

        class_map = {}
        for cls in classifications:
            path = cls["path"]
            class_map[path] = cls
            self.catalog.update_category(path, cls["category"], cls["confidence"])

        classified_count = sum(1 for c in classifications if c["category"] != "unknown")
        result.files_classified = classified_count
        logger.info(f"  Classified: {classified_count}/{len(file_data)} files via LLM")
        self.catalog.conn.commit()
        return class_map

    def _phase_embed(
        self,
        result: PipelineResult,
        file_data: list[dict],
        classifications: dict[str, dict],
        force_reindex: bool = False,
    ):
        """Phase 4: Chunk and embed files."""
        if force_reindex:
            logger.info(
                "  Force reindex requested; deferring embedding to the full catalog rebuild phase."
            )
            return

        try:
            from .bm25_index import BM25HybridIndex
        except ImportError:
            from bm25_index import BM25HybridIndex

        embedder = get_embedder()

        # BM25 index builder
        bm25 = BM25HybridIndex()
        bm25_chunks = []

        # Prepare per-file chunk jobs, then embed changed chunks in cross-file batches.
        all_chunk_jobs = []
        for fd in file_data:
            if fd.get("change_type") == "deleted":
                continue
            path = fd["path"]
            content = fd.get("content_summary", "")
            if not content or not content.strip():
                try:
                    self._clear_file_chunks(path)
                except Exception as e:
                    self.errors.append(f"Clear chunks error: {path} — {e}")
                    result.errors += 1
                continue
            cls_info = classifications.get(path, {})
            category = cls_info.get("category", "unknown")
            all_chunk_jobs.append((fd, content, category, cls_info))

        total_chunks = 0
        files_indexed = 0

        def _build_chunk_records(
            job: dict, dense_vecs: list, sparse_vecs: list
        ) -> list[dict]:
            chunk_records = []
            for i, chunk in enumerate(job["chunks_to_embed"]):
                chunk_id = f"{job['path']}::chunk_{chunk.chunk_index}"
                chunk_records.append(
                    {
                        "id": chunk_id,
                        "file_id": job["path"],
                        "chunk_index": chunk.chunk_index,
                        "chunk_hash": chunk.chunk_hash,
                        "content": chunk.content,
                        "vector": dense_vecs[i] if i < len(dense_vecs) else [],
                        "sparse_vector": sparse_vecs[i] if i < len(sparse_vecs) else {},
                        "file_type": job["fd"].get("ext", ""),
                        "category": job["category"],
                        "mtime": job["fd"].get("mtime", 0),
                    }
                )

                bm25_chunks.append(
                    {
                        "id": chunk_id,
                        "text": chunk.content,
                        "file_ext": job["file_ext"],
                    }
                )
            return chunk_records

        # Embed in sequential batches to avoid VRAM OOM.
        BATCH_FILES = 8  # Group 8 files, then encode all changed chunks in one call.
        total_batches = max((len(all_chunk_jobs) + BATCH_FILES - 1) // BATCH_FILES, 1)
        for batch_number, batch_start in enumerate(
            range(0, len(all_chunk_jobs), BATCH_FILES), start=1
        ):
            self._heartbeat("embed", batch=batch_number, total_batches=total_batches)
            batch = all_chunk_jobs[batch_start : batch_start + BATCH_FILES]
            prepared_jobs = []
            batch_texts = []

            for fd, content, category, cls_info in batch:
                path = fd["path"]
                file_ext = fd.get("ext", "")
                try:
                    chunks = self.chunker.chunk(content, path)
                    if not chunks:
                        self._clear_file_chunks(path)
                        continue

                    existing_chunks = self.vector_store.get_file_chunks(path)
                    existing_hashes = {
                        c.get("chunk_index"): c.get("chunk_hash")
                        for c in existing_chunks
                    }
                    existing_indices = set()
                    for existing_chunk in existing_chunks:
                        raw_index = existing_chunk.get("chunk_index")
                        if raw_index is None:
                            continue
                        try:
                            existing_indices.add(int(raw_index))
                        except (TypeError, ValueError):
                            continue
                    current_indices = {int(c.chunk_index) for c in chunks}
                    stale_chunk_indices = sorted(existing_indices - current_indices)
                    chunks_to_embed = [
                        c
                        for c in chunks
                        if existing_hashes.get(c.chunk_index) != c.chunk_hash
                    ]

                    if not chunks_to_embed and not stale_chunk_indices:
                        continue

                    text_start = len(batch_texts)
                    batch_texts.extend([c.content for c in chunks_to_embed])
                    prepared_jobs.append(
                        {
                            "fd": fd,
                            "path": path,
                            "file_ext": file_ext,
                            "category": category,
                            "confidence": cls_info.get("confidence", 0.0),
                            "chunks": chunks,
                            "chunks_to_embed": chunks_to_embed,
                            "stale_chunk_indices": stale_chunk_indices,
                            "text_start": text_start,
                            "text_count": len(chunks_to_embed),
                            "chunk_records": [],
                        }
                    )
                except Exception as e:
                    self.errors.append(f"Embed error: {path} — {e}")
                    result.errors += 1

            if not prepared_jobs:
                continue

            if batch_texts:
                logger.info(
                    "  Embedding batch %s/%s: %s files, %s chunks",
                    batch_number,
                    total_batches,
                    len(prepared_jobs),
                    len(batch_texts),
                )

            batch_chunk_records = []
            if batch_texts:
                try:
                    encoded = embedder.encode(
                        batch_texts,
                        return_dense=True,
                        return_sparse=True,
                    )
                    dense_vecs = encoded.get("dense_vecs", [])
                    sparse_vecs = encoded.get(
                        "lexical_weights", [{}] * len(batch_texts)
                    )

                    for job in prepared_jobs:
                        if not job["chunks_to_embed"]:
                            continue
                        start = job["text_start"]
                        end = start + job["text_count"]
                        job_records = _build_chunk_records(
                            job, dense_vecs[start:end], sparse_vecs[start:end]
                        )
                        job["chunk_records"] = job_records
                        batch_chunk_records.extend(job_records)
                except Exception as e:
                    logger.warning(
                        "  Batch %s encode failed (%s); falling back to per-file encoding.",
                        batch_number,
                        e,
                    )
                    for job in prepared_jobs:
                        if not job["chunks_to_embed"]:
                            continue
                        try:
                            encoded = embedder.encode(
                                [chunk.content for chunk in job["chunks_to_embed"]],
                                return_dense=True,
                                return_sparse=True,
                            )
                            dense_vecs = encoded.get("dense_vecs", [])
                            sparse_vecs = encoded.get(
                                "lexical_weights", [{}] * job["text_count"]
                            )
                            job_records = _build_chunk_records(
                                job, dense_vecs, sparse_vecs
                            )
                            job["chunk_records"] = job_records
                            batch_chunk_records.extend(job_records)
                        except Exception as file_exc:
                            self.errors.append(
                                f"Embed error: {job['path']} — {file_exc}"
                            )
                            result.errors += 1

            vector_write_failed = False
            if batch_chunk_records:
                try:
                    self._upsert_chunk_records("batch", batch_chunk_records)
                except Exception as e:
                    vector_write_failed = True
                    self.errors.append(f"Vector upsert error: {e}")
                    result.errors += 1

            batch_chunks_indexed = 0
            batch_files_indexed = 0
            for job in prepared_jobs:
                if vector_write_failed and job.get("chunk_records"):
                    continue
                try:
                    if job["stale_chunk_indices"]:
                        self._delete_file_chunk_indices(
                            job["path"], job["stale_chunk_indices"]
                        )
                except Exception as e:
                    self.errors.append(f"Vector delete error: {job['path']} — {e}")
                    result.errors += 1
                    continue

                self.catalog.update_chunk_count(job["path"], len(job["chunks"]))
                if job["category"] != "unknown":
                    self.catalog.update_category(
                        job["path"], job["category"], job["confidence"]
                    )
                if job.get("chunk_records") or job["stale_chunk_indices"]:
                    total_chunks += job["text_count"]
                    batch_chunks_indexed += job["text_count"]
                    batch_files_indexed += 1
                    files_indexed += 1
            self.catalog.conn.commit()

            logger.info(
                "    Batch %s complete: %s files indexed, %s chunks updated",
                batch_number,
                batch_files_indexed,
                batch_chunks_indexed,
            )

            # Clear GPU cache between batches
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        result.files_indexed = files_indexed
        result.chunks_created = total_chunks
        logger.info(
            f"  Indexed: {files_indexed} files, {total_chunks} chunks updated via batch-embedding"
        )

        # Build BM25 index from accumulated chunks
        if bm25_chunks:
            logger.info(f"  Building BM25 index from {len(bm25_chunks)} chunks...")
            bm25.add_chunks(bm25_chunks)
            bm25.save(str(config.bm25_index_path))
            logger.info(f"  BM25 index saved ({len(bm25)} chunks)")

    def _phase_force_reindex(
        self,
        result: PipelineResult,
        classifications: dict[str, dict],
        skip_paths: Optional[set[str]] = None,
    ):
        """Embed ALL cataloged files regardless of mtime.

        This is used when chunk coverage is low due to interrupted scans
        OR when chunking strategy changes (e.g., enabling smart chunking).
        It deletes existing chunks for each file and re-chunks from scratch.

        OPTIMIZED (2026-04-13): Uses embedder's effective batch size (FP16-aware),
        skips redundant "check existing chunks" step since we delete everything anyway.
        """
        try:
            from .bm25_index import BM25HybridIndex
        except ImportError:
            from bm25_index import BM25HybridIndex

        embedder = get_embedder()
        import torch

        # BM25 index builder for force reindex
        bm25 = BM25HybridIndex()
        bm25_chunks = []

        # Use embedder's calibrated batch size when available, otherwise fall
        # back to the configured batch size.
        batch_files = max(
            int(
                getattr(embedder, "_effective_batch_size", config.embedding_batch_size)
                or 0
            ),
            1,
        )
        skip_paths = set(skip_paths or set())
        logger.info(f"  Force reindex batch size: {batch_files} files (FP16 optimized)")

        total_to_process = 0
        total_indexed = 0
        total_chunks = 0
        total_errors = 0
        total_rechunked = 0

        files = [
            record
            for record in self.catalog.get_all_files()
            if record.get("path") not in skip_paths
        ]
        logger.info(
            f"  Force reindex candidates: {len(files)} files "
            f"({len(skip_paths)} skipped because they are deleted or out of scope)"
        )

        total_batches = max((len(files) + batch_files - 1) // batch_files, 1)
        for batch_start in range(0, len(files), batch_files):
            batch_number = (batch_start // batch_files) + 1
            self._heartbeat(
                "force_reindex",
                batch=batch_number,
                total_batches=total_batches,
                files_processed=total_to_process,
            )
            batch = files[batch_start : batch_start + batch_files]

            for record in batch:
                path = str(record.get("path") or "")
                if not path:
                    continue

                total_to_process += 1
                try:
                    content = self._get_record_index_text(
                        record, refresh_from_source=True
                    )
                    self.catalog.update_content_summary(path, content)

                    if not content or not content.strip():
                        self._clear_file_chunks(path)
                        continue

                    chunks = self.chunker.chunk(content, path)
                    if not chunks:
                        self._clear_file_chunks(path)
                        continue

                    existing_indices = self._existing_chunk_indices(path)
                    removed_chunks = self._delete_file_chunk_indices(
                        path, existing_indices
                    )
                    if removed_chunks > 0:
                        total_rechunked += 1

                    texts = [chunk.content for chunk in chunks]
                    encoded = embedder.encode(
                        texts,
                        return_dense=True,
                        return_sparse=True,
                    )

                    dense_vecs = encoded.get("dense_vecs", [])
                    sparse_vecs = encoded.get("lexical_weights", [{}] * len(chunks))

                    cls_info = classifications.get(path, {})
                    category = (
                        cls_info.get("category") or record.get("category") or "unknown"
                    )
                    confidence = cls_info.get(
                        "confidence", record.get("confidence") or 0.0
                    )
                    file_ext = record.get("ext", "")

                    chunk_records = []
                    for i, chunk in enumerate(chunks):
                        chunk_id = f"{path}::chunk_{chunk.chunk_index}"
                        chunk_records.append(
                            {
                                "id": chunk_id,
                                "file_id": path,
                                "chunk_index": chunk.chunk_index,
                                "chunk_hash": chunk.chunk_hash,
                                "content": chunk.content,
                                "vector": dense_vecs[i] if i < len(dense_vecs) else [],
                                "sparse_vector": sparse_vecs[i]
                                if i < len(sparse_vecs)
                                else {},
                                "file_type": file_ext,
                                "category": category,
                                "mtime": record.get("mtime", 0),
                            }
                        )

                        # BM25 chunk
                        bm25_chunks.append(
                            {
                                "id": chunk_id,
                                "text": chunk.content,
                                "file_ext": file_ext,
                            }
                        )

                    self._upsert_chunk_records(path, chunk_records)
                    self.catalog.update_chunk_count(path, len(chunks))
                    if category != "unknown":
                        self.catalog.update_category(path, category, confidence)
                    self.catalog.conn.commit()

                    total_indexed += 1
                    total_chunks += len(chunk_records)

                except Exception as e:
                    self.errors.append(f"Force reindex error: {path} — {e}")
                    result.errors += 1
                    total_errors += 1

            # Clear GPU cache between batches
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        # Build BM25 index from force reindex chunks
        if bm25_chunks:
            logger.info(
                f"  Building BM25 index from {len(bm25_chunks)} force reindex chunks..."
            )
            bm25.add_chunks(bm25_chunks)
            bm25.save(str(config.bm25_index_path))
            logger.info(f"  BM25 index saved ({len(bm25)} chunks)")

        result.files_indexed += total_indexed
        result.chunks_created += total_chunks
        logger.info(
            f"  Force reindex complete: {total_to_process} files processed, "
            f"{total_indexed} indexed, "
            f"{total_rechunked} re-chunked (strategy change), "
            f"{total_chunks} new chunks, {total_errors} errors"
        )

    def _cleanup_paths(
        self, result: PipelineResult, paths: set[str], *, label: str
    ) -> int:
        """Remove a set of indexed paths from the catalog and vector store."""
        if not paths:
            logger.info(f"  No {label} files to clean up.")
            return 0

        logger.info(f"  Cleaning up {len(paths)} {label} files from index...")
        removed = 0
        for path in sorted(paths):
            try:
                self.catalog.delete_file(path)
                self.vector_store.delete_by_file(path)
                removed += 1
            except Exception as e:
                self.errors.append(f"Cleanup error: {path} — {e}")
                result.errors += 1

        logger.info(f"  Removed {removed} {label} files from index.")
        return removed

    def _phase_cleanup(
        self, result: PipelineResult, deleted: set[str], prunable_excluded: set[str]
    ):
        """Phase 5: Remove genuinely deleted files and newly out-of-scope excluded files."""
        deleted = set(deleted)
        prunable_excluded = set(prunable_excluded) - deleted
        removed_deleted = self._cleanup_paths(result, deleted, label="deleted")
        removed_excluded = self._cleanup_paths(
            result, prunable_excluded, label="excluded"
        )
        result.files_deleted = removed_deleted
        result.files_pruned = removed_excluded


def run_nightly(force_reindex: bool = False):
    """Compatibility wrapper for the FileMind indexing pipeline."""
    orchestrator = NightlyOrchestrator()
    return orchestrator.run(force_reindex=force_reindex)


FileMindOrchestrator = NightlyOrchestrator


def run_index_pipeline(force_reindex: bool = False):
    """Preferred name for invoking the FileMind indexing pipeline."""
    return run_nightly(force_reindex=force_reindex)
