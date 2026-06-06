#!/usr/bin/env python3
"""Post-upgrade FileMind benchmark harness.

This is an operator-facing benchmark runner, not an indexing shortcut.  The
default mode is intentionally read-only against the live index: it captures
runtime health, runs deterministic query probes, records latency/quality
metrics, and writes a self-contained result bundle under ``filemind/.bench``.

Shadow rebuilds are available only behind an explicit flag so a normal
benchmark run never resets the live FileMind collection by accident.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any, Mapping

FILEMIND_DIR = Path(__file__).resolve().parent
AI_STATION_ROOT = FILEMIND_DIR.parent
RUN_PY = FILEMIND_DIR / "run.py"
DEFAULT_PYTHON = AI_STATION_ROOT / "venvs" / "semantic-core" / "Scripts" / "python.exe"
DEFAULT_BENCH_ROOT = FILEMIND_DIR / ".bench"
DEFAULT_QUERY_FILE = FILEMIND_DIR / ".bench" / "sparse_eval_medium" / "queries.json"
DEFAULT_SHADOW_CORPUS = FILEMIND_DIR / ".bench" / "sparse_eval_medium" / "corpus"
DEFAULT_EMPTY_ROOT = FILEMIND_DIR / ".bench" / "sparse_eval_medium" / "empty"
SENSITIVE_ENV_FRAGMENTS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")

LIVE_QUERY_SET: list[dict[str, Any]] = [
    {
        "query": "run_index_pipeline",
        "expected": ["nightly.py"],
        "bucket": "code-symbol",
    },
    {
        "query": "vector target chunk parity completeness verification",
        "expected": ["verify.py"],
        "bucket": "integrity",
    },
    {
        "query": "qdrant sparse vector prefetch",
        "expected": ["vector_store.py"],
        "bucket": "retrieval-path",
    },
    {
        "query": "scan lock cooperative cancellation",
        "expected": ["scan_lock.py", "run.py"],
        "bucket": "recovery",
    },
    {
        "query": "FileMind post upgrade benchmark",
        "expected": ["benchmark_post_upgrade.py"],
        "bucket": "benchmark-control",
    },
]


@dataclass
class CommandResult:
    """Serializable command execution record."""

    label: str
    command: list[str]
    returncode: int
    duration_seconds: float
    stdout_log: str
    stderr_log: str
    timed_out: bool = False


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_label(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "command"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


def append_jsonl(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def percentile(values: list[float], pct: float) -> float | None:
    """Return an interpolated percentile for a small latency sample."""
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    rank = (len(ordered) - 1) * (pct / 100.0)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def latency_summary(values: list[float]) -> dict[str, float | int | None]:
    """Summarize latency values without requiring third-party packages."""
    if not values:
        return {
            "count": 0,
            "mean_seconds": None,
            "p50_seconds": None,
            "p95_seconds": None,
            "max_seconds": None,
        }
    return {
        "count": len(values),
        "mean_seconds": round(mean(values), 6),
        "p50_seconds": round(median(values), 6),
        "p95_seconds": round(percentile(values, 95) or 0.0, 6),
        "max_seconds": round(max(values), 6),
    }


def normalize_path(value: str) -> str:
    return value.replace("\\", "/").lower()


def expected_rank(results: list[Any], expected: list[str]) -> int | None:
    """Return the 1-based rank of the first expected file match."""
    if not expected:
        return None

    expected_norm = [normalize_path(item) for item in expected]
    expected_names = {Path(item).name.lower() for item in expected}

    for rank, result in enumerate(results, start=1):
        raw_path = getattr(result, "file_path", "")
        if isinstance(result, dict):
            raw_path = str(result.get("file_path") or result.get("path") or "")
        path_norm = normalize_path(str(raw_path))
        path_name = Path(path_norm).name.lower()
        if (
            any(item in path_norm for item in expected_norm)
            or path_name in expected_names
        ):
            return rank
    return None


def redact_env(env: Mapping[str, str]) -> dict[str, str]:
    """Keep benchmark-relevant environment values while redacting credentials."""
    prefixes = ("FILEMIND_", "AI_STATION", "HF_", "TRANSFORMERS_", "CUDA", "OLLAMA")
    snapshot: dict[str, str] = {}
    for key, value in sorted(env.items()):
        if not key.startswith(prefixes):
            continue
        if any(fragment in key.upper() for fragment in SENSITIVE_ENV_FRAGMENTS):
            snapshot[key] = "<redacted>"
        else:
            snapshot[key] = value
    return snapshot


def run_command(
    *,
    label: str,
    command: list[str],
    cwd: Path,
    run_dir: Path,
    timeout_seconds: int,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Run a command and persist stdout/stderr logs."""
    log_dir = run_dir / "command_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_label = safe_label(label)
    stdout_log = log_dir / f"{log_label}.stdout.log"
    stderr_log = log_dir / f"{log_label}.stderr.log"
    start = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
        duration = time.perf_counter() - start
        stdout_log.write_text(completed.stdout or "", encoding="utf-8")
        stderr_log.write_text(completed.stderr or "", encoding="utf-8")
        return CommandResult(
            label=label,
            command=command,
            returncode=completed.returncode,
            duration_seconds=round(duration, 6),
            stdout_log=str(stdout_log),
            stderr_log=str(stderr_log),
        )
    except subprocess.TimeoutExpired as exc:
        duration = time.perf_counter() - start
        stdout_text = exc.stdout or ""
        stderr_text = exc.stderr or ""
        if isinstance(stdout_text, bytes):
            stdout_text = stdout_text.decode("utf-8", errors="replace")
        if isinstance(stderr_text, bytes):
            stderr_text = stderr_text.decode("utf-8", errors="replace")
        stdout_log.write_text(stdout_text, encoding="utf-8")
        stderr_log.write_text(stderr_text, encoding="utf-8")
        return CommandResult(
            label=label,
            command=command,
            returncode=124,
            duration_seconds=round(duration, 6),
            stdout_log=str(stdout_log),
            stderr_log=str(stderr_log),
            timed_out=True,
        )


def load_queries(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return LIVE_QUERY_SET
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list):
        raise ValueError(f"Query file must contain a JSON list: {path}")
    queries: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict) or not item.get("query"):
            raise ValueError(f"Invalid query row in {path}: {item!r}")
        queries.append(
            {
                "query": str(item["query"]),
                "expected": [str(value) for value in item.get("expected", [])],
                "bucket": str(item.get("bucket", "imported")),
            }
        )
    return queries


def capture_static_snapshot(args: argparse.Namespace, run_dir: Path) -> dict[str, Any]:
    snapshot = {
        "captured_at": utc_now_iso(),
        "ai_station_root": str(AI_STATION_ROOT),
        "filemind_dir": str(FILEMIND_DIR),
        "python_executable": str(args.python),
        "platform": platform.platform(),
        "python_version": sys.version,
        "benchmark_args": vars(args),
        "environment": redact_env(os.environ),
    }
    write_json(run_dir / "environment_snapshot.json", snapshot)
    return snapshot


def run_preflight(args: argparse.Namespace, run_dir: Path) -> list[CommandResult]:
    python = str(args.python)
    commands: list[tuple[str, list[str], int]] = [
        ("python_version", [python, "--version"], 30),
        ("filemind_runtime", [python, str(RUN_PY), "runtime"], 180),
        ("filemind_deps", [python, str(RUN_PY), "deps"], 180),
        ("filemind_scan_status", [python, str(RUN_PY), "scan-status"], 60),
        ("filemind_stats", [python, str(RUN_PY), "stats"], 180),
    ]
    if not args.skip_verify:
        commands.append(("filemind_verify", [python, str(RUN_PY), "verify"], 900))

    results = [
        run_command(
            label=label,
            command=command,
            cwd=FILEMIND_DIR,
            run_dir=run_dir,
            timeout_seconds=timeout,
        )
        for label, command, timeout in commands
    ]
    write_json(run_dir / "preflight_results.json", [asdict(item) for item in results])
    return results


def compact_result(result: Any) -> dict[str, Any]:
    return {
        "file_path": str(getattr(result, "file_path", "")),
        "chunk_index": int(getattr(result, "chunk_index", -1)),
        "score": float(getattr(result, "score", 0.0)),
        "category": str(getattr(result, "category", "")),
        "file_type": str(getattr(result, "file_type", "")),
        "is_protected": bool(getattr(result, "is_protected", False)),
    }


def run_live_query_benchmark(
    *,
    queries: list[dict[str, Any]],
    repeats: int,
    top_k: int,
    reranking: bool,
    run_dir: Path,
) -> dict[str, Any]:
    """Run read-only live query probes through FileMind's SearchEngine."""
    sys.path.insert(0, str(FILEMIND_DIR))
    from search import SearchEngine  # noqa: PLC0415

    latency_path = run_dir / "latency_results.jsonl"
    quality_rows: list[dict[str, Any]] = []
    all_latencies: list[float] = []
    first_latency: float | None = None

    engine = SearchEngine(reranking=reranking)
    try:
        for query_index, row in enumerate(queries):
            query = row["query"]
            expected = row.get("expected", [])
            best_rank: int | None = None
            first_result_set: list[dict[str, Any]] = []
            query_latencies: list[float] = []
            for repeat_index in range(repeats):
                start = time.perf_counter()
                results = engine.search(query, top_k=top_k, use_hybrid=True)
                elapsed = time.perf_counter() - start
                if first_latency is None:
                    first_latency = elapsed
                all_latencies.append(elapsed)
                query_latencies.append(elapsed)
                rank = expected_rank(results, expected)
                if rank is not None and (best_rank is None or rank < best_rank):
                    best_rank = rank
                compact = [compact_result(item) for item in results[:top_k]]
                if repeat_index == 0:
                    first_result_set = compact
                append_jsonl(
                    latency_path,
                    {
                        "observed_at": utc_now_iso(),
                        "query_index": query_index,
                        "repeat_index": repeat_index,
                        "query": query,
                        "bucket": row.get("bucket", ""),
                        "reranking": reranking,
                        "top_k": top_k,
                        "duration_seconds": round(elapsed, 6),
                        "result_count": len(results),
                        "expected_rank": rank,
                    },
                )

            quality_rows.append(
                {
                    "query": query,
                    "bucket": row.get("bucket", ""),
                    "expected": expected,
                    "best_expected_rank": best_rank,
                    "hit_at_1": best_rank == 1,
                    "hit_at_3": best_rank is not None and best_rank <= 3,
                    "hit_at_5": best_rank is not None and best_rank <= 5,
                    "result_count": len(first_result_set),
                    "latency": latency_summary(query_latencies),
                    "top_results": first_result_set,
                }
            )
    finally:
        engine.close()

    expected_rows = [row for row in quality_rows if row["expected"]]
    reciprocal_ranks = [
        (1.0 / int(row["best_expected_rank"])) if row["best_expected_rank"] else 0.0
        for row in expected_rows
    ]
    summary = {
        "mode": "live-read-only",
        "query_count": len(quality_rows),
        "repeats": repeats,
        "top_k": top_k,
        "reranking": reranking,
        "first_query_latency_seconds": (
            round(first_latency, 6) if first_latency is not None else None
        ),
        "all_latency": latency_summary(all_latencies),
        "warm_latency": latency_summary(all_latencies[1:]),
        "hit1": sum(1 for row in expected_rows if row["hit_at_1"]),
        "hit3": sum(1 for row in expected_rows if row["hit_at_3"]),
        "hit5": sum(1 for row in expected_rows if row["hit_at_5"]),
        "mrr": round(mean(reciprocal_ranks), 6) if reciprocal_ranks else None,
        "expected_query_count": len(expected_rows),
        "zero_result_queries": [
            row["query"] for row in quality_rows if row["result_count"] == 0
        ],
        "quality_rows": quality_rows,
    }
    write_json(run_dir / "quality_results.json", summary)
    return summary


def build_shadow_env(args: Any, run_dir: Path) -> dict[str, str]:
    run_id = run_dir.name.lower().replace("-", "_")
    collection = args.shadow_collection or f"file_chunks_{run_id}"
    empty = args.shadow_empty_root
    env = os.environ.copy()
    env.update(
        {
            "AI_STATION_ROOT": str(args.shadow_corpus),
            "FILEMIND_SCAN_ROOTS": str(args.shadow_corpus),
            "FILEMIND_INDEX_DIR": str(run_dir / "shadow_index"),
            "FILEMIND_QDRANT_MODE": args.shadow_qdrant_mode,
            "FILEMIND_QDRANT_COLLECTION": collection,
            "FILEMIND_KIMI_DIR": str(empty / ".kimi"),
            "FILEMIND_OBSIDIAN_VAULT_DIR": str(empty / "obsidian"),
            "FILEMIND_PC_FOCUS_DIR": str(empty / "pc-focus"),
            "FILEMIND_CLINE_DIR": str(empty / ".cline"),
            "FILEMIND_CLAUDE_DIR": str(empty / ".claude"),
            "FILEMIND_OPENCLAW_DIR": str(empty / ".openclaw"),
            "FILEMIND_AGENTS_DIR": str(empty / ".agents"),
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_DATASETS_OFFLINE": "1",
        }
    )
    return env


def run_shadow_rebuild(args: argparse.Namespace, run_dir: Path) -> dict[str, Any]:
    env = build_shadow_env(args, run_dir)
    write_json(run_dir / "shadow_environment.json", redact_env(env))
    python = str(args.python)
    commands: list[tuple[str, list[str], int]] = [
        (
            "shadow_scan_rebuild",
            [python, str(RUN_PY), "scan", "--rebuild"],
            args.shadow_timeout_seconds,
        ),
        ("shadow_verify", [python, str(RUN_PY), "verify"], 900),
    ]
    if not args.skip_shadow_query_probe:
        shadow_query_dir = run_dir / "shadow_query_probe"
        query_args: list[str] = []
        if args.query_file:
            query_args.extend(["--query-file", str(args.query_file)])
        else:
            query_args.append("--use-controlled-query-file")
        if args.rerank:
            query_args.append("--rerank")
        if args.require_hit_at:
            query_args.extend(["--require-hit-at", str(args.require_hit_at)])
        for option_name in ("min_hit1", "min_hit3", "min_hit5"):
            value = getattr(args, option_name)
            if value:
                query_args.extend([f"--{option_name.replace('_', '-')}", str(value)])
        if args.min_mrr:
            query_args.extend(["--min-mrr", str(args.min_mrr)])
        child_command = [
            python,
            str(Path(__file__).resolve()),
            "--run-dir",
            str(shadow_query_dir),
            "--skip-preflight",
            "--repeats",
            str(args.repeats),
            "--top-k",
            str(args.top_k),
            "--allow-live-expected-gate",
            *query_args,
        ]
        if args.strict or args.require_hit_at:
            child_command.append("--strict")
        commands.append(("shadow_query_probe", child_command, 1800))
    results = [
        run_command(
            label=label,
            command=command,
            cwd=FILEMIND_DIR,
            run_dir=run_dir,
            timeout_seconds=timeout,
            env=env,
        )
        for label, command, timeout in commands
    ]
    payload = {"commands": [asdict(item) for item in results]}
    write_json(run_dir / "shadow_rebuild_results.json", payload)
    return payload


def live_require_hit_at(args: Any) -> int:
    """Return the strict expected-hit gate that is valid for the live lane.

    The historical ``sparse_eval_medium`` query file was authored for its own
    controlled corpus.  Using its expected-file targets as a strict gate against
    the much noisier live workspace creates false failures.  Shadow rebuild
    runs enforce that expected-target gate in the isolated child probe instead.
    """
    if (
        args.require_hit_at
        and args.use_controlled_query_file
        and args.shadow_rebuild
        and not args.allow_live_expected_gate
    ):
        return 0
    return args.require_hit_at


def live_thresholds(args: Any) -> dict[str, float | int]:
    """Return metric thresholds that are valid for the live lane."""
    controlled_shadow = (
        args.use_controlled_query_file
        and args.shadow_rebuild
        and not args.allow_live_expected_gate
    )
    if controlled_shadow:
        return {"min_hit1": 0, "min_hit3": 0, "min_hit5": 0, "min_mrr": 0.0}
    return {
        "min_hit1": int(args.min_hit1),
        "min_hit3": int(args.min_hit3),
        "min_hit5": int(args.min_hit5),
        "min_mrr": float(args.min_mrr),
    }


def build_gates(
    *,
    preflight: list[CommandResult],
    live_summary: dict[str, Any] | None,
    shadow_summary: dict[str, Any] | None,
    require_hit_at: int,
    thresholds: dict[str, float | int] | None = None,
) -> dict[str, Any]:
    gates: list[dict[str, Any]] = []
    for result in preflight:
        gates.append(
            {
                "name": result.label,
                "status": "pass" if result.returncode == 0 else "fail",
                "detail": f"exit={result.returncode}, duration={result.duration_seconds}s",
            }
        )

    if live_summary:
        zero_queries = live_summary.get("zero_result_queries", [])
        gates.append(
            {
                "name": "live_queries_nonzero",
                "status": "pass" if not zero_queries else "fail",
                "detail": f"zero_result_queries={len(zero_queries)}",
            }
        )
        if require_hit_at:
            missed = [
                row["query"]
                for row in live_summary.get("quality_rows", [])
                if row.get("expected")
                and (
                    row.get("best_expected_rank") is None
                    or int(row["best_expected_rank"]) > require_hit_at
                )
            ]
            gates.append(
                {
                    "name": f"expected_hit_at_{require_hit_at}",
                    "status": "pass" if not missed else "fail",
                    "detail": f"missed={len(missed)}",
                }
            )
        thresholds = thresholds or {}
        for metric, label in (
            ("hit1", "min_hit1"),
            ("hit3", "min_hit3"),
            ("hit5", "min_hit5"),
        ):
            minimum = int(thresholds.get(label, 0) or 0)
            if minimum:
                actual = int(live_summary.get(metric, 0) or 0)
                gates.append(
                    {
                        "name": label,
                        "status": "pass" if actual >= minimum else "fail",
                        "detail": f"actual={actual}, minimum={minimum}",
                    }
                )
        min_mrr = float(thresholds.get("min_mrr", 0.0) or 0.0)
        if min_mrr:
            actual_mrr = float(live_summary.get("mrr") or 0.0)
            gates.append(
                {
                    "name": "min_mrr",
                    "status": "pass" if actual_mrr >= min_mrr else "fail",
                    "detail": f"actual={actual_mrr}, minimum={min_mrr}",
                }
            )

    if shadow_summary:
        failed = [
            item
            for item in shadow_summary.get("commands", [])
            if int(item.get("returncode", 1)) != 0
        ]
        gates.append(
            {
                "name": "shadow_rebuild_commands",
                "status": "pass" if not failed else "fail",
                "detail": f"failed_commands={len(failed)}",
            }
        )

    overall = "pass" if all(gate["status"] == "pass" for gate in gates) else "fail"
    return {"overall_status": overall, "gates": gates}


def write_markdown_report(run_dir: Path, summary: dict[str, Any]) -> Path:
    gates = summary.get("gates", {})
    live = summary.get("live_query_benchmark") or {}
    lines = [
        "# FileMind Post-Upgrade Benchmark Report",
        "",
        f"- Run directory: `{run_dir}`",
        f"- Observed at: `{summary.get('observed_at')}`",
        f"- Overall status: **{gates.get('overall_status', 'unknown').upper()}**",
        f"- Mode: `{summary.get('mode')}`",
        "",
        "## Gates",
        "",
    ]
    for gate in gates.get("gates", []):
        lines.append(
            f"- **{gate['status'].upper()}** `{gate['name']}` - {gate['detail']}"
        )
    if live:
        lines.extend(
            [
                "",
                "## Live read-only query benchmark",
                "",
                f"- Queries: `{live.get('query_count')}`",
                f"- Repeats: `{live.get('repeats')}`",
                f"- Top K: `{live.get('top_k')}`",
                f"- Reranking: `{live.get('reranking')}`",
                f"- First query latency: `{live.get('first_query_latency_seconds')}` seconds",
                f"- Warm p95 latency: `{(live.get('warm_latency') or {}).get('p95_seconds')}` seconds",
                f"- Hit@1/3/5: `{live.get('hit1')}/{live.get('hit3')}/{live.get('hit5')}` "
                f"of `{live.get('expected_query_count')}` expected-query rows",
                f"- MRR: `{live.get('mrr')}`",
                "",
                "Detailed JSON artifacts are in this run directory.",
            ]
        )
    report_path = run_dir / "BENCHMARK_REPORT.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a reproducible post-upgrade FileMind benchmark bundle."
    )
    parser.add_argument("--python", type=Path, default=DEFAULT_PYTHON)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--query-file", type=Path, default=None)
    parser.add_argument("--use-controlled-query-file", action="store_true")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--rerank", action="store_true")
    parser.add_argument("--skip-preflight", action="store_true")
    parser.add_argument("--skip-verify", action="store_true")
    parser.add_argument("--skip-live-queries", action="store_true")
    parser.add_argument("--skip-shadow-query-probe", action="store_true")
    parser.add_argument("--require-hit-at", type=int, choices=[0, 1, 3, 5], default=0)
    parser.add_argument("--min-hit1", type=int, default=0)
    parser.add_argument("--min-hit3", type=int, default=0)
    parser.add_argument("--min-hit5", type=int, default=0)
    parser.add_argument("--min-mrr", type=float, default=0.0)
    parser.add_argument(
        "--allow-live-expected-gate",
        action="store_true",
        help=(
            "Allow --require-hit-at against the live index even when using the "
            "historical controlled query file. Normally this is blocked because "
            "those expected targets belong to the controlled corpus."
        ),
    )
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--shadow-rebuild", action="store_true")
    parser.add_argument("--shadow-corpus", type=Path, default=DEFAULT_SHADOW_CORPUS)
    parser.add_argument("--shadow-empty-root", type=Path, default=DEFAULT_EMPTY_ROOT)
    parser.add_argument(
        "--shadow-qdrant-mode", choices=["http", "local"], default="http"
    )
    parser.add_argument("--shadow-collection", default="")
    parser.add_argument("--shadow-timeout-seconds", type=int, default=7200)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if (
        (
            args.require_hit_at
            or args.min_hit1
            or args.min_hit3
            or args.min_hit5
            or args.min_mrr
        )
        and args.use_controlled_query_file
        and not args.shadow_rebuild
        and not args.allow_live_expected_gate
    ):
        raise SystemExit(
            "The historical controlled query file is not a strict live-index "
            "gate. Use --shadow-rebuild to enforce quality gates in isolation, "
            "or pass --allow-live-expected-gate for an intentional live probe."
        )
    query_file = args.query_file
    if args.use_controlled_query_file and query_file is None:
        query_file = DEFAULT_QUERY_FILE

    run_dir = args.run_dir
    if run_dir is None:
        stamp = datetime.now().strftime("post_upgrade_%Y%m%d-%H%M%S")
        run_dir = DEFAULT_BENCH_ROOT / stamp
    run_dir.mkdir(parents=True, exist_ok=True)

    queries = [] if args.skip_live_queries else load_queries(query_file)
    summary: dict[str, Any] = {
        "observed_at": utc_now_iso(),
        "mode": "post-upgrade-filemind-benchmark",
        "run_dir": str(run_dir),
        "query_file": str(query_file) if query_file else "<built-in-live-query-set>",
        "shadow_rebuild_requested": bool(args.shadow_rebuild),
    }
    summary["environment_snapshot"] = capture_static_snapshot(args, run_dir)

    preflight: list[CommandResult] = []
    if not args.skip_preflight:
        preflight = run_preflight(args, run_dir)
    summary["preflight"] = [asdict(item) for item in preflight]

    live_summary: dict[str, Any] | None = None
    if not args.skip_live_queries:
        live_summary = run_live_query_benchmark(
            queries=queries,
            repeats=args.repeats,
            top_k=args.top_k,
            reranking=args.rerank,
            run_dir=run_dir,
        )
    summary["live_query_benchmark"] = live_summary

    shadow_summary: dict[str, Any] | None = None
    if args.shadow_rebuild:
        shadow_summary = run_shadow_rebuild(args, run_dir)
    summary["shadow_rebuild"] = shadow_summary

    gates = build_gates(
        preflight=preflight,
        live_summary=live_summary,
        shadow_summary=shadow_summary,
        require_hit_at=live_require_hit_at(args),
        thresholds=live_thresholds(args),
    )
    summary["gates"] = gates
    write_json(run_dir / "summary.json", summary)
    report_path = write_markdown_report(run_dir, summary)

    print(f"Benchmark run directory: {run_dir}")
    print(f"Summary: {run_dir / 'summary.json'}")
    print(f"Report: {report_path}")
    print(f"Overall status: {gates['overall_status'].upper()}")
    if args.strict and gates["overall_status"] != "pass":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
