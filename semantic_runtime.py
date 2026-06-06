"""Packaged semantic-runtime probe for the FileMind desktop sidecar.

The normal FileMind API can start in degraded/catalog-only mode when the vector
stack is absent or Qdrant is down. The desktop installer path also needs a
separate proof that the heavy semantic dependencies can be bundled into an
app-owned executable without relying on a user-installed Python interpreter or
user-profile model caches.

This module performs that proof without downloading model blobs or touching the
production FileMind index. It verifies imports, a tiny Torch CPU operation, and
the app-owned Hugging Face / sentence-transformers / Torch cache wiring. Model
availability is reported as ``cached`` or ``setup_required``; the latter is OK
for installer smoke tests unless the caller explicitly requires a seeded local
model.
"""

from __future__ import annotations

import importlib.metadata as metadata
import json
import os
import sys
from pathlib import Path
from typing import Any


def _resolve_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def _is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _version(package_name: str) -> str:
    try:
        return metadata.version(package_name)
    except metadata.PackageNotFoundError:
        module_name = {
            "qdrant-client": "qdrant_client",
            "rank-bm25": "rank_bm25",
            "sentence-transformers": "sentence_transformers",
        }.get(package_name, package_name.replace("-", "_"))
        try:
            module = __import__(module_name)
        except Exception:
            return "missing"
        return str(getattr(module, "__version__", "importable"))


def _dependency_versions() -> dict[str, str]:
    return {
        "torch": _version("torch"),
        "sentence-transformers": _version("sentence-transformers"),
        "transformers": _version("transformers"),
        "qdrant-client": _version("qdrant-client"),
        "rank-bm25": _version("rank-bm25"),
        "numpy": _version("numpy"),
    }


def _torch_probe() -> dict[str, Any]:
    import torch

    tensor_factory = getattr(torch, "tensor")
    cuda = getattr(torch, "cuda")
    value = tensor_factory([1.0, 2.0, 3.0]).sum().item()
    return {
        "status": "ok" if value == 6.0 else "error",
        "version": getattr(torch, "__version__", "unknown"),
        "cpu_tensor_sum": value,
        "cuda_available": bool(cuda.is_available()),
    }


def _sentence_transformers_probe() -> dict[str, Any]:
    import sentence_transformers
    from sentence_transformers import CrossEncoder, SentenceTransformer

    return {
        "status": "ok",
        "version": getattr(sentence_transformers, "__version__", "unknown"),
        "sentence_transformer_class": SentenceTransformer.__name__,
        "cross_encoder_class": CrossEncoder.__name__,
    }


def _transformers_probe() -> dict[str, Any]:
    import transformers

    return {
        "status": "ok",
        "version": getattr(transformers, "__version__", "unknown"),
    }


def _model_cache_status(model_name: str) -> dict[str, Any]:
    from filemind.embedder import (
        _get_local_model_snapshot,
        _get_model_cache_dir,
        _has_local_model_cache,
    )

    cache_dir = _get_model_cache_dir(model_name)
    snapshot = _get_local_model_snapshot(model_name)
    cached = _has_local_model_cache(model_name)
    return {
        "embedding_model": model_name,
        "status": "cached" if cached else "setup_required",
        "cache_dir": str(cache_dir),
        "snapshot": str(snapshot) if snapshot is not None else None,
    }


def probe_semantic_runtime(*, require_cached_model: bool = False) -> dict[str, Any]:
    """Return a JSON-serializable semantic runtime packaging report."""
    from filemind.config import config

    # The probe must never download models. These process-local flags make the
    # packaging check deterministic even on a machine with network access.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_DATASETS_OFFLINE"] = "1"

    app_data_raw = os.getenv("FILEMIND_APP_DATA_DIR")
    app_data = _resolve_path(app_data_raw) if app_data_raw else None
    model_cache_root = _resolve_path(
        os.getenv("FILEMIND_MODEL_CACHE_DIR", str(config.huggingface_cache_dir.parent))
    )
    hf_home = _resolve_path(os.getenv("HF_HOME", str(config.huggingface_cache_dir)))
    hf_hub_cache = _resolve_path(os.getenv("HF_HUB_CACHE", str(hf_home / "hub")))
    sentence_transformers_home = _resolve_path(
        os.getenv(
            "SENTENCE_TRANSFORMERS_HOME",
            str(model_cache_root / "sentence-transformers"),
        )
    )
    torch_home = _resolve_path(os.getenv("TORCH_HOME", str(model_cache_root / "torch")))

    for path in (
        model_cache_root,
        hf_home,
        hf_hub_cache,
        sentence_transformers_home,
        torch_home,
    ):
        path.mkdir(parents=True, exist_ok=True)

    cache_is_app_owned = bool(app_data) and all(
        _is_relative_to(path, app_data)
        for path in (
            model_cache_root,
            hf_home,
            hf_hub_cache,
            sentence_transformers_home,
            torch_home,
        )
    )

    dependencies = _dependency_versions()
    errors: list[str] = []
    probes: dict[str, Any] = {}

    for name, probe_func in (
        ("torch", _torch_probe),
        ("sentence_transformers", _sentence_transformers_probe),
        ("transformers", _transformers_probe),
    ):
        try:
            probes[name] = probe_func()
        except (
            Exception
        ) as exc:  # pragma: no cover - exercised by packaged smoke checks
            probes[name] = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
            errors.append(f"{name}: {type(exc).__name__}: {exc}")

    requested_embedding_device = str(
        getattr(config, "embedding_device", "cuda")
    ).lower()
    raw_torch_probe = probes.get("torch")
    torch_probe: dict[str, Any] = (
        raw_torch_probe if isinstance(raw_torch_probe, dict) else {}
    )
    if (
        requested_embedding_device.startswith("cuda")
        and torch_probe.get("status") == "ok"
        and not bool(torch_probe.get("cuda_available"))
    ):
        errors.append(
            "FileMind requested CUDA embeddings, but the packaged Torch runtime cannot access CUDA"
        )

    try:
        model = _model_cache_status(config.embedding_model)
    except Exception as exc:  # pragma: no cover - exercised by packaged smoke checks
        model = {
            "embedding_model": getattr(config, "embedding_model", "unknown"),
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
        }
        errors.append(f"model_cache: {type(exc).__name__}: {exc}")

    if require_cached_model and model.get("status") != "cached":
        errors.append(
            f"embedding model is not cached in the app-owned model cache: {model.get('cache_dir')}"
        )
    if not cache_is_app_owned:
        errors.append("semantic model caches are not under FILEMIND_APP_DATA_DIR")

    return {
        "status": "ok" if not errors else "blocked",
        "python_runtime": sys.executable,
        "packaged": bool(getattr(sys, "frozen", False)),
        "requested_embedding_device": requested_embedding_device,
        "dependencies": dependencies,
        "probes": probes,
        "cache": {
            "app_data": str(app_data) if app_data else None,
            "model_cache_root": str(model_cache_root),
            "hf_home": str(hf_home),
            "hf_hub_cache": str(hf_hub_cache),
            "sentence_transformers_home": str(sentence_transformers_home),
            "torch_home": str(torch_home),
            "is_app_owned": cache_is_app_owned,
            "offline_flags": {
                "HF_HUB_OFFLINE": os.getenv("HF_HUB_OFFLINE"),
                "TRANSFORMERS_OFFLINE": os.getenv("TRANSFORMERS_OFFLINE"),
                "HF_DATASETS_OFFLINE": os.getenv("HF_DATASETS_OFFLINE"),
            },
        },
        "model": model,
        "errors": errors,
    }


def main() -> int:
    report = probe_semantic_runtime()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("status") == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
