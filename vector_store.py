# pyright: reportMissingParameterType=false, reportMissingTypeArgument=false, reportUnknownLambdaType=false, reportUnknownParameterType=false
"""
Vector Store — Qdrant wrapper for file chunk embeddings.

Serverless, embedded vector database with persistent storage.
Supports hybrid search (dense vector + sparse/lexical).
"""

import logging
import uuid
import zlib
from pathlib import Path
from typing import Any, Optional, cast

from qdrant_client import QdrantClient, models

try:
    from .config import config
except ImportError:
    from config import config

logger = logging.getLogger(__name__)


def generate_uuid(chunk_id: str) -> str:
    """Generate a deterministic UUID from chunk ID string."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


class VectorStore:
    """Qdrant wrapper for file chunk storage and search."""

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize vector store.

        Args:
            db_path: Path to Qdrant directory
        """
        self.db_path = Path(db_path) if db_path else config.qdrant_path
        self.connection_mode = getattr(config, "qdrant_mode", "local").lower()
        self.collection_name = getattr(config, "qdrant_collection", "file_chunks")
        self.qdrant_url = self._resolve_qdrant_url()
        self.client = self._create_client()
        self._ensure_collection()

    def _resolve_qdrant_url(self) -> str:
        qdrant_url = getattr(config, "qdrant_url", "").strip()
        if qdrant_url:
            return qdrant_url
        qdrant_host = getattr(config, "qdrant_host", "127.0.0.1")
        qdrant_port = getattr(config, "qdrant_port", 6333)
        return f"http://{qdrant_host}:{qdrant_port}"

    def _create_client(self) -> QdrantClient:
        if self.connection_mode == "http":
            logger.info(
                "Connecting FileMind vector store to shared Qdrant at %s",
                self.qdrant_url,
            )
            return QdrantClient(url=self.qdrant_url)

        self.db_path.mkdir(parents=True, exist_ok=True)
        logger.info(
            "Connecting FileMind vector store to local Qdrant path %s", self.db_path
        )
        return QdrantClient(path=str(self.db_path))

    def _ensure_collection(self):
        """Ensure collection exists and has appropriate configurations."""
        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config={
                    "dense": models.VectorParams(
                        size=config.embedding_dim, distance=models.Distance.COSINE
                    )
                },
                sparse_vectors_config={
                    "sparse": models.SparseVectorParams(
                        index=models.SparseIndexParams(on_disk=True)
                    )
                },
            )
            # Create payload indices
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="file_id",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="file_type",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="category",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="content",
                field_schema=models.TextIndexParams(
                    type=models.TextIndexType.TEXT,
                    tokenizer=models.TokenizerType.WORD,
                    min_token_len=2,
                    max_token_len=30,
                    lowercase=True,
                ),
            )
            logger.info("Created new Qdrant collection: file_chunks")
        else:
            logger.info("Opened existing Qdrant collection: file_chunks")

    def reset_collection(self):
        """Drop and recreate the FileMind collection for a clean full rebuild."""
        if self.client.collection_exists(self.collection_name):
            self.client.delete_collection(self.collection_name)
            logger.info("Deleted existing Qdrant collection: %s", self.collection_name)
        self._ensure_collection()

    def _parse_sparse(self, sparse_dict: dict) -> models.SparseVector:
        """Parse BGE-M3 lexical weights into Qdrant SparseVector format."""
        indices = []
        values = []
        for token, weight in sparse_dict.items():
            if weight > 0:
                if isinstance(token, int):
                    indices.append(token)
                elif isinstance(token, str) and token.isdigit():
                    indices.append(int(token))
                else:
                    indices.append(zlib.crc32(str(token).encode("utf-8")))
                values.append(float(weight))
        return models.SparseVector(indices=indices, values=values)

    def _dict_to_filter(self, filter_dict: Optional[dict]) -> Optional[models.Filter]:
        """Convert basic dictionary to Qdrant filter condition."""
        if not filter_dict:
            return None
        must_conditions = []
        for k, v in filter_dict.items():
            must_conditions.append(
                models.FieldCondition(key=k, match=models.MatchValue(value=v))
            )
        return models.Filter(must=must_conditions)

    def upsert_chunks(self, chunks: list[dict]) -> int:
        """
        Insert or update chunks in Qdrant.
        """
        if not chunks:
            return 0

        points = []
        for chunk in chunks:
            vector = chunk.get("vector") or [0.0] * config.embedding_dim
            sparse_dict = chunk.get("sparse_vector", {})

            payload = {
                "id": chunk["id"],
                "file_id": chunk["file_id"],
                "chunk_index": int(chunk["chunk_index"]),
                "chunk_hash": chunk.get("chunk_hash", ""),
                "content": chunk["content"],
                "file_type": chunk.get("file_type", ""),
                "category": chunk.get("category", "unknown"),
                "mtime": float(chunk.get("mtime", 0)),
            }

            points.append(
                models.PointStruct(
                    id=generate_uuid(chunk["id"]),
                    vector={"dense": vector, "sparse": self._parse_sparse(sparse_dict)},
                    payload=payload,
                )
            )

        try:
            self.client.upsert(
                collection_name=self.collection_name,
                points=points,
                wait=True,
            )
            count = len(points)
            logger.debug(f"Upserted {count} chunks")
            return count
        except Exception as e:
            logger.error(f"Upsert failed: {e}")
            return 0

    def delete_by_file(self, file_id: str) -> int:
        """Delete all chunks for a file."""
        try:
            filter_obj = models.Filter(
                must=[
                    models.FieldCondition(
                        key="file_id", match=models.MatchValue(value=file_id)
                    )
                ]
            )
            count_res = self.client.count(
                collection_name=self.collection_name, count_filter=filter_obj
            )
            n = count_res.count

            if n > 0:
                self.client.delete(
                    collection_name=self.collection_name,
                    points_selector=filter_obj,
                    wait=True,
                )
                logger.debug(f"Deleted {n} chunks for {file_id}")
            return n
        except Exception as e:
            logger.error(f"Delete failed for {file_id}: {e}")
            return 0

    def delete_file_chunks(self, file_id: str, chunk_indices: list[int]) -> int:
        """Delete specific chunk indexes for a file, raising on write failure."""
        unique_indices = sorted({int(index) for index in chunk_indices})
        if not unique_indices:
            return 0

        point_ids = [
            generate_uuid(f"{file_id}::chunk_{chunk_index}")
            for chunk_index in unique_indices
        ]
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.PointIdsList(points=cast(Any, point_ids)),
            wait=True,
        )
        logger.debug(
            "Deleted %s stale chunk(s) for %s: %s",
            len(point_ids),
            file_id,
            unique_indices,
        )
        return len(point_ids)

    def move_file(
        self,
        old_file_id: str,
        new_file_id: str,
        new_mtime: Optional[float] = None,
        new_file_type: Optional[str] = None,
    ) -> int:
        """Re-key all chunks for a moved file without re-embedding."""
        if old_file_id == new_file_id:
            return len(self.get_file_chunks(old_file_id))

        try:
            moved_points = []
            offset = None
            while True:
                points, next_offset = self.client.scroll(
                    collection_name=self.collection_name,
                    scroll_filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="file_id",
                                match=models.MatchValue(value=old_file_id),
                            )
                        ]
                    ),
                    limit=256,
                    offset=offset,
                    with_payload=True,
                    with_vectors=True,
                )

                for hit in points:
                    payload = dict(hit.payload or {})
                    chunk_index = int(payload.get("chunk_index", 0))
                    new_chunk_id = f"{new_file_id}::chunk_{chunk_index}"
                    payload["id"] = new_chunk_id
                    payload["file_id"] = new_file_id
                    if new_mtime is not None:
                        payload["mtime"] = float(new_mtime)
                    if new_file_type is not None:
                        payload["file_type"] = new_file_type

                    moved_points.append(
                        models.PointStruct(
                            id=generate_uuid(new_chunk_id),
                            vector=cast(Any, hit.vector),
                            payload=payload,
                        )
                    )

                if next_offset is None:
                    break
                offset = next_offset

            if not moved_points:
                return 0

            self.client.upsert(
                collection_name=self.collection_name,
                points=moved_points,
                wait=True,
            )
            self.delete_by_file(old_file_id)
            logger.debug(
                f"Moved {len(moved_points)} chunks from {old_file_id} to {new_file_id}"
            )
            return len(moved_points)
        except Exception as e:
            logger.error(f"Move failed for {old_file_id} -> {new_file_id}: {e}")
            return -1

    def search_dense(
        self, vector: list[float], top_k: int = 20, where: Optional[dict] = None
    ) -> list[dict]:
        """Search by dense vector (cosine similarity)."""
        try:
            # qdrant-client >= 1.7 uses query_points instead of search
            results = self.client.query_points(
                collection_name=self.collection_name,
                query=vector,
                using="dense",
                query_filter=self._dict_to_filter(where),
                limit=top_k,
            )
            docs = []
            for hit in results.points:
                doc = dict(hit.payload or {})
                # Polyfill for search.py hybrid fallback compat
                doc["_distance"] = hit.score
                docs.append(doc)
            return docs
        except Exception as e:
            logger.error(f"Dense search failed: {e}")
            return []

    def build_fts_index(self):
        """No-op. Qdrant handles payload indexing automatically."""
        pass

    def search_fts(
        self, query: str, top_k: int = 20, where: Optional[dict] = None
    ) -> list[dict]:
        """Search built-in Qdrant Text index."""
        try:
            must_conditions: list[models.Condition] = [
                models.FieldCondition(key="content", match=models.MatchText(text=query))
            ]

            f = self._dict_to_filter(where)
            if f and f.must:
                must = f.must if isinstance(f.must, list) else [f.must]
                must_conditions.extend(must)

            results = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=models.Filter(must=must_conditions),
                limit=top_k,
                with_payload=True,
            )
            docs = []
            for hit in results[0]:
                docs.append(hit.payload)
            return docs
        except Exception as e:
            logger.error(f"Qdrant FTS search failed: {e}")
            return []

    def search_hybrid(
        self,
        query_text: str,
        query_vector: list[float],
        top_k: int = 20,
        sparse_dict: Optional[dict] = None,
        where: Optional[dict] = None,
    ) -> list[dict]:
        """Hybrid search blending Dense Vector and Sparse Vector."""
        try:
            prefetch = [
                models.Prefetch(query=query_vector, using="dense", limit=top_k * 4)
            ]
            if sparse_dict:
                prefetch.append(
                    models.Prefetch(
                        query=self._parse_sparse(sparse_dict),
                        using="sparse",
                        limit=top_k * 4,
                    )
                )

            results = self.client.query_points(
                collection_name=self.collection_name,
                prefetch=prefetch,
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                query_filter=self._dict_to_filter(where),
                limit=top_k,
            )

            docs = []
            for hit in results.points:
                doc = dict(hit.payload or {})
                # RRF score
                doc["_relevance_score"] = hit.score
                docs.append(doc)
            return docs
        except Exception as e:
            logger.error(f"Qdrant hybrid search failed: {e}")
            return []

    def count(self) -> int:
        """Total chunks in store."""
        try:
            return self.client.count(collection_name=self.collection_name).count
        except Exception:
            return 0

    def get_file_chunks(self, file_id: str) -> list[dict]:
        """Get all chunks for a specific file."""
        try:
            results = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="file_id", match=models.MatchValue(value=file_id)
                        )
                    ]
                ),
                limit=1000,
                with_payload=True,
            )
            docs = []
            for hit in results[0]:
                docs.append(hit.payload)
            return sorted(docs, key=lambda x: x.get("chunk_index", 0))
        except Exception as e:
            logger.error(f"Get chunks failed for {file_id}: {e}")
            raise

    def export_bm25_chunks(self, batch_size: int = 1000) -> list[dict]:
        """Export all chunk payloads needed to rebuild the BM25 index."""
        chunks = []
        offset = None

        while True:
            points, next_offset = self.client.scroll(
                collection_name=self.collection_name,
                limit=batch_size,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )

            for hit in points:
                payload = hit.payload or {}
                chunk_id = (
                    payload.get("id")
                    or f"{payload.get('file_id', '')}::chunk_{payload.get('chunk_index', 0)}"
                )
                text = payload.get("content", "")
                if not chunk_id or not text:
                    continue

                chunks.append(
                    {
                        "id": chunk_id,
                        "text": text,
                        "file_ext": payload.get("file_type", ""),
                    }
                )

            if next_offset is None:
                break
            offset = next_offset

        return chunks

    def create_scalar_index(self, column: str):
        """Create a payload index on a metadata column for faster pre-filtering."""
        try:
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name=column,
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
            logger.info(f"Created scalar index on {column}")
        except Exception:
            pass

    def close(self):
        """Cleanup."""
        try:
            self.client.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
