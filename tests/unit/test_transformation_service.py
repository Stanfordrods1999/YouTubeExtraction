"""Unit tests for TransformationService (Rocchio relevance feedback).

Covers the pure math of `rocchio_embedding` and the async orchestration in
`compute_query_vector` (which fans out two repo fetches and folds them into
the Rocchio formula). No live Supabase or OpenAI — the repo is mocked.
"""
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from src.app.services.transformationService import TransformationService

# --------------------------------------------------------------------------- #
# rocchio_embedding  (α·q0 + β·mean(rel) − γ·mean(nonrel), then L2-normalised)
# --------------------------------------------------------------------------- #

def test_alpha_only_returns_normalised_q0():
    # No feedback → just the (normalised) original query vector.
    out = TransformationService.rocchio_embedding([3.0, 4.0], rel_embs=[], nonrel_embs=[])
    assert np.isclose(np.linalg.norm(out), 1.0)
    assert np.allclose(out, [0.6, 0.8])


def test_relevant_mean_is_added_with_beta():
    # q = 1.0*[1,0] + 1.0*mean([[0,1],[0,1]]) = [1,1] → normalised.
    out = TransformationService.rocchio_embedding(
        [1.0, 0.0], rel_embs=[[0.0, 1.0], [0.0, 1.0]], nonrel_embs=[],
        alpha=1.0, beta=1.0, gamma=0.0,
    )
    assert np.allclose(out, [1 / np.sqrt(2), 1 / np.sqrt(2)])


def test_nonrelevant_mean_is_subtracted_with_gamma():
    # q = 1.0*[1,1] - 1.0*[1,0] = [0,1].
    out = TransformationService.rocchio_embedding(
        [1.0, 1.0], rel_embs=[], nonrel_embs=[[1.0, 0.0]],
        alpha=1.0, beta=0.0, gamma=1.0,
    )
    assert np.allclose(out, [0.0, 1.0])


def test_empty_and_none_feedback_are_noops():
    # None nonrel and empty rel must both be treated as "no feedback".
    out = TransformationService.rocchio_embedding([3.0, 4.0], rel_embs=[], nonrel_embs=None)
    assert np.allclose(out, [0.6, 0.8])


def test_zero_vector_returns_original_without_dividing_by_zero():
    # A zero result vector would blow up on normalisation; guard returns q0.
    out = TransformationService.rocchio_embedding([0.0, 0.0], rel_embs=[], nonrel_embs=[])
    assert out == [0.0, 0.0]


def test_output_is_a_plain_list_not_ndarray():
    out = TransformationService.rocchio_embedding([3.0, 4.0], rel_embs=[], nonrel_embs=[])
    assert isinstance(out, list)
    assert all(isinstance(x, float) for x in out)


# --------------------------------------------------------------------------- #
# compute_query_vector  (async: fetch selected + non-selected, then Rocchio)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_compute_query_vector_fetches_both_selections():
    async def fake_fetch(ids):
        return {"sel": [[0.0, 1.0]], "non": [[1.0, 0.0]]}[ids[0]]

    repo = MagicMock()
    repo.getEmbeddedUnits = AsyncMock(side_effect=fake_fetch)

    svc = TransformationService(repo)
    out = await svc.compute_query_vector([1.0, 1.0], ["sel"], ["non"])

    # Both selection sets were fetched from the repo.
    assert repo.getEmbeddedUnits.await_count == 2
    fetched = [c.args[0] for c in repo.getEmbeddedUnits.await_args_list]
    assert ["sel"] in fetched and ["non"] in fetched
    # Result is a normalised vector folded through Rocchio.
    assert np.isclose(np.linalg.norm(out), 1.0)


@pytest.mark.asyncio
async def test_empty_selection_ids_skip_the_repo():
    # _fetch short-circuits on empty id lists — no query is issued.
    repo = MagicMock()
    repo.getEmbeddedUnits = AsyncMock()

    svc = TransformationService(repo)
    out = await svc.compute_query_vector([3.0, 4.0], [], [])

    repo.getEmbeddedUnits.assert_not_awaited()
    assert np.allclose(out, [0.6, 0.8])
