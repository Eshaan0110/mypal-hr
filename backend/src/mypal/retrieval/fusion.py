"""Reciprocal Rank Fusion (RRF): merge several ranked lists into one.

Each list votes for its items with 1 / (k + rank). Only the *positions* matter, never the raw
scores - which is the point: a cosine similarity (0..1) and a BM25 score (0..anything) cannot be
added together meaningfully, but "ranked 1st by keywords and 3rd by meaning" can.

k (60 by convention, from the original RRF paper) damps the difference between top ranks, so one
list cannot dominate just by being confident about its first item.

    item found 1st by both lists:   1/61 + 1/61 = 0.0328
    1st by one list, absent in other: 1/61        = 0.0164
"""

import uuid
from collections import defaultdict

DEFAULT_K = 60


def reciprocal_rank_fusion(
    rankings: list[list[uuid.UUID]], k: int = DEFAULT_K
) -> list[tuple[uuid.UUID, float]]:
    scores: dict[uuid.UUID, float] = defaultdict(float)
    first_seen: dict[uuid.UUID, int] = {}
    order = 0
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] += 1.0 / (k + rank)
            if item not in first_seen:
                first_seen[item] = order
                order += 1
    # Ties are broken by first appearance, so the result is deterministic.
    return sorted(scores.items(), key=lambda pair: (-pair[1], first_seen[pair[0]]))
