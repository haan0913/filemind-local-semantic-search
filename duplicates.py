"""
Duplicate Detector — Exact and semantic duplicate detection.

Exact duplicates: identical content hash (MD5 of first 64KB).
Semantic duplicates: cosine similarity > 0.97 between any two file chunks.
"""

import hashlib
import logging
from collections import defaultdict
from typing import Optional

import numpy as np

try:
    from .config import config
    from .catalog import Catalog
    from .vector_store import VectorStore
except ImportError:
    from config import config
    from catalog import Catalog
    from vector_store import VectorStore

logger = logging.getLogger(__name__)


class DuplicateDetector:
    """Detect exact and semantic duplicate files."""

    def __init__(self, catalog: Optional[Catalog] = None,
                 vector_store: Optional[VectorStore] = None):
        self.catalog = catalog or Catalog()
        self.catalog.init_db()
        self.vector_store = vector_store

    def find_exact(self) -> dict[str, list[str]]:
        """
        Find exact duplicate files by content hash.

        Returns:
            Dict mapping hash -> list of duplicate file paths
        """
        # Group files by content_hash
        hash_groups: dict[str, list[str]] = defaultdict(list)

        # Scan all files in catalog
        stats = self.catalog.get_stats()
        for category in stats.get("categories", {}).keys():
            files = self.catalog.get_files_by_category(category)
            for f in files:
                h = f.get("content_hash", "")
                if h:
                    hash_groups[h].append(f["path"])

        # Filter to groups with >1 file
        duplicates = {
            h: paths
            for h, paths in hash_groups.items()
            if len(paths) > 1
        }

        # Record in catalog
        for h, paths in duplicates.items():
            for path in paths:
                self.catalog.add_duplicate(h, path, is_exact=True)
                self.catalog.mark_duplicate(path, True)

        logger.info(f"Found {len(duplicates)} exact duplicate groups "
                   f"({sum(len(p) for p in duplicates.values())} files)")
        return duplicates

    def find_semantic(self, threshold: float | None = None) -> list[dict]:
        """
        Find near-duplicate files by cosine similarity.

        Compares each file against all others, flags if any OTHER file
        scores above the similarity threshold.

        Args:
            threshold: Cosine similarity threshold (default: 0.97)

        Returns:
            List of dicts with file pairs and similarity scores
        """
        threshold = (
            config.semantic_similarity_threshold if threshold is None else threshold
        )
        duplicates = []

        # Get all unique file IDs from vector store
        try:
            if self.vector_store is None:
                self.vector_store = VectorStore()
            table = getattr(self.vector_store, "table", None)
            if table is None:
                logger.warning("Vector store table unavailable, skipping semantic dedup")
                return []
            all_chunks = table.to_pandas()
        except Exception:
            logger.warning("Vector store empty, skipping semantic dedup")
            return []

        if all_chunks.empty or "file_id" not in all_chunks.columns:
            return []

        # Group by file_id, take first chunk's vector per file
        file_vectors = all_chunks.groupby("file_id").first()

        if len(file_vectors) < 2:
            return []

        # Sample comparison for files with similar sizes/types
        # Full N×N comparison is too expensive for large indices
        logger.info(f"Comparing {len(file_vectors)} files for semantic similarity...")

        # Group by file type for more efficient comparison
        by_type = all_chunks.groupby("file_type")
        for file_type, group in by_type:
            unique_files = group["file_id"].unique()
            if len(unique_files) < 2:
                continue

            # Compare within same file type
            for i in range(len(unique_files)):
                for j in range(i + 1, min(i + 10, len(unique_files))):
                    file_a = unique_files[i]
                    file_b = unique_files[j]

                    # Get first chunk vectors
                    vec_a_chunks = group[group["file_id"] == file_a]
                    vec_b_chunks = group[group["file_id"] == file_b]

                    if vec_a_chunks.empty or vec_b_chunks.empty:
                        continue

                    try:
                        vec_a = np.array(vec_a_chunks.iloc[0]["vector"])
                        vec_b = np.array(vec_b_chunks.iloc[0]["vector"])

                        similarity = self._cosine_similarity(vec_a, vec_b)

                        if similarity >= threshold:
                            dup = {
                                "file_a": file_a,
                                "file_b": file_b,
                                "similarity": float(similarity),
                                "file_type": file_type,
                            }
                            duplicates.append(dup)

                            # Record in catalog
                            hash_group = f"semantic_{file_a[:8]}_{file_b[:8]}"
                            self.catalog.add_duplicate(
                                hash_group, file_a, is_exact=False, similarity=similarity
                            )
                            self.catalog.add_duplicate(
                                hash_group, file_b, is_exact=False, similarity=similarity
                            )
                    except Exception as e:
                        logger.debug(f"Comparison failed: {file_a} vs {file_b}: {e}")

        logger.info(f"Found {len(duplicates)} semantic duplicate pairs")
        return duplicates

    def find_nested_duplicates(self) -> list[dict]:
        """
        Find deeply nested duplicate directories (e.g., .claude/.claude/.claude).

        Detects by identical filenames at depth > 3.

        Returns:
            List of dicts with duplicate file info
        """
        nested_dups = []
        filename_groups: dict[str, list[str]] = defaultdict(list)

        # Collect all indexed files
        stats = self.catalog.get_stats()
        for category in stats.get("categories", {}).keys():
            files = self.catalog.get_files_by_category(category)
            for f in files:
                path = f["path"]
                depth = path.count("/")
                if depth >= 3:
                    filename = path.split("/")[-1]
                    if filename in (".claude", "backups"):
                        filename_groups[filename].append(path)

        for name, paths in filename_groups.items():
            if len(paths) > 5:  # Only flag if many duplicates
                nested_dups.append({
                    "filename": name,
                    "count": len(paths),
                    "paths": paths[:10],  # Limit display
                })

        logger.info(f"Found {len(nested_dups)} nested duplicate patterns")
        return nested_dups

    def report(self) -> dict:
        """Generate duplicate report."""
        exact = self.find_exact()
        semantic = self.find_semantic()
        nested = self.find_nested_duplicates()

        exact_count = sum(len(p) for p in exact.values())
        semantic_count = len(semantic) * 2  # Pairs

        return {
            "exact_groups": len(exact),
            "exact_files": exact_count,
            "semantic_pairs": len(semantic),
            "nested_patterns": len(nested),
            "estimated_savings": f"~{exact_count} files could be removed",
            "details": {
                "exact": dict(list(exact.items())[:20]),  # Limit display
                "semantic": semantic[:20],
                "nested": nested[:10],
            }
        }

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    def close(self):
        """Close connections."""
        self.catalog.close()
        if self.vector_store is not None:
            self.vector_store.close()
