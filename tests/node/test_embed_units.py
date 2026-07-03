
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
async def test_empty_run_ids_returns_zero_and_builds_no_service():
    created = []
    with patch(f"{MODULE}.get_repo") as mock_get_repo, \
         patch(f"{MODULE}.embeddingService",
               side_effect=make_service_factory({}, created)):
        result = await embedUnits({"extraction_run_ids": []})

    assert result == {"embedded_count": 0}
    assert created == []                      # no service constructed
    mock_get_repo.assert_called_once()        # repo still resolved once


@pytest.mark.asyncio
async def test_single_run_id_passes_repo_and_id_and_returns_count():
    created = []
    fake_repo = object()
    with patch(f"{MODULE}.get_repo", return_value=fake_repo), \
         patch(f"{MODULE}.embeddingService",
               side_effect=make_service_factory({"run-1": 7}, created)):
        result = await embedUnits({"extraction_run_ids": ["run-1"]})

    assert result == {"embedded_count": 7}
    assert created == [(fake_repo, "run-1")]  # correct repo + id wiring


@pytest.mark.asyncio
async def test_multiple_run_ids_sums_counts():
    # set() iteration order is nondeterministic, so counts are keyed by id
    counts = {"run-1": 3, "run-2": 5, "run-3": 0}
    created = []
    with patch(f"{MODULE}.get_repo", return_value=object()), \
         patch(f"{MODULE}.embeddingService",
               side_effect=make_service_factory(counts, created)):
        result = await embedUnits(
            {"extraction_run_ids": ["run-1", "run-2", "run-3"]}
        )

    assert result == {"embedded_count": 8}
    assert sorted(rid for _, rid in created) == ["run-1", "run-2", "run-3"]


@pytest.mark.asyncio
async def test_duplicate_run_ids_are_deduplicated():
    # Fan-out can echo the same run id from multiple sources; the set()
    # must collapse them so each run is embedded exactly once.
    created = []
    with patch(f"{MODULE}.get_repo", return_value=object()), \
         patch(f"{MODULE}.embeddingService",
               side_effect=make_service_factory({"run-1": 4}, created)):
        result = await embedUnits(
            {"extraction_run_ids": ["run-1", "run-1", "run-1"]}
        )

    assert result == {"embedded_count": 4}    # counted once, not 12
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
            await embedUnits({"extraction_run_ids": ["run-1"]})


@pytest.mark.asyncio
async def test_repo_resolved_at_call_time_not_import_time():
    # Call twice with different repos; each invocation must use the repo
    # returned by get_repo() at that moment (call-time DI, lazy singleton).
    created = []
    repo_a, repo_b = object(), object()
    with patch(f"{MODULE}.get_repo", side_effect=[repo_a, repo_b]), \
         patch(f"{MODULE}.embeddingService",
               side_effect=make_service_factory({"r": 1}, created)):
        await embedUnits({"extraction_run_ids": ["r"]})
        await embedUnits({"extraction_run_ids": ["r"]})

    assert created[0][0] is repo_a
    assert created[1][0] is repo_b