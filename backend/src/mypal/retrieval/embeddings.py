"""Embeddings: turning text into vectors that search can compare.

Two kinds are used together (hybrid search):

- Dense ("meaning") vectors from a small neural model: 384 numbers per text. Texts with similar
  meaning end up close even when they share no words ("unwell" ~ "sick leave").
- Sparse ("keyword") vectors for BM25: one weight per word that actually occurs. Exact terms
  match strongly ("SA-1", "Grade C") even when the neural model has never seen them. The BM25
  term weights are computed here; the rarity (IDF) part is computed by Qdrant across the whole
  collection.

Both sit behind small protocols so the local fastembed models can later be replaced by approved
hosted ones. Changing a model requires re-indexing every chunk, because vectors from different
models are not comparable.
"""

import threading
from dataclasses import dataclass
from typing import Protocol

from mypal.config import Settings


@dataclass(frozen=True)
class SparseEmbedding:
    indices: list[int]  # one id per distinct word
    values: list[float]  # that word's weight


class Embedder(Protocol):
    @property
    def model_name(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    def embed_passages(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class SparseEmbedder(Protocol):
    def embed_passages(self, texts: list[str]) -> list[SparseEmbedding]: ...

    def embed_query(self, text: str) -> SparseEmbedding: ...


def passage_text(heading_path: list[str], text: str) -> str:
    """What gets embedded for a chunk: its headings give context ("Sick leave") that the body
    text alone may not repeat."""
    if heading_path:
        return " > ".join(heading_path) + "\n" + text
    return text


class _LazyModel:
    """fastembed models take seconds to load and download on first use, so load on demand."""

    def __init__(self, factory) -> None:  # noqa: ANN001
        self._factory = factory
        self._model = None
        self._lock = threading.Lock()

    def get(self):  # noqa: ANN201
        with self._lock:
            if self._model is None:
                self._model = self._factory()
            return self._model


class FastEmbedEmbedder:
    """Local ONNX dense embedding model (no GPU, no external service)."""

    _DIMENSIONS = {"BAAI/bge-small-en-v1.5": 384}

    def __init__(self, model_name: str, cache_dir: str) -> None:
        if model_name not in self._DIMENSIONS:
            raise ValueError(f"Unsupported embedding model {model_name!r}")
        self._model_name = model_name

        def load():  # noqa: ANN202
            from fastembed import TextEmbedding

            return TextEmbedding(model_name, cache_dir=cache_dir)

        self._model = _LazyModel(load)

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._DIMENSIONS[self._model_name]

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._model.get().passage_embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        # query_embed adds the instruction prefix bge models expect for search queries.
        return next(iter(self._model.get().query_embed([text]))).tolist()


class FastEmbedBM25:
    """BM25 term weights (fastembed's "Qdrant/bm25": English stemming, stop words removed)."""

    def __init__(self, cache_dir: str) -> None:
        def load():  # noqa: ANN202
            from fastembed import SparseTextEmbedding

            return SparseTextEmbedding("Qdrant/bm25", cache_dir=cache_dir)

        self._model = _LazyModel(load)

    @staticmethod
    def _convert(raw) -> SparseEmbedding:  # noqa: ANN001
        return SparseEmbedding(
            indices=[int(i) for i in raw.indices], values=[float(v) for v in raw.values]
        )

    def embed_passages(self, texts: list[str]) -> list[SparseEmbedding]:
        return [self._convert(raw) for raw in self._model.get().passage_embed(texts)]

    def embed_query(self, text: str) -> SparseEmbedding:
        return self._convert(next(iter(self._model.get().query_embed([text]))))


def create_embedder(settings: Settings) -> Embedder:
    return FastEmbedEmbedder(settings.embedding_model, settings.embedding_cache_dir)


def create_sparse_embedder(settings: Settings) -> SparseEmbedder:
    return FastEmbedBM25(settings.embedding_cache_dir)
