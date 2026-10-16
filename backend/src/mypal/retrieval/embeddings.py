"""Embeddings: turning text into vectors so that similar meanings end up close together.

The Embedder protocol is the only thing the rest of the code depends on, so the local fastembed
model can later be swapped for an approved hosted model (e.g. Azure OpenAI embeddings). Changing
the model requires re-indexing every chunk, because vectors from different models are not
comparable.
"""

import threading
from typing import Protocol

from mypal.config import Settings


class Embedder(Protocol):
    @property
    def model_name(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    def embed_passages(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


def passage_text(heading_path: list[str], text: str) -> str:
    """What gets embedded for a chunk: its headings give context ("Sick leave") that the body
    text alone may not repeat."""
    if heading_path:
        return " > ".join(heading_path) + "\n" + text
    return text


class FastEmbedEmbedder:
    """Local ONNX embedding model (no GPU, no external service). Loaded on first use, because
    loading takes seconds and the first run downloads the model (~70 MB)."""

    _DIMENSIONS = {"BAAI/bge-small-en-v1.5": 384}

    def __init__(self, model_name: str, cache_dir: str) -> None:
        if model_name not in self._DIMENSIONS:
            raise ValueError(f"Unsupported embedding model {model_name!r}")
        self._model_name = model_name
        self._cache_dir = cache_dir
        self._model = None
        self._lock = threading.Lock()

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._DIMENSIONS[self._model_name]

    def _loaded(self):  # noqa: ANN202 - fastembed's type is only imported lazily
        with self._lock:
            if self._model is None:
                from fastembed import TextEmbedding

                self._model = TextEmbedding(self._model_name, cache_dir=self._cache_dir)
            return self._model

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._loaded().passage_embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        # query_embed adds the instruction prefix bge models expect for search queries.
        return next(iter(self._loaded().query_embed([text]))).tolist()


def create_embedder(settings: Settings) -> Embedder:
    return FastEmbedEmbedder(settings.embedding_model, settings.embedding_cache_dir)
