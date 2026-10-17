"""The Qdrant index.

Each point is one chunk: its id is the chunk's UUID, and it carries two named vectors:
- "dense": the meaning vector (cosine similarity);
- "bm25":  the sparse keyword vector; Qdrant applies the IDF (word rarity) part of BM25.
Its payload holds only the chunk id and version id. Policy text, titles and links stay in
Postgres, which remains the source of truth; this index can always be rebuilt from it.

Every search MUST pass the list of version ids the asker is allowed to see (from the scope gate).
The same filter is applied to the dense and the keyword search. With an empty list, nothing is
searched at all.
"""

import uuid
import warnings
from dataclasses import dataclass
from urllib.parse import urlparse

from qdrant_client import QdrantClient, models

from mypal.config import Settings
from mypal.retrieval.embeddings import SparseEmbedding

DENSE = "dense"
SPARSE = "bm25"


@dataclass(frozen=True)
class SearchHit:
    chunk_id: uuid.UUID
    version_id: uuid.UUID
    # Dense: cosine similarity (-1..1, higher is more similar).
    # BM25: an unbounded relevance score, only meaningful for ranking within one query.
    score: float


class IndexConfigurationError(RuntimeError):
    pass


class VectorIndex:
    def __init__(self, client: QdrantClient, collection: str) -> None:
        self._client = client
        self.collection = collection

    def ensure_collection(self, dimension: int) -> None:
        if not self._client.collection_exists(self.collection):
            self._create(dimension)
            return
        params = self._client.get_collection(self.collection).config.params
        dense = params.vectors.get(DENSE) if isinstance(params.vectors, dict) else None
        if dense is None or SPARSE not in (params.sparse_vectors or {}):
            raise IndexConfigurationError(
                f"Collection {self.collection!r} uses an older layout without hybrid search. "
                "Rebuild it from Postgres with: uv run mypal-policy reindex --recreate"
            )
        if dense.size != dimension:
            raise IndexConfigurationError(
                f"Collection {self.collection!r} holds {dense.size}-dimension vectors but the "
                f"embedding model produces {dimension}. Rebuild it with: "
                "uv run mypal-policy reindex --recreate"
            )

    def recreate(self, dimension: int) -> None:
        """Drop and recreate the collection. Safe only because Postgres holds the truth and
        every active version is re-indexed right afterwards."""
        if self._client.collection_exists(self.collection):
            self._client.delete_collection(self.collection)
        self._create(dimension)

    def _create(self, dimension: int) -> None:
        self._client.create_collection(
            self.collection,
            vectors_config={
                DENSE: models.VectorParams(size=dimension, distance=models.Distance.COSINE)
            },
            sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)},
        )
        # An index on version_id keeps the scope filter fast as the corpus grows.
        self._client.create_payload_index(
            self.collection, "version_id", field_schema=models.PayloadSchemaType.KEYWORD
        )

    def upsert_version(
        self,
        version_id: uuid.UUID,
        chunk_ids: list[uuid.UUID],
        dense_vectors: list[list[float]],
        sparse_vectors: list[SparseEmbedding],
    ) -> None:
        """Replace all points of one version (safe to repeat: re-indexing is idempotent)."""
        self.delete_version(version_id)
        self._client.upsert(
            self.collection,
            points=[
                models.PointStruct(
                    id=str(chunk_id),
                    vector={
                        DENSE: dense,
                        SPARSE: models.SparseVector(indices=sparse.indices, values=sparse.values),
                    },
                    payload={"chunk_id": str(chunk_id), "version_id": str(version_id)},
                )
                for chunk_id, dense, sparse in zip(
                    chunk_ids, dense_vectors, sparse_vectors, strict=True
                )
            ],
            wait=True,
        )

    def delete_version(self, version_id: uuid.UUID) -> None:
        self._client.delete(
            self.collection,
            points_selector=models.FilterSelector(filter=_versions_filter([version_id])),
            wait=True,
        )

    def search_dense(
        self, vector: list[float], allowed_version_ids: list[uuid.UUID], limit: int
    ) -> list[SearchHit]:
        return self._search(vector, DENSE, allowed_version_ids, limit)

    def search_sparse(
        self, vector: SparseEmbedding, allowed_version_ids: list[uuid.UUID], limit: int
    ) -> list[SearchHit]:
        if not vector.indices:  # e.g. a question made only of stop words
            return []
        query = models.SparseVector(indices=vector.indices, values=vector.values)
        return self._search(query, SPARSE, allowed_version_ids, limit)

    def _search(
        self,
        query: list[float] | models.SparseVector,
        using: str,
        allowed_version_ids: list[uuid.UUID],
        limit: int,
    ) -> list[SearchHit]:
        if not allowed_version_ids:
            return []  # nothing the asker may see: do not query at all
        response = self._client.query_points(
            self.collection,
            query=query,
            using=using,
            query_filter=_versions_filter(allowed_version_ids),
            limit=limit,
            with_payload=True,
        )
        return [
            SearchHit(
                chunk_id=uuid.UUID(point.payload["chunk_id"]),
                version_id=uuid.UUID(point.payload["version_id"]),
                score=point.score,
            )
            for point in response.points
            if point.payload
        ]

    def count(self) -> int:
        return self._client.count(self.collection, exact=True).count

    def drop(self) -> None:
        self._client.delete_collection(self.collection)


def _versions_filter(version_ids: list[uuid.UUID]) -> models.Filter:
    return models.Filter(
        must=[
            models.FieldCondition(
                key="version_id",
                match=models.MatchAny(any=[str(v) for v in version_ids]),
            )
        ]
    )


def create_index(settings: Settings, collection: str | None = None) -> VectorIndex:
    api_key = settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None
    with warnings.catch_warnings():
        # Qdrant warns about sending a key over plain HTTP. Acceptable only for this machine;
        # any shared environment must use HTTPS, so the warning stays for every other host.
        if urlparse(settings.qdrant_url).hostname in ("127.0.0.1", "localhost", "::1"):
            warnings.filterwarnings("ignore", message=".*insecure connection.*")
        client = QdrantClient(url=settings.qdrant_url, api_key=api_key, timeout=10)
    return VectorIndex(client, collection or settings.qdrant_collection)
