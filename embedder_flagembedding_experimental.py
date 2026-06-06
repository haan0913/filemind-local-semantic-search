"""
Experimental BGE-M3 backend using FlagEmbedding.

This module is intentionally isolated from the default runtime path.
It is loaded only when FILEMIND_EMBEDDING_BACKEND=flagembedding_experimental
is selected, so production remains on the stable sentence-transformers path.
"""

from __future__ import annotations

import gc
import importlib
import logging
from typing import Optional

import numpy as np

try:
    from .config import config
    from .embedder import _enable_huggingface_offline_mode, _get_local_model_snapshot, _get_torch
except ImportError:
    from config import config
    from embedder import _enable_huggingface_offline_mode, _get_local_model_snapshot, _get_torch

logger = logging.getLogger(__name__)


class FlagEmbeddingExperimentalEmbedder:
    """Optional BGE-M3 backend that returns real lexical weights when available."""

    def __init__(
        self,
        model_name: str = "BAAI/bge-m3",
        device: str = "cuda",
        batch_size: int = 32,
    ):
        torch = _get_torch()
        self.model_name = model_name
        self.requested_device = (device or "cuda").lower()
        self.device = self.requested_device if self.requested_device != "cuda" or torch.cuda.is_available() else "cpu"
        self.batch_size = batch_size
        self._model = None
        if self.requested_device == "cuda" and self.device != "cuda":
            logger.warning(
                "CUDA was requested for the experimental embedding backend, but this Torch runtime "
                "has no GPU access. Falling back to CPU."
            )

    @property
    def model(self):
        """Lazy-load BGEM3FlagModel only when the experimental backend is selected."""
        if self._model is None:
            try:
                flag_embedding = importlib.import_module("FlagEmbedding")
                model_cls = getattr(flag_embedding, "BGEM3FlagModel")
            except ImportError as exc:
                raise RuntimeError(
                    "FlagEmbedding is not installed in this environment. "
                    "Use a separate experimental venv before enabling this backend."
                ) from exc

            offline_mode = _enable_huggingface_offline_mode(self.model_name)
            if offline_mode:
                logger.info(
                    "Using cached Hugging Face files for %s in offline mode (FlagEmbedding backend).",
                    self.model_name,
                )
            model_load_path = self.model_name
            if offline_mode:
                snapshot_path = _get_local_model_snapshot(self.model_name)
                if snapshot_path is not None:
                    model_load_path = str(snapshot_path)
                    logger.info(
                        "Resolved cached snapshot for %s to %s",
                        self.model_name,
                        model_load_path,
                    )

            logger.info("Loading experimental BGEM3FlagModel backend (%s)...", self.device)
            self._model = model_cls(
                model_load_path,
                use_fp16=self.device == "cuda",
            )
            logger.info("Experimental BGEM3FlagModel backend loaded successfully")
        return self._model

    def encode(
        self,
        texts: list[str],
        return_dense: bool = True,
        return_sparse: bool = True,
        batch_size: Optional[int] = None,
    ) -> dict:
        """Encode texts via FlagEmbedding, preserving BGE-M3 lexical weights."""
        if not texts:
            return {"dense_vecs": [], "lexical_weights": []}

        valid_indices = [i for i, text in enumerate(texts) if text and text.strip()]
        valid_texts = [texts[i] for i in valid_indices]
        if not valid_texts:
            return {"dense_vecs": [], "lexical_weights": []}

        output = self.model.encode(
            valid_texts,
            batch_size=batch_size or self.batch_size,
            return_dense=return_dense,
            return_sparse=return_sparse,
            return_colbert_vecs=False,
        )

        result = {}
        if return_dense:
            dense_output = output.get("dense_vecs", [])
            full_dense = [[]] * len(texts)
            for idx, orig_i in enumerate(valid_indices):
                dense_vec = dense_output[idx]
                if hasattr(dense_vec, "tolist"):
                    dense_vec = dense_vec.tolist()
                full_dense[orig_i] = dense_vec
            result["dense_vecs"] = full_dense

        if return_sparse:
            sparse_output = output.get("lexical_weights", [])
            full_sparse = [{}] * len(texts)
            for idx, orig_i in enumerate(valid_indices):
                full_sparse[orig_i] = dict(sparse_output[idx] or {})
            result["lexical_weights"] = full_sparse

        return result

    def encode_with_normalization(self, texts: list[str]) -> dict:
        """Normalize dense vectors for cosine similarity parity with the default backend."""
        result = self.encode(texts, return_dense=True, return_sparse=True)
        if "dense_vecs" in result:
            norm_dense = []
            for vec in result["dense_vecs"]:
                if not vec:
                    norm_dense.append([0.0] * config.embedding_dim)
                    continue
                arr = np.array(vec, dtype=np.float32)
                norm = np.linalg.norm(arr)
                if norm > 0:
                    arr = arr / norm
                norm_dense.append(arr.tolist())
            result["dense_vecs"] = norm_dense
        return result

    def _clear_cache(self):
        gc.collect()
        if self.device == "cuda":
            _get_torch().cuda.empty_cache()

    def clear_cache(self):
        self._clear_cache()

    def get_device_info(self) -> str:
        if self.device == "cuda":
            torch = _get_torch()
            return (
                f"CUDA: {torch.cuda.get_device_name(0)} | "
                f"VRAM: {torch.cuda.memory_allocated() / 1e9:.2f}GB / "
                f"{torch.cuda.get_device_properties(0).total_memory / 1e9:.2f}GB"
            )
        return "CPU"
