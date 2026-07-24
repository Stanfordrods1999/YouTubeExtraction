"""Unit tests for the eval harness's pure pieces: IR metrics, source-level
judging, and the markdown summary — everything except the live DB calls."""
from math import log2

import numpy as np
import pytest

from evals.metrics import dcg_at_k, mrr, ndcg_at_k, precision_at_k
from evals.run_eval import format_markdown_table, judge, mean_scores, score


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #

def test_precision_at_k_counts_relevant_in_top_k():
    rels = [True, False, True, True]
    assert precision_at_k(rels, 2) == 0.5
    assert precision_at_k(rels, 4) == 0.75


def test_precision_at_k_short_result_list_counts_missing_as_nonrelevant():
    assert precision_at_k([True], 10) == 0.1


def test_precision_at_k_rejects_nonpositive_k():
    with pytest.raises(ValueError):
        precision_at_k([True], 0)


def test_mrr_is_reciprocal_rank_of_first_hit():
    assert mrr([False, False, True, True]) == pytest.approx(1 / 3)
    assert mrr([True]) == 1.0
    assert mrr([False, False]) == 0.0


def test_dcg_discounts_by_log_rank():
    # relevant at ranks 1 and 3: 1/log2(2) + 1/log2(4) = 1 + 0.5
    assert dcg_at_k([True, False, True], 3) == pytest.approx(1.5)


def test_ndcg_is_one_for_ideal_ordering_and_zero_for_no_relevant():
    assert ndcg_at_k([True, True, False], 3) == pytest.approx(1.0)
    assert ndcg_at_k([False, False], 2) == 0.0


def test_ndcg_penalises_late_relevant():
    # One relevant item at rank 3 vs the ideal rank 1.
    out = ndcg_at_k([False, False, True], 3)
    assert out == pytest.approx((1 / log2(4)) / 1.0)
    assert 0 < out < 1


# --------------------------------------------------------------------------- #
# judging + aggregation
# --------------------------------------------------------------------------- #

def test_judge_marks_units_by_labeled_source_url():
    retrieved = [
        {"content": "a", "source_url": "https://good.example"},
        {"content": "b", "source_url": "https://bad.example"},
        {"content": "c"},                       # no source_url → non-relevant
    ]
    assert judge(retrieved, {"https://good.example"}) == [True, False, False]


def test_score_and_mean_scores_aggregate_per_metric():
    rows = [score([True, False], 2), score([False, False], 2)]
    avg = mean_scores(rows)
    assert avg["P@2"] == pytest.approx(0.25)
    assert avg["MRR"] == pytest.approx(0.5)
    assert mean_scores([]) is None


def test_format_markdown_table_has_row_per_config_and_dash_for_missing():
    results = {
        "question-only": [score([True, False], 2)],
        "blend-initial": [],
        "blend-refined": [score([False, True], 2)],
    }
    table = format_markdown_table(results, 2)
    lines = table.splitlines()
    assert lines[0].startswith("| configuration | P@2 | MRR | nDCG@2 |")
    assert any(line.startswith("| question-only | 0.500") for line in lines)
    assert any(line.startswith("| blend-initial | — | — | — | 0 |") for line in lines)
    assert any(line.startswith("| blend-refined |") for line in lines)


def test_blend_used_by_evals_is_normalised():
    # The eval leans on QueryService.blend; sanity-check the invariant here
    # too since eval conclusions depend on it.
    from src.app.services.queryService import QueryService
    out = QueryService.blend([1.0, 0.0], [0.0, 1.0], 0.5)
    assert np.isclose(np.linalg.norm(out), 1.0)
