"""Hybrid retrieval against a real Qdrant collection (fake, deterministic embedders)."""

import uuid

import pytest
from qdrant_client import models

from mypal.retrieval.index import IndexConfigurationError, VectorIndex
from tests.fakes import fake_retriever

VERSION_A, VERSION_B = uuid.uuid4(), uuid.uuid4()
SICK, CASUAL, FORM, OTHER_CO = (uuid.uuid4() for _ in range(4))
TEXTS = {
    SICK: "Sick leave: employees are entitled to ten days of sick leave per year.",
    CASUAL: "Casual leave: employees are entitled to eight days of casual leave per year.",
    FORM: "Complete form SA-1 and state the reason for the request.",
    OTHER_CO: "Form SA-1 secret rules for another company.",
}


@pytest.fixture
def indexed(vector_index: VectorIndex) -> VectorIndex:
    retriever = fake_retriever(vector_index)
    retriever.index_version(
        VERSION_A, [SICK, CASUAL, FORM], [TEXTS[c] for c in (SICK, CASUAL, FORM)]
    )
    retriever.index_version(VERSION_B, [OTHER_CO], [TEXTS[OTHER_CO]])
    return vector_index


def test_hybrid_returns_relevant_chunk_first(indexed: VectorIndex) -> None:
    result = fake_retriever(indexed).retrieve("how many days of sick leave", [VERSION_A], top_k=3)

    assert result.chunks[0].chunk_id == SICK
    assert result.best_dense_score is not None and result.best_dense_score > 0


def test_keyword_search_finds_exact_codes(indexed: VectorIndex) -> None:
    result = fake_retriever(indexed, mode="sparse").retrieve("SA-1", [VERSION_A], top_k=3)

    assert [c.chunk_id for c in result.chunks] == [FORM]


@pytest.mark.parametrize("mode", ["dense", "sparse", "hybrid"])
def test_every_search_mode_respects_the_scope_filter(indexed: VectorIndex, mode: str) -> None:
    """Version B's chunk matches "form SA-1" well, but B is not in the allowed list."""
    result = fake_retriever(indexed, mode=mode).retrieve("form SA-1 rules", [VERSION_A], top_k=5)

    assert OTHER_CO not in {c.chunk_id for c in result.chunks}
    assert all(c.version_id == VERSION_A for c in result.chunks)


def test_no_allowed_versions_means_no_search_at_all(indexed: VectorIndex) -> None:
    result = fake_retriever(indexed).retrieve("sick leave", [], top_k=5)

    assert result.chunks == []
    assert result.best_dense_score is None


def test_reranker_reorders_candidates(indexed: VectorIndex) -> None:
    class PrefersCasual:
        model_name = "test-reranker"

        def score(self, query: str, passages: list[str]) -> list[float]:
            return [1.0 if "casual" in p.lower() else 0.0 for p in passages]

    retriever = fake_retriever(indexed, reranker=PrefersCasual())
    result = retriever.retrieve(
        "sick leave days",
        [VERSION_A],
        top_k=3,
        load_texts=lambda ids: {i: TEXTS[i] for i in ids},
    )

    assert result.chunks[0].chunk_id == CASUAL


def test_reindexing_a_version_replaces_its_points(indexed: VectorIndex) -> None:
    fake_retriever(indexed).index_version(VERSION_A, [SICK], [TEXTS[SICK]])

    assert indexed.count() == 2  # SICK + OTHER_CO; CASUAL and FORM were replaced


def test_old_single_vector_layout_is_detected(vector_index: VectorIndex) -> None:
    vector_index._client.create_collection(
        vector_index.collection,
        vectors_config=models.VectorParams(size=256, distance=models.Distance.COSINE),
    )

    with pytest.raises(IndexConfigurationError, match="reindex --recreate"):
        vector_index.ensure_collection(256)

    vector_index.recreate(256)
    vector_index.ensure_collection(256)  # the new layout is accepted
