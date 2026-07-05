"""
Singleton embedding model loader for the Hybrid RAG layer.

Uses sentence-transformers/all-MiniLM-L6-v2 — a small (80MB) but high-quality
model that runs locally on CPU with no API cost. Loaded once on first call and
cached for the process lifetime.

Graceful degradation: if sentence-transformers or torch is unavailable (e.g.
missing install, low-RAM machine), all public functions return None and callers
fall back to BM25-only mode without crashing.
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

_model = None
_model_lock = threading.Lock()
_load_attempted = False
_load_failed = False

_MODEL_NAME = "all-MiniLM-L6-v2"


def _load_model() -> None:
    """Load the embedding model exactly once. Thread-safe."""
    global _model, _load_attempted, _load_failed

    with _model_lock:
        if _load_attempted:
            return
        _load_attempted = True
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            logger.info("RAG Embeddings: Loading model '%s'...", _MODEL_NAME)
            _model = SentenceTransformer(_MODEL_NAME)
            logger.info("RAG Embeddings: Model loaded successfully.")
        except Exception as exc:
            _load_failed = True
            logger.warning(
                "RAG Embeddings: Failed to load '%s' (%s). "
                "Falling back to BM25-only retrieval.",
                _MODEL_NAME,
                exc,
            )


def get_model():
    """Return the loaded SentenceTransformer model, or None if unavailable."""
    if not _load_attempted:
        _load_model()
    return _model


def embed_texts(texts: list[str]) -> Optional[np.ndarray]:
    """
    Embed a list of strings into dense vectors.

    Returns a (N, D) float32 numpy array, or None if the model is unavailable.
    """
    model = get_model()
    if model is None:
        return None
    try:
        return model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
    except Exception as exc:
        logger.error("RAG Embeddings: embed_texts failed: %s", exc)
        return None


def embed_query(query: str) -> Optional[np.ndarray]:
    """
    Embed a single query string into a dense vector.

    Returns a (D,) float32 numpy array, or None if the model is unavailable.
    """
    result = embed_texts([query])
    if result is None:
        return None
    return result[0]
