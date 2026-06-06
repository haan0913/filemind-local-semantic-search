"""Desktop sidecar entrypoint for the FileMind API.

This module is intentionally small and import-order sensitive: it resolves
desktop app-data paths before importing ``filemind.api`` so the packaged
backend does not default to the source-tree ``filemind/.index`` directory.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path


if __package__ in {None, ""}:
    # Running as ``python filemind/sidecar.py`` or as the PyInstaller entry
    # script should still be able to import the package by name.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _default_app_data_dir() -> Path:
    """Return the normal per-user desktop app-data root for FileMind."""
    base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
    if base:
        return Path(base) / "AI_STATION" / "FileMind"
    return Path.home() / ".ai_station" / "filemind"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the FileMind API as a desktop sidecar."
    )
    parser.add_argument("--host", default=os.getenv("FILEMIND_API_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port", type=int, default=int(os.getenv("FILEMIND_API_PORT", "8072"))
    )
    parser.add_argument(
        "--app-data",
        type=Path,
        default=Path(os.getenv("FILEMIND_APP_DATA_DIR", str(_default_app_data_dir()))),
        help="Per-user app-owned data directory. Defaults to LOCALAPPDATA/AI_STATION/FileMind.",
    )
    parser.add_argument(
        "--ai-station-root",
        type=Path,
        default=None,
        help="Optional content/config root. Defaults to <app-data>/workspace when AI_STATION_ROOT is unset.",
    )
    parser.add_argument(
        "--qdrant-url",
        default=os.getenv("FILEMIND_QDRANT_URL", "http://127.0.0.1:6333"),
        help="Shared/native Qdrant URL used by the packaged API.",
    )
    parser.add_argument(
        "--model-cache",
        type=Path,
        default=None,
        help="App-owned Hugging Face / Torch model cache. Defaults to <app-data>/models.",
    )
    parser.add_argument(
        "--self-test-semantic-runtime",
        action="store_true",
        help="Run the packaged semantic runtime dependency/cache probe and exit instead of starting the API server.",
    )
    parser.add_argument(
        "--semantic-runtime-report",
        type=Path,
        default=None,
        help="Optional JSON report path for --self-test-semantic-runtime.",
    )
    parser.add_argument(
        "--require-cached-embedding-model",
        action="store_true",
        help="Make --self-test-semantic-runtime fail unless the embedding model is already present in the app-owned cache.",
    )
    parser.add_argument("--log-level", default=os.getenv("LOG_LEVEL", "INFO"))
    return parser


def configure_sidecar_environment(args: argparse.Namespace) -> dict[str, str]:
    """Create sidecar directories and set FileMind env vars before imports."""
    app_data = Path(args.app_data).expanduser().resolve()
    index_dir = app_data / "index"
    log_dir = app_data / "logs"
    model_cache_root = (
        Path(getattr(args, "model_cache", None) or app_data / "models")
        .expanduser()
        .resolve()
    )
    hf_home = model_cache_root / "huggingface"
    hf_hub_cache = hf_home / "hub"
    sentence_transformers_home = model_cache_root / "sentence-transformers"
    torch_home = model_cache_root / "torch"
    workspace_root = (
        Path(args.ai_station_root).expanduser().resolve()
        if args.ai_station_root
        else app_data / "workspace"
    )

    for directory in (
        app_data,
        index_dir,
        log_dir,
        model_cache_root,
        hf_home,
        hf_hub_cache,
        sentence_transformers_home,
        torch_home,
        workspace_root,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    configured = {
        "FILEMIND_APP_DATA_DIR": str(app_data),
        "FILEMIND_INDEX_DIR": str(index_dir),
        "FILEMIND_BM25_INDEX_PATH": str(index_dir / "bm25_index.json"),
        "FILEMIND_PROGRESS_FILE": str(index_dir / "nightly_progress.json"),
        "FILEMIND_QDRANT_MODE": "http",
        "FILEMIND_QDRANT_URL": str(args.qdrant_url),
        "FILEMIND_API_HOST": str(args.host),
        "FILEMIND_API_PORT": str(args.port),
        "FILEMIND_MODEL_CACHE_DIR": str(model_cache_root),
        "FILEMIND_HUGGINGFACE_CACHE_DIR": str(hf_home),
        "HF_HOME": str(hf_home),
        "HF_HUB_CACHE": str(hf_hub_cache),
        "SENTENCE_TRANSFORMERS_HOME": str(sentence_transformers_home),
        "TORCH_HOME": str(torch_home),
        "LOG_LEVEL": str(args.log_level).upper(),
    }
    if "AI_STATION_ROOT" not in os.environ:
        configured["AI_STATION_ROOT"] = str(workspace_root)

    for key, value in configured.items():
        os.environ[key] = value

    log_file = log_dir / "filemind-api-sidecar.log"
    logging.basicConfig(
        level=getattr(logging, configured["LOG_LEVEL"], logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
        force=True,
    )
    configured["FILEMIND_SIDECAR_LOG_FILE"] = str(log_file)
    return configured


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configured = configure_sidecar_environment(args)
    logger = logging.getLogger("filemind.sidecar")
    logger.info(
        "Starting FileMind sidecar with app_data=%s",
        configured["FILEMIND_APP_DATA_DIR"],
    )

    if args.self_test_semantic_runtime:
        from filemind.semantic_runtime import probe_semantic_runtime

        report = probe_semantic_runtime(
            require_cached_model=args.require_cached_embedding_model
        )
        output = json.dumps(report, indent=2, sort_keys=True)
        if args.semantic_runtime_report:
            args.semantic_runtime_report.parent.mkdir(parents=True, exist_ok=True)
            args.semantic_runtime_report.write_text(output + "\n", encoding="utf-8")
        print(output)
        return 0 if report.get("status") == "ok" else 2

    import uvicorn
    from filemind.api import app

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level=str(args.log_level).lower(),
        access_log=True,
        log_config=None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
