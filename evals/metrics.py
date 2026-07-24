"""Standard binary-relevance IR metrics.

`relevances` is the ranked list of judgments for one query: relevances[i]
is True iff the i-th retrieved item is relevant. Pure functions — no I/O —
so they're unit-testable without a database.
"""
from math import log2
from typing import Sequence


def precision_at_k(relevances: Sequence[bool], k: int) -> float:
    """Fraction of the top-k results that are relevant (missing ranks count
    as non-relevant, the standard convention)."""
    if k <= 0:
        raise ValueError("k must be positive")
    return sum(bool(r) for r in relevances[:k]) / k


def mrr(relevances: Sequence[bool]) -> float:
    """Reciprocal rank of the first relevant result; 0 if none."""
    for rank, rel in enumerate(relevances, start=1):
        if rel:
            return 1.0 / rank
    return 0.0


def dcg_at_k(relevances: Sequence[bool], k: int) -> float:
    return sum(
        bool(rel) / log2(rank + 1)
        for rank, rel in enumerate(relevances[:k], start=1)
    )


def ndcg_at_k(relevances: Sequence[bool], k: int) -> float:
    """DCG normalised by the ideal ordering of the same judgments."""
    ideal = sorted(relevances, reverse=True)
    idcg = dcg_at_k(ideal, k)
    return dcg_at_k(relevances, k) / idcg if idcg > 0 else 0.0
