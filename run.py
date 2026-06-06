"""
FileMind CLI — Command-line interface for FileMind.

Usage:
    python run.py scan [--full]       # Run scan/index pipeline
    python run.py search "query"      # Search files
    python run.py stats               # Show statistics
    python run.py duplicates          # Find duplicates
    python run.py health              # Health check
    python run.py runtime             # Show model/device placement
    python run.py dashboard           # Launch web UI
    python run.py classify            # Classify unclassified files
"""

import argparse
import logging
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import config, ensure_dirs
from scan_lock import (
    SCAN_CANCEL_PATH,
    SCAN_LOCK_PATH,
    read_scan_cancel,
    read_scan_lock,
    request_scan_cancel,
    scan_lock,
)

# Ensure runtime directories exist before startup touches the log or index paths.
ensure_dirs()

# ── Logging ──────────────────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, config.log_level, logging.INFO),
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(config.log_file, encoding="utf-8"),
    ],
)
logger = logging.getLogger("filemind.cli")
FILEMIND_RECOVERY_COMMAND = r"C:\AI_STATION\scripts\start_ai_station_session.ps1"


def _validate_optional_dependencies() -> list[str]:
    """Auto-disable optional features only for commands that need FileMind internals.

    Recovery commands such as ``scan-status`` and ``scan-cancel`` must stay
    lightweight enough to work while the embedding/runtime stack is unhealthy.
    """
    from check_deps import validate_all

    return validate_all(config)


def _safe_console_text(value) -> str:
    """Return text that won't crash on legacy Windows console encodings."""
    text = "" if value is None else str(value)
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding, errors="replace")


def _console_print(value=""):
    print(_safe_console_text(value))


def _status_marker(status: str) -> str:
    """Return a compact marker for health/runtime status output."""
    normalized = (status or "").strip().lower()
    if normalized == "ok":
        return "OK "
    if (
        normalized in {"warn", "warning", "partial", "idle", "degraded"}
        or "not available" in normalized
    ):
        return "WARN"
    return "ERR"


def _probe_qdrant_dependency() -> dict:
    """Return a cheap upstream probe without constructing VectorStore."""
    mode = getattr(config, "qdrant_mode", "local").lower()
    if mode != "http":
        return {"status": "not-applicable", "mode": mode}

    qdrant_url = (getattr(config, "qdrant_url", "") or "http://127.0.0.1:6333").rstrip(
        "/"
    )
    ready_url = f"{qdrant_url}/readyz"
    try:
        import requests

        response = requests.get(ready_url, timeout=2)
    except Exception as exc:
        return {
            "status": "unavailable",
            "mode": mode,
            "url": ready_url,
            "message": str(exc),
        }
    return {
        "status": "ok" if 200 <= response.status_code < 300 else "unavailable",
        "mode": mode,
        "url": ready_url,
        "http_status": response.status_code,
    }


def _get_ollama_api_status() -> dict:
    """Return Ollama API health without affecting FileMind vector state."""
    try:
        import requests

        response = requests.get(f"{config.ollama_api_url}/api/tags", timeout=5)
        return {"status": "ok", "code": response.status_code}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def _get_catalog_health() -> dict:
    """Return catalog health without touching Qdrant."""
    from catalog import Catalog

    catalog = Catalog()
    try:
        catalog.init_db()
        return {"status": "ok", "count": catalog.count()}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
    finally:
        catalog.close()


def _get_vector_store_health() -> dict:
    """Return vector health, explicitly degrading when shared Qdrant is down."""
    qdrant = _probe_qdrant_dependency()
    if qdrant.get("status") == "unavailable":
        return {
            "status": "degraded",
            "upstream_dependency": "qdrant-shared",
            "dependency_status": "unavailable",
            "message": "Qdrant is unavailable; catalog/exact/BM25 search fallbacks remain usable.",
            "error": qdrant.get("message"),
            "recovery": FILEMIND_RECOVERY_COMMAND,
        }

    try:
        from vector_store import VectorStore

        vector_store = VectorStore()
        try:
            return {
                "status": "ok",
                "count": vector_store.count(),
                "upstream_dependency": "qdrant-shared"
                if qdrant.get("status") == "ok"
                else None,
                "dependency_status": qdrant.get("status"),
            }
        finally:
            vector_store.close()
    except Exception as exc:
        return {
            "status": "degraded",
            "upstream_dependency": "qdrant-shared"
            if qdrant.get("status") == "ok"
            else None,
            "dependency_status": qdrant.get("status"),
            "message": "Vector store is unavailable; catalog/exact/BM25 search fallbacks remain usable.",
            "error": str(exc),
            "recovery": FILEMIND_RECOVERY_COMMAND,
        }


def _get_gpu_status() -> dict:
    """Return lightweight GPU availability without touching Qdrant."""
    requested_device = str(getattr(config, "embedding_device", "cuda")).lower()
    try:
        import torch

        if torch.cuda.is_available():
            return {
                "status": "ok",
                "torch_version": getattr(torch, "__version__", "unknown"),
                "torch_cuda_version": str(getattr(torch.version, "cuda", None)),
                "device": torch.cuda.get_device_name(0),
                "vram_used_gb": torch.cuda.memory_allocated() / 1e9,
                "vram_total_gb": torch.cuda.get_device_properties(0).total_memory / 1e9,
            }
        status = (
            "error"
            if requested_device.startswith("cuda")
            else "not available (CPU only)"
        )
        return {
            "status": status,
            "torch_version": getattr(torch, "__version__", "unknown"),
            "torch_cuda_version": str(getattr(torch.version, "cuda", None)),
            "message": (
                "CUDA is requested for FileMind embeddings, but this Python runtime "
                "is using a CPU-only Torch build."
                if requested_device.startswith("cuda")
                else "Torch CUDA is not available; CPU mode was explicitly requested."
            ),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _get_embedding_runtime_status() -> dict:
    """Return embedder backend/requested-device/actual-device without full model work."""
    try:
        from embedder import get_embedder

        embedder = get_embedder()
        requested_device = getattr(
            embedder, "requested_device", getattr(config, "embedding_device", "cuda")
        )
        device_info = embedder.get_device_info()
        status = "ok"
        message = None
        if (
            str(requested_device).lower().startswith("cuda")
            and getattr(embedder, "device", "").lower() != "cuda"
        ):
            status = "error"
            message = (
                "FileMind requested CUDA embeddings, but the active Torch runtime cannot access CUDA. "
                "Install the CUDA Torch wheel or explicitly set FILEMIND_EMBEDDING_DEVICE=cpu."
            )
        return {
            "status": status,
            "backend": getattr(config, "embedding_backend", "sentence_transformers"),
            "requested_device": requested_device,
            "device": device_info,
            **({"message": message} if message else {}),
        }
    except Exception as e:
        return {
            "status": "error",
            "backend": getattr(config, "embedding_backend", "sentence_transformers"),
            "requested_device": getattr(config, "embedding_device", "cuda"),
            "error": str(e),
        }


def _get_ollama_runtime_status() -> dict:
    """Return the active Ollama model placement, if the CLI is available."""
    status = {
        "status": "idle",
        "runtime": "ollama",
        "model": getattr(config, "classification_model", ""),
    }
    try:
        result = subprocess.run(
            ["ollama", "ps"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except FileNotFoundError:
        status.update({"status": "error", "error": "ollama CLI not found"})
        return status
    except Exception as e:
        status.update({"status": "error", "error": str(e)})
        return status

    if result.returncode != 0:
        status.update(
            {
                "status": "error",
                "error": (result.stderr or result.stdout or "").strip()
                or "ollama ps failed",
            }
        )
        return status

    lines = [line.rstrip() for line in result.stdout.splitlines() if line.strip()]
    if len(lines) <= 1:
        status["message"] = "No Ollama models are currently loaded."
        return status

    status.update({"status": "ok", "ps_output": lines})
    return status


def _print_health_report(checks: dict, title: str = "System Health"):
    """Render health/runtime status blocks consistently."""
    print(f"\n{'=' * 60}")
    print(title)
    print(f"{'=' * 60}")
    for component, status in checks.items():
        marker = _status_marker(status.get("status", "unknown"))
        print(f"[{marker}] {component}: {status.get('status', 'unknown')}")
        if "backend" in status:
            print(f"      Backend: {status['backend']}")
        if "requested_device" in status:
            print(f"      Requested: {status['requested_device']}")
        if "torch_version" in status:
            print(f"      Torch: {status['torch_version']}")
        if "torch_cuda_version" in status:
            print(f"      Torch CUDA: {status['torch_cuda_version']}")
        if "model" in status:
            print(f"      Model: {status['model']}")
        if "runtime" in status:
            print(f"      Runtime: {status['runtime']}")
        if "upstream_dependency" in status and status["upstream_dependency"]:
            print(f"      Upstream: {status['upstream_dependency']}")
        if "dependency_status" in status and status["dependency_status"]:
            print(f"      Dependency: {status['dependency_status']}")
        if "message" in status:
            _console_print(f"      {status['message']}")
        if "error" in status:
            _console_print(f"      Error: {status['error']}")
        if "recovery" in status:
            _console_print(f"      Recovery: {status['recovery']}")
        if "device" in status:
            _console_print(f"      Device: {status['device']}")
        if "vram_total_gb" in status:
            print(
                f"      VRAM: {status['vram_used_gb']:.1f} / {status['vram_total_gb']:.1f} GB"
            )
        if "count" in status:
            print(f"      Count: {status['count']}")
        if "ps_output" in status:
            for line in status["ps_output"]:
                _console_print(f"      {line}")


# ── Commands ─────────────────────────────────────────────────────────────


def cmd_scan(args):
    """Run scan/index pipeline."""
    ensure_dirs()
    _validate_optional_dependencies()
    if args.prune_excluded and (args.full or args.rebuild):
        raise SystemExit(
            "--prune-excluded is a standalone maintenance mode; do not combine it with --full or --rebuild."
        )

    if args.prune_excluded:
        from nightly import FileMindOrchestrator

        orchestrator = FileMindOrchestrator()
        result = orchestrator.prune_excluded()
        print(f"\n{'=' * 60}")
        print(f"Result: {'SUCCESS' if result.success else 'FAILED'}")
        print(f"  Deleted: {result.files_deleted}")
        print(f"  Pruned excluded: {result.files_pruned}")
        print(f"  Excluded retained: {result.files_excluded_retained}")
        print(f"  Errors: {result.errors}")
        print(f"  Duration: {result.duration_seconds:.1f}s")
        print(f"{'=' * 60}")
        return

    if args.full or args.rebuild:
        from nightly import run_index_pipeline

        scan_mode = "rebuild" if args.rebuild else "full"
        try:
            with scan_lock(scan_mode):
                print(f"Scan lock: {SCAN_LOCK_PATH}")
                result = run_index_pipeline(force_reindex=args.rebuild)
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc
        print(f"\n{'=' * 60}")
        print(f"Result: {'SUCCESS' if result.success else 'FAILED'}")
        print(f"  Files scanned: {result.files_scanned}")
        print(f"  New: {result.files_new}")
        print(f"  Modified: {result.files_modified}")
        print(f"  Moved: {getattr(result, 'files_moved', 0)}")
        print(f"  Deleted: {result.files_deleted}")
        print(f"  Indexed: {result.files_indexed}")
        print(f"  Chunks: {result.chunks_created}")
        print(f"  Errors: {result.errors}")
        print(f"  Duration: {result.duration_seconds:.1f}s")
        print(f"{'=' * 60}")
    else:
        from catalog import Catalog
        from scanner import FileScanner

        # Quick scan: detect changes only
        scanner = FileScanner()
        catalog = Catalog()
        catalog.init_db()

        changes, deleted = scanner.scan()
        summary = scanner.get_changes_summary(changes, deleted)
        prunable_excluded = len(scanner.prunable_excluded_paths)
        retained_excluded = len(scanner.retained_excluded_paths)

        print("\nQuick Scan Results:")
        print(f"  New: {summary['new']}")
        print(f"  Modified: {summary['modified']}")
        print(f"  Moved: {summary.get('moved', 0)}")
        print(f"  Deleted: {summary['deleted']}")
        print(f"  Prunable excluded: {prunable_excluded}")
        print(f"  Retained excluded: {retained_excluded}")
        print(f"  Total: {summary['total_changes']}")

        if changes:
            print("\nChanged files:")
            for c in changes[:20]:
                print(f"  [{c.change_type}] {c.path} ({c.size / 1024:.1f}KB)")
            if len(changes) > 20:
                print(f"  ... and {len(changes) - 20} more")

        catalog.close()


def cmd_scan_status(args):
    """Show current full-scan lock/progress and recovery commands."""
    lock = read_scan_lock()
    cancel = read_scan_cancel()
    if not lock:
        print("No FileMind full/rebuild/repair scan lock is present.")
        print(f"Lock path: {SCAN_LOCK_PATH}")
        return
    print("FileMind scan lock:")
    for key in (
        "pid",
        "mode",
        "status",
        "phase",
        "started_at",
        "heartbeat_at",
        "command",
    ):
        if key in lock:
            _console_print(f"  {key}: {lock[key]}")
    progress = lock.get("progress") if isinstance(lock.get("progress"), dict) else {}
    if progress:
        print("  progress:")
        for key, value in sorted(progress.items()):
            _console_print(f"    {key}: {value}")
    if cancel:
        print("Cancel request:")
        for key, value in sorted(cancel.items()):
            _console_print(f"  {key}: {value}")
    print("\nRecovery commands:")
    print("  Request cooperative cancel:")
    print(
        '    python C:\\AI_STATION\\filemind\\run.py scan-cancel --reason "operator timeout"'
    )
    print("  After the process exits, verify/repair metadata:")
    print("    python C:\\AI_STATION\\filemind\\run.py verify --repair-chunk-counts")


def cmd_scan_cancel(args):
    """Request cooperative cancellation of a running FileMind scan."""
    if not read_scan_lock():
        raise SystemExit(
            f"No scan lock is present at {SCAN_LOCK_PATH}; nothing to cancel."
        )
    payload = request_scan_cancel(args.reason, requested_by=args.requested_by)
    print(f"Cancellation requested: {payload['reason']}")
    print(f"Cancel path: {SCAN_CANCEL_PATH}")


def cmd_search(args):
    """Search files."""
    ensure_dirs()
    _validate_optional_dependencies()
    from search import SearchEngine, hybrid_search

    query = " ".join(args.query)
    ft = args.type if args.type else None
    cat = args.category if args.category else None

    print(f"Searching: {query}")
    if ft:
        print(f"  Type filter: {ft}")
    if cat:
        print(f"  Category filter: {cat}")
    print()

    if args.keyword:
        engine = SearchEngine(reranking=args.rerank)
        results = engine.keyword_search(query, args.top_k)
        if args.rerank:
            results = engine._rerank(query, results, args.top_k)
        engine.close()
    elif args.semantic:
        engine = SearchEngine(reranking=args.rerank)
        results = engine.semantic_search(query, args.top_k)
        if args.rerank:
            results = engine._rerank(query, results, args.top_k)
        engine.close()
    else:
        results = hybrid_search(
            query, args.top_k, ft, cat, use_hyde=args.hyde, reranking=args.rerank
        )

    if not results:
        print("No results found.")
        return

    for i, r in enumerate(results, 1):
        _console_print(f"[{i}] {r.file_path}")
        if r.file_type:
            _console_print(f"    Type: {r.file_type} | Category: {r.category}")
        if r.score:
            _console_print(f"    Score: {r.score:.4f}")
        if getattr(r, "is_protected", False):
            _console_print(
                "    Protected: snippet redacted; use `secrets` for local credential metadata."
            )
        if r.snippet:
            _console_print(f"    {r.snippet[:200]}")
        _console_print()


def cmd_secrets(args):
    """Local protected-lane credential lookup."""
    ensure_dirs()
    from protected_secrets import ProtectedSecretAccessError, lookup_protected_secrets

    roots = args.root or config.scan_roots
    try:
        results = lookup_protected_secrets(
            roots,
            " ".join(args.query),
            reveal=args.reveal,
            explicit_local_disclosure=args.i_understand_local_secret_disclosure,
            max_results=args.top_k,
        )
    except ProtectedSecretAccessError as exc:
        raise SystemExit(str(exc)) from exc

    if not results:
        print("No protected credential candidates found.")
        return

    for i, result in enumerate(results, 1):
        _console_print(f"[{i}] {result.path}")
        _console_print(f"    Service hint: {result.service_hint}")
        if result.revealed:
            _console_print("    Revealed locally:")
            _console_print(result.revealed_text[:2000])
        elif result.redacted_snippet:
            _console_print("    Redacted snippet:")
            _console_print(result.redacted_snippet[:500])
        _console_print()


def cmd_stats(args):
    """Show statistics."""
    ensure_dirs()
    from catalog import Catalog

    catalog = Catalog()
    catalog.init_db()

    stats = catalog.get_stats()
    print("\nFileMind Statistics")
    print(f"{'=' * 40}")
    print(f"Total files:  {stats['total_files']}")
    print(f"Total size:   {stats['total_size_mb']:.1f} MB")
    print(f"Duplicates:   {stats['duplicates']}")
    print()

    print("Categories:")
    for cat, cnt in sorted(stats.get("categories", {}).items()):
        bar = "#" * (cnt // 10 + 1)
        print(f"  {cat:20s} {cnt:5d} {bar}")

    print()
    print("Top Extensions:")
    for ext, cnt in stats.get("top_extensions", {}).items():
        print(f"  {ext:10s} {cnt:5d}")

    # Scan history
    history = catalog.get_scan_history(5)
    if history:
        print()
        print("Recent Scans:")
        for h in history:
            status = h.get("status", "unknown")
            started = time.strftime("%Y-%m-%d %H:%M", time.localtime(h["started_at"]))
            print(
                f"  {started} | {status:8s} | scanned={h['files_scanned']} "
                f"new={h['files_new']} err={h['errors']}"
            )

    catalog.close()


def cmd_duplicates(args):
    """Find and report duplicates."""
    ensure_dirs()
    _validate_optional_dependencies()
    from duplicates import DuplicateDetector

    print("Finding duplicates...")
    detector = DuplicateDetector()
    report = detector.report()

    print(f"\n{'=' * 60}")
    print("Duplicate Report")
    print(f"{'=' * 60}")
    print(f"Exact duplicate groups:  {report['exact_groups']}")
    print(f"Exact duplicate files:   {report['exact_files']}")
    print(f"Semantic duplicate pairs: {report['semantic_pairs']}")
    print(f"Nested duplicate patterns: {report['nested_patterns']}")
    print(f"Estimated savings: {report['estimated_savings']}")

    if report["details"]["exact"]:
        print("\nExact Duplicates:")
        for h, paths in list(report["details"]["exact"].items())[:15]:
            print(f"  Hash {h[:12]}...")
            for p in paths[:5]:
                print(f"    {p}")
            if len(paths) > 5:
                print(f"    ... and {len(paths) - 5} more")

    detector.close()


def cmd_health(args):
    """Health check."""
    ensure_dirs()
    checks = {
        "ollama": _get_ollama_api_status(),
        "catalog": _get_catalog_health(),
        "vector_store": _get_vector_store_health(),
        "gpu": _get_gpu_status(),
        "embedding": _get_embedding_runtime_status(),
        "classifier_runtime": _get_ollama_runtime_status(),
    }
    _print_health_report(checks)


def cmd_runtime(args):
    """Show lightweight runtime placement for embeddings and Ollama models."""
    ensure_dirs()
    checks = {
        "gpu": _get_gpu_status(),
        "embedding": _get_embedding_runtime_status(),
        "classifier_runtime": _get_ollama_runtime_status(),
    }
    _print_health_report(checks, title="Runtime Placement")


def cmd_dashboard(args):
    """Launch web dashboard."""
    ensure_dirs()
    from dashboard import launch_dashboard

    port = args.port if args.port else config.dashboard_port
    print(f"Launching dashboard at http://localhost:{port}")
    launch_dashboard(port=port)


def cmd_classify(args):
    """Classify unclassified files."""
    ensure_dirs()
    _validate_optional_dependencies()
    from catalog import Catalog
    from classifier import Classifier

    catalog = Catalog()
    catalog.init_db()

    # Get unclassified files
    files = catalog.get_files_by_category("unknown")
    if not files:
        print("No unclassified files.")
        catalog.close()
        return

    print(f"Classifying {len(files)} files...")

    classifier = Classifier()
    file_data = [
        {
            "path": f["path"],
            "ext": f.get("ext", ""),
            "content_summary": f.get("content_summary", ""),
        }
        for f in files
    ]

    results = classifier.classify(file_data)
    classified = 0
    for r in results:
        if r["category"] != "unknown":
            catalog.update_category(r["path"], r["category"], r["confidence"])
            classified += 1

    catalog.conn.commit()  # Persist results to DB
    print(f"Classified: {classified} files")
    print(f"Still unknown: {len(results) - classified}")

    catalog.close()


def cmd_interactive(args):
    """Interactive REPL mode for fast queries."""
    ensure_dirs()
    _validate_optional_dependencies()
    from search import SearchEngine

    print("Initializing Search Engine (loading models)...")

    # Instantiate once to keep models hot
    engine = SearchEngine(reranking=args.rerank)
    print("Search Engine ready! Type 'exit' or 'quit' to close.")
    print(
        "Usage: <query> [--hyde] [--type .pdf] [--category code] or use inline type:pdf"
    )

    while True:
        try:
            raw_input = input("\nfilemind> ")
        except (KeyboardInterrupt, EOFError):
            break

        if raw_input.strip().lower() in ("exit", "quit"):
            break

        if not raw_input.strip():
            continue

        use_hyde = args.hyde
        q = raw_input
        if "--hyde" in q:
            use_hyde = True
            q = q.replace("--hyde", "")

        q = q.strip()
        if not q:
            continue

        top_k = args.top_k
        start_time = time.time()

        results = engine.search(q, top_k=top_k, use_hyde=use_hyde, use_hybrid=True)
        duration = time.time() - start_time

        if not results:
            print(f"No results found in {duration:.2f}s.")
            continue

        print(f"Found {len(results)} results in {duration:.2f}s:\n")
        for i, r in enumerate(results, 1):
            print(f"[{i}] {r.file_path}")
            if r.file_type:
                print(f"    Type: {r.file_type} | Category: {r.category}")
            if r.score:
                print(f"    Score: {r.score:.4f}")
            if getattr(r, "is_protected", False):
                print(
                    "    Protected: snippet redacted; use `secrets` for local credential metadata."
                )
            if r.snippet:
                print(f"    {r.snippet[:150].replace(chr(10), ' ')}")
            print()

    engine.close()


# ── Argument Parser ──────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="filemind",
        description="FileMind — PC-Wide Semantic File Indexing & Search",
    )
    sub = parser.add_subparsers(dest="command", help="Command to run")

    # scan
    p_scan = sub.add_parser("scan", help="Run scan/index pipeline")
    p_scan.add_argument(
        "--full",
        action="store_true",
        help="Run full pipeline (extract, embed, classify)",
    )
    p_scan.add_argument(
        "--rebuild",
        action="store_true",
        help="Force re-index all files (re-chunk, re-embed)",
    )
    p_scan.add_argument(
        "--prune-excluded",
        action="store_true",
        help="Prune files that are still on disk but are now intentionally excluded from the live index",
    )

    sub.add_parser(
        "scan-status",
        help="Show full-scan lock heartbeat/progress and recovery commands",
    )
    p_scan_cancel = sub.add_parser(
        "scan-cancel", help="Request cooperative cancellation of a running full scan"
    )
    p_scan_cancel.add_argument(
        "--reason", required=True, help="Human-readable cancellation reason"
    )
    p_scan_cancel.add_argument(
        "--requested-by",
        default="operator",
        help="Requester label recorded in the cancel file",
    )

    # search
    p_search = sub.add_parser("search", help="Search files")
    p_search.add_argument("query", nargs="+", help="Search query")
    p_search.add_argument("--type", help="Filter by file extension")
    p_search.add_argument("--category", help="Filter by category")
    p_search.add_argument("--top-k", type=int, default=20, help="Max results")
    p_search.add_argument("--keyword", action="store_true", help="Keyword-only search")
    p_search.add_argument(
        "--semantic", action="store_true", help="Semantic-only search"
    )
    p_search.add_argument(
        "--rerank", action="store_true", help="Enable cross-encoder reranking"
    )
    p_search.add_argument(
        "--hyde", action="store_true", help="Enable HyDE query expansion via Ollama"
    )

    # protected local credential lookup
    p_secrets = sub.add_parser(
        "secrets", help="Protected local-only credential metadata lookup"
    )
    p_secrets.add_argument("query", nargs="*", help="Credential/service/path query")
    p_secrets.add_argument(
        "--root",
        action="append",
        help="Root to inspect; defaults to FileMind scan roots",
    )
    p_secrets.add_argument("--top-k", type=int, default=20, help="Max results")
    p_secrets.add_argument(
        "--reveal", action="store_true", help="Reveal values locally"
    )
    p_secrets.add_argument(
        "--i-understand-local-secret-disclosure",
        action="store_true",
        help="Required with --reveal; confirms this local session may display secrets",
    )

    # stats
    sub.add_parser("stats", help="Show statistics")

    # duplicates
    sub.add_parser("duplicates", help="Find duplicate files")

    # health
    sub.add_parser("health", help="System health check")
    sub.add_parser("runtime", help="Show embedding/Ollama device placement")

    # dashboard
    p_dash = sub.add_parser("dashboard", help="Launch web dashboard")
    p_dash.add_argument("--port", type=int, help="Port number")

    # classify
    sub.add_parser("classify", help="Classify unclassified files")

    # deps
    sub.add_parser("deps", help="Check dependency status for optional features")

    # interactive
    p_repl = sub.add_parser("interactive", help="Interactive REPL mode")
    p_repl.add_argument("--top-k", type=int, default=20, help="Max results")
    p_repl.add_argument(
        "--rerank", action="store_true", help="Enable cross-encoder reranking"
    )
    p_repl.add_argument(
        "--hyde", action="store_true", help="Enable HyDE query expansion via Ollama"
    )

    # verify
    p_verify = sub.add_parser("verify", help="Verify 100% scan completeness")
    p_verify.add_argument(
        "--repair-missing",
        action="store_true",
        help="Target-index a small verify missing-from-catalog set without running scan --full",
    )
    p_verify.add_argument(
        "--repair-limit",
        type=int,
        default=25,
        help="Maximum missing files the targeted repair mode may index (default: 25)",
    )
    p_verify.add_argument(
        "--repair-chunk-counts",
        action="store_true",
        help="Repair catalog chunk_count metadata from Qdrant when catalog paths are complete",
    )

    return parser


def cmd_deps(args):
    """Check dependency status for all optional features."""
    from check_deps import DependencyChecker

    checker = DependencyChecker()
    _console_print(checker.report())


def cmd_verify(args):
    """Verify scan completeness."""
    from verify import (
        build_verification_report,
        render_verification_report,
        repair_catalog_chunk_counts_from_vectors,
    )

    report = build_verification_report()
    _console_print(render_verification_report(report))

    repair_missing = bool(getattr(args, "repair_missing", False))
    repair_chunk_counts = bool(getattr(args, "repair_chunk_counts", False))

    if not repair_missing and not repair_chunk_counts:
        if str(report.get("status", "")).upper() == "FAIL":
            raise SystemExit("FileMind verify failed; see drift details above.")
        return

    if report.get("scan_in_progress"):
        raise SystemExit(
            "Targeted repair refused: a FileMind scan or repair is already in progress. "
            "Rerun verify after it completes."
        )

    repaired_report = report

    if repair_missing:
        missing_paths = list(repaired_report.get("missing_paths") or [])
        if not missing_paths:
            print("Targeted missing-file repair: no missing catalog paths to index.")
        else:
            if args.repair_limit < 1:
                raise SystemExit("--repair-limit must be at least 1")
            if len(missing_paths) > args.repair_limit:
                raise SystemExit(
                    f"Targeted repair refused {len(missing_paths)} missing paths; "
                    f"limit is {args.repair_limit}. Increase --repair-limit only after reviewing the sample."
                )

            try:
                from nightly import FileMindOrchestrator

                with scan_lock("repair_missing"):
                    print(f"Scan lock: {SCAN_LOCK_PATH}")
                    orchestrator = FileMindOrchestrator()
                    try:
                        result = orchestrator.repair_missing_index_entries(
                            missing_paths,
                            max_files=args.repair_limit,
                        )
                    finally:
                        orchestrator.catalog.close()
                        orchestrator.vector_store.close()
            except RuntimeError as exc:
                raise SystemExit(str(exc)) from exc

            print(
                f"\nTargeted Missing-File Repair Result: {'SUCCESS' if result.success else 'FAILED'}"
            )
            print(f"  Missing paths requested: {len(missing_paths)}")
            print(f"  Files indexed: {result.files_indexed}")
            print(f"  Chunks: {result.chunks_created}")
            print(f"  Errors: {result.errors}")
            for message in result.error_messages[:5]:
                _console_print(f"  Error: {message}")

            if not result.success:
                raise SystemExit(
                    "Targeted missing-file repair failed; see errors above."
                )

            repaired_report = build_verification_report()
            _console_print(render_verification_report(repaired_report))

    if repair_chunk_counts:
        if repaired_report.get("scan_in_progress"):
            raise SystemExit(
                "Chunk-count repair refused: a FileMind scan or repair is already in progress."
            )
        if int(repaired_report.get("missing_from_catalog_count") or 0) or int(
            repaired_report.get("catalog_only_count") or 0
        ):
            raise SystemExit(
                "Chunk-count repair refused: catalog paths are not complete. "
                "Resolve missing/catalog-only drift before syncing chunk counts."
            )
        if str(repaired_report.get("vector_target_kind", "")).lower() != "shared":
            raise SystemExit(
                "Chunk-count repair refused: vector target is not the shared FileMind Qdrant target."
            )

        try:
            with scan_lock("repair_chunk_counts"):
                print(f"Scan lock: {SCAN_LOCK_PATH}")
                chunk_repair = repair_catalog_chunk_counts_from_vectors()
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc

        print(
            f"\nChunk-Count Repair Result: {'SUCCESS' if chunk_repair.get('success') else 'FAILED'}"
        )
        print(f"  Rows updated: {chunk_repair.get('updated', 0)}")
        print(f"  Message: {chunk_repair.get('message', '')}")
        for path, before, after in list(chunk_repair.get("updates") or [])[:10]:
            _console_print(f"  {path}: {before} -> {after}")
        if not chunk_repair.get("success"):
            raise SystemExit("Chunk-count repair failed; see details above.")

        repaired_report = build_verification_report()
        _console_print(render_verification_report(repaired_report))

    if str(repaired_report.get("status", "")).upper() == "FAIL":
        raise SystemExit(
            "FileMind verify still failed after targeted repair; see drift details above."
        )


# ── Main ─────────────────────────────────────────────────────────────────

COMMANDS = {
    "scan": cmd_scan,
    "scan-status": cmd_scan_status,
    "scan-cancel": cmd_scan_cancel,
    "search": cmd_search,
    "secrets": cmd_secrets,
    "stats": cmd_stats,
    "duplicates": cmd_duplicates,
    "health": cmd_health,
    "runtime": cmd_runtime,
    "dashboard": cmd_dashboard,
    "classify": cmd_classify,
    "interactive": cmd_interactive,
    "verify": cmd_verify,
    "deps": cmd_deps,
}


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    cmd = COMMANDS.get(args.command)
    if cmd:
        cmd(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
