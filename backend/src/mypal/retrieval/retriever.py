"""The Retriever: one place that decides how a search is run, used by the chat pipeline, by
publishing (indexing) and by the retrieval evaluation.

    mode "dense"  - meaning search only
    mode "sparse" - BM25 keyword search only (used for evaluation comparisons)
    mode "hybrid" - both, merged with Reciprocal Rank Fusion
    optional reranker - re-orders the top candidates with a cross-encoder

Every search is restricted to `allowed_version_ids` from the scope gate; both the dense and the
keyword search use that same filter.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from mypal.config import Settings
from mypal.retrieval.embeddings import (
    Embedder,
    SparseEmbedder,
    create_embedder,
    create_sparse_embedder,
)
from mypal.retrieval.fusion import reciprocal_rank_fusion
from mypal.retrieval.index import SearchHit, VectorIndex, create_index
from mypal.retrieval.rerank import FastEmbedReranker, Reranker

Mode = Literal["dense", "sparse", "hybrid"]
TextLoader = Callable[[list[uuid.UUID]], dict[uuid.UUID, str]]


@dataclass(frozen=True)
class RankedChunk:
    chunk_id: uuid.UUID
    version_id: uuid.UUID
    score: float  # the final ranking score (cosine, BM25, RRF or reranker - depends on mode)
    dense_score: float | None  # cosine similarity, when the dense search found this chunk


@dataclass
class RetrievalResult:
    chunks: list[RankedChunk] = field(default_factory=list)
    # Best meaning-similarity of any allowed chunk. Used by the confidence gate because, unlike
    # BM25 or RRF scores, cosine similarity is comparable across questions.
    best_dense_score: float | None = None


class Retriever:
    def __init__(
        self,
        dense: Embedder,
        sparse: SparseEmbedder,
        index: VectorIndex,
        mode: Mode = "hybrid",
        candidates: int = 20,
        rrf_k: int = 60,
        reranker: Reranker | None = None,
        rerank_candidates: int = 10,
    ) -> None:
        self.dense = dense
        self.sparse = sparse
        self.index = index
        self.mode = mode
        self.candidates = candidates
        self.rrf_k = rrf_k
        self.reranker = reranker
        self.rerank_candidates = rerank_candidates

    def index_version(
        self, version_id: uuid.UUID, chunk_ids: list[uuid.UUID], texts: list[str]
    ) -> None:
        """Embed a version's chunks both ways and store them (replacing any earlier points)."""
        self.index.ensure_collection(self.dense.dimension)
        self.index.upsert_version(
            version_id,
            chunk_ids,
            self.dense.embed_passages(texts),
            self.sparse.embed_passages(texts),
        )

    def retrieve(
        self,
        query: str,
        allowed_version_ids: list[uuid.UUID],
        top_k: int,
        load_texts: TextLoader | None = None,
    ) -> RetrievalResult:
        if not allowed_version_ids:
            return RetrievalResult()

        dense_hits: list[SearchHit] = []
        sparse_hits: list[SearchHit] = []
        if self.mode in ("dense", "hybrid"):
            dense_hits = self.index.search_dense(
                self.dense.embed_query(query), allowed_version_ids, self.candidates
            )
        if self.mode in ("sparse", "hybrid"):
            sparse_hits = self.index.search_sparse(
                self.sparse.embed_query(query), allowed_version_ids, self.candidates
            )

        if self.mode == "dense":
            ranked = [(h.chunk_id, h.score) for h in dense_hits]
        elif self.mode == "sparse":
            ranked = [(h.chunk_id, h.score) for h in sparse_hits]
        else:
            ranked = reciprocal_rank_fusion(
                [[h.chunk_id for h in dense_hits], [h.chunk_id for h in sparse_hits]],
                k=self.rrf_k,
            )

        if self.reranker is not None and load_texts is not None and ranked:
            ranked = self._rerank(query, ranked[: self.rerank_candidates], load_texts)

        version_of = {h.chunk_id: h.version_id for h in [*dense_hits, *sparse_hits]}
        dense_score = {h.chunk_id: h.score for h in dense_hits}
        return RetrievalResult(
            chunks=[
                RankedChunk(chunk_id, version_of[chunk_id], score, dense_score.get(chunk_id))
                for chunk_id, score in ranked[:top_k]
            ],
            best_dense_score=dense_hits[0].score if dense_hits else None,
        )

    def _rerank(
        self, query: str, ranked: list[tuple[uuid.UUID, float]], load_texts: TextLoader
    ) -> list[tuple[uuid.UUID, float]]:
        texts = load_texts([chunk_id for chunk_id, _ in ranked])
        ids = [chunk_id for chunk_id, _ in ranked if chunk_id in texts]
        scores = self.reranker.score(query, [texts[i] for i in ids])  # type: ignore[union-attr]
        return sorted(zip(ids, scores, strict=True), key=lambda pair: -pair[1])


def create_retriever(settings: Settings, index: VectorIndex | None = None) -> Retriever:
    reranker = (
        FastEmbedReranker(settings.reranker_model, settings.embedding_cache_dir)
        if settings.reranker_model
        else None
    )
    return Retriever(
        dense=create_embedder(settings),
        sparse=create_sparse_embedder(settings),
        index=index or create_index(settings),
        mode=settings.retrieval_mode,
        candidates=settings.retrieval_candidates,
        rrf_k=settings.rrf_k,
        reranker=reranker,
        rerank_candidates=settings.rerank_candidates,
    )
