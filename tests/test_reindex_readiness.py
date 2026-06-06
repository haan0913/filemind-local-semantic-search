# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportMissingParameterType=false, reportOptionalSubscript=false, reportPrivateUsage=false, reportUnknownLambdaType=false, reportUnknownParameterType=false
"""Focused regressions for FileMind full-reindex readiness."""

import os
import sys
import tempfile
import unittest
import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from filemind.catalog import Catalog
from filemind import config as config_module
from filemind.config import config
from filemind import embedder as embedder_module
from filemind.embedder_flagembedding_experimental import (
    FlagEmbeddingExperimentalEmbedder,
)
from filemind import run as run_module
from filemind import verify as verify_module
from filemind.nightly import NightlyOrchestrator, PipelineResult
from filemind.scanner import FileScanner
from filemind.search import SearchEngine, SearchResult
from filemind.vector_store import VectorStore, generate_uuid


@dataclass
class FakeChunk:
    chunk_index: int
    chunk_hash: str
    content: str


class FakeBM25:
    def __init__(self):
        self.chunks = []

    def add_chunks(self, chunks):
        self.chunks.extend(chunks)

    def save(self, path):
        return None

    def __len__(self):
        return len(self.chunks)


class FakeEmbedder:
    _effective_batch_size = 4

    def encode(self, texts, return_dense=True, return_sparse=True):
        return {
            "dense_vecs": [[0.1, 0.2] for _ in texts],
            "lexical_weights": [{"token": 1.0} for _ in texts],
        }


class FakeSearchBM25:
    is_built = True

    def __init__(self, hits):
        self.hits = list(hits)
        self.calls = []

    def search(self, query, top_k):
        self.calls.append({"query": query, "top_k": top_k})
        return self.hits[:top_k]


class FakeHybridVectorStore:
    def __init__(self, raw_results):
        self.raw_results = list(raw_results)
        self.calls = []

    def search_hybrid(self, query, vector, top_k, sparse_dict=None, where=None):
        self.calls.append(
            {
                "query": query,
                "vector": vector,
                "top_k": top_k,
                "sparse_dict": sparse_dict,
                "where": where,
            }
        )
        return self.raw_results[:top_k]


class RecordingCatalog:
    def __init__(self, records=None):
        self.records = list(records or [])
        self.chunk_counts = {}
        self.updated_summaries = {}
        self.updated_categories = []
        self.upserts = []
        self.conn = SimpleNamespace(commit=MagicMock())

    def get_all_files(self):
        return list(self.records)

    def fts_search(self, query, top_k=20):
        return []

    def upsert_file(self, **record):
        self.upserts.append(record)
        for index, existing in enumerate(self.records):
            if existing.get("path") == record.get("path"):
                self.records[index] = {**existing, **record}
                return
        self.records.append(dict(record))

    def update_content_summary(self, path, content_summary):
        self.updated_summaries[path] = content_summary

    def update_chunk_count(self, path, count):
        self.chunk_counts[path] = count

    def update_category(self, path, category, confidence):
        self.updated_categories.append((path, category, confidence))


class RecordingVectorStore:
    def __init__(
        self,
        existing_by_file=None,
        *,
        fail_upsert: bool = False,
        fail_delete: bool = False,
        fail_get: bool = False,
        connection_mode: str = "http",
        qdrant_url: str | None = None,
        collection_name: str | None = None,
    ):
        self.existing_by_file = dict(existing_by_file or {})
        self.deleted = []
        self.file_chunk_deletes = []
        self.upserts = []
        self.fts_rebuilds = 0
        self.fail_upsert = fail_upsert
        self.fail_delete = fail_delete
        self.fail_get = fail_get
        self.connection_mode = connection_mode
        self.qdrant_url = qdrant_url or config.qdrant_url
        self.collection_name = collection_name or config.qdrant_collection
        self.db_path = config.qdrant_path

    def get_file_chunks(self, path):
        if self.fail_get:
            raise RuntimeError("get chunks failed")
        return list(self.existing_by_file.get(path, []))

    def delete_by_file(self, path):
        if self.fail_delete:
            raise RuntimeError("delete failed")
        self.deleted.append(path)
        existing = self.existing_by_file.pop(path, [])
        return len(existing)

    def delete_file_chunks(self, path, chunk_indices):
        if self.fail_delete:
            raise RuntimeError("delete failed")
        chunk_indices = sorted({int(index) for index in chunk_indices})
        self.file_chunk_deletes.append((path, chunk_indices))
        existing = list(self.existing_by_file.get(path, []))
        remaining = [
            chunk
            for chunk in existing
            if int(chunk.get("chunk_index")) not in set(chunk_indices)
        ]
        self.existing_by_file[path] = remaining
        return len(chunk_indices)

    def upsert_chunks(self, chunks):
        if self.fail_upsert:
            return 0
        self.upserts.append(list(chunks))
        grouped = {}
        for chunk in chunks:
            grouped.setdefault(chunk["file_id"], []).append(
                {
                    "chunk_index": chunk["chunk_index"],
                    "chunk_hash": chunk["chunk_hash"],
                }
            )
        self.existing_by_file.update(grouped)
        return len(chunks)

    def build_fts_index(self):
        self.fts_rebuilds += 1


class FakeScrollClient:
    def __init__(self, batches):
        self.batches = list(batches)
        self.calls = []

    def scroll(self, **kwargs):
        self.calls.append(kwargs)
        if not self.batches:
            return [], None
        return self.batches.pop(0)


class RecordingChunker:
    def __init__(self, chunks_by_path):
        self.chunks_by_path = chunks_by_path
        self.seen = {}

    def chunk(self, content, path):
        self.seen[path] = content
        return list(self.chunks_by_path.get(path, []))


class ReindexReadinessTests(unittest.TestCase):
    def tearDown(self):
        embedder_module.reset_embedder_singleton()

    @staticmethod
    def _test_file_hash(path: Path) -> str:
        digest = hashlib.md5(usedforsecurity=False)
        digest.update(path.read_bytes())
        return digest.hexdigest()

    def _freshness_record_for_path(self, path: Path, index_path: str) -> dict:
        stat = path.stat()
        content_hash = self._test_file_hash(path)
        return {
            "path": index_path,
            "full_path": str(path),
            "size": stat.st_size,
            "mtime": stat.st_mtime,
            "content_hash": content_hash,
            "source_size": stat.st_size,
            "source_mtime": stat.st_mtime,
            "source_content_hash": content_hash,
            "content_summary": path.read_text(encoding="utf-8"),
            "category": "documentation",
            "ext": ".md",
            "chunk_count": 1,
        }

    @staticmethod
    def _freshness_engine(records: list[dict]) -> SearchEngine:
        engine = SearchEngine.__new__(SearchEngine)
        engine.catalog = RecordingCatalog(records)
        engine.vector_store = None
        engine._vector_store_error = RuntimeError("vector disabled for unit test")
        engine.bm25 = None
        engine._embedder = None
        engine.do_reranking = False
        engine._reranker_model = None
        return engine

    @staticmethod
    def _freshness_engine_for_catalog(catalog: Catalog) -> SearchEngine:
        engine = SearchEngine.__new__(SearchEngine)
        engine.catalog = catalog
        engine.vector_store = None
        engine._vector_store_error = RuntimeError("vector disabled for fixture test")
        engine.bm25 = None
        engine._embedder = None
        engine.do_reranking = False
        engine._reranker_model = None
        return engine

    def test_catalog_keeps_longer_content_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "catalog.db"
            catalog = Catalog(db_path=db_path)
            catalog.init_db()

            long_summary = "A" * 1200
            catalog.upsert_file(
                path="docs/plan.md",
                full_path="C:/tmp/docs/plan.md",
                size=1200,
                mtime=1.0,
                content_hash="hash-1",
                ext=".md",
                content_summary=long_summary,
            )
            catalog.conn.commit()

            record = catalog.get_file("docs/plan.md")
            self.assertEqual(len(record["content_summary"]), len(long_summary))
            self.assertEqual(record["source_mtime"], 1.0)
            self.assertEqual(record["source_size"], 1200)
            self.assertEqual(record["source_content_hash"], "hash-1")
            self.assertEqual(
                json.loads(record["source_metadata"]),
                {
                    "source_mtime": 1.0,
                    "source_size": 1200,
                    "source_content_hash": "hash-1",
                },
            )

            updated_summary = "B" * 900
            catalog.update_content_summary("docs/plan.md", updated_summary)
            catalog.conn.commit()
            record = catalog.get_file("docs/plan.md")
            self.assertEqual(record["content_summary"], updated_summary)

            catalog.close()

    def test_search_fresh_file_result_is_returned(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "source.md"
            source.write_text("fresh source content", encoding="utf-8")
            engine = self._freshness_engine(
                [self._freshness_record_for_path(source, "docs/source.md")]
            )

            results = engine.search("source.md", top_k=1)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].file_path, "docs/source.md")
        self.assertEqual(results[0].freshness_status, "fresh")

    def test_exact_path_result_matches_direct_file_fixture_before_filename_peer(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            target = tmp / "docs" / "phase211-target.md"
            filename_peer = tmp / "archive" / "phase211-target.md"
            target.parent.mkdir(parents=True)
            filename_peer.parent.mkdir(parents=True)
            target.write_text(
                "phase 211 exact target direct filesystem evidence\n"
                "unique-direct-token-211\n",
                encoding="utf-8",
            )
            filename_peer.write_text(
                "phase 211 filename peer should rank after exact path\n",
                encoding="utf-8",
            )
            target_record = self._freshness_record_for_path(
                target, "docs/phase211-target.md"
            )
            target_record["chunk_count"] = 0
            peer_record = self._freshness_record_for_path(
                filename_peer, "archive/phase211-target.md"
            )
            peer_record["chunk_count"] = 3
            engine = self._freshness_engine([peer_record, target_record])
            expected_source_path = str(target)
            expected_hash = self._test_file_hash(target)

            results = engine.search(
                "noisy operator words compare docs/phase211-target.md to disk",
                top_k=2,
            )

        self.assertEqual(
            [result.file_path for result in results],
            ["docs/phase211-target.md", "archive/phase211-target.md"],
        )
        self.assertEqual(results[0].freshness_status, "fresh")
        self.assertIn(
            "unique-direct-token-211",
            results[0].snippet,
        )
        self.assertEqual(
            results[0].freshness_evidence["source_path"],
            expected_source_path,
        )
        self.assertEqual(
            results[0].freshness_evidence["source_content_hash"],
            expected_hash,
        )
        self.assertEqual(
            results[0].freshness_evidence["current_content_hash"],
            expected_hash,
        )

    def test_exact_path_stays_first_and_top_k_limits_fake_vector_bm25_peers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            target = tmp / "docs" / "phase211-deterministic-target.md"
            vector_only_peer = tmp / "peers" / "phase211-vector-only-peer.md"
            vector_bm25_peer = tmp / "peers" / "phase211-vector-bm25-peer.md"
            bm25_only_peer = tmp / "peers" / "phase211-bm25-only-peer.md"
            for fixture_path in (
                target,
                vector_only_peer,
                vector_bm25_peer,
                bm25_only_peer,
            ):
                fixture_path.parent.mkdir(parents=True, exist_ok=True)

            target.write_text(
                "phase 211 deterministic exact path direct evidence\n",
                encoding="utf-8",
            )
            vector_only_peer.write_text(
                "phase 211 vector-only peer should not displace exact path\n",
                encoding="utf-8",
            )
            vector_bm25_peer.write_text(
                "phase 211 fake vector and bm25 peer should be the one peer kept\n",
                encoding="utf-8",
            )
            bm25_only_peer.write_text(
                "phase 211 bm25-only peer should be trimmed by top k\n",
                encoding="utf-8",
            )

            target_record = self._freshness_record_for_path(
                target, "docs/phase211-deterministic-target.md"
            )
            target_record["chunk_count"] = 0
            vector_only_record = self._freshness_record_for_path(
                vector_only_peer, "docs/phase211-vector-only-peer.md"
            )
            vector_bm25_record = self._freshness_record_for_path(
                vector_bm25_peer, "docs/phase211-vector-bm25-peer.md"
            )
            bm25_only_record = self._freshness_record_for_path(
                bm25_only_peer, "docs/phase211-bm25-only-peer.md"
            )
            engine = self._freshness_engine(
                [
                    vector_only_record,
                    vector_bm25_record,
                    bm25_only_record,
                    target_record,
                ]
            )
            fake_vector = FakeHybridVectorStore(
                [
                    {
                        "file_id": "docs/phase211-vector-only-peer.md",
                        "chunk_index": 0,
                        "_relevance_score": 0.99,
                        "content": vector_only_record["content_summary"],
                        "category": "documentation",
                        "file_type": ".md",
                        "mtime": vector_only_record["source_mtime"],
                    },
                    {
                        "file_id": "docs/phase211-vector-bm25-peer.md",
                        "chunk_index": 0,
                        "_relevance_score": 0.98,
                        "content": vector_bm25_record["content_summary"],
                        "category": "documentation",
                        "file_type": ".md",
                        "mtime": vector_bm25_record["source_mtime"],
                    },
                ]
            )
            engine.vector_store = fake_vector
            engine._vector_store_error = None
            engine._embedder = FakeEmbedder()
            fake_bm25 = FakeSearchBM25(
                [
                    ("docs/phase211-vector-bm25-peer.md::chunk_0", 12.0),
                    ("docs/phase211-bm25-only-peer.md::chunk_0", 11.0),
                ]
            )
            engine.bm25 = fake_bm25
            expected_source_paths = {
                "docs/phase211-deterministic-target.md": str(target),
                "docs/phase211-vector-bm25-peer.md": str(vector_bm25_peer),
            }
            expected_hashes = {
                "docs/phase211-deterministic-target.md": self._test_file_hash(target),
                "docs/phase211-vector-bm25-peer.md": self._test_file_hash(
                    vector_bm25_peer
                ),
            }

            results = engine.search(
                "compare docs/phase211-deterministic-target.md with fake peers",
                top_k=2,
            )

        self.assertEqual(
            [result.file_path for result in results],
            [
                "docs/phase211-deterministic-target.md",
                "docs/phase211-vector-bm25-peer.md",
            ],
        )
        self.assertEqual(len(results), 2)
        self.assertEqual(fake_vector.calls[0]["top_k"], 2)
        self.assertEqual(fake_bm25.calls[0]["top_k"], 4)
        self.assertEqual(
            fake_bm25.calls[0]["query"],
            "compare docs/phase211-deterministic-target.md with fake peers",
        )
        self.assertEqual(
            fake_vector.calls[0]["query"],
            "compare docs/phase211-deterministic-target.md with fake peers",
        )
        for result in results:
            self.assertEqual(result.freshness_status, "fresh")
            evidence = result.freshness_evidence
            self.assertEqual(evidence["source_path"], expected_source_paths[result.file_path])
            self.assertEqual(
                evidence["source_content_hash"],
                expected_hashes[result.file_path],
            )
            self.assertEqual(
                evidence["current_content_hash"],
                expected_hashes[result.file_path],
            )

    def test_exact_path_stays_first_when_reranker_prefers_peer(self):
        class PeerPreferringReranker:
            def __init__(self):
                self.pairs = []
                self.scores = []
                self.normalize = None

            def compute_score(self, pairs, normalize=True):
                self.pairs = list(pairs)
                self.normalize = normalize
                self.scores = []
                for _, snippet in pairs:
                    if "reranker-preferred-peer-token-211" in snippet:
                        self.scores.append(0.99)
                    elif "exact-direct-rerank-token-211" in snippet:
                        self.scores.append(0.01)
                    else:
                        self.scores.append(0.5)
                return list(self.scores)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            target = tmp / "docs" / "phase211-rerank-target.md"
            peer = tmp / "peers" / "phase211-rerank-peer.md"
            for fixture_path in (target, peer):
                fixture_path.parent.mkdir(parents=True, exist_ok=True)

            target.write_text(
                "phase 211 exact path direct file evidence\n"
                "exact-direct-rerank-token-211\n",
                encoding="utf-8",
            )
            peer.write_text(
                "phase 211 fake vector and bm25 peer\n"
                "reranker-preferred-peer-token-211\n",
                encoding="utf-8",
            )

            target_record = self._freshness_record_for_path(
                target, "docs/phase211-rerank-target.md"
            )
            target_record["chunk_count"] = 0
            peer_record = self._freshness_record_for_path(
                peer, "docs/phase211-rerank-peer.md"
            )
            peer_record["chunk_count"] = 4
            engine = self._freshness_engine([peer_record, target_record])
            fake_vector = FakeHybridVectorStore(
                [
                    {
                        "file_id": "docs/phase211-rerank-peer.md",
                        "chunk_index": 0,
                        "_relevance_score": 0.99,
                        "content": peer_record["content_summary"],
                        "category": "documentation",
                        "file_type": ".md",
                        "mtime": peer_record["source_mtime"],
                    },
                    {
                        "file_id": "docs/phase211-rerank-target.md",
                        "chunk_index": 0,
                        "_relevance_score": 0.50,
                        "content": target_record["content_summary"],
                        "category": "documentation",
                        "file_type": ".md",
                        "mtime": target_record["source_mtime"],
                    },
                ]
            )
            engine.vector_store = fake_vector
            engine._vector_store_error = None
            engine._embedder = FakeEmbedder()
            fake_bm25 = FakeSearchBM25(
                [
                    ("docs/phase211-rerank-peer.md::chunk_0", 12.0),
                    ("docs/phase211-rerank-target.md::chunk_0", 1.0),
                ]
            )
            engine.bm25 = fake_bm25
            reranker = PeerPreferringReranker()
            engine.do_reranking = True
            engine._reranker_model = reranker
            expected_source_path = str(target)
            expected_hash = self._test_file_hash(target)

            results = engine.search(
                "compare docs/phase211-rerank-target.md against peer evidence",
                top_k=2,
            )

        self.assertEqual(
            [result.file_path for result in results],
            [
                "docs/phase211-rerank-target.md",
                "docs/phase211-rerank-peer.md",
            ],
        )
        self.assertEqual(results[0].chunk_index, -1)
        self.assertEqual(results[0].freshness_status, "fresh")
        self.assertIn("exact-direct-rerank-token-211", results[0].snippet)
        self.assertEqual(
            results[0].freshness_evidence["source_path"],
            expected_source_path,
        )
        self.assertEqual(
            results[0].freshness_evidence["source_content_hash"],
            expected_hash,
        )
        self.assertEqual(
            results[0].freshness_evidence["current_content_hash"],
            expected_hash,
        )
        self.assertEqual(fake_vector.calls[0]["top_k"], 4)
        self.assertEqual(fake_bm25.calls[0]["top_k"], 4)
        self.assertTrue(reranker.pairs)
        self.assertTrue(reranker.normalize)
        peer_scores = [
            score
            for (_, snippet), score in zip(reranker.pairs, reranker.scores)
            if "reranker-preferred-peer-token-211" in snippet
        ]
        target_scores = [
            score
            for (_, snippet), score in zip(reranker.pairs, reranker.scores)
            if "exact-direct-rerank-token-211" in snippet
        ]
        self.assertEqual(peer_scores, [0.99])
        self.assertEqual(target_scores, [0.01])
        self.assertGreater(peer_scores[0], target_scores[0])

    def test_noisy_backslash_exact_path_short_circuits_fuzzy_peers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            target = tmp / "docs" / "phase211-backslash-target.md"
            peer = tmp / "archive" / "phase211-backslash-target.md"
            for fixture_path in (target, peer):
                fixture_path.parent.mkdir(parents=True, exist_ok=True)

            target.write_text(
                "phase 211 noisy backslash exact path direct evidence\n"
                "unique-backslash-direct-token-211\n",
                encoding="utf-8",
            )
            peer.write_text(
                "phase 211 same basename peer with more chunks\n"
                "backslash-peer-token-211\n",
                encoding="utf-8",
            )

            target_record = self._freshness_record_for_path(
                target, "docs/phase211-backslash-target.md"
            )
            target_record["chunk_count"] = 0
            peer_record = self._freshness_record_for_path(
                peer, "archive/phase211-backslash-target.md"
            )
            peer_record["chunk_count"] = 9
            engine = self._freshness_engine([peer_record, target_record])
            fake_vector = FakeHybridVectorStore(
                [
                    {
                        "file_id": "archive/phase211-backslash-target.md",
                        "chunk_index": 0,
                        "_relevance_score": 0.99,
                        "content": peer_record["content_summary"],
                        "category": "documentation",
                        "file_type": ".md",
                        "mtime": peer_record["source_mtime"],
                    }
                ]
            )
            engine.vector_store = fake_vector
            engine._vector_store_error = None
            engine._embedder = FakeEmbedder()
            fake_bm25 = FakeSearchBM25(
                [("archive/phase211-backslash-target.md::chunk_0", 99.0)]
            )
            engine.bm25 = fake_bm25
            expected_source_path = str(target)
            expected_hash = self._test_file_hash(target)

            results = engine.search(
                "noisy prose inspect Windows path "
                "docs\\phase211-backslash-target.md before fuzzy peers",
                top_k=2,
            )

        self.assertEqual(
            [result.file_path for result in results],
            [
                "docs/phase211-backslash-target.md",
                "archive/phase211-backslash-target.md",
            ],
        )
        self.assertEqual(results[0].chunk_index, -1)
        self.assertEqual(results[0].freshness_status, "fresh")
        self.assertIn("unique-backslash-direct-token-211", results[0].snippet)
        self.assertEqual(
            results[0].freshness_evidence["source_path"],
            expected_source_path,
        )
        self.assertEqual(
            results[0].freshness_evidence["source_content_hash"],
            expected_hash,
        )
        self.assertEqual(
            results[0].freshness_evidence["current_content_hash"],
            expected_hash,
        )
        self.assertEqual(fake_vector.calls, [])
        self.assertEqual(fake_bm25.calls, [])

    def test_noisy_absolute_windows_full_path_short_circuits_fuzzy_peers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            target = tmp / "docs" / "phase211-absolute-target.md"
            peer = tmp / "archive" / "phase211-absolute-target.md"
            for fixture_path in (target, peer):
                fixture_path.parent.mkdir(parents=True, exist_ok=True)

            target.write_text(
                "phase 211 absolute Windows full path direct evidence\n"
                "unique-absolute-direct-token-211\n",
                encoding="utf-8",
            )
            peer.write_text(
                "phase 211 same basename absolute-path fuzzy peer\n"
                "absolute-peer-token-211\n",
                encoding="utf-8",
            )

            target_record = self._freshness_record_for_path(
                target, "docs/phase211-absolute-target.md"
            )
            target_record["chunk_count"] = 0
            peer_record = self._freshness_record_for_path(
                peer, "archive/phase211-absolute-target.md"
            )
            peer_record["chunk_count"] = 9
            engine = self._freshness_engine([peer_record, target_record])
            fake_vector = FakeHybridVectorStore(
                [
                    {
                        "file_id": "archive/phase211-absolute-target.md",
                        "chunk_index": 0,
                        "_relevance_score": 0.99,
                        "content": peer_record["content_summary"],
                        "category": "documentation",
                        "file_type": ".md",
                        "mtime": peer_record["source_mtime"],
                    }
                ]
            )
            engine.vector_store = fake_vector
            engine._vector_store_error = None
            engine._embedder = FakeEmbedder()
            fake_bm25 = FakeSearchBM25(
                [("archive/phase211-absolute-target.md::chunk_0", 99.0)]
            )
            engine.bm25 = fake_bm25
            expected_source_path = str(target)
            expected_hash = self._test_file_hash(target)
            windows_full_path_token = str(target).replace("/", "\\")

            results = engine.search(
                f"noisy prose inspect direct file {windows_full_path_token} "
                "before same-basename fuzzy peers",
                top_k=2,
            )

        self.assertEqual(
            [result.file_path for result in results],
            [
                "docs/phase211-absolute-target.md",
                "archive/phase211-absolute-target.md",
            ],
        )
        self.assertEqual(results[0].chunk_index, -1)
        self.assertEqual(results[0].freshness_status, "fresh")
        self.assertIn("unique-absolute-direct-token-211", results[0].snippet)
        self.assertEqual(
            results[0].freshness_evidence["source_path"],
            expected_source_path,
        )
        self.assertEqual(
            results[0].freshness_evidence["source_content_hash"],
            expected_hash,
        )
        self.assertEqual(
            results[0].freshness_evidence["current_content_hash"],
            expected_hash,
        )
        self.assertEqual(fake_vector.calls, [])
        self.assertEqual(fake_bm25.calls, [])

    def test_quoted_spaced_absolute_windows_full_path_short_circuits_fuzzy_peers(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            target = (
                tmp
                / "docs with spaces"
                / "phase211 spaced target.md"
            )
            peer = tmp / "archive" / "phase211 spaced target.md"
            for fixture_path in (target, peer):
                fixture_path.parent.mkdir(parents=True, exist_ok=True)

            target.write_text(
                "phase 211 quoted spaced full path direct evidence\n"
                "unique-quoted-spaced-direct-token-211\n",
                encoding="utf-8",
            )
            peer.write_text(
                "phase 211 same basename spaced fuzzy peer\n"
                "quoted-spaced-peer-token-211\n",
                encoding="utf-8",
            )

            target_record = self._freshness_record_for_path(
                target, "docs with spaces/phase211 spaced target.md"
            )
            target_record["chunk_count"] = 0
            peer_record = self._freshness_record_for_path(
                peer, "archive/phase211 spaced target.md"
            )
            peer_record["chunk_count"] = 9
            engine = self._freshness_engine([peer_record, target_record])
            fake_vector = FakeHybridVectorStore(
                [
                    {
                        "file_id": "archive/phase211 spaced target.md",
                        "chunk_index": 0,
                        "_relevance_score": 0.99,
                        "content": peer_record["content_summary"],
                        "category": "documentation",
                        "file_type": ".md",
                        "mtime": peer_record["source_mtime"],
                    }
                ]
            )
            engine.vector_store = fake_vector
            engine._vector_store_error = None
            engine._embedder = FakeEmbedder()
            fake_bm25 = FakeSearchBM25(
                [("archive/phase211 spaced target.md::chunk_0", 99.0)]
            )
            engine.bm25 = fake_bm25
            expected_source_path = str(target)
            expected_hash = self._test_file_hash(target)
            windows_full_path_token = str(target).replace("/", "\\")

            results = engine.search(
                f'inspect "{windows_full_path_token}" before fuzzy peers',
                top_k=2,
            )

        self.assertEqual(
            [result.file_path for result in results],
            [
                "docs with spaces/phase211 spaced target.md",
                "archive/phase211 spaced target.md",
            ],
        )
        self.assertEqual(results[0].chunk_index, -1)
        self.assertEqual(results[0].freshness_status, "fresh")
        self.assertIn("unique-quoted-spaced-direct-token-211", results[0].snippet)
        self.assertEqual(
            results[0].freshness_evidence["source_path"],
            expected_source_path,
        )
        self.assertEqual(
            results[0].freshness_evidence["source_content_hash"],
            expected_hash,
        )
        self.assertEqual(
            results[0].freshness_evidence["current_content_hash"],
            expected_hash,
        )
        self.assertEqual(fake_vector.calls, [])
        self.assertEqual(fake_bm25.calls, [])

    def test_search_changed_file_result_is_marked_and_dropped_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "changed.md"
            source.write_text("original content", encoding="utf-8")
            engine = self._freshness_engine(
                [self._freshness_record_for_path(source, "docs/changed.md")]
            )
            source.write_text("changed content", encoding="utf-8")

            marked = engine.search("changed.md", top_k=1, include_stale=True)
            default_results = engine.search("changed.md", top_k=1)

        self.assertEqual(len(marked), 1)
        self.assertEqual(marked[0].freshness_status, "changed")
        self.assertEqual(default_results, [])

    def test_search_deleted_source_result_is_marked_and_dropped_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "deleted.md"
            source.write_text("content before deletion", encoding="utf-8")
            engine = self._freshness_engine(
                [self._freshness_record_for_path(source, "docs/deleted.md")]
            )
            source.unlink()

            marked = engine.search("deleted.md", top_k=1, include_stale=True)
            default_results = engine.search("deleted.md", top_k=1)

        self.assertEqual(len(marked), 1)
        self.assertEqual(marked[0].freshness_status, "deleted")
        self.assertEqual(default_results, [])

    def test_search_missing_catalog_metadata_is_marked_and_dropped_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "metadata.md"
            source.write_text("metadata missing", encoding="utf-8")
            engine = self._freshness_engine(
                [
                    {
                        "path": "docs/metadata.md",
                        "full_path": str(source),
                        "content_summary": "metadata missing",
                        "category": "documentation",
                        "ext": ".md",
                    }
                ]
            )

            marked = engine.search("metadata.md", top_k=1, include_stale=True)
            default_results = engine.search("metadata.md", top_k=1)

        self.assertEqual(len(marked), 1)
        self.assertEqual(marked[0].freshness_status, "missing_catalog")
        self.assertEqual(default_results, [])

    def test_search_stale_chunk_mtime_evidence_is_marked_and_dropped_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "stale.md"
            source.write_text("stale chunk mtime target", encoding="utf-8")
            record = self._freshness_record_for_path(source, "docs/stale.md")
            engine = self._freshness_engine([record])
            stale_result = SearchResult(
                file_path="docs/stale.md",
                snippet="stale chunk mtime target",
                mtime=record["source_mtime"] - 30.0,
            )

            marked = engine._apply_freshness_gate(
                [stale_result], include_stale=True
            )
            default_results = engine._apply_freshness_gate([stale_result])

        self.assertEqual(len(marked), 1)
        self.assertEqual(marked[0].freshness_status, "stale")
        self.assertEqual(default_results, [])

    def test_search_missing_chunk_evidence_is_marked_and_dropped_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "chunked.md"
            source.write_text("chunk count source still matches disk", encoding="utf-8")
            record = self._freshness_record_for_path(source, "docs/chunked.md")
            record["chunk_count"] = 1
            engine = self._freshness_engine([record])
            missing_chunk_result = SearchResult(
                file_path="docs/chunked.md",
                chunk_index=3,
                snippet="chunk count source still matches disk",
                mtime=record["source_mtime"],
            )

            marked = engine._apply_freshness_gate(
                [missing_chunk_result], include_stale=True
            )
            default_results = engine._apply_freshness_gate([missing_chunk_result])

        self.assertEqual(len(marked), 1)
        self.assertEqual(marked[0].freshness_status, "missing_chunk")
        self.assertEqual(marked[0].freshness_evidence["catalog_chunk_count"], 1)
        self.assertEqual(default_results, [])

    def test_search_unindexed_live_file_path_reports_degraded_miss(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "new_file_not_yet_indexed.md"
            source.write_text("new live file not yet indexed", encoding="utf-8")
            engine = self._freshness_engine([])

            results = engine.search(str(source), top_k=1)

        report = engine.last_report.to_dict()
        self.assertEqual(results, [])
        self.assertEqual(report["status"], "degraded")
        self.assertEqual(
            report["authority"], "degraded_filemind_output_not_source_truth"
        )
        self.assertEqual(report["miss_state"], "unindexed_live_file")
        self.assertIn("unindexed_live_file", report["degraded_reasons"])
        self.assertEqual(
            [path.casefold() for path in report["unindexed_live_file_paths"]],
            [str(source).casefold()],
        )
        self.assertTrue(report["partial"])

    def test_catalog_fts_freshness_gate_with_persisted_temp_catalog(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            source = tmp / "catalog_fts.md"
            source.write_text("freshnessneedle original source", encoding="utf-8")
            db_path = tmp / "catalog.db"
            catalog = Catalog(db_path=db_path)
            catalog.init_db()
            stat = source.stat()
            content_hash = self._test_file_hash(source)
            catalog.upsert_file(
                path="docs/catalog_fts.md",
                full_path=str(source),
                size=stat.st_size,
                mtime=stat.st_mtime,
                content_hash=content_hash,
                source_size=stat.st_size,
                source_mtime=stat.st_mtime,
                source_content_hash=content_hash,
                ext=".md",
                content_summary="freshnessneedle persisted catalog content",
                category="documentation",
                chunk_count=1,
            )
            catalog.conn.commit()
            engine = self._freshness_engine_for_catalog(catalog)

            fresh = engine.search("freshnessneedle", top_k=3)
            source.write_text("freshnessneedle mutated live source", encoding="utf-8")
            default_after_change = engine.search("freshnessneedle", top_k=3)
            stale_after_change = engine.search(
                "freshnessneedle", top_k=3, include_stale=True
            )

            catalog.close()

        self.assertEqual([result.file_path for result in fresh], ["docs/catalog_fts.md"])
        self.assertEqual(fresh[0].freshness_status, "fresh")
        self.assertEqual(default_after_change, [])
        self.assertEqual(
            [result.freshness_status for result in stale_after_change], ["changed"]
        )
        self.assertEqual(
            stale_after_change[0].freshness_evidence["catalog_path"],
            "docs/catalog_fts.md",
        )
        self.assertIn("current_content_hash", stale_after_change[0].freshness_evidence)

    def test_bm25_fusion_freshness_gate_labels_stale_fixture_results(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            fresh_source = tmp / "bm25_fresh.md"
            changed_source = tmp / "bm25_changed.md"
            fresh_source.write_text("bm25 fresh source", encoding="utf-8")
            changed_source.write_text("bm25 changed source before", encoding="utf-8")
            fresh_record = self._freshness_record_for_path(
                fresh_source, "docs/bm25_fresh.md"
            )
            changed_record = self._freshness_record_for_path(
                changed_source, "docs/bm25_changed.md"
            )
            changed_source.write_text("bm25 changed source after", encoding="utf-8")
            engine = self._freshness_engine([fresh_record, changed_record])
            engine.bm25 = FakeSearchBM25(
                [
                    ("docs/bm25_fresh.md::chunk_0", 4.0),
                    ("docs/bm25_changed.md::chunk_0", 3.5),
                ]
            )

            default_results = engine.search("bm25 fixture query", top_k=5)
            diagnostic_results = engine.search(
                "bm25 fixture query", top_k=5, include_stale=True
            )

        self.assertEqual(
            [result.file_path for result in default_results], ["docs/bm25_fresh.md"]
        )
        statuses = {
            result.file_path: result.freshness_status for result in diagnostic_results
        }
        self.assertEqual(statuses["docs/bm25_fresh.md"], "fresh")
        self.assertEqual(statuses["docs/bm25_changed.md"], "changed")
        changed_result = next(
            result
            for result in diagnostic_results
            if result.file_path == "docs/bm25_changed.md"
        )
        self.assertIn("current_content_hash", changed_result.freshness_evidence)

    def test_vector_hybrid_freshness_gate_labels_unfresh_fixture_results(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            changed_source = tmp / "vector_changed.md"
            deleted_source = tmp / "vector_deleted.md"
            missing_metadata_source = tmp / "vector_missing_metadata.md"
            changed_source.write_text("vector changed source before", encoding="utf-8")
            deleted_source.write_text("vector deleted source before", encoding="utf-8")
            missing_metadata_source.write_text(
                "vector missing metadata source", encoding="utf-8"
            )
            changed_record = self._freshness_record_for_path(
                changed_source, "docs/vector_changed.md"
            )
            deleted_record = self._freshness_record_for_path(
                deleted_source, "docs/vector_deleted.md"
            )
            missing_metadata_record = {
                "path": "docs/vector_missing_metadata.md",
                "full_path": str(missing_metadata_source),
                "content_summary": "vector missing metadata source",
                "category": "documentation",
                "ext": ".md",
            }
            changed_source.write_text("vector changed source after", encoding="utf-8")
            deleted_source.unlink()

            engine = self._freshness_engine(
                [changed_record, deleted_record, missing_metadata_record]
            )
            engine.vector_store = FakeHybridVectorStore(
                [
                    {
                        "file_id": "docs/vector_changed.md",
                        "chunk_index": 0,
                        "_relevance_score": 0.95,
                        "content": "vector changed source before",
                        "category": "documentation",
                        "file_type": ".md",
                        "mtime": changed_record["source_mtime"],
                    },
                    {
                        "file_id": "docs/vector_deleted.md",
                        "chunk_index": 0,
                        "_relevance_score": 0.9,
                        "content": "vector deleted source before",
                        "category": "documentation",
                        "file_type": ".md",
                        "mtime": deleted_record["source_mtime"],
                    },
                    {
                        "file_id": "docs/vector_missing_metadata.md",
                        "chunk_index": 0,
                        "_relevance_score": 0.85,
                        "content": "vector missing metadata source",
                        "category": "documentation",
                        "file_type": ".md",
                        "mtime": 0,
                    },
                ]
            )
            engine._vector_store_error = None
            engine._embedder = FakeEmbedder()

            default_results = engine.search("vector fixture query", top_k=5)
            diagnostic_results = engine.search(
                "vector fixture query", top_k=5, include_stale=True
            )

        self.assertEqual(default_results, [])
        statuses = {
            result.file_path: result.freshness_status for result in diagnostic_results
        }
        self.assertEqual(
            statuses,
            {
                "docs/vector_changed.md": "changed",
                "docs/vector_deleted.md": "deleted",
                "docs/vector_missing_metadata.md": "missing_catalog",
            },
        )
        self.assertEqual(
            set(statuses),
            {
                "docs/vector_changed.md",
                "docs/vector_deleted.md",
                "docs/vector_missing_metadata.md",
            },
        )

    def test_search_report_marks_vector_unavailable_fallback_as_degraded(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "source.md"
            source.write_text("fresh source content", encoding="utf-8")
            engine = self._freshness_engine(
                [self._freshness_record_for_path(source, "docs/source.md")]
            )
            engine._vector_store_error = RuntimeError("qdrant connection refused")

            results = engine.search("source.md related context", top_k=2)

        report = engine.last_report.to_dict()
        self.assertEqual([result.file_path for result in results], ["docs/source.md"])
        self.assertEqual(report["status"], "degraded")
        self.assertEqual(
            report["authority"], "degraded_filemind_output_not_source_truth"
        )
        self.assertTrue(report["partial"])
        self.assertIn("vector_unavailable", report["degraded_reasons"])
        self.assertEqual(report["backend_status"]["vector"], "unavailable")
        self.assertIn("qdrant connection refused", report["backend_errors"]["vector"])

    def test_search_report_marks_unfresh_filtered_candidates_as_explicit_miss(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "changed.md"
            source.write_text("original content", encoding="utf-8")
            engine = self._freshness_engine(
                [self._freshness_record_for_path(source, "docs/changed.md")]
            )
            source.write_text("changed content", encoding="utf-8")

            results = engine.search("changed.md", top_k=1)

        report = engine.last_report.to_dict()
        self.assertEqual(results, [])
        self.assertEqual(report["status"], "degraded")
        self.assertEqual(report["miss_state"], "all_candidates_filtered")
        self.assertIn("unfresh_results_filtered", report["degraded_reasons"])
        self.assertEqual(report["filtered_freshness_counts"], {"changed": 1})
        self.assertTrue(report["partial"])

    def test_search_report_marks_protected_or_excluded_path_results(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "token.env"
            source.write_text("SECRET_TOKEN=redacted-for-test", encoding="utf-8")
            engine = self._freshness_engine(
                [self._freshness_record_for_path(source, "secrets/token.env")]
            )

            results = engine.search("secrets/token.env", top_k=1)

        report = engine.last_report.to_dict()
        self.assertEqual([result.file_path for result in results], ["secrets/token.env"])
        self.assertTrue(results[0].is_protected)
        self.assertEqual(report["status"], "degraded")
        self.assertIn("protected_or_excluded_path", report["degraded_reasons"])
        self.assertGreaterEqual(report["protected_count"], 1)
        self.assertEqual(
            report["authority"], "degraded_filemind_output_not_source_truth"
        )

    def test_search_report_marks_zero_result_benchmark_miss_state(self):
        engine = self._freshness_engine([])
        engine.vector_store = FakeHybridVectorStore([])
        engine._vector_store_error = None
        engine._embedder = FakeEmbedder()

        results = engine.search("smoke benchmark nohit", top_k=1)

        report = engine.last_report.to_dict()
        self.assertEqual(results, [])
        self.assertEqual(report["status"], "empty")
        self.assertEqual(report["miss_state"], "benchmark_miss_or_no_results")
        self.assertEqual(report["authority"], "no_results_not_source_truth")
        self.assertIn("smoke/benchmark", report["warnings"][0])
        self.assertFalse(report["partial"])

    def test_make_index_path_namespaces_user_roots(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            ai_root = tmp / "AI_STATION"
            user_home = tmp / "user"
            claude_root = user_home / ".claude"
            target = claude_root / "settings.json"
            target.parent.mkdir(parents=True)
            target.write_text("{}", encoding="utf-8")

            scan_cfg = replace(
                config,
                ai_station_root=ai_root,
                user_home=user_home,
                scan_roots=[str(claude_root)],
            )
            scanner = FileScanner(config_obj=scan_cfg)

            self.assertEqual(
                scanner._make_index_path(str(target), claude_root),
                ".claude/settings.json",
            )

    def test_build_scan_roots_supports_full_override_for_scoped_runs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            root_a = tmp / "scope_a"
            root_b = tmp / "scope_b"
            root_a.mkdir()
            root_b.mkdir()

            with patch.dict(
                os.environ,
                {"FILEMIND_SCAN_ROOTS": os.pathsep.join([str(root_a), str(root_b)])},
                clear=False,
            ):
                roots = config_module._build_scan_roots()

            self.assertEqual(roots, [str(root_a.resolve()), str(root_b.resolve())])

    def test_qdrant_defaults_to_shared_http_even_when_legacy_flag_is_zero(self):
        with patch.dict(os.environ, {"AI_STATION_USE_SHARED_QDRANT": "0"}, clear=True):
            mode = config_module._build_qdrant_mode()
            url = config_module._build_qdrant_url(mode)

        self.assertEqual(mode, "http")
        self.assertEqual(url, "http://127.0.0.1:6333")

    def test_qdrant_local_mode_requires_explicit_filemind_mode(self):
        with patch.dict(os.environ, {"FILEMIND_QDRANT_MODE": "local"}, clear=True):
            mode = config_module._build_qdrant_mode()
            url = config_module._build_qdrant_url(mode)

        self.assertEqual(mode, "local")
        self.assertEqual(url, "")

    def test_experience_trace_raw_files_are_excluded_from_live_scan_scope(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "AI_STATION"
            raw_dir = workspace / "hub" / "memory" / "experience_traces" / "raw"
            raw_dir.mkdir(parents=True)
            (raw_dir / "trace.json").write_text("{}", encoding="utf-8")

            kept = workspace / "hub" / "memory" / "experience_traces" / "README.md"
            kept.write_text("experience trace docs", encoding="utf-8")

            scan_cfg = replace(
                config,
                ai_station_root=workspace,
                user_home=Path(tmpdir) / "user",
                scan_roots=[str(workspace)],
                skip_subdirs=set(config_module.SKIP_SUBDIRS),
                skip_file_patterns=set(),
                index_extensions={".json", ".md"},
            )
            scanner = FileScanner(config_obj=scan_cfg)

            paths, _ = verify_module.collect_indexable_disk_paths(
                roots=[str(workspace)],
                scanner=scanner,
            )

        self.assertIn("hub/memory/experience_traces/README.md", paths)
        self.assertNotIn("hub/memory/experience_traces/raw/trace.json", paths)

    def test_runtime_health_and_acceptance_artifacts_are_excluded_from_live_scan_scope(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "AI_STATION"
            noisy_files = [
                workspace / ".ai_station" / "lint-tools-312" / "pyvenv.cfg",
                workspace / ".kimi" / "batch1_contents.md",
                workspace
                / "hub"
                / "data"
                / "acceptance"
                / "task51"
                / "verify.stdout.log",
                workspace / "hub" / "data" / "hook-log" / "events.2026-04-25.jsonl",
                workspace
                / "hub"
                / "data"
                / "prompt-ledger"
                / "days"
                / "2026-04-25.jsonl",
                workspace
                / "hub"
                / "scripts"
                / ".runtime"
                / "hub-script-tools"
                / "pyvenv.cfg",
            ]
            for path in noisy_files:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("runtime artifact", encoding="utf-8")
            durable_doc = workspace / "hub" / "docs" / "ATLAS_E2E_ACCEPTANCE_RUNBOOK.md"
            durable_doc.parent.mkdir(parents=True, exist_ok=True)
            durable_doc.write_text("durable runbook", encoding="utf-8")

            scan_cfg = replace(
                config,
                ai_station_root=workspace,
                user_home=Path(tmpdir) / "user",
                scan_roots=[str(workspace)],
                skip_subdirs=set(config_module.SKIP_SUBDIRS),
                skip_file_patterns=set(config_module.SKIP_FILE_PATTERNS),
                index_extensions={".cfg", ".jsonl", ".log", ".md"},
            )
            scanner = FileScanner(config_obj=scan_cfg)

            paths, _ = verify_module.collect_indexable_disk_paths(
                roots=[str(workspace)],
                scanner=scanner,
            )

        self.assertEqual(paths, {"hub/docs/ATLAS_E2E_ACCEPTANCE_RUNBOOK.md"})

    def test_runtime_parser_accepts_runtime_command(self):
        parser = run_module.build_parser()
        args = parser.parse_args(["runtime"])
        self.assertEqual(args.command, "runtime")

    def test_classifier_can_skip_llm_for_deterministic_shadow_rebuilds(self):
        from filemind.classifier import Classifier

        classifier_config = SimpleNamespace(
            ollama_api_url="http://127.0.0.1:9",
            categories=["code", "documentation", "config", "unknown"],
            classification_batch_size=5,
            classification_confidence_threshold=0.6,
            classification_confidence_fallback_threshold=0.7,
            classification_model="unavailable",
            classification_llm_enabled=False,
            rule_based_fallback=True,
        )

        with patch("filemind.classifier.config", classifier_config):
            classifier = Classifier()
            with patch.object(
                classifier,
                "_classify_batch",
                side_effect=AssertionError("LLM should not be called"),
            ):
                results = classifier.classify(
                    [
                        {
                            "path": "logs/service.log",
                            "ext": ".log",
                            "content_summary": "runtime log",
                        },
                        {
                            "path": "docs/readme.md",
                            "ext": ".md",
                            "content_summary": "documentation",
                        },
                    ]
                )

        self.assertEqual(
            results,
            [
                {
                    "path": "docs/readme.md",
                    "category": "documentation",
                    "confidence": 0.9,
                },
                {"path": "logs/service.log", "category": "unknown", "confidence": 0.0},
            ],
        )

    def test_verify_parser_accepts_targeted_repair_flags(self):
        parser = run_module.build_parser()
        args = parser.parse_args(
            [
                "verify",
                "--repair-missing",
                "--repair-limit",
                "3",
                "--repair-chunk-counts",
            ]
        )

        self.assertEqual(args.command, "verify")
        self.assertTrue(args.repair_missing)
        self.assertEqual(args.repair_limit, 3)
        self.assertTrue(args.repair_chunk_counts)

    def test_verify_exits_nonzero_when_report_status_is_fail(self):
        fake_verify = SimpleNamespace(
            build_verification_report=MagicMock(return_value={"status": "FAIL"}),
            render_verification_report=MagicMock(return_value="Status: FAIL"),
            repair_catalog_chunk_counts_from_vectors=MagicMock(),
        )

        with patch.dict(sys.modules, {"verify": fake_verify}):
            with self.assertRaises(SystemExit) as raised:
                run_module.cmd_verify(SimpleNamespace(repair_missing=False))

        self.assertIn("verify failed", str(raised.exception))

    def test_verify_ok_status_keeps_existing_zero_exit_behavior(self):
        fake_verify = SimpleNamespace(
            build_verification_report=MagicMock(return_value={"status": "OK"}),
            render_verification_report=MagicMock(return_value="Status: OK"),
            repair_catalog_chunk_counts_from_vectors=MagicMock(),
        )

        with patch.dict(sys.modules, {"verify": fake_verify}):
            self.assertIsNone(
                run_module.cmd_verify(SimpleNamespace(repair_missing=False))
            )

    def test_embedding_runtime_status_reports_requested_and_actual_device(self):
        fake_embedder = SimpleNamespace(
            requested_device="cuda",
            device="cpu",
            get_device_info=lambda: "CPU",
        )
        fake_embedder_module = SimpleNamespace(get_embedder=lambda: fake_embedder)

        with patch.dict(sys.modules, {"embedder": fake_embedder_module}):
            status = run_module._get_embedding_runtime_status()

        self.assertEqual(status["status"], "error")
        self.assertEqual(status["backend"], config.embedding_backend)
        self.assertEqual(status["requested_device"], "cuda")
        self.assertEqual(status["device"], "CPU")
        self.assertIn("requested CUDA", status["message"])

    def test_ollama_runtime_status_reports_loaded_models(self):
        fake_result = SimpleNamespace(
            returncode=0,
            stdout=(
                "NAME    ID    SIZE    PROCESSOR    CONTEXT    UNTIL\n"
                "gemma3:4b  abc123  3.3 GB  100% GPU  5m\n"
            ),
            stderr="",
        )
        with patch.object(run_module.subprocess, "run", return_value=fake_result):
            status = run_module._get_ollama_runtime_status()

        self.assertEqual(status["status"], "ok")
        self.assertEqual(status["runtime"], "ollama")
        self.assertEqual(status["model"], config.classification_model)
        self.assertEqual(len(status["ps_output"]), 2)
        self.assertIn("100% GPU", status["ps_output"][1])

    def test_force_reindex_requires_shared_qdrant(self):
        orchestrator = NightlyOrchestrator.__new__(NightlyOrchestrator)
        orchestrator.vector_store = SimpleNamespace(connection_mode="local")

        with self.assertRaises(RuntimeError):
            orchestrator._ensure_force_reindex_target()

        orchestrator.vector_store = SimpleNamespace(connection_mode="http")
        orchestrator._ensure_force_reindex_target()

    def test_force_reindex_resets_collection_and_chunk_counts_before_rebuild(self):
        commit = MagicMock()
        orchestrator = NightlyOrchestrator.__new__(NightlyOrchestrator)
        orchestrator.vector_store = SimpleNamespace(
            connection_mode="http",
            reset_collection=MagicMock(),
        )
        orchestrator.catalog = SimpleNamespace(
            reset_all_chunk_counts=MagicMock(),
            conn=SimpleNamespace(commit=commit),
        )

        orchestrator._reset_force_reindex_target()

        orchestrator.vector_store.reset_collection.assert_called_once_with()
        orchestrator.catalog.reset_all_chunk_counts.assert_called_once_with()
        commit.assert_called_once_with()

    def test_phase_force_reindex_reextracts_from_source_and_skips_removed_paths(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "fresh.txt"
            source.write_text("fresh source text for rebuild", encoding="utf-8")

            catalog = RecordingCatalog(
                [
                    {
                        "path": "docs/fresh.txt",
                        "full_path": str(source),
                        "content_summary": "stale",
                        "category": "documentation",
                        "confidence": 0.75,
                        "ext": ".txt",
                        "mtime": 10.0,
                    },
                    {
                        "path": "docs/skip.txt",
                        "full_path": str(source),
                        "content_summary": "skip me",
                        "category": "documentation",
                        "confidence": 0.5,
                        "ext": ".txt",
                        "mtime": 10.0,
                    },
                ]
            )
            vector_store = RecordingVectorStore(
                {
                    "docs/fresh.txt": [{"chunk_index": 0, "chunk_hash": "old"}],
                    "docs/skip.txt": [{"chunk_index": 0, "chunk_hash": "skip"}],
                }
            )
            chunker = RecordingChunker(
                {
                    "docs/fresh.txt": [
                        FakeChunk(0, "hash-0", "fresh source"),
                        FakeChunk(1, "hash-1", "text for rebuild"),
                    ]
                }
            )

            orchestrator = NightlyOrchestrator.__new__(NightlyOrchestrator)
            orchestrator.catalog = catalog
            orchestrator.vector_store = vector_store
            orchestrator.chunker = chunker
            orchestrator.errors = []

            result = PipelineResult()

            with (
                patch("filemind.nightly.get_embedder", return_value=FakeEmbedder()),
                patch("filemind.bm25_index.BM25HybridIndex", FakeBM25),
            ):
                orchestrator._phase_force_reindex(
                    result,
                    classifications={},
                    skip_paths={"docs/skip.txt"},
                )

            self.assertEqual(
                chunker.seen["docs/fresh.txt"],
                "fresh source text for rebuild",
            )
            self.assertEqual(
                catalog.updated_summaries["docs/fresh.txt"],
                "fresh source text for rebuild",
            )
            self.assertNotIn("docs/skip.txt", chunker.seen)
            self.assertEqual(result.files_indexed, 1)
            self.assertEqual(result.chunks_created, 2)
            self.assertEqual(catalog.chunk_counts["docs/fresh.txt"], 2)
            self.assertEqual(len(vector_store.upserts), 1)

    def test_phase_embed_preserves_full_chunk_count_on_partial_update(self):
        catalog = RecordingCatalog()
        vector_store = RecordingVectorStore(
            {
                "docs/guide.md": [
                    {"chunk_index": 0, "chunk_hash": "same"},
                    {"chunk_index": 1, "chunk_hash": "old"},
                ]
            }
        )
        chunker = RecordingChunker(
            {
                "docs/guide.md": [
                    FakeChunk(0, "same", "unchanged"),
                    FakeChunk(1, "new", "updated"),
                ]
            }
        )

        orchestrator = NightlyOrchestrator.__new__(NightlyOrchestrator)
        orchestrator.catalog = catalog
        orchestrator.vector_store = vector_store
        orchestrator.chunker = chunker
        orchestrator.errors = []

        result = PipelineResult()
        file_data = [
            {
                "path": "docs/guide.md",
                "content_summary": "updated content",
                "ext": ".md",
                "mtime": 5.0,
            }
        ]
        classifications = {
            "docs/guide.md": {"category": "documentation", "confidence": 0.9}
        }

        with (
            patch("filemind.nightly.get_embedder", return_value=FakeEmbedder()),
            patch("filemind.bm25_index.BM25HybridIndex", FakeBM25),
        ):
            orchestrator._phase_embed(result, file_data, classifications)

        self.assertEqual(catalog.chunk_counts["docs/guide.md"], 2)
        self.assertEqual(result.files_indexed, 1)
        self.assertEqual(result.chunks_created, 1)
        self.assertEqual(len(vector_store.upserts), 1)
        self.assertEqual(len(vector_store.upserts[0]), 1)

    def test_phase_embed_deletes_stale_trailing_chunks_after_file_shrink(self):
        catalog = RecordingCatalog()
        vector_store = RecordingVectorStore(
            {
                "docs/shrink.md": [
                    {"chunk_index": 0, "chunk_hash": "same"},
                    {"chunk_index": 1, "chunk_hash": "old-tail"},
                    {"chunk_index": 2, "chunk_hash": "older-tail"},
                ]
            }
        )
        chunker = RecordingChunker(
            {
                "docs/shrink.md": [
                    FakeChunk(0, "same", "unchanged"),
                ]
            }
        )

        orchestrator = NightlyOrchestrator.__new__(NightlyOrchestrator)
        orchestrator.catalog = catalog
        orchestrator.vector_store = vector_store
        orchestrator.chunker = chunker
        orchestrator.errors = []

        result = PipelineResult()
        file_data = [
            {
                "path": "docs/shrink.md",
                "content_summary": "shorter content",
                "ext": ".md",
                "mtime": 6.0,
            }
        ]

        with (
            patch("filemind.nightly.get_embedder", return_value=FakeEmbedder()),
            patch("filemind.bm25_index.BM25HybridIndex", FakeBM25),
        ):
            orchestrator._phase_embed(result, file_data, classifications={})

        self.assertEqual(vector_store.file_chunk_deletes, [("docs/shrink.md", [1, 2])])
        self.assertEqual(
            vector_store.existing_by_file["docs/shrink.md"],
            [{"chunk_index": 0, "chunk_hash": "same"}],
        )
        self.assertEqual(catalog.chunk_counts["docs/shrink.md"], 1)
        self.assertEqual(result.errors, 0)

    def test_phase_embed_does_not_update_catalog_when_vector_upsert_fails(self):
        catalog = RecordingCatalog()
        vector_store = RecordingVectorStore(fail_upsert=True)
        chunker = RecordingChunker(
            {
                "docs/fail.md": [
                    FakeChunk(0, "new", "new content"),
                ]
            }
        )

        orchestrator = NightlyOrchestrator.__new__(NightlyOrchestrator)
        orchestrator.catalog = catalog
        orchestrator.vector_store = vector_store
        orchestrator.chunker = chunker
        orchestrator.errors = []

        result = PipelineResult()
        file_data = [
            {
                "path": "docs/fail.md",
                "content_summary": "new content",
                "ext": ".md",
                "mtime": 7.0,
            }
        ]

        with (
            patch("filemind.nightly.get_embedder", return_value=FakeEmbedder()),
            patch("filemind.bm25_index.BM25HybridIndex", FakeBM25),
        ):
            orchestrator._phase_embed(
                result,
                file_data,
                classifications={
                    "docs/fail.md": {"category": "documentation", "confidence": 0.9}
                },
            )

        self.assertEqual(catalog.chunk_counts, {})
        self.assertEqual(catalog.updated_categories, [])
        self.assertEqual(result.errors, 1)
        self.assertIn("Vector upsert error", orchestrator.errors[0])

    def test_phase_embed_does_not_update_catalog_when_stale_delete_fails(self):
        catalog = RecordingCatalog()
        vector_store = RecordingVectorStore(
            {
                "docs/delete-fail.md": [
                    {"chunk_index": 0, "chunk_hash": "same"},
                    {"chunk_index": 1, "chunk_hash": "old-tail"},
                ]
            },
            fail_delete=True,
        )
        chunker = RecordingChunker(
            {
                "docs/delete-fail.md": [
                    FakeChunk(0, "same", "unchanged"),
                ]
            }
        )

        orchestrator = NightlyOrchestrator.__new__(NightlyOrchestrator)
        orchestrator.catalog = catalog
        orchestrator.vector_store = vector_store
        orchestrator.chunker = chunker
        orchestrator.errors = []

        result = PipelineResult()
        file_data = [
            {
                "path": "docs/delete-fail.md",
                "content_summary": "shorter content",
                "ext": ".md",
                "mtime": 8.0,
            }
        ]

        with (
            patch("filemind.nightly.get_embedder", return_value=FakeEmbedder()),
            patch("filemind.bm25_index.BM25HybridIndex", FakeBM25),
        ):
            orchestrator._phase_embed(result, file_data, classifications={})

        self.assertEqual(catalog.chunk_counts, {})
        self.assertEqual(result.errors, 1)
        self.assertIn("Vector delete error", orchestrator.errors[0])

    def test_phase_embed_does_not_update_catalog_when_existing_chunk_read_fails(self):
        catalog = RecordingCatalog()
        vector_store = RecordingVectorStore(fail_get=True)
        chunker = RecordingChunker(
            {
                "docs/read-fail.md": [
                    FakeChunk(0, "new", "new content"),
                ]
            }
        )

        orchestrator = NightlyOrchestrator.__new__(NightlyOrchestrator)
        orchestrator.catalog = catalog
        orchestrator.vector_store = vector_store
        orchestrator.chunker = chunker
        orchestrator.errors = []

        result = PipelineResult()
        file_data = [
            {
                "path": "docs/read-fail.md",
                "content_summary": "new content",
                "ext": ".md",
                "mtime": 9.0,
            }
        ]

        with (
            patch("filemind.nightly.get_embedder", return_value=FakeEmbedder()),
            patch("filemind.bm25_index.BM25HybridIndex", FakeBM25),
        ):
            orchestrator._phase_embed(result, file_data, classifications={})

        self.assertEqual(catalog.chunk_counts, {})
        self.assertEqual(vector_store.upserts, [])
        self.assertEqual(result.errors, 1)
        self.assertIn("Embed error: docs/read-fail.md", orchestrator.errors[0])

    def test_phase_embed_batches_changed_chunks_across_files(self):
        catalog = RecordingCatalog()
        vector_store = RecordingVectorStore()
        chunker = RecordingChunker(
            {
                "docs/a.md": [
                    FakeChunk(0, "a-0", "alpha"),
                    FakeChunk(1, "a-1", "bravo"),
                ],
                "docs/b.md": [
                    FakeChunk(0, "b-0", "charlie"),
                ],
            }
        )

        orchestrator = NightlyOrchestrator.__new__(NightlyOrchestrator)
        orchestrator.catalog = catalog
        orchestrator.vector_store = vector_store
        orchestrator.chunker = chunker
        orchestrator.errors = []

        result = PipelineResult()
        file_data = [
            {
                "path": "docs/a.md",
                "content_summary": "alpha bravo",
                "ext": ".md",
                "mtime": 1.0,
            },
            {
                "path": "docs/b.md",
                "content_summary": "charlie",
                "ext": ".md",
                "mtime": 2.0,
            },
        ]
        classifications = {
            "docs/a.md": {"category": "documentation", "confidence": 0.9},
            "docs/b.md": {"category": "documentation", "confidence": 0.8},
        }

        recording_embedder = MagicMock()
        recording_embedder.encode.return_value = {
            "dense_vecs": [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]],
            "lexical_weights": [{"a": 1.0}, {"b": 1.0}, {"c": 1.0}],
        }

        with (
            patch("filemind.nightly.get_embedder", return_value=recording_embedder),
            patch("filemind.bm25_index.BM25HybridIndex", FakeBM25),
        ):
            orchestrator._phase_embed(result, file_data, classifications)

        recording_embedder.encode.assert_called_once_with(
            ["alpha", "bravo", "charlie"],
            return_dense=True,
            return_sparse=True,
        )
        self.assertEqual(result.files_indexed, 2)
        self.assertEqual(result.chunks_created, 3)
        self.assertEqual(catalog.chunk_counts["docs/a.md"], 2)
        self.assertEqual(catalog.chunk_counts["docs/b.md"], 1)
        self.assertEqual(len(vector_store.upserts), 1)
        self.assertEqual(len(vector_store.upserts[0]), 3)

    def test_repair_missing_index_entries_targets_verify_missing_paths_without_scan(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "AI_STATION"
            source = workspace / "docs" / "repair.txt"
            source.parent.mkdir(parents=True)
            source.write_text("alpha bravo repair target", encoding="utf-8")

            scan_cfg = replace(
                config,
                ai_station_root=workspace,
                user_home=Path(tmpdir) / "user",
                scan_roots=[str(workspace)],
                skip_dirs=set(),
                skip_subdirs=set(),
                skip_file_patterns=set(),
                index_extensions={".txt"},
            )
            scanner = FileScanner(config_obj=scan_cfg)
            scanner.scan = MagicMock(
                side_effect=AssertionError("full scan must not run")
            )

            catalog = RecordingCatalog()
            vector_store = RecordingVectorStore()
            chunker = RecordingChunker(
                {
                    "docs/repair.txt": [
                        FakeChunk(0, "repair-0", "alpha bravo"),
                        FakeChunk(1, "repair-1", "repair target"),
                    ]
                }
            )

            orchestrator = NightlyOrchestrator.__new__(NightlyOrchestrator)
            orchestrator.catalog = catalog
            orchestrator.vector_store = vector_store
            orchestrator.scanner = scanner
            orchestrator.chunker = chunker
            orchestrator.errors = []

            fake_classifier = SimpleNamespace(
                classify=lambda file_data: [
                    {
                        "path": fd["path"],
                        "category": "documentation",
                        "confidence": 0.9,
                    }
                    for fd in file_data
                ]
            )

            with (
                patch(
                    "filemind.nightly.extract_content",
                    return_value="alpha bravo repair target",
                ),
                patch("filemind.nightly.Classifier", return_value=fake_classifier),
                patch("filemind.nightly.get_embedder", return_value=FakeEmbedder()),
                patch("filemind.bm25_index.BM25HybridIndex", FakeBM25),
                patch.object(orchestrator, "_rebuild_bm25_index") as rebuild_bm25,
            ):
                result = orchestrator.repair_missing_index_entries(
                    ["docs/repair.txt"],
                    max_files=3,
                )

            scanner.scan.assert_not_called()
            self.assertTrue(result.success)
            self.assertEqual(result.files_scanned, 1)
            self.assertEqual(result.files_new, 1)
            self.assertEqual(result.files_indexed, 1)
            self.assertEqual(result.chunks_created, 2)
            self.assertEqual(catalog.upserts[0]["path"], "docs/repair.txt")
            self.assertEqual(catalog.chunk_counts["docs/repair.txt"], 2)
            self.assertEqual(vector_store.fts_rebuilds, 1)
            rebuild_bm25.assert_called_once_with()

    def test_repair_missing_index_entries_refuses_large_drift_sets(self):
        orchestrator = NightlyOrchestrator.__new__(NightlyOrchestrator)
        orchestrator.catalog = RecordingCatalog()
        orchestrator.vector_store = RecordingVectorStore()
        orchestrator.scanner = SimpleNamespace(scan=MagicMock())
        orchestrator.errors = []

        result = orchestrator.repair_missing_index_entries(
            ["docs/a.txt", "docs/b.txt"],
            max_files=1,
        )

        self.assertFalse(result.success)
        self.assertEqual(result.errors, 1)
        self.assertIn("refused 2 missing files", result.error_messages[0])
        orchestrator.scanner.scan.assert_not_called()

    def test_embedder_uses_offline_huggingface_mode_when_model_is_cached(self):
        fake_model = object()
        observed_env = {}

        def _capture_ctor(*args, **kwargs):
            observed_env["HF_HUB_OFFLINE"] = os.environ.get("HF_HUB_OFFLINE")
            observed_env["TRANSFORMERS_OFFLINE"] = os.environ.get(
                "TRANSFORMERS_OFFLINE"
            )
            observed_env["HF_DATASETS_OFFLINE"] = os.environ.get("HF_DATASETS_OFFLINE")
            return fake_model

        fake_ctor = MagicMock(side_effect=_capture_ctor)

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("filemind.embedder._has_local_model_cache", return_value=True),
            patch("filemind.embedder._get_local_model_snapshot", return_value=None),
            patch.dict(
                sys.modules,
                {
                    "sentence_transformers": SimpleNamespace(
                        SentenceTransformer=fake_ctor
                    )
                },
            ),
        ):
            embedder = embedder_module.Embedder(device="cpu")
            model = embedder.model

        self.assertIs(model, fake_model)
        self.assertEqual(observed_env["HF_HUB_OFFLINE"], "1")
        self.assertEqual(observed_env["TRANSFORMERS_OFFLINE"], "1")
        self.assertEqual(observed_env["HF_DATASETS_OFFLINE"], "1")
        fake_ctor.assert_called_once_with(
            "BAAI/bge-m3",
            device="cpu",
            trust_remote_code=True,
            local_files_only=True,
        )

    def test_embedder_uses_cached_snapshot_path_in_offline_mode_when_available(self):
        fake_model = object()
        fake_snapshot = Path("C:/tmp/hf-cache/models--BAAI--bge-m3/snapshots/abc123")
        fake_ctor = MagicMock(return_value=fake_model)

        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "filemind.embedder._enable_huggingface_offline_mode",
                return_value=True,
            ),
            patch(
                "filemind.embedder._get_local_model_snapshot",
                return_value=fake_snapshot,
            ),
            patch.dict(
                sys.modules,
                {
                    "sentence_transformers": SimpleNamespace(
                        SentenceTransformer=fake_ctor
                    )
                },
            ),
        ):
            embedder = embedder_module.Embedder(device="cpu")
            model = embedder.model

        self.assertIs(model, fake_model)
        fake_ctor.assert_called_once_with(
            str(fake_snapshot),
            device="cpu",
            trust_remote_code=True,
            local_files_only=True,
        )

    def test_get_embedder_can_select_experimental_backend_without_changing_default(
        self,
    ):
        fake_experimental = object()

        with patch(
            "filemind.embedder._create_embedder",
            return_value=fake_experimental,
        ) as factory:
            embedder = embedder_module.get_embedder(
                device="cpu",
                backend="flagembedding_experimental",
            )

        self.assertIs(embedder, fake_experimental)
        factory.assert_called_once_with(
            backend="flagembedding_experimental",
            model_name="BAAI/bge-m3",
            device="cpu",
            batch_size=32,
        )

    def test_experimental_embedder_uses_cached_snapshot_path_in_offline_mode(self):
        fake_snapshot = Path("C:/tmp/hf-cache/models--BAAI--bge-m3/snapshots/abc123")
        init_calls = []

        class FakeBGEM3FlagModel:
            def __init__(self, model_name, use_fp16):
                init_calls.append((model_name, use_fp16))

        with (
            patch(
                "filemind.embedder_flagembedding_experimental._enable_huggingface_offline_mode",
                return_value=True,
            ),
            patch(
                "filemind.embedder_flagembedding_experimental._get_local_model_snapshot",
                return_value=fake_snapshot,
            ),
            patch.dict(
                sys.modules,
                {"FlagEmbedding": SimpleNamespace(BGEM3FlagModel=FakeBGEM3FlagModel)},
            ),
        ):
            embedder = FlagEmbeddingExperimentalEmbedder(device="cpu")
            _ = embedder.model

        self.assertEqual(init_calls, [(str(fake_snapshot), False)])

    def test_vector_store_accepts_integer_sparse_token_ids(self):
        store = VectorStore.__new__(VectorStore)
        sparse = store._parse_sparse({101: 0.5, "token": 0.25, 202: 0.0})
        self.assertEqual(sparse.indices[0], 101)
        self.assertEqual(sparse.values[0], 0.5)
        self.assertEqual(len(sparse.indices), 2)

    def test_vector_store_accepts_numeric_string_sparse_token_ids(self):
        store = VectorStore.__new__(VectorStore)
        sparse = store._parse_sparse({"11675": 0.5, "token": 0.25, "0": 0.1})
        self.assertEqual(sparse.indices[0], 11675)
        self.assertEqual(sparse.indices[2], 0)

    def test_rerank_supports_cross_encoder_compute_score_api(self):
        class ComputeScoreReranker:
            def compute_score(self, pairs, normalize=True):
                self.pairs = pairs
                self.normalize = normalize
                return [0.1, 0.9]

        engine = SearchEngine.__new__(SearchEngine)
        engine._reranker_model = ComputeScoreReranker()

        results = [
            SearchResult(file_path="docs/a.md", snippet="first"),
            SearchResult(file_path="docs/b.md", snippet="second"),
        ]

        reranked = engine._rerank("query", results, top_k=2)

        self.assertEqual([r.file_path for r in reranked], ["docs/b.md", "docs/a.md"])
        self.assertEqual(
            engine.reranker.pairs, [("query", "first"), ("query", "second")]
        )
        self.assertTrue(engine.reranker.normalize)

    def test_rerank_supports_cross_encoder_predict_api(self):
        class PredictReranker:
            def predict(self, pairs, show_progress_bar=False):
                self.pairs = pairs
                self.show_progress_bar = show_progress_bar
                return [0.2, 1.7]

        engine = SearchEngine.__new__(SearchEngine)
        engine._reranker_model = PredictReranker()

        results = [
            SearchResult(file_path="docs/a.md", snippet="first"),
            SearchResult(file_path="docs/b.md", snippet="second"),
        ]

        reranked = engine._rerank("query", results, top_k=2)

        self.assertEqual([r.file_path for r in reranked], ["docs/b.md", "docs/a.md"])
        self.assertEqual(
            engine.reranker.pairs, [("query", "first"), ("query", "second")]
        )
        self.assertFalse(engine.reranker.show_progress_bar)
        self.assertLessEqual(reranked[0].score, 1.0)

    def test_hybrid_search_passes_query_adaptive_semantic_weight_into_rrf(self):
        engine = SearchEngine.__new__(SearchEngine)
        engine.catalog = SimpleNamespace()
        engine.vector_store = SimpleNamespace(
            search_hybrid=lambda *args, **kwargs: [
                {
                    "file_id": "docs/guide.md",
                    "chunk_index": 0,
                    "_relevance_score": 0.9,
                    "content": "guide",
                    "category": "documentation",
                    "file_type": ".md",
                    "mtime": 1.0,
                }
            ]
        )
        engine.bm25 = SimpleNamespace(
            is_built=True,
            search=lambda query, top_k: [("docs/guide.md::chunk_0", 4.2)],
        )
        engine._embedder = SimpleNamespace(
            encode=lambda texts, return_dense=True, return_sparse=True: {
                "dense_vecs": [[0.1, 0.2]],
                "lexical_weights": [{}],
            }
        )
        engine.do_reranking = False
        engine._reranker_model = None

        with (
            patch.object(SearchEngine, "_detect_query_intent", return_value=3.0),
            patch.object(
                SearchEngine,
                "_rrf_fusion_3way",
                return_value=[],
            ) as fusion,
        ):
            results = engine.search("how do i rebuild the live index safely", top_k=5)

        self.assertEqual(results, [])
        self.assertEqual(fusion.call_count, 1)
        self.assertEqual(fusion.call_args.kwargs["semantic_weight"], 3.0)

    def test_verify_uses_effective_scan_scope_and_chunk_counts(self):
        catalog = RecordingCatalog(
            [
                {
                    "path": "docs/a.md",
                    "full_path": "C:/docs/a.md",
                    "content_summary": "alpha",
                    "chunk_count": 2,
                    "size": 100,
                },
                {
                    "path": "docs/b.md",
                    "full_path": "C:/docs/b.md",
                    "content_summary": "",
                    "chunk_count": 0,
                    "size": 120,
                },
                {
                    "path": "docs/skip.md",
                    "full_path": "C:/docs/skip.md",
                    "content_summary": "stale",
                    "chunk_count": 1,
                    "size": 140,
                },
            ]
        )
        fake_scanner = SimpleNamespace(
            _canonical_fs_path=lambda path: path.lower(),
            _evaluate_existing_path_scope=lambda path, size=0: (False, "file_rule"),
        )

        with (
            patch(
                "filemind.verify.collect_indexable_disk_paths",
                return_value=(
                    {"docs/a.md", "docs/b.md"},
                    {"c:/docs/a.md", "c:/docs/b.md"},
                ),
            ),
            patch(
                "filemind.verify.os.path.exists",
                side_effect=lambda path: path == "C:/docs/skip.md",
            ),
        ):
            report = verify_module.build_verification_report(
                catalog=catalog,
                scanner=fake_scanner,
                vector_chunk_count=3,
                vector_chunk_error=None,
                vector_target="shared:http://127.0.0.1:6333 [file_chunks]",
            )

        self.assertEqual(report["disk_file_count"], 2)
        self.assertEqual(report["catalog_file_count"], 3)
        self.assertEqual(report["indexed_in_scope_count"], 2)
        self.assertEqual(report["missing_from_catalog_count"], 0)
        self.assertEqual(report["catalog_only_count"], 1)
        self.assertEqual(report["catalog_only_breakdown"], {"file_rule": 1})
        self.assertEqual(report["files_with_content"], 2)
        self.assertEqual(report["files_with_embeddings"], 2)
        self.assertEqual(report["catalog_chunk_count"], 3)
        self.assertEqual(report["vector_chunk_count"], 3)
        self.assertTrue(report["chunk_parity"])
        self.assertEqual(report["status"], "WARN")

    def test_verify_collect_scope_uses_scanner_dotenv_extension_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, ".env").write_text("TOKEN=redacted\n", encoding="utf-8")
            Path(tmp, ".env.example").write_text("TOKEN=\n", encoding="utf-8")

            disk_paths, _ = verify_module.collect_indexable_disk_paths(
                roots=[tmp],
                scanner=FileScanner(),
            )

        self.assertTrue(any(path.endswith(".env") for path in disk_paths))
        self.assertTrue(any(path.endswith(".env.example") for path in disk_paths))

    def test_verify_warns_for_local_vector_target_mismatch_without_calling_it_corruption(
        self,
    ):
        catalog = RecordingCatalog(
            [
                {
                    "path": "docs/a.md",
                    "full_path": "C:/docs/a.md",
                    "content_summary": "alpha",
                    "chunk_count": 2,
                    "size": 100,
                }
            ]
        )

        with patch(
            "filemind.verify.collect_indexable_disk_paths",
            return_value=({"docs/a.md"}, {"c:/docs/a.md"}),
        ):
            report = verify_module.build_verification_report(
                catalog=catalog,
                scanner=SimpleNamespace(),
                vector_chunk_count=1,
                vector_chunk_error=None,
                vector_target="local:C:/AI_STATION/filemind/.index/qdrant [file_chunks]",
            )

        self.assertFalse(report["chunk_parity"])
        self.assertEqual(report["vector_target_kind"], "local")
        self.assertEqual(report["status"], "WARN")
        self.assertIn("local legacy/scratch Qdrant", report["status_message"])
        self.assertIn("may be stale", report["vector_target_note"])
        self.assertNotIn("corruption", report["status_message"].split("before")[0])

    def test_verify_warns_when_vector_store_is_unavailable(self):
        catalog = RecordingCatalog(
            [
                {
                    "path": "docs/a.md",
                    "full_path": "C:/docs/a.md",
                    "content_summary": "alpha",
                    "chunk_count": 2,
                    "size": 100,
                }
            ]
        )

        with patch(
            "filemind.verify.collect_indexable_disk_paths",
            return_value=({"docs/a.md"}, {"c:/docs/a.md"}),
        ):
            report = verify_module.build_verification_report(
                catalog=catalog,
                scanner=SimpleNamespace(),
                vector_chunk_count=None,
                vector_chunk_error="qdrant connection refused",
                vector_target="unavailable",
            )

        self.assertIsNone(report["chunk_parity"])
        self.assertEqual(report["vector_target_kind"], "unavailable")
        self.assertEqual(report["status"], "WARN")
        self.assertIn("vector parity is degraded", report["status_message"])
        self.assertIn("Vector store is unavailable", report["vector_target_note"])

    def test_repair_catalog_chunk_counts_syncs_from_vector_counts(self):
        catalog = RecordingCatalog(
            [
                {"path": "docs/a.md", "chunk_count": 0},
                {"path": "docs/b.md", "chunk_count": 2},
            ]
        )
        vector_store = RecordingVectorStore()

        with patch(
            "filemind.verify.get_vector_file_chunk_counts",
            return_value={"docs/a.md": 3, "docs/b.md": 2},
        ):
            result = verify_module.repair_catalog_chunk_counts_from_vectors(
                catalog=catalog,
                vector_store=vector_store,
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["updated"], 1)
        self.assertEqual(catalog.chunk_counts, {"docs/a.md": 3})
        catalog.conn.commit.assert_called_once()

    def test_repair_catalog_chunk_counts_refuses_extra_vector_file_ids(self):
        catalog = RecordingCatalog([{"path": "docs/a.md", "chunk_count": 1}])
        vector_store = RecordingVectorStore()

        with patch(
            "filemind.verify.get_vector_file_chunk_counts",
            return_value={"docs/a.md": 1, "missing.md": 1},
        ):
            result = verify_module.repair_catalog_chunk_counts_from_vectors(
                catalog=catalog,
                vector_store=vector_store,
            )

        self.assertFalse(result["success"])
        self.assertEqual(result["extra_vector_paths"], ["missing.md"])
        self.assertEqual(catalog.chunk_counts, {})

    def test_repair_catalog_chunk_counts_refuses_noncanonical_vector_target(self):
        catalog = RecordingCatalog([{"path": "docs/a.md", "chunk_count": 0}])
        vector_store = RecordingVectorStore(connection_mode="local")

        result = verify_module.repair_catalog_chunk_counts_from_vectors(
            catalog=catalog,
            vector_store=vector_store,
        )

        self.assertFalse(result["success"])
        self.assertIn("canonical shared HTTP Qdrant target", result["message"])
        self.assertEqual(catalog.chunk_counts, {})

    def test_repair_catalog_chunk_counts_refuses_collection_drift(self):
        catalog = RecordingCatalog([{"path": "docs/a.md", "chunk_count": 0}])
        vector_store = RecordingVectorStore(collection_name="wrong_chunks")

        result = verify_module.repair_catalog_chunk_counts_from_vectors(
            catalog=catalog,
            vector_store=vector_store,
        )

        self.assertFalse(result["success"])
        self.assertIn("collection does not match", result["message"])
        self.assertEqual(catalog.chunk_counts, {})

    def test_repair_catalog_chunk_counts_refuses_shared_url_drift(self):
        catalog = RecordingCatalog([{"path": "docs/a.md", "chunk_count": 0}])
        vector_store = RecordingVectorStore(qdrant_url="http://127.0.0.1:6334")

        result = verify_module.repair_catalog_chunk_counts_from_vectors(
            catalog=catalog,
            vector_store=vector_store,
        )

        self.assertFalse(result["success"])
        self.assertIn("shared Qdrant URL drifted", result["message"])
        self.assertEqual(catalog.chunk_counts, {})

    def test_repair_catalog_chunk_counts_heartbeats_and_checks_cancel_per_batch(self):
        catalog = RecordingCatalog(
            [
                {"path": "docs/a.md", "chunk_count": 0},
                {"path": "docs/b.md", "chunk_count": 0},
            ]
        )
        vector_store = RecordingVectorStore()
        vector_store.client = FakeScrollClient(
            [
                ([SimpleNamespace(payload={"file_id": "docs/a.md"})], "next"),
                ([SimpleNamespace(payload={"file_id": "docs/b.md"})], None),
            ]
        )

        with (
            patch("filemind.verify.heartbeat_scan_lock") as heartbeat,
            patch("filemind.verify.raise_if_scan_cancel_requested") as cancel_check,
        ):
            result = verify_module.repair_catalog_chunk_counts_from_vectors(
                catalog=catalog,
                vector_store=vector_store,
                scroll_batch_size=1,
                update_batch_size=1,
            )

        self.assertTrue(result["success"])
        self.assertEqual(catalog.chunk_counts, {"docs/a.md": 1, "docs/b.md": 1})
        phases = [call.kwargs["phase"] for call in heartbeat.call_args_list]
        self.assertEqual(phases.count("repair_chunk_counts_scroll"), 2)
        self.assertEqual(phases.count("repair_chunk_counts_update"), 2)
        self.assertGreaterEqual(cancel_check.call_count, 4)

    def test_vector_store_writes_wait_for_qdrant_acknowledgement(self):
        class FakeClient:
            def __init__(self):
                self.upsert_calls = []
                self.delete_calls = []

            def upsert(self, **kwargs):
                self.upsert_calls.append(kwargs)

            def count(self, **kwargs):
                return SimpleNamespace(count=1)

            def delete(self, **kwargs):
                self.delete_calls.append(kwargs)

        fake_client = FakeClient()
        store = VectorStore.__new__(VectorStore)
        store.client = fake_client
        store.collection_name = "file_chunks"

        upserted = store.upsert_chunks(
            [
                {
                    "id": "docs/a.md::chunk_0",
                    "file_id": "docs/a.md",
                    "chunk_index": 0,
                    "content": "alpha",
                    "vector": [0.1] * config.embedding_dim,
                    "sparse_vector": {},
                }
            ]
        )
        deleted = store.delete_by_file("docs/a.md")

        self.assertEqual(upserted, 1)
        self.assertEqual(deleted, 1)
        self.assertTrue(fake_client.upsert_calls[0]["wait"])
        self.assertTrue(fake_client.delete_calls[0]["wait"])

    def test_vector_store_deletes_specific_stale_chunk_ids(self):
        class FakeClient:
            def __init__(self):
                self.delete_calls = []

            def delete(self, **kwargs):
                self.delete_calls.append(kwargs)

        fake_client = FakeClient()
        store = VectorStore.__new__(VectorStore)
        store.client = fake_client
        store.collection_name = "file_chunks"

        deleted = store.delete_file_chunks("docs/a.md", [2, 1, 1])

        self.assertEqual(deleted, 2)
        selector = fake_client.delete_calls[0]["points_selector"]
        self.assertEqual(
            selector.points,
            [
                generate_uuid("docs/a.md::chunk_1"),
                generate_uuid("docs/a.md::chunk_2"),
            ],
        )
        self.assertTrue(fake_client.delete_calls[0]["wait"])

    def test_verify_renderer_is_ascii_safe(self):
        rendered = verify_module.render_verification_report(
            {
                "disk_file_count": 10,
                "catalog_file_count": 10,
                "indexed_in_scope_count": 10,
                "missing_from_catalog_count": 0,
                "catalog_only_count": 0,
                "catalog_only_breakdown": {},
                "missing_paths": [],
                "catalog_only_paths": [],
                "files_with_content": 10,
                "files_with_embeddings": 9,
                "catalog_chunk_count": 15,
                "vector_chunk_count": 15,
                "vector_chunk_error": None,
                "vector_target": "shared:http://127.0.0.1:6333 [file_chunks]",
                "completeness_pct": 100.0,
                "embedding_coverage_pct": 90.0,
                "chunk_parity": True,
                "status": "OK",
                "status_message": "Catalog matches the current FileMind scan scope.",
            }
        )

        self.assertIn("Status: OK", rendered)
        self.assertTrue(all(ord(ch) < 128 for ch in rendered))


if __name__ == "__main__":
    unittest.main(verbosity=2)
