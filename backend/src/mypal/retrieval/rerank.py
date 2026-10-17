"""Optional reranking with a cross-encoder.

The dense embedder is a "bi-encoder": it turns the question and each passage into vectors
*separately*, which is fast enough to search thousands of chunks. A cross-encoder reads the
question and one passage *together* and scores how well that passage answers it - more accurate,
but one model run per candidate, so it is only applied to the few candidates search returned.

Whether it is worth its cost is decided by measurement (mypal-eval-retrieval), not assumed.
"""

from typing import Protocol

from mypal.retrieval.embeddings import _LazyModel


class Reranker(Protocol):
    @property
    def model_name(self) -> str: ...

    def score(self, query: str, passages: list[str]) -> list[float]: ...


class FastEmbedReranker:
    def __init__(self, model_name: str, cache_dir: str) -> None:
        self._model_name = model_name

        def load():  # noqa: ANN202
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            return TextCrossEncoder(model_name, cache_dir=cache_dir)

        self._model = _LazyModel(load)

    @property
    def model_name(self) -> str:
        return self._model_name

    def score(self, query: str, passages: list[str]) -> list[float]:
        return [float(s) for s in self._model.get().rerank(query, passages)]
