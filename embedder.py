"""
BGE-M3 Embedder — Dense + Sparse vector encoding.

Uses BAAI/bge-m3 model with GPU acceleration for efficient batch encoding.
Returns dense vectors (1024 dims) for hybrid search.

NOTE (2026-04-13): FP16 enabled for ~65% throughput gain and ~50% VRAM savings.
Accuracy impact is negligible for retrieval tasks (~0.002 recall delta).
Dynamic batch sizing adjusts on OOM — try high, halve on failure.

Sparse/lexical weights are NOT available via sentence-transformers for BGE-M3.
The system uses a standalone BM25 index for the sparse/lexical leg of hybrid search.
See bm25_index.py for the BM25 implementation.

VRAM usage: ~1.1GB on CUDA with FP16 (was ~2.2GB in FP32).
"""

import gc
import logging
import os
import threading
from pathlib import Path
from typing import Any, Iterable, Optional, cast

import numpy as np

try:
    from .config import config
except ImportError:
    from config import config


def _get_torch():
    """Lazy torch import."""
    import torch

    return torch


logger = logging.getLogger(__name__)


def _get_huggingface_home() -> Path:
    """Return the Hugging Face cache root used by transformers."""
    hf_home = os.getenv("HF_HOME")
    if hf_home:
        return Path(hf_home)

    xdg_cache_home = os.getenv("XDG_CACHE_HOME")
    if xdg_cache_home:
        return Path(xdg_cache_home) / "huggingface"

    return Path.home() / ".cache" / "huggingface"


def _get_model_cache_dir(model_name: str) -> Path:
    """Map a Hugging Face model name to its local cache directory."""
    return _get_huggingface_home() / "hub" / f"models--{model_name.replace('/', '--')}"


def _has_local_model_cache(model_name: str) -> bool:
    """Return True when a model snapshot already exists locally."""
    snapshots_dir = _get_model_cache_dir(model_name) / "snapshots"
    if not snapshots_dir.exists():
        return False

    for snapshot_dir in snapshots_dir.iterdir():
        if not snapshot_dir.is_dir():
            continue
        if (snapshot_dir / "modules.json").exists() or (
            snapshot_dir / "config.json"
        ).exists():
            return True

    return False


def _get_local_model_snapshot(model_name: str) -> Optional[Path]:
    """Return the newest cached snapshot path for a model, if one exists."""
    snapshots_dir = _get_model_cache_dir(model_name) / "snapshots"
    if not snapshots_dir.exists():
        return None

    candidates: list[Path] = []
    for snapshot_dir in snapshots_dir.iterdir():
        if not snapshot_dir.is_dir():
            continue
        if (snapshot_dir / "modules.json").exists() or (
            snapshot_dir / "config.json"
        ).exists():
            candidates.append(snapshot_dir)

    if not candidates:
        return None

    return max(candidates, key=lambda path: path.stat().st_mtime)


def _enable_huggingface_offline_mode(model_name: str) -> bool:
    """Force offline loads when the requested model is already cached locally."""
    if not _has_local_model_cache(model_name):
        return False

    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("HF_DATASETS_OFFLINE", "1")

    # huggingface_hub / transformers snapshot offline mode into module globals on import,
    # so update those flags too when the libraries were imported earlier in-process.
    try:
        import huggingface_hub.constants as hf_constants

        hf_constants.HF_HUB_OFFLINE = True
    except Exception:
        pass

    try:
        import transformers.utils.hub as transformers_hub

        setattr(transformers_hub, "HF_HUB_OFFLINE", True)
    except Exception:
        pass

    return True


class SentenceTransformersEmbedder:
    """Default BGE-M3 embedding backend using sentence-transformers."""

    def __init__(
        self,
        model_name: str = "BAAI/bge-m3",
        device: str = "cuda",
        batch_size: int = 32,
    ):
        """
        Initialize the embedder. Downloads model on first run (~2.3GB).

        Args:
            model_name: HuggingFace model identifier
            device: "cuda" or "cpu"
            batch_size: Initial batch size (dynamically adjusted on OOM)
        """
        torch = _get_torch()
        self.model_name = model_name
        self.requested_device = (device or "cuda").lower()
        self.device = (
            self.requested_device
            if self.requested_device != "cuda" or torch.cuda.is_available()
            else "cpu"
        )
        self.batch_size = batch_size
        self._model = None
        self._fp16_enabled = False
        self._effective_batch_size = batch_size  # Dynamic batch tracking
        if self.requested_device == "cuda" and self.device != "cuda":
            logger.warning(
                "CUDA was requested for embeddings, but this Torch runtime has no GPU access. "
                "Falling back to CPU."
            )

    @property
    def model(self):
        """Lazy-load the model on first access."""
        if self._model is None:
            logger.info(
                f"Loading BGE-M3 model via sentence-transformers ({self.device})..."
            )
            try:
                from sentence_transformers import SentenceTransformer

                offline_mode = _enable_huggingface_offline_mode(self.model_name)
                model_ref = self.model_name
                if offline_mode:
                    snapshot_path = _get_local_model_snapshot(self.model_name)
                    logger.info(
                        "Using cached Hugging Face files for %s in offline mode.",
                        self.model_name,
                    )
                    if snapshot_path is not None:
                        model_ref = str(snapshot_path)
                        logger.info(
                            "Loading cached snapshot for %s from %s",
                            self.model_name,
                            model_ref,
                        )
                self._model = SentenceTransformer(
                    model_ref,
                    device=self.device,
                    trust_remote_code=True,
                    local_files_only=offline_mode,
                )

                # Enable FP16 on GPU for ~65% throughput gain and ~50% VRAM savings
                if self.device == "cuda":
                    torch = _get_torch()
                    self._model.half()
                    self._fp16_enabled = True
                    # Verify dtype
                    base_dtype = self._model[0].auto_model.dtype
                    logger.info(
                        f"BGE-M3 loaded in FP16 on {torch.cuda.get_device_name(0)} (base: {base_dtype})"
                    )

                logger.info("BGE-M3 model loaded successfully (sentence-transformers)")
            except Exception as e:
                logger.error(f"Failed to load BGE-M3 via sentence-transformers: {e}")
                raise
        return self._model

    def encode(
        self,
        texts: list[str],
        return_dense: bool = True,
        return_sparse: bool = True,
        batch_size: Optional[int] = None,
    ) -> dict:
        """
        Encode texts into dense vectors.

        NOTE: sentence-transformers does NOT return sparse/lexical weights
        for BGE-M3. When return_sparse=True, empty dicts are returned as
        placeholders. Use the standalone BM25 index (bm25_index.py) for
        the sparse/lexical leg of hybrid search.

        Dynamic batch sizing: starts at configured batch_size, halves on OOM,
        caches the working size for subsequent calls.

        Args:
            texts: List of text strings to encode
            return_dense: Include dense vector output (always True in practice)
            return_sparse: Placeholder only — use BM25 index for lexical matching
            batch_size: Override default batch size

        Returns:
            Dict with keys: 'dense_vecs' (list of lists), 'lexical_weights' (list of empty dicts)
        """
        if not texts:
            return {"dense_vecs": [], "lexical_weights": []}

        bs = batch_size or self._effective_batch_size

        # Filter out empty strings
        valid_indices = [i for i, t in enumerate(texts) if t and t.strip()]
        valid_texts = [texts[i] for i in valid_indices]

        if not valid_texts:
            return {"dense_vecs": [], "lexical_weights": []}

        # Process in batches to manage VRAM
        all_dense = []

        for i in range(0, len(valid_texts), bs):
            batch = valid_texts[i : i + bs]

            try:
                # sentence-transformers returns numpy array of shape (n, 1024)
                output = self.model.encode(
                    batch,
                    batch_size=bs,
                    show_progress_bar=False,
                    normalize_embeddings=True,
                )

                if return_dense:
                    if isinstance(output, np.ndarray):
                        if output.ndim == 2:
                            all_dense.extend(output.tolist())
                        else:
                            all_dense.append(output.tolist())
                    else:
                        # Fallback for unexpected types
                        for vec in cast(Iterable[Any], output):
                            if hasattr(vec, "tolist"):
                                all_dense.append(vec.tolist())
                            else:
                                all_dense.append(vec)

                # Success — cache this batch size for future calls
                self._effective_batch_size = bs

            except Exception as e:
                error_str = str(e).lower()
                # Dynamic batch sizing: halve on OOM
                if "out of memory" in error_str or "oom" in error_str:
                    new_bs = max(bs // 2, 1)
                    logger.warning(f"OOM at batch_size={bs}, reducing to {new_bs}")
                    self._effective_batch_size = new_bs
                    # Retry this batch at smaller size
                    try:
                        output = self.model.encode(
                            batch,
                            batch_size=new_bs,
                            show_progress_bar=False,
                            normalize_embeddings=True,
                        )
                        if return_dense and isinstance(output, np.ndarray):
                            if output.ndim == 2:
                                all_dense.extend(output.tolist())
                            else:
                                all_dense.append(output.tolist())
                        self._effective_batch_size = new_bs
                        continue
                    except Exception as retry_err:
                        logger.error(f"Encoding error after OOM reduction: {retry_err}")

                else:
                    logger.error(f"Encoding error at batch {i // bs}: {e}")

                # Pad with empty vectors to maintain indices
                if return_dense:
                    all_dense.extend([[0.0] * 1024] * len(batch))

            # Periodic VRAM cleanup
            if i % 1000 == 0:
                self._clear_cache()

        # Re-index to match original input order
        result = {}
        if return_dense:
            full_dense = [[]] * len(texts)
            for idx, orig_i in enumerate(valid_indices):
                full_dense[orig_i] = all_dense[idx]
            result["dense_vecs"] = full_dense

        # Sparse not available — return empty dicts as placeholders
        # BM25 index provides the sparse/lexical leg of hybrid search
        if return_sparse:
            result["lexical_weights"] = [{}] * len(texts)

        return result

    def encode_with_normalization(
        self,
        texts: list[str],
    ) -> dict:
        """Encode with L2-normalized dense vectors for cosine similarity.

        Normalization is already handled by sentence-transformers (normalize_embeddings=True),
        but we re-normalize here for safety and backward compatibility.
        """
        result = self.encode(texts, return_dense=True, return_sparse=True)

        # Normalize dense vectors (double-normalize for safety)
        if "dense_vecs" in result:
            norm_dense = []
            for vec in result["dense_vecs"]:
                if not vec:  # Empty vector
                    norm_dense.append([0.0] * 1024)
                    continue
                arr = np.array(vec, dtype=np.float32)
                norm = np.linalg.norm(arr)
                if norm > 0:
                    arr = arr / norm
                norm_dense.append(arr.tolist())
            result["dense_vecs"] = norm_dense

        return result

    def _clear_cache(self):
        """Free GPU memory."""
        gc.collect()
        if self.device == "cuda":
            _get_torch().cuda.empty_cache()

    def clear_cache(self):
        """Public method to free GPU memory."""
        self._clear_cache()

    def get_device_info(self) -> str:
        """Return current device info."""
        if self.device == "cuda":
            torch = _get_torch()
            return (
                f"CUDA: {torch.cuda.get_device_name(0)} | "
                f"VRAM: {torch.cuda.memory_allocated() / 1e9:.2f}GB / "
                f"{torch.cuda.get_device_properties(0).total_memory / 1e9:.2f}GB"
            )
        return "CPU"


# Module-level singleton
_embedder_lock = threading.Lock()
_embedder = None
_embedder_key: Optional[tuple[str, str, str, int]] = None


def _normalize_backend_name(backend: Optional[str]) -> str:
    value = (
        (backend or getattr(config, "embedding_backend", "sentence_transformers"))
        .strip()
        .lower()
    )
    aliases = {
        "st": "sentence_transformers",
        "sentence-transformer": "sentence_transformers",
        "sentence-transformers": "sentence_transformers",
        "flagembedding": "flagembedding_experimental",
        "flag_embedding": "flagembedding_experimental",
        "flagembedding_experimental": "flagembedding_experimental",
    }
    return aliases.get(value, value)


def _create_embedder(
    backend: str,
    model_name: str,
    device: str,
    batch_size: int,
):
    """Instantiate the configured embedder backend."""
    if backend == "sentence_transformers":
        return SentenceTransformersEmbedder(
            model_name=model_name,
            device=device,
            batch_size=batch_size,
        )

    if backend == "flagembedding_experimental":
        try:
            try:
                from .embedder_flagembedding_experimental import (
                    FlagEmbeddingExperimentalEmbedder,
                )
            except ImportError:
                from embedder_flagembedding_experimental import (
                    FlagEmbeddingExperimentalEmbedder,
                )
        except ImportError as exc:
            raise RuntimeError(
                "The experimental FlagEmbedding backend is not available. "
                "Install FlagEmbedding in an isolated environment before selecting "
                "FILEMIND_EMBEDDING_BACKEND=flagembedding_experimental."
            ) from exc

        return FlagEmbeddingExperimentalEmbedder(
            model_name=model_name,
            device=device,
            batch_size=batch_size,
        )

    raise ValueError(f"Unknown embedding backend: {backend}")


def reset_embedder_singleton():
    """Reset the global embedder singleton. Useful for tests and experiments."""
    global _embedder, _embedder_key
    _embedder = None
    _embedder_key = None


def get_embedder(
    model_name: str = "BAAI/bge-m3",
    device: str = "cuda",
    batch_size: int = 32,
    backend: Optional[str] = None,
):
    """Get or create the global embedder instance in a thread-safe manner."""
    global _embedder, _embedder_key
    normalized_backend = _normalize_backend_name(backend)
    requested_key = (normalized_backend, model_name, device, batch_size)

    if _embedder is None or _embedder_key != requested_key:
        with _embedder_lock:
            if _embedder is None or _embedder_key != requested_key:
                _embedder = _create_embedder(
                    backend=normalized_backend,
                    model_name=model_name,
                    device=device,
                    batch_size=batch_size,
                )
                _embedder_key = requested_key
    return _embedder


def encode_batch(texts: list[str]) -> dict:
    """Convenience function: encode with default embedder."""
    return get_embedder().encode_with_normalization(texts)


# Backward compatibility for code/tests importing Embedder directly.
Embedder = SentenceTransformersEmbedder
