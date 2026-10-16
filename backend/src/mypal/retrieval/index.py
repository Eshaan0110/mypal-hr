"""The Qdrant vector index.

Each point is one chunk: its id is the chunk's UUID, its vector is the chunk's embedding, and its
payload holds only the chunk id and version id. Policy text, titles and links stay in Postgres,
which remains the source of truth; this index can always be rebuilt from it.

Every search MUST pass the list of version ids the asker is allowed to see (from the scope
resolver). With an empty list, nothing is searched at all.
"""

import uuid
import warnings
from dataclasses import dataclass
from urllib.parse import urlparse

from qdrant_client import QdrantClient, models

from mypal.config import Settings


@dataclass(frozen=True)
class SearchHit:
    chunk_id: uuid.UUID
    version_id: uuid.UUID
    score: float  # cosine similarity: higher is more similar


class IndexConfigurationError(RuntimeError):
    pass


class VectorIndex:
    def __init__(self, client: QdrantClient, collection: str) -> None:
        self._client = client
        self.collection = collection

    def ensure_collection(self, dimension: int) -> None:
        if self._client.collection_exists(self.collection):
            existing = self._client.get_collection(self.collection).config.params.vectors
            size = existing.size if isinstance(existing, models.VectorParams) else None
            if size != dimension:
                raise IndexConfigurationError(
                    f"Collection {self.collection!r} holds {size}-dimension vectors but the "
                    f"embedding model produces {dimension}. Re-index with the new model."
                )
            return
        self._client.create_collection(
            self.collection,
            vectors_config=models.VectorParams(size=dimension, distance=models.Distance.COSINE),
        )
        # An index on version_id keeps the scope filter fast as the corpus grows.
        self._client.create_payload_index(
            self.collection, "version_id", field_schema=models.PayloadSchemaType.KEYWORD
        )

    def upsert_version(
        self,
        version_id: uuid.UUID,
        chunk_ids: list[uuid.UUID],
        vectors: list[list[float]],
    ) -> None:
        """Replace all points of one version (safe to repeat: re-indexing is idempotent)."""
        self.delete_version(version_id)
        self._client.upsert(
            self.collection,
            points=[
                models.PointStruct(
                    id=str(chunk_id),
                    vector=vector,
                    payload={"chunk_id": str(chunk_id), "version_id": str(version_id)},
                )
                for chunk_id, vector in zip(chunk_ids, vectors, strict=True)
            ],
            wait=True,
        )

    def delete_version(self, version_id: uuid.UUID) -> None:
        self._client.delete(
            self.collection,
            points_selector=models.FilterSelector(filter=_versions_filter([version_id])),
            wait=True,
        )

    def search(
        self,
        vector: list[float],
        allowed_version_ids: list[uuid.UUID],
        limit: int,
    ) -> list[SearchHit]:
        if not allowed_version_ids:
            return []  # nothing the asker may see: do not query at all
        response = self._client.query_points(
            self.collection,
            query=vector,
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
