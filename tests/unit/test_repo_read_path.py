"""Unit tests for the read-path repository methods (fake client chain)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.supabaseRepository import SupabaseRepository


def make_chain(rows):
    """A fake Supabase client whose fluent chain returns `rows` on execute()."""
    chain = MagicMock()
    for method in ("table", "select", "insert", "eq", "in_", "order", "limit", "rpc"):
        getattr(chain, method).return_value = chain
    resp = MagicMock()
    resp.data = rows
    chain.execute = AsyncMock(return_value=resp)
    return chain


@pytest.mark.asyncio
async def test_match_units_calls_rpc_with_query_params():
    repo = SupabaseRepository()
    repo.client = make_chain([{"content": "a fact", "similarity": 0.9}])

    out = await repo.matchUnits([0.1, 0.2], k=7, topic_id="top-1")

    assert out == [{"content": "a fact", "similarity": 0.9}]
    repo.client.rpc.assert_called_once_with("match_units", {
        "query_embedding": [0.1, 0.2],
        "match_count": 7,
        "filter_topic": "top-1",
    })


@pytest.mark.asyncio
async def test_match_units_empty_result_returns_empty_list():
    repo = SupabaseRepository()
    repo.client = make_chain(None)

    assert await repo.matchUnits([0.1]) == []


@pytest.mark.asyncio
async def test_get_latest_centroid_decodes_json_string():
    repo = SupabaseRepository()
    repo.client = make_chain([{"centroid": "[0.1, 0.2]"}])

    out = await repo.getLatestCentroid("run-42")

    assert out == [0.1, 0.2]
    repo.client.table.assert_called_once_with("topic_centroids")
    repo.client.eq.assert_called_once_with("thread_id", "run-42")
    repo.client.order.assert_called_once_with("created_at", desc=True)


@pytest.mark.asyncio
async def test_get_latest_centroid_missing_thread_returns_none():
    repo = SupabaseRepository()
    repo.client = make_chain([])

    assert await repo.getLatestCentroid("nope") is None


@pytest.mark.asyncio
async def test_save_centroid_inserts_full_row():
    repo = SupabaseRepository()
    repo.client = make_chain([{"id": "c1"}])

    await repo.saveCentroid(
        thread_id="run-42", kind="refined", centroid=[0.5],
        topic_text="qec", iteration=2,
    )

    (row,), _ = repo.client.insert.call_args
    assert row == {
        "thread_id": "run-42",
        "kind": "refined",
        "centroid": [0.5],
        "topic_text": "qec",
        "iteration": 2,
    }
