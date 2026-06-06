# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportMissingParameterType=false
from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

from filemind import search as search_module
from filemind.catalog import Catalog
from filemind.search import (
    SearchEngine,
    SearchResult,
    _extract_file_lookup_tokens,
    _is_precise_file_lookup,
)


def _file_freshness_fields(path: str) -> dict[str, object]:
    source = Path(path)
    payload = source.read_bytes()
    stat = source.stat()
    digest = hashlib.md5(payload).hexdigest()
    return {
        "full_path": str(source),
        "size": stat.st_size,
        "mtime": stat.st_mtime,
        "content_hash": digest,
        "source_size": stat.st_size,
        "source_mtime": stat.st_mtime,
        "source_content_hash": digest,
    }


def test_extract_file_lookup_tokens_ignores_model_version_dots() -> None:
    tokens = _extract_file_lookup_tokens(
        "Find LOCAL_MODEL_AGENTIC_CODING_BENCHMARK_HARNESS.md for qwen2.5-coder routing."
    )

    assert tokens == ["local_model_agentic_coding_benchmark_harness.md"]


def test_precise_file_lookup_excludes_common_filenames_without_path() -> None:
    assert _is_precise_file_lookup(["local_model_agentic_coding_benchmark_harness.md"])
    assert _is_precise_file_lookup(["filemind/readme.md"])
    assert not _is_precise_file_lookup(["readme.md"])


def test_fts_search_falls_back_for_operator_punctuation(tmp_path) -> None:
    catalog = Catalog(db_path=tmp_path / "catalog.db")
    catalog.init_db()
    try:
        catalog.upsert_file(
            path="README.md",
            full_path=str(tmp_path / "README.md"),
            size=100,
            mtime=1.0,
            content_hash="readme",
            ext=".md",
            content_summary="Alias-backed shadow rebuild instructions.",
            category="documentation",
            chunk_count=1,
        )
        catalog.upsert_file(
            path="FILEMIND_CLI_USAGE.md",
            full_path=str(tmp_path / "FILEMIND_CLI_USAGE.md"),
            size=100,
            mtime=1.0,
            content_hash="cli",
            ext=".md",
            content_summary="Verify 100 percent scan completeness from the CLI.",
            category="documentation",
            chunk_count=1,
        )

        hyphenated = catalog.fts_search("alias-backed shadow rebuild", top_k=5)
        percent = catalog.fts_search("verify 100% scan completeness", top_k=5)

        assert [row["path"] for row in hyphenated][:1] == ["README.md"]
        assert [row["path"] for row in percent][:1] == ["FILEMIND_CLI_USAGE.md"]
    finally:
        catalog.close()


def test_fts_search_falls_back_to_recall_terms_when_strict_match_is_empty(
    tmp_path,
) -> None:
    catalog = Catalog(db_path=tmp_path / "catalog.db")
    catalog.init_db()
    try:
        catalog.upsert_file(
            path="config.py",
            full_path=str(tmp_path / "config.py"),
            size=100,
            mtime=1.0,
            content_hash="config",
            ext=".py",
            content_summary="FileMind scan roots and Obsidian vault configuration.",
            category="code",
            chunk_count=1,
        )

        results = catalog.fts_search("scan roots ai station obsidian vault", top_k=5)

        assert [row["path"] for row in results][:1] == ["config.py"]
    finally:
        catalog.close()


def test_query_intent_balances_technical_lexical_queries() -> None:
    engine = SearchEngine.__new__(SearchEngine)

    assert engine._detect_query_intent("schema_migrations needs_classification") == 0.8
    assert engine._detect_query_intent("alias-backed shadow rebuild") == 0.8
    assert engine._detect_query_intent("scan roots ai station obsidian vault") == 1.0
    assert engine._detect_query_intent("gemma4 reliability") == 1.2


def test_exact_catalog_search_returns_zero_chunk_markdown_from_catalog() -> None:
    engine = SearchEngine.__new__(SearchEngine)
    engine.catalog = SimpleNamespace(
        get_all_files=lambda: [
            {
                "path": "hub/docs/evals/LOCAL_MODEL_AGENTIC_CODING_BENCHMARK_HARNESS.md",
                "full_path": "C:/AI_STATION/hub/docs/evals/LOCAL_MODEL_AGENTIC_CODING_BENCHMARK_HARNESS.md",
                "content_summary": "Local Model Agentic Coding Benchmark Harness task plan and runbook.",
                "category": "documentation",
                "ext": ".md",
                "mtime": 1.0,
                "chunk_count": 0,
            },
            {
                "path": "hub/docs/evals/CODEX_ENHANCEMENT_EVAL_PLAN.md",
                "full_path": "C:/AI_STATION/hub/docs/evals/CODEX_ENHANCEMENT_EVAL_PLAN.md",
                "content_summary": "Different benchmark plan.",
                "category": "documentation",
                "ext": ".md",
                "mtime": 2.0,
                "chunk_count": 4,
            },
        ]
    )

    results = engine._exact_catalog_search(
        "Find LOCAL_MODEL_AGENTIC_CODING_BENCHMARK_HARNESS.md for the local model benchmark harness docs.",
        top_k=5,
    )

    assert [result.file_path for result in results] == [
        "hub/docs/evals/LOCAL_MODEL_AGENTIC_CODING_BENCHMARK_HARNESS.md"
    ]
    assert results[0].chunk_index == -1
    assert results[0].category == "documentation"
    assert results[0].score >= 1.75


def test_exact_results_stay_ahead_of_higher_scored_fuzzy_hits() -> None:
    exact = [
        SearchResult(
            file_path="hub/docs/architecture/QWEN_ADVISORY_VERIFICATION_PATTERN.md",
            chunk_index=0,
            score=1.75,
            snippet="Exact catalog hit",
        )
    ]
    fuzzy = [
        SearchResult(
            file_path="AGENTS.md",
            chunk_index=0,
            score=99.0,
            snippet="Fuzzy semantic hit",
        )
    ]

    merged = SearchEngine._merge_exact_results(exact, fuzzy, top_k=2)

    assert [result.file_path for result in merged] == [
        "hub/docs/architecture/QWEN_ADVISORY_VERIFICATION_PATTERN.md",
        "AGENTS.md",
    ]


def test_precise_file_query_keeps_content_chunks_for_same_file() -> None:
    engine = SearchEngine.__new__(SearchEngine)
    source_fields = _file_freshness_fields(
        "C:/AI_STATION/projects/source/ai_station_context/station_supervisor.py"
    )
    engine.catalog = SimpleNamespace(
        get_all_files=lambda: [
            {
                "path": "projects/source/ai_station_context/station_supervisor.py",
                "content_summary": "Station supervisor startup and timeout handling.",
                "category": "code",
                "ext": ".py",
                "chunk_count": 3,
                **source_fields,
            },
        ]
    )
    engine._embedder = SimpleNamespace(
        encode=lambda texts, return_dense=True, return_sparse=True: {
            "dense_vecs": [[0.1, 0.2]],
            "lexical_weights": [{}],
        }
    )
    engine.vector_store = SimpleNamespace(
        search_hybrid=lambda *args, **kwargs: [
            {
                "file_id": "projects/source/ai_station_context/station_supervisor.py",
                "chunk_index": 2,
                "content": "timeout handling uses action.timeout_s for startup actions",
                "_relevance_score": 0.9,
                "category": "code",
                "file_type": ".py",
                "mtime": source_fields["mtime"],
            }
        ]
    )
    engine.bm25 = None
    engine.do_reranking = False

    results = engine.search("timeout handling in station_supervisor.py", top_k=5)

    assert [(result.file_path, result.chunk_index) for result in results] == [
        ("projects/source/ai_station_context/station_supervisor.py", -1),
        ("projects/source/ai_station_context/station_supervisor.py", 2),
    ]
    assert "timeout handling uses action.timeout_s" in results[1].snippet


def test_keyword_search_uses_catalog_without_constructing_vector_store(
    monkeypatch,
) -> None:
    class BrokenVectorStore:
        def __init__(self) -> None:
            raise AssertionError(
                "VectorStore should not be constructed for catalog keyword search"
            )

    class DummyCatalog:
        def init_db(self) -> None:
            return None

        def fts_search(self, query: str, top_k: int):
            assert query == "context status"
            assert top_k == 3
            return [
                {
                    "path": "hub/docs/context/CURRENT_CONTEXT_STATUS.md",
                    "content_summary": "Current context status report",
                    "category": "documentation",
                    "ext": ".md",
                    "mtime": 1.0,
                    "rank": -1.2,
                }
            ]

        def close(self) -> None:
            return None

    monkeypatch.setattr(search_module, "VectorStore", BrokenVectorStore)
    engine = SearchEngine(
        catalog=DummyCatalog(),
        bm25_index=SimpleNamespace(is_built=False),
        reranking=False,
    )

    results = engine.keyword_search("context status", top_k=3)

    assert [result.file_path for result in results] == [
        "hub/docs/context/CURRENT_CONTEXT_STATUS.md"
    ]
    assert results[0].category == "documentation"


def test_hybrid_search_falls_back_to_catalog_and_bm25_when_vector_store_is_down(
    monkeypatch,
) -> None:
    class BrokenVectorStore:
        def __init__(self) -> None:
            raise RuntimeError("qdrant connection refused")

    class DummyCatalog:
        def init_db(self) -> None:
            return None

        def get_all_files(self):
            return [
                {
                    "path": "hub/docs/context/CURRENT_CONTEXT_STATUS.md",
                    "content_summary": "Current context status report",
                    "category": "documentation",
                    "ext": ".md",
                    "mtime": 1.0,
                },
                {
                    "path": "hub/docs/runbooks/CODEX_OPERATING_PLAYBOOK.md",
                    "content_summary": "Codex operating playbook",
                    "category": "documentation",
                    "ext": ".md",
                    "mtime": 2.0,
                },
            ]

        def fts_search(self, query: str, top_k: int):
            return [
                {
                    "path": "hub/docs/context/CURRENT_CONTEXT_STATUS.md",
                    "content_summary": "Current context status report",
                    "category": "documentation",
                    "ext": ".md",
                    "mtime": 1.0,
                    "rank": -1.0,
                }
            ]

        def close(self) -> None:
            return None

    class DummyBm25:
        is_built = True

        def search(self, query: str, top_k: int):
            return [("hub/docs/runbooks/CODEX_OPERATING_PLAYBOOK.md::chunk_0", 4.2)]

    monkeypatch.setattr(search_module, "VectorStore", BrokenVectorStore)
    engine = SearchEngine(
        catalog=DummyCatalog(),
        bm25_index=DummyBm25(),
        reranking=False,
    )

    results = engine.search("context status", top_k=5)

    assert {result.file_path for result in results} == {
        "hub/docs/context/CURRENT_CONTEXT_STATUS.md",
        "hub/docs/runbooks/CODEX_OPERATING_PLAYBOOK.md",
    }


def test_precise_exact_search_returns_catalog_hits_without_vector_when_top_k_is_satisfied(
    monkeypatch,
) -> None:
    class BrokenVectorStore:
        def __init__(self) -> None:
            raise AssertionError(
                "VectorStore should not be constructed for satisfied exact lookup"
            )

    class DummyCatalog:
        def init_db(self) -> None:
            return None

        def get_all_files(self):
            return [
                {
                    "path": "filemind/AGENTS.md",
                    "content_summary": "FileMind agent scope.",
                    "category": "documentation",
                    "ext": ".md",
                    "chunk_count": 1,
                    **_file_freshness_fields("C:/AI_STATION/filemind/AGENTS.md"),
                }
            ]

        def close(self) -> None:
            return None

    monkeypatch.setattr(search_module, "VectorStore", BrokenVectorStore)
    engine = SearchEngine(
        catalog=DummyCatalog(),
        bm25_index=SimpleNamespace(is_built=False),
        reranking=False,
    )

    results = engine.search("filemind/AGENTS.md", top_k=1)

    assert [result.file_path for result in results] == ["filemind/AGENTS.md"]
