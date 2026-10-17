import uuid

import pytest

from mypal.retrieval.fusion import reciprocal_rank_fusion

A, B, C, D = (uuid.uuid4() for _ in range(4))


def test_item_ranked_well_by_both_lists_wins() -> None:
    fused = reciprocal_rank_fusion([[A, B, C], [B, A, D]])

    assert [item for item, _ in fused][:2] in ([A, B], [B, A])
    assert {item for item, _ in fused} == {A, B, C, D}


def test_agreement_beats_a_single_first_place() -> None:
    # C is only first in one list; B is second in both.
    fused = dict(reciprocal_rank_fusion([[C, B], [D, B]]))

    assert fused[B] > fused[C]


def test_scores_follow_the_rrf_formula() -> None:
    fused = dict(reciprocal_rank_fusion([[A], [A]], k=60))

    assert fused[A] == pytest.approx(2 / 61)


def test_only_positions_matter_so_lists_need_no_common_score_scale() -> None:
    # The function never sees raw scores - cosine vs BM25 scales cannot distort the result.
    assert reciprocal_rank_fusion([[A, B]]) == reciprocal_rank_fusion([[A, B]], k=60)


def test_ties_are_broken_deterministically() -> None:
    first = reciprocal_rank_fusion([[A], [B]])
    again = reciprocal_rank_fusion([[A], [B]])

    assert first == again
    assert [item for item, _ in first] == [A, B]


def test_empty_input_gives_empty_result() -> None:
    assert reciprocal_rank_fusion([[], []]) == []
