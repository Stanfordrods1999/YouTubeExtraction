"""Unit tests for the embedUnits node (subgraph fan-in).

Contract: embed every pending unit for each unique extraction run, then
surface the plain source ids for the human-selection interrupt as a
*partial* update — `{"sourceIds": [...]}` — never the whole mutated state
(returning full state would re-feed the add-reducer channels into
themselves and duplicate their contents).
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.app.graph.nodes.embedUnits import embedUnits

MODULE = "src.app.graph.nodes.embedUnits"


def make_service_factory(counts_by_run_id, created):
    """Returns a fake embeddingService class.

    counts_by_run_id: dict e_run_id -> int returned by embed_pending()
    created: list that records (repo, e_run_id) for each construction
    """

    def factory(*, repo, e_run_id):
        created.append((repo, e_run_id))
        svc = MagicMock()
        svc.embed_pending = AsyncMock(return_value=counts_by_run_id[e_run_id])
        return svc

    return factory


@pytest.mark.asyncio
async def test_empty_run_ids_builds_no_service_and_returns_empty_source_ids():
    created = []
    with patch(f"{MODULE}.get_repo") as mock_get_repo, \
         patch(f"{MODULE}.embeddingService",
               side_effect=make_service_factory({}, created)):
        result = await embedUnits({"extraction_run_ids": [], "source_ids": []})

    assert result == {"sourceIds": []}
    assert created == []                      # no service constructed
    mock_get_repo.assert_called_once()        # repo still resolved once


@pytest.mark.asyncio
async def test_missing_source_ids_key_is_tolerated():
    # A defensive path: fan-in state without source_ids must not KeyError.
    with patch(f"{MODULE}.get_repo", return_value=object()), \
         patch(f"{MODULE}.embeddingService",
               side_effect=make_service_factory({}, [])):
        result = await embedUnits({"extraction_run_ids": []})

    assert result == {"sourceIds": []}


@pytest.mark.asyncio
async def test_embeds_each_run_and_surfaces_source_ids_in_order():
    counts = {"run-1": 3, "run-2": 5}
    created = []
    source_rows = [
        {"id": "src-a", "source_url": "https://a.example"},
        {"id": "src-b", "source_url": "https://b.example"},
    ]
    fake_repo = object()
    with patch(f"{MODULE}.get_repo", return_value=fake_repo), \
         patch(f"{MODULE}.embeddingService",
               side_effect=make_service_factory(counts, created)):
        result = await embedUnits({
            "extraction_run_ids": ["run-1", "run-2"],
            "source_ids": source_rows,
        })

    # Source ids surfaced as a partial update, order preserved.
    assert result == {"sourceIds": ["src-a", "src-b"]}
    # Each run embedded exactly once, with the resolved repo.
    assert sorted(rid for _, rid in created) == ["run-1", "run-2"]
    assert all(repo is fake_repo for repo, _ in created)


@pytest.mark.asyncio
async def test_duplicate_run_ids_are_deduplicated():
    # Fan-out can echo the same run id from multiple sources; the set()
    # must collapse them so each run is embedded exactly once.
    created = []
    with patch(f"{MODULE}.get_repo", return_value=object()), \
         patch(f"{MODULE}.embeddingService",
               side_effect=make_service_factory({"run-1": 4}, created)):
        await embedUnits({
            "extraction_run_ids": ["run-1", "run-1", "run-1"],
            "source_ids": [],
        })

    assert len(created) == 1                  # constructed once


@pytest.mark.asyncio
async def test_embed_pending_exception_propagates():
    # RetryPolicy on the node handles retries; the node itself must not
    # swallow errors.
    def factory(*, repo, e_run_id):
        svc = MagicMock()
        svc.embed_pending = AsyncMock(side_effect=ValueError("boom"))
        return svc

    with patch(f"{MODULE}.get_repo", return_value=object()), \
         patch(f"{MODULE}.embeddingService", side_effect=factory):
        with pytest.raises(ValueError, match="boom"):
            await embedUnits({"extraction_run_ids": ["run-1"], "source_ids": []})
