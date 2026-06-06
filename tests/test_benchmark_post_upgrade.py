from __future__ import annotations

from types import SimpleNamespace

from filemind import benchmark_post_upgrade as bench


def test_expected_rank_matches_path_suffix_and_basename() -> None:
    results = [
        SimpleNamespace(file_path="docs/README.md"),
        SimpleNamespace(file_path="C:/AI_STATION/filemind/nightly.py"),
    ]

    assert bench.expected_rank(results, ["nightly.py"]) == 2
    assert bench.expected_rank(results, ["filemind/nightly.py"]) == 2
    assert bench.expected_rank(results, ["missing.py"]) is None


def test_latency_summary_reports_percentiles() -> None:
    summary = bench.latency_summary([0.1, 0.2, 0.4, 0.8])

    assert summary["count"] == 4
    assert summary["p50_seconds"] == 0.3
    assert summary["p95_seconds"] == 0.74
    assert summary["max_seconds"] == 0.8


def test_build_shadow_env_uses_isolated_targets(tmp_path) -> None:
    args = SimpleNamespace(
        shadow_collection="file_chunks_unit_test",
        shadow_corpus=tmp_path / "corpus",
        shadow_empty_root=tmp_path / "empty",
        shadow_qdrant_mode="http",
    )

    env = bench.build_shadow_env(args, tmp_path / "run")

    assert env["FILEMIND_SCAN_ROOTS"] == str(tmp_path / "corpus")
    assert env["FILEMIND_INDEX_DIR"] == str(tmp_path / "run" / "shadow_index")
    assert env["FILEMIND_QDRANT_COLLECTION"] == "file_chunks_unit_test"
    assert env["FILEMIND_QDRANT_MODE"] == "http"


def test_load_queries_accepts_utf8_bom(tmp_path) -> None:
    query_path = tmp_path / "queries.json"
    query_path.write_text(
        '\ufeff[{"query": "run_index_pipeline", "expected": ["nightly.py"]}]',
        encoding="utf-8",
    )

    loaded = bench.load_queries(query_path)

    assert loaded == [
        {
            "query": "run_index_pipeline",
            "expected": ["nightly.py"],
            "bucket": "imported",
        }
    ]


def test_live_require_hit_at_defers_controlled_gate_to_shadow() -> None:
    args = SimpleNamespace(
        require_hit_at=5,
        use_controlled_query_file=True,
        shadow_rebuild=True,
        allow_live_expected_gate=False,
    )

    assert bench.live_require_hit_at(args) == 0


def test_live_require_hit_at_allows_explicit_live_probe() -> None:
    args = SimpleNamespace(
        require_hit_at=5,
        use_controlled_query_file=True,
        shadow_rebuild=True,
        allow_live_expected_gate=True,
    )

    assert bench.live_require_hit_at(args) == 5


def test_live_thresholds_defer_controlled_gate_to_shadow() -> None:
    args = SimpleNamespace(
        use_controlled_query_file=True,
        shadow_rebuild=True,
        allow_live_expected_gate=False,
        min_hit1=17,
        min_hit3=23,
        min_hit5=26,
        min_mrr=0.68,
    )

    assert bench.live_thresholds(args) == {
        "min_hit1": 0,
        "min_hit3": 0,
        "min_hit5": 0,
        "min_mrr": 0.0,
    }


def test_build_gates_applies_quality_thresholds() -> None:
    gates = bench.build_gates(
        preflight=[],
        live_summary={
            "zero_result_queries": [],
            "hit1": 17,
            "hit3": 23,
            "hit5": 26,
            "mrr": 0.69,
        },
        shadow_summary=None,
        require_hit_at=0,
        thresholds={"min_hit1": 17, "min_hit3": 23, "min_hit5": 26, "min_mrr": 0.68},
    )

    assert gates["overall_status"] == "pass"
