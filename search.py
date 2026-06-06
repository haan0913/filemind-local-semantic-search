"""
Search Engine — Hybrid search with RRF fusion.

Combines FTS5 keyword search, BM25 lexical search, and dense vector
semantic search using Reciprocal Rank Fusion (RRF) for ranked results.
Cross-encoder reranking reorders top results for maximum relevance.
"""

import logging
import math
import re
import hashlib
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Optional, cast

try:
    from .config import config
    from .catalog import Catalog
    from .vector_store import VectorStore
    from .bm25_index import BM25HybridIndex
    from .protected_secrets import (
        contains_secret_value,
        is_secret_like_path,
        normal_search_snippet,
    )
except ImportError:
    from config import config
    from catalog import Catalog
    from vector_store import VectorStore
    from bm25_index import BM25HybridIndex
    from protected_secrets import (
        contains_secret_value,
        is_secret_like_path,
        normal_search_snippet,
    )

logger = logging.getLogger(__name__)

RRF_K = 60  # RRF constant (standard value)
FRESHNESS_FRESH = "fresh"
FRESHNESS_CHANGED = "changed"
FRESHNESS_DELETED = "deleted"
FRESHNESS_MISSING_CATALOG = "missing_catalog"
FRESHNESS_MISSING_CHUNK = "missing_chunk"
FRESHNESS_STALE = "stale"
FRESHNESS_MTIME_TOLERANCE_SECONDS = 0.001
SEARCH_STATUS_OK = "ok"
SEARCH_STATUS_EMPTY = "empty"
SEARCH_STATUS_DEGRADED = "degraded"
SEARCH_AUTHORITY_CURRENT = "current_source_truth"
SEARCH_AUTHORITY_EMPTY = "no_results_not_source_truth"
SEARCH_AUTHORITY_DEGRADED = "degraded_filemind_output_not_source_truth"
DEGRADED_VECTOR_UNAVAILABLE = "vector_unavailable"
DEGRADED_CATALOG_UNAVAILABLE = "catalog_unavailable"
DEGRADED_UNFRESH_FILTERED = "unfresh_results_filtered"
DEGRADED_UNFRESH_INCLUDED = "unfresh_results_included"
DEGRADED_PROTECTED_PATH = "protected_or_excluded_path"
DEGRADED_UNINDEXED_LIVE_FILE = "unindexed_live_file"
FILE_LOOKUP_RE = re.compile(
    r"(?i)(?:[A-Za-z]:[\\/])?(?:[\w.@+#%~-]+[\\/])*[\w.@+#%~-]+\.[a-z0-9]{1,10}"
)
QUOTED_FILE_LOOKUP_RE = re.compile(
    r"(?i)(?:"
    r'"(?P<double>[^"\r\n]+\.[a-z0-9]{1,10})"'
    r"|"
    r"'(?P<single>[^'\r\n]+\.[a-z0-9]{1,10})'"
    r"|"
    r"`(?P<backtick>[^`\r\n]+\.[a-z0-9]{1,10})`"
    r")"
)
COMMON_EXACT_FILENAMES = {
    "agents.md",
    "license",
    "license.md",
    "package.json",
    "pyproject.toml",
    "readme.md",
    "requirements.txt",
}


def _resolve_top_k(top_k: Optional[int]) -> int:
    """Resolve caller-provided top_k against configured search defaults."""
    return config.search.default_top_k if top_k is None else top_k


def _normalize_lookup_path(value: str) -> str:
    """Normalize a user/file path token for catalog comparisons."""
    return value.replace("\\", "/").strip().strip("\"'`;,()[]{}<>").lstrip("./").lower()


def _extract_file_lookup_tokens(query: str) -> list[str]:
    """Extract filename/path tokens that should be looked up exactly.

    Vector search is intentionally fuzzy; when a user names a concrete file
    such as ``CURRENT_CONTEXT_STATUS.md`` or ``hub/docs/HANDOFF.md`` we should
    search the catalog by path/name as well.  This also surfaces cataloged
    files whose chunk_count is currently zero, which is a known recovery state
    after interrupted scans.
    """

    tokens: list[str] = []
    seen: set[str] = set()

    def add_token(raw_token: str) -> None:
        token = _normalize_lookup_path(raw_token)
        if not token:
            return
        suffix = PurePosixPath(token).suffix.lower()
        if suffix not in config.index_extensions:
            return
        if token not in seen:
            seen.add(token)
            tokens.append(token)

    for match in QUOTED_FILE_LOOKUP_RE.finditer(query):
        add_token(next(group for group in match.groups() if group))

    for match in FILE_LOOKUP_RE.finditer(query):
        add_token(match.group(0))
    return tokens


def _is_precise_file_lookup(tokens: list[str]) -> bool:
    """Return true when exact catalog lookup can safely avoid fuzzy retrieval."""
    if not tokens:
        return False
    return any(
        "/" in token or PurePosixPath(token).name not in COMMON_EXACT_FILENAMES
        for token in tokens
    )


@dataclass
class SearchResult:
    """Single search result."""

    file_path: str
    chunk_index: int = -1
    score: float = 0.0
    keyword_rank: int = 0
    semantic_rank: int = 0
    snippet: str = ""
    category: str = ""
    file_type: str = ""
    mtime: float = 0.0
    is_protected: bool = False
    freshness_status: str = FRESHNESS_MISSING_CATALOG
    freshness_evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchReport:
    """Structured degraded-mode metadata for CLI/API-facing search callers."""

    query: str = ""
    top_k: int = 0
    status: str = SEARCH_STATUS_OK
    authority: str = SEARCH_AUTHORITY_CURRENT
    returned_count: int = 0
    candidate_count: int = 0
    partial: bool = False
    miss_state: str = "none"
    degraded_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    backend_status: dict[str, str] = field(default_factory=dict)
    backend_errors: dict[str, str] = field(default_factory=dict)
    freshness_counts: dict[str, int] = field(default_factory=dict)
    filtered_freshness_counts: dict[str, int] = field(default_factory=dict)
    unindexed_live_file_paths: list[str] = field(default_factory=list)
    protected_count: int = 0
    _freshness_seen_keys: set[str] = field(default_factory=set, repr=False)

    def mark_degraded(self, reason: str, warning: str) -> None:
        """Record one degraded condition without duplicating report noise."""

        if reason not in self.degraded_reasons:
            self.degraded_reasons.append(reason)
        if warning and warning not in self.warnings:
            self.warnings.append(warning)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable report for CLI/API output surfaces."""

        return {
            "query": self.query,
            "top_k": self.top_k,
            "status": self.status,
            "authority": self.authority,
            "returned_count": self.returned_count,
            "candidate_count": self.candidate_count,
            "partial": self.partial,
            "miss_state": self.miss_state,
            "degraded_reasons": list(self.degraded_reasons),
            "warnings": list(self.warnings),
            "backend_status": dict(self.backend_status),
            "backend_errors": dict(self.backend_errors),
            "freshness_counts": dict(self.freshness_counts),
            "filtered_freshness_counts": dict(self.filtered_freshness_counts),
            "unindexed_live_file_paths": list(self.unindexed_live_file_paths),
            "protected_count": self.protected_count,
        }


class SearchEngine:
    """Hybrid search with RRF fusion."""

    def __init__(
        self,
        catalog: Optional[Catalog] = None,
        vector_store: Optional[VectorStore] = None,
        bm25_index: Optional[BM25HybridIndex] = None,
        reranking: bool = config.enable_reranking,
    ):
        """
        Initialize search engine.

        Args:
            catalog: Catalog instance for FTS5
            vector_store: VectorStore instance for semantic search
            bm25_index: BM25HybridIndex for lexical matching
            reranking: Enable CrossEncoder reranking
        """
        self.catalog = catalog or Catalog()
        self.catalog.init_db()
        self.vector_store = vector_store
        self._vector_store_error: Exception | None = None
        self.bm25 = bm25_index or self._load_bm25()
        self._embedder = None
        self.do_reranking = reranking
        self._reranker_model = None
        self._catalog_error: Exception | None = None
        self._vector_store_checked = False
        self.last_report = SearchReport()

    def _get_vector_store(self) -> Optional[VectorStore]:
        """Return the vector store if Qdrant is available, otherwise degrade."""
        self._vector_store_checked = True
        vector_store = getattr(self, "vector_store", None)
        if vector_store is not None:
            return vector_store

        if getattr(self, "_vector_store_error", None) is not None:
            return None

        try:
            self.vector_store = VectorStore()
            return self.vector_store
        except Exception as exc:
            self._vector_store_error = exc
            logger.warning(
                "Vector search unavailable; continuing with catalog/BM25 fallback: %s",
                exc,
            )
            return None

    @property
    def reranker(self):
        """Lazy-load cross-encoder reranker via sentence-transformers (pure Python)."""
        if self._reranker_model is None:
            from sentence_transformers import CrossEncoder

            self._reranker_model = CrossEncoder(config.reranker_model, device="cpu")
        return self._reranker_model

    @property
    def embedder(self):
        """Lazy-load embedder for query encoding."""
        if self._embedder is None:
            try:
                from .embedder import get_embedder
            except ImportError:
                from embedder import get_embedder
            self._embedder = get_embedder()
        return self._embedder

    def _load_bm25(self) -> Optional[BM25HybridIndex]:
        """Load BM25 index from disk. Returns None if not available."""
        bm25 = BM25HybridIndex()
        bm25_path = Path(config.bm25_index_path)
        if bm25_path.exists():
            if bm25.load(str(bm25_path)):
                logger.info(f"BM25 index loaded ({len(bm25)} chunks)")
                return bm25
        logger.info("BM25 index not found on disk — lexical search disabled")
        return None

    def _catalog_records_by_path(self, paths: set[str]) -> dict[str, dict]:
        """Return catalog metadata for the requested index paths."""
        if not paths:
            return {}
        normalized = {self._catalog_path_key(path) for path in paths if path}
        try:
            records = self.catalog.get_all_files()
        except Exception as exc:
            self._catalog_error = exc
            logger.warning("Catalog metadata lookup failed: %s", exc)
            return {}
        matched: dict[str, dict] = {}
        for record in records:
            record_path = str(record.get("path") or "")
            record_full_path = str(record.get("full_path") or "")
            for key in {
                self._catalog_path_key(record_path),
                self._catalog_path_key(record_full_path),
            }:
                if key and key in normalized:
                    matched[key] = record
        return matched

    @staticmethod
    def _catalog_path_key(path: str) -> str:
        """Normalize a result/catalog path for freshness metadata joins."""

        return path.replace("\\", "/").lower()

    @staticmethod
    def _first_record_value(record: dict, *keys: str) -> Any:
        """Return the first present, non-empty catalog value from candidate keys."""

        for key in keys:
            if key not in record:
                continue
            value = record[key]
            if value is None or value == "":
                continue
            return value
        return None

    @staticmethod
    def _mtime_matches(left: float, right: float) -> bool:
        """Compare filesystem timestamps with a small precision tolerance."""

        return abs(float(left) - float(right)) <= FRESHNESS_MTIME_TOLERANCE_SECONDS

    @staticmethod
    def _hash_source_file(path: Path) -> str:
        """Return the MD5 content hash used by FileMind source metadata."""

        try:
            digest = hashlib.md5(usedforsecurity=False)
        except TypeError:
            digest = hashlib.md5()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _source_path_for_record(result: SearchResult, record: dict) -> Path | None:
        """Resolve the disk path represented by a catalog record."""

        raw_full_path = str(record.get("full_path") or "").strip()
        if raw_full_path:
            return Path(raw_full_path)

        raw_path = str(record.get("path") or result.file_path or "").strip()
        if not raw_path:
            return None

        candidate = Path(raw_path)
        if candidate.is_absolute():
            return candidate
        return Path(config.ai_station_root) / raw_path

    def _evaluate_result_freshness(
        self, result: SearchResult, record: dict | None
    ) -> SearchResult:
        """Attach freshness status/evidence to a result using catalog + disk state."""

        evidence: dict[str, Any] = {
            "result_file_path": result.file_path,
            "result_chunk_index": int(result.chunk_index),
            "result_mtime": float(result.mtime or 0.0),
        }

        if not record:
            result.freshness_status = FRESHNESS_MISSING_CATALOG
            result.freshness_evidence = evidence
            return result

        source_mtime_value = self._first_record_value(record, "source_mtime", "mtime")
        source_size_value = self._first_record_value(record, "source_size", "size")
        source_hash_value = self._first_record_value(
            record, "source_content_hash", "content_hash"
        )
        chunk_count_value = self._first_record_value(record, "chunk_count")
        source_path = self._source_path_for_record(result, record)
        evidence.update(
            {
                "catalog_path": str(record.get("path") or ""),
                "catalog_full_path": str(record.get("full_path") or ""),
                "catalog_chunk_count": chunk_count_value,
                "source_path": str(source_path) if source_path is not None else "",
                "source_mtime": source_mtime_value,
                "source_size": source_size_value,
                "source_content_hash": source_hash_value,
            }
        )

        if (
            source_path is None
            or source_mtime_value is None
            or source_size_value is None
            or source_hash_value is None
        ):
            result.freshness_status = FRESHNESS_MISSING_CATALOG
            result.freshness_evidence = evidence
            return result

        try:
            source_mtime = float(source_mtime_value)
            source_size = int(source_size_value)
        except (TypeError, ValueError):
            result.freshness_status = FRESHNESS_MISSING_CATALOG
            result.freshness_evidence = evidence
            return result

        if not source_path.exists() or not source_path.is_file():
            result.freshness_status = FRESHNESS_DELETED
            result.freshness_evidence = evidence
            return result

        try:
            stat = source_path.stat()
            current_hash = self._hash_source_file(source_path)
        except OSError as exc:
            evidence["error"] = str(exc)
            result.freshness_status = FRESHNESS_DELETED
            result.freshness_evidence = evidence
            return result

        current_size = int(stat.st_size)
        current_mtime = float(stat.st_mtime)
        evidence.update(
            {
                "current_mtime": current_mtime,
                "current_size": current_size,
                "current_content_hash": current_hash,
            }
        )

        if current_size != source_size or current_hash != str(source_hash_value):
            result.freshness_status = FRESHNESS_CHANGED
            result.freshness_evidence = evidence
            return result

        if not self._mtime_matches(current_mtime, source_mtime):
            result.freshness_status = FRESHNESS_STALE
            result.freshness_evidence = evidence
            return result

        if result.chunk_index >= 0:
            try:
                catalog_chunk_count = int(chunk_count_value)
            except (TypeError, ValueError):
                catalog_chunk_count = -1
            if catalog_chunk_count <= int(result.chunk_index):
                result.freshness_status = FRESHNESS_MISSING_CHUNK
                result.freshness_evidence = evidence
                return result

        result_mtime = float(result.mtime or 0.0)
        if result_mtime > 0.0 and not self._mtime_matches(result_mtime, source_mtime):
            result.freshness_status = FRESHNESS_STALE
            result.freshness_evidence = evidence
            return result

        result.freshness_status = FRESHNESS_FRESH
        result.freshness_evidence = evidence
        return result

    @staticmethod
    def _record_search_candidate(
        report: SearchReport | None,
        result: SearchResult,
        *,
        include_stale: bool,
    ) -> None:
        """Accumulate candidate-level freshness/protection metadata."""

        if report is None:
            return

        candidate_key = f"{result.file_path}::{int(result.chunk_index)}"
        if candidate_key in report._freshness_seen_keys:
            return
        report._freshness_seen_keys.add(candidate_key)
        report.candidate_count += 1
        report.freshness_counts[result.freshness_status] = (
            report.freshness_counts.get(result.freshness_status, 0) + 1
        )

        if result.is_protected:
            report.protected_count += 1
            report.mark_degraded(
                DEGRADED_PROTECTED_PATH,
                "Protected or excluded-path search output was redacted and must not be treated as full source truth.",
            )

        if result.freshness_status == FRESHNESS_FRESH:
            return

        if include_stale:
            report.mark_degraded(
                DEGRADED_UNFRESH_INCLUDED,
                "Search output includes non-fresh results for diagnostics; verify current files directly before using them as evidence.",
            )
            return

        report.filtered_freshness_counts[result.freshness_status] = (
            report.filtered_freshness_counts.get(result.freshness_status, 0) + 1
        )
        report.mark_degraded(
            DEGRADED_UNFRESH_FILTERED,
            "Non-fresh FileMind candidates were filtered; absence from results is not proof that no current file exists.",
        )

    def _apply_freshness_gate(
        self,
        results: list[SearchResult],
        *,
        include_stale: bool = False,
        report: SearchReport | None = None,
    ) -> list[SearchResult]:
        """Mark result freshness and drop unfresh results unless explicitly requested."""

        if not results:
            return []

        records = self._catalog_records_by_path({result.file_path for result in results})
        catalog_lookup_failed = getattr(self, "_catalog_error", None) is not None and not records
        gated: list[SearchResult] = []
        for result in results:
            record = records.get(self._catalog_path_key(result.file_path))
            self._evaluate_result_freshness(result, record)
            if catalog_lookup_failed or (
                record is not None
                and result.freshness_status == FRESHNESS_MISSING_CATALOG
                and not record.get("full_path")
            ):
                self._record_search_candidate(
                    report, result, include_stale=True
                )
                gated.append(result)
                continue
            self._record_search_candidate(
                report, result, include_stale=include_stale
            )
            if include_stale or result.freshness_status == FRESHNESS_FRESH:
                gated.append(result)
        return gated

    def _catalog_keyword_search(self, query: str, top_k: int) -> list[SearchResult]:
        """Pure catalog FTS5 keyword search that does not require Qdrant."""
        results: list[SearchResult] = []
        try:
            rows = self.catalog.fts_search(query, top_k)
        except Exception as exc:
            self._catalog_error = exc
            logger.warning("Catalog FTS search failed: %s", exc)
            return results

        for rank, row in enumerate(rows, start=1):
            file_path = str(row.get("path") or "")
            if not file_path:
                continue
            content_summary = str(row.get("content_summary") or "")
            snippet, protected = self._safe_result_snippet(file_path, content_summary)
            raw_score = row.get("rank", 0.0)
            try:
                # SQLite FTS5 BM25 ranks are usually negative; convert to a
                # positive display score while preserving rank order.
                score = abs(float(raw_score))
            except (TypeError, ValueError):
                score = 0.0
            results.append(
                SearchResult(
                    file_path=file_path,
                    chunk_index=-1,
                    score=score,
                    keyword_rank=rank,
                    snippet=snippet,
                    category=str(row.get("category") or ""),
                    file_type=str(row.get("ext") or PurePosixPath(file_path).suffix),
                    mtime=float(row.get("mtime") or 0.0),
                    is_protected=protected,
                )
            )
        return results

    def _safe_result_snippet(
        self, file_path: str, content: str, max_chars: int = 200
    ) -> tuple[str, bool]:
        """Return a normal-output-safe snippet plus protected-lane marker."""

        protected = is_secret_like_path(file_path) or contains_secret_value(content)
        return normal_search_snippet(file_path, content, max_chars=max_chars), protected

    def _exact_catalog_search(
        self,
        query: str,
        *,
        top_k: int,
        file_type: Optional[str] = None,
        category: Optional[str] = None,
    ) -> list[SearchResult]:
        """Return high-confidence catalog hits for exact filename/path queries.

        This is a metadata/content-summary lane, not a vector lane.  It is
        deliberately allowed to return records with ``chunk_count == 0`` so a
        user can still find a cataloged Markdown/documentation file while the
        vector index is being repaired.
        """

        tokens = _extract_file_lookup_tokens(query)
        if not tokens:
            return []

        try:
            records = self.catalog.get_all_files()
        except Exception as exc:
            self._catalog_error = exc
            logger.warning("Exact catalog lookup failed: %s", exc)
            return []

        scored: dict[str, SearchResult] = {}
        for record in records:
            path = str(record.get("path") or "").replace("\\", "/")
            if not path:
                continue
            ext = str(record.get("ext") or PurePosixPath(path).suffix).lower()
            rec_category = str(record.get("category") or "")
            if file_type and ext != file_type:
                continue
            if category and rec_category != category:
                continue

            path_lower = path.lower()
            full_path_lower = (
                str(record.get("full_path") or "").replace("\\", "/").lower()
            )
            name_lower = PurePosixPath(path_lower).name
            stem_lower = PurePosixPath(path_lower).stem

            best_score = 0.0
            for token in tokens:
                token_name = PurePosixPath(token).name
                token_stem = PurePosixPath(token).stem
                if path_lower == token or full_path_lower == token:
                    best_score = max(best_score, 2.0)
                elif path_lower.endswith(f"/{token}") or full_path_lower.endswith(
                    f"/{token}"
                ):
                    best_score = max(best_score, 1.9)
                elif name_lower == token_name:
                    best_score = max(best_score, 1.75)
                elif token_stem and stem_lower == token_stem:
                    best_score = max(best_score, 1.35)

            if best_score <= 0:
                continue

            content_summary = str(record.get("content_summary") or "")
            snippet, protected = self._safe_result_snippet(path, content_summary)
            chunk_count = int(record.get("chunk_count") or 0)
            # Prefer records with live chunks when scores tie, but keep
            # zero-chunk catalog records discoverable.
            best_score += min(0.08, max(0, chunk_count) * 0.01)
            result = SearchResult(
                file_path=path,
                chunk_index=-1,
                score=best_score,
                keyword_rank=1,
                snippet=snippet,
                category=rec_category,
                file_type=ext,
                mtime=float(record.get("mtime") or 0.0),
                is_protected=protected,
            )
            existing = scored.get(path)
            if existing is None or result.score > existing.score:
                scored[path] = result

        return sorted(scored.values(), key=lambda item: (-item.score, item.file_path))[
            :top_k
        ]

    def _new_search_report(self, query: str, top_k: int) -> SearchReport:
        """Start a per-search degraded-mode report."""

        self._catalog_error = None
        self._vector_store_checked = False
        report = SearchReport(
            query=query,
            top_k=top_k,
            backend_status={
                "catalog": "ok",
                "vector": "not_used",
                "bm25": "ok" if getattr(self, "bm25", None) else "unavailable",
            },
        )
        self.last_report = report
        return report

    @staticmethod
    def _mark_protected_lookup_tokens(
        report: SearchReport, lookup_tokens: list[str]
    ) -> None:
        for token in lookup_tokens:
            if not is_secret_like_path(token):
                continue
            report.protected_count += 1
            report.mark_degraded(
                DEGRADED_PROTECTED_PATH,
                "The query names a protected or excluded-looking path; use direct authorized file inspection instead of treating FileMind output as complete.",
            )

    @staticmethod
    def _resolve_live_lookup_path(token: str) -> Path | None:
        """Resolve an exact path-like lookup token to a direct filesystem path."""

        normalized = token.replace("\\", "/").strip()
        if not normalized or (
            "/" not in normalized and not re.match(r"^[a-z]:/", normalized)
        ):
            return None
        candidate = Path(normalized)
        if not candidate.is_absolute():
            candidate = Path(config.ai_station_root) / normalized
        return candidate

    def _mark_unindexed_live_lookup_tokens(
        self, report: SearchReport, lookup_tokens: list[str]
    ) -> None:
        """Warn when an exact file named by the query exists but is absent from FileMind."""

        path_tokens = [
            token
            for token in lookup_tokens
            if self._resolve_live_lookup_path(token) is not None
        ]
        if not path_tokens:
            return

        catalog_matches = self._catalog_records_by_path(set(path_tokens))
        for token in path_tokens:
            if self._catalog_path_key(token) in catalog_matches:
                continue
            live_path = self._resolve_live_lookup_path(token)
            if live_path is None or not live_path.exists() or not live_path.is_file():
                continue
            live_path_text = str(live_path)
            if live_path_text not in report.unindexed_live_file_paths:
                report.unindexed_live_file_paths.append(live_path_text)
            report.mark_degraded(
                DEGRADED_UNINDEXED_LIVE_FILE,
                "A live file named by the query is not present in the FileMind "
                "index; inspect it directly or reindex before trusting FileMind absence.",
            )

    def _finish_search_report(
        self, report: SearchReport, results: list[SearchResult]
    ) -> list[SearchResult]:
        """Finalize report status and expose it on ``last_report``."""

        report.returned_count = len(results)

        if getattr(self, "_vector_store_checked", False):
            vector_error = getattr(self, "_vector_store_error", None)
            if getattr(self, "vector_store", None) is not None:
                report.backend_status["vector"] = "ok"
            elif vector_error is not None:
                report.backend_status["vector"] = "unavailable"
                report.backend_errors["vector"] = str(vector_error)
                report.mark_degraded(
                    DEGRADED_VECTOR_UNAVAILABLE,
                    "Vector backend/index is unavailable; results are fallback-only and not complete source truth.",
                )
            else:
                report.backend_status["vector"] = "ok"

        catalog_error = getattr(self, "_catalog_error", None)
        if catalog_error is not None:
            report.backend_status["catalog"] = "unavailable"
            report.backend_errors["catalog"] = str(catalog_error)
            report.mark_degraded(
                DEGRADED_CATALOG_UNAVAILABLE,
                "Catalog lookup failed; FileMind output is partial and must be verified against direct filesystem evidence.",
            )

        if report.returned_count == 0:
            if report.unindexed_live_file_paths:
                report.miss_state = "unindexed_live_file"
            elif report.filtered_freshness_counts:
                report.miss_state = "all_candidates_filtered"
            elif report.degraded_reasons:
                report.miss_state = "degraded_backend_miss"
            else:
                report.miss_state = "benchmark_miss_or_no_results"
                report.warnings.append(
                    "No current FileMind results returned; smoke/benchmark workflows must treat this as an explicit miss, not source-truth proof."
                )
        else:
            report.miss_state = "none"

        if report.degraded_reasons:
            report.status = SEARCH_STATUS_DEGRADED
            report.authority = SEARCH_AUTHORITY_DEGRADED
        elif report.returned_count == 0:
            report.status = SEARCH_STATUS_EMPTY
            report.authority = SEARCH_AUTHORITY_EMPTY
        else:
            report.status = SEARCH_STATUS_OK
            report.authority = SEARCH_AUTHORITY_CURRENT

        report.partial = bool(
            report.degraded_reasons
            and (
                report.returned_count > 0
                or report.filtered_freshness_counts
                or report.unindexed_live_file_paths
            )
        )
        self.last_report = report
        return results

    @staticmethod
    def _merge_exact_results(
        exact_results: list[SearchResult],
        ranked_results: list[SearchResult],
        top_k: int,
    ) -> list[SearchResult]:
        if not exact_results:
            return ranked_results[:top_k]

        merged: list[SearchResult] = []
        seen_results: set[tuple[str, int]] = set()
        for result in sorted(
            exact_results, key=lambda item: (-item.score, item.file_path)
        ):
            key = (result.file_path.replace("\\", "/").lower(), int(result.chunk_index))
            if key in seen_results:
                continue
            seen_results.add(key)
            merged.append(result)

        for result in ranked_results:
            key = (result.file_path.replace("\\", "/").lower(), int(result.chunk_index))
            if key in seen_results:
                continue
            seen_results.add(key)
            merged.append(result)
            if len(merged) >= top_k:
                break

        return merged[:top_k]

    def _detect_query_intent(self, query: str) -> float:
        query_lower = query.lower().strip()
        words = query_lower.split()
        if '"' in query or (words and "." in words[-1]):
            return 0.8
        if re.search(r"\b\w+_\w+\b", query_lower):
            return 0.8
        if "-" in query_lower:
            return 0.8
        word_count = len(words)
        if word_count <= 2:
            return 1.2
        question_words = ["how", "what", "find", "show", "files", "where"]
        if any(query_lower.startswith(w) for w in question_words) or word_count >= 7:
            return 1.4
        return 1.0

    def _hyde_expand(self, query: str) -> str:
        """Hypothetical Document Embeddings via Ollama."""
        try:
            import requests

            prompt = f"Write a short file (50 words) that would match this search: '{query}'. Return only the content."
            payload = {
                "model": config.hyde_model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 100},
            }
            response = requests.post(
                f"{config.ollama_api_url}/api/chat", json=payload, timeout=10
            )
            if response.status_code == 200:
                expanded = response.json().get("message", {}).get("content", "").strip()
                if expanded:
                    return expanded
        except Exception as e:
            logger.warning(f"HyDE expansion failed: {e}")
        return query

    def _rerank(
        self, query: str, results: list[SearchResult], top_k: int
    ) -> list[SearchResult]:
        if not results:
            return []
        try:
            # Log pre-rerank order for verification
            pre_order = [r.file_path.rsplit("/", 1)[-1] for r in results[:5]]
            logger.debug(f"Pre-rerank top-5: {pre_order}")

            pairs = [(query, r.snippet) for r in results]
            reranker = cast(Any, self.reranker)
            if hasattr(reranker, "compute_score"):
                scores = reranker.compute_score(pairs, normalize=True)
            elif hasattr(reranker, "predict"):
                raw_scores = reranker.predict(pairs, show_progress_bar=False)
                if hasattr(raw_scores, "tolist"):
                    raw_scores = raw_scores.tolist()
                if raw_scores and isinstance(raw_scores[0], (list, tuple)):
                    raw_scores = [row[-1] for row in raw_scores]
                scores = []
                for value in raw_scores:
                    score = float(value)
                    if score < 0.0 or score > 1.0:
                        # Preserve older normalized-score behavior when predict()
                        # returns logits instead of probabilities.
                        if score >= 0:
                            exp_neg = math.exp(-score)
                            score = 1.0 / (1.0 + exp_neg)
                        else:
                            exp_pos = math.exp(score)
                            score = exp_pos / (1.0 + exp_pos)
                    scores.append(score)
            else:
                raise AttributeError(
                    "CrossEncoder exposes neither compute_score() nor predict()"
                )
            for r, score in zip(results, scores):
                r.score = float(score)
            results.sort(key=lambda x: x.score, reverse=True)

            # Log post-rerank order for verification
            post_order = [r.file_path.rsplit("/", 1)[-1] for r in results[:5]]
            logger.debug(f"Post-rerank top-5: {post_order}")
            if pre_order != post_order:
                logger.info(f"Reranker reordered: {pre_order[0]} -> {post_order[0]}")

            return results[:top_k]
        except Exception as e:
            logger.error(f"Reranking failed: {e}")
            return results[:top_k]

    def search(
        self,
        query: str,
        top_k: Optional[int] = None,
        file_type: Optional[str] = None,
        category: Optional[str] = None,
        use_hybrid: bool = True,
        use_hyde: bool = False,
        include_stale: bool = False,
    ) -> list[SearchResult]:
        """
        Hybrid search: keyword + semantic → RRF fusion.

        Args:
            query: Search query (natural language or keywords)
            top_k: Number of results to return
            file_type: Filter by file extension (e.g., ".py")
            category: Filter by category
            include_stale: Include stale/deleted/missing results after labeling them

        Returns:
            Sorted list of SearchResults by combined RRF score
        """
        import re

        original_query = query
        top_k = _resolve_top_k(top_k)
        report = self._new_search_report(original_query, top_k)

        # Parse inline query operators
        type_match = re.search(r"type:([^\s]+)", query, re.IGNORECASE)
        cat_match = re.search(r"in:([^\s]+)", query, re.IGNORECASE)

        if type_match:
            matched_type = type_match.group(1).lower()
            if not matched_type.startswith("."):
                matched_type = f".{matched_type}"
            file_type = matched_type
            query = query.replace(type_match.group(0), "").strip()

        if cat_match:
            category = cat_match.group(1).lower()
            query = query.replace(cat_match.group(0), "").strip()

        exact_results = self._exact_catalog_search(
            query,
            top_k=top_k,
            file_type=file_type,
            category=category,
        )
        exact_results = self._apply_freshness_gate(
            exact_results, include_stale=include_stale, report=report
        )
        lookup_tokens = _extract_file_lookup_tokens(query)
        self._mark_protected_lookup_tokens(report, lookup_tokens)
        self._mark_unindexed_live_lookup_tokens(report, lookup_tokens)
        if (
            use_hybrid
            and exact_results
            and _is_precise_file_lookup(lookup_tokens)
            and len(exact_results) >= top_k
            and not self.do_reranking
        ):
            return self._finish_search_report(report, exact_results[:top_k])

        semantic_weight = self._detect_query_intent(query)

        expanded_query = query
        if use_hyde and semantic_weight >= 2.0:
            expanded_query = self._hyde_expand(query)

        if use_hybrid:
            where_dict = {}
            if file_type:
                where_dict["file_type"] = file_type
            if category:
                where_dict["category"] = category

            results = []
            vector_store = self._get_vector_store()
            if vector_store is not None:
                res = self.embedder.encode(
                    [query], return_dense=True, return_sparse=True
                )
                query_vec1 = res.get("dense_vecs", [[]])[0]
                sparse_dict1 = res.get("lexical_weights", [{}])[0]

                if use_hyde and expanded_query != query:
                    import numpy as np

                    res2 = self.embedder.encode(
                        [expanded_query], return_dense=True, return_sparse=True
                    )
                    query_vec2 = res2.get("dense_vecs", [[]])[0]
                    vector = (
                        (1 - config.hyde_weight) * np.array(query_vec1)
                        + config.hyde_weight * np.array(query_vec2)
                    ).tolist()
                else:
                    vector = query_vec1

                if vector:
                    raw_results = vector_store.search_hybrid(
                        query,
                        vector,
                        top_k * 2 if self.do_reranking else top_k,
                        sparse_dict=sparse_dict1,
                        where=where_dict if where_dict else None,
                    )
                    seen = set()
                    for r in raw_results:
                        key = (r.get("file_id", ""), r.get("chunk_index", -1))
                        if key not in seen:
                            seen.add(key)
                            score = float(
                                r.get("_relevance_score", r.get("_distance", 1.0))
                            )
                            snippet, protected = self._safe_result_snippet(
                                key[0], r.get("content", "")
                            )
                            results.append(
                                SearchResult(
                                    file_path=key[0],
                                    chunk_index=int(key[1]),
                                    score=score,
                                    snippet=snippet,
                                    category=r.get("category", ""),
                                    file_type=r.get("file_type", ""),
                                    mtime=r.get("mtime", 0),
                                    is_protected=protected,
                                )
                            )
                else:
                    logger.warning(
                        "Vector search skipped because query embedding was empty."
                    )

            # BM25 lexical search — add as third leg of RRF fusion
            bm25_results = []
            if self.bm25 and self.bm25.is_built:
                bm25_hits = self.bm25.search(query, top_k=top_k * 2)
                bm25_paths = {
                    chunk_id.rsplit("::chunk_", 1)[0]
                    for chunk_id, _ in bm25_hits
                    if "::chunk_" in chunk_id
                }
                bm25_metadata = self._catalog_records_by_path(bm25_paths)
                for chunk_id, bm25_score in bm25_hits:
                    # Parse chunk_id format: "file_path::chunk_N"
                    parts = chunk_id.rsplit("::chunk_", 1)
                    if len(parts) == 2:
                        record = bm25_metadata.get(
                            parts[0].replace("\\", "/").lower(), {}
                        )
                        snippet, protected = self._safe_result_snippet(
                            parts[0],
                            str(record.get("content_summary") or ""),
                        )
                        bm25_results.append(
                            SearchResult(
                                file_path=parts[0],
                                chunk_index=int(parts[1]),
                                score=bm25_score,
                                snippet=snippet,
                                category=str(record.get("category") or ""),
                                file_type=str(
                                    record.get("ext") or PurePosixPath(parts[0]).suffix
                                ),
                                mtime=float(record.get("mtime") or 0.0),
                                is_protected=protected or is_secret_like_path(parts[0]),
                            )
                        )

            keyword_results = self._catalog_keyword_search(query, top_k * 2)

            if bm25_results or keyword_results:
                # Three-way RRF: catalog keyword + semantic + BM25. This still
                # works when Qdrant is unreachable because dense results are
                # simply empty.
                fused = self._rrf_fusion_3way(
                    results,  # from Qdrant hybrid (dense+sparse prefetch)
                    keyword_results,
                    bm25_results,  # standalone BM25 lexical
                    semantic_weight=semantic_weight,
                    bm25_weight=1.0,
                )
                final_res = [r for _, r in fused[: top_k * 2]]
            else:
                final_res = results

            ranked = (
                self._rerank(query, final_res, top_k)
                if self.do_reranking
                else final_res[:top_k]
            )
            merged = self._merge_exact_results(exact_results, ranked, top_k)
            final_results = self._apply_freshness_gate(
                merged, include_stale=include_stale, report=report
            )[:top_k]
            return self._finish_search_report(report, final_results)

        # Step 1: Keyword search (FTS5)
        keyword_results = self._keyword_search(query, top_k * 2)

        # Step 2: Semantic search (vector)
        semantic_results = self._semantic_search(query, top_k * 2)

        # Step 3: Apply filters
        if file_type:
            keyword_results = [r for r in keyword_results if r.file_type == file_type]
            semantic_results = [r for r in semantic_results if r.file_type == file_type]
        if category:
            keyword_results = [r for r in keyword_results if r.category == category]
            semantic_results = [r for r in semantic_results if r.category == category]

        # Step 4: RRF fusion
        fused = self._rrf_fusion(keyword_results, semantic_results, semantic_weight)

        # Step 5: Deduplicate by file_path + chunk_index
        seen = set()
        unique_results = []
        for score, result in fused:
            key = (result.file_path, result.chunk_index)
            if key not in seen:
                seen.add(key)
                result.score = score
                unique_results.append(result)

        final_res = (
            unique_results[: top_k * 2] if self.do_reranking else unique_results[:top_k]
        )
        ranked = (
            self._rerank(query, final_res, top_k) if self.do_reranking else final_res
        )
        merged = self._merge_exact_results(exact_results, ranked, top_k)
        final_results = self._apply_freshness_gate(
            merged, include_stale=include_stale, report=report
        )[:top_k]
        return self._finish_search_report(report, final_results)

    def keyword_search(
        self, query: str, top_k: int = 20, *, include_stale: bool = False
    ) -> list[SearchResult]:
        """Pure keyword search via FTS5."""
        report = self._new_search_report(query, top_k)
        final_results = self._apply_freshness_gate(
            self._keyword_search(query, top_k),
            include_stale=include_stale,
            report=report,
        )
        return self._finish_search_report(report, final_results)

    def semantic_search(
        self, query: str, top_k: int = 20, *, include_stale: bool = False
    ) -> list[SearchResult]:
        """Pure semantic search via vector similarity."""
        report = self._new_search_report(query, top_k)
        final_results = self._apply_freshness_gate(
            self._semantic_search(query, top_k),
            include_stale=include_stale,
            report=report,
        )
        return self._finish_search_report(report, final_results)

    def _keyword_search(self, query: str, top_k: int) -> list[SearchResult]:
        """Keyword search, preferring catalog FTS5 and degrading if Qdrant is down."""
        results = self._catalog_keyword_search(query, top_k)
        if results:
            return results

        vector_store = self._get_vector_store()
        if vector_store is None:
            return []

        results = []
        for row in vector_store.search_fts(query, top_k):
            file_path = row.get("file_id", "")
            snippet, protected = self._safe_result_snippet(
                file_path, row.get("content", "")
            )
            results.append(
                SearchResult(
                    file_path=file_path,
                    chunk_index=row.get("chunk_index", -1),
                    snippet=snippet,
                    category=row.get("category", ""),
                    file_type=row.get("file_type", ""),
                    mtime=row.get("mtime", 0),
                    is_protected=protected,
                )
            )
        return results

    def _semantic_search(self, query: str, top_k: int) -> list[SearchResult]:
        """Dense vector semantic search."""
        try:
            vector_store = self._get_vector_store()
            if vector_store is None:
                return []

            # Encode query
            query_vec = self.embedder.encode(
                [query],
                return_dense=True,
                return_sparse=True,
            )
            if not query_vec.get("dense_vecs") or not query_vec["dense_vecs"][0]:
                return []

            vector = query_vec["dense_vecs"][0]

            # Search
            chunks = vector_store.search_dense(vector, top_k)

            results = []
            for chunk in chunks:
                file_path = chunk.get("file_id", "")
                snippet, protected = self._safe_result_snippet(
                    file_path, chunk.get("content", "")
                )
                results.append(
                    SearchResult(
                        file_path=file_path,
                        chunk_index=chunk.get("chunk_index", -1),
                        snippet=snippet,
                        category=chunk.get("category", ""),
                        file_type=chunk.get("file_type", ""),
                        mtime=chunk.get("mtime", 0),
                        is_protected=protected,
                    )
                )
            return results
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return []

    def _rrf_fusion(
        self,
        keyword_results: list[SearchResult],
        semantic_results: list[SearchResult],
        semantic_weight: float = 2.0,
    ) -> list[tuple[float, SearchResult]]:
        """
        Combine ranked lists using Reciprocal Rank Fusion.

        RRF(d) = 1 / (k + rank_keyword(d)) + 1 / (k + rank_semantic(d))

        Args:
            keyword_results: Keyword results in rank order
            semantic_results: Semantic results in rank order

        Returns:
            List of (rrf_score, SearchResult) sorted by score desc
        """
        scores: dict[str, float] = {}
        result_map: dict[str, SearchResult] = {}

        # Keyword ranks
        for rank, result in enumerate(keyword_results):
            key = f"{result.file_path}::{result.chunk_index}"
            rrf_score = 1 / (RRF_K + rank)
            scores[key] = scores.get(key, 0) + rrf_score
            if key not in result_map:
                result.keyword_rank = rank + 1
                result_map[key] = result

        # Semantic ranks (higher weight depending on semantic_weight variable)
        for rank, result in enumerate(semantic_results):
            key = f"{result.file_path}::{result.chunk_index}"
            rrf_score = semantic_weight / (RRF_K + rank)
            scores[key] = scores.get(key, 0) + rrf_score
            if key not in result_map:
                result.semantic_rank = rank + 1
                result_map[key] = result
            elif result_map[key].semantic_rank == 0:
                result_map[key].semantic_rank = rank + 1

        # Sort by combined score
        fused = []
        for key, score in scores.items():
            if key in result_map:
                fused.append((score, result_map[key]))

        fused.sort(key=lambda x: x[0], reverse=True)
        return fused

    def _rrf_fusion_3way(
        self,
        dense_results: list[SearchResult],
        keyword_results: list[SearchResult],
        bm25_results: list[SearchResult],
        semantic_weight: float = 2.0,
        bm25_weight: float = 1.0,
    ) -> list[tuple[float, SearchResult]]:
        """
        Three-way Reciprocal Rank Fusion: dense + keyword + BM25.

        RRF(d) = semantic_weight/(k + rank_dense) + 1/(k + rank_keyword) + bm25_weight/(k + rank_bm25)

        Args:
            dense_results: Qdrant dense vector results
            keyword_results: FTS5 keyword results
            bm25_results: Standalone BM25 lexical results
            semantic_weight: Weight for dense vector ranks
            bm25_weight: Weight for BM25 lexical ranks

        Returns:
            List of (rrf_score, SearchResult) sorted by score desc
        """
        scores: dict[str, float] = {}
        result_map: dict[str, SearchResult] = {}

        # Dense vector ranks
        for rank, result in enumerate(dense_results):
            key = f"{result.file_path}::{result.chunk_index}"
            scores[key] = scores.get(key, 0.0) + semantic_weight / (RRF_K + rank)
            if key not in result_map:
                result_map[key] = result

        # Keyword ranks (from Qdrant FTS, already merged in dense_results)
        for rank, result in enumerate(keyword_results):
            key = f"{result.file_path}::{result.chunk_index}"
            scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank)
            if key not in result_map:
                result_map[key] = result

        # BM25 lexical ranks
        for rank, result in enumerate(bm25_results):
            key = f"{result.file_path}::{result.chunk_index}"
            scores[key] = scores.get(key, 0.0) + bm25_weight / (RRF_K + rank)
            if key not in result_map:
                result_map[key] = result

        fused = [
            (score, result_map[key])
            for key, score in scores.items()
            if key in result_map
        ]
        fused.sort(key=lambda x: x[0], reverse=True)
        return fused

    def close(self):
        """Close connections."""
        self.catalog.close()
        vector_store = getattr(self, "vector_store", None)
        if vector_store is not None:
            vector_store.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def hybrid_search(
    query: str,
    top_k: Optional[int] = None,
    file_type: Optional[str] = None,
    category: Optional[str] = None,
    use_hyde: bool = False,
    reranking: bool = False,
) -> list[SearchResult]:
    """Convenience function: search with default engine."""
    top_k = _resolve_top_k(top_k)
    engine = SearchEngine(reranking=reranking)
    try:
        return engine.search(query, top_k, file_type, category, use_hyde=use_hyde)
    finally:
        engine.close()
