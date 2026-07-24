"""Unit tests for the reliability-focused repository methods (fake chain)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.supabaseRepository import SupabaseRepository


def make_chain(rows):
    chain = MagicMock()
    for method in ("table", "select", "insert", "upsert", "update", "eq",
                   "neq", "in_", "order", "limit", "rpc"):
        getattr(chain, method).return_value = chain
    resp = MagicMock()
    resp.data = rows
    chain.execute = AsyncMock(return_value=resp)
    return chain


@pytest.mark.asyncio
async def test_create_sources_upserts_on_topic_and_url():
    repo = SupabaseRepository()
    repo.client = make_chain([{"id": "s1"}])
    rows = [{"source_url": "https://a.example", "topic_id": "t1"}]

    out = await repo.createSources(rows)

    assert out == [{"id": "s1"}]
    repo.client.upsert.assert_called_once_with(
        rows, on_conflict="topic_id,source_url"
    )


@pytest.mark.asyncio
async def test_update_source_status_targets_ids():
    repo = SupabaseRepository()
    repo.client = make_chain([])

    await repo.updateSourceStatus(["s1", "s2"], "embedded")

    repo.client.update.assert_called_once_with({"status": "embedded"})
    repo.client.in_.assert_called_once_with("id", ["s1", "s2"])
    repo.client.neq.assert_not_called()


@pytest.mark.asyncio
async def test_update_source_status_can_exclude_failed_sources():
    repo = SupabaseRepository()
    repo.client = make_chain([])

    await repo.updateSourceStatus(["s1"], "embedded", exclude_failed=True)

    repo.client.neq.assert_called_once_with("status", "failed")


@pytest.mark.asyncio
async def test_has_embedded_units_is_boolean():
    repo = SupabaseRepository()
    repo.client = make_chain([{"id": "u1"}])
    assert await repo.hasEmbeddedUnits("run-1") is True

    repo.client = make_chain([])
    assert await repo.hasEmbeddedUnits("run-1") is False


@pytest.mark.asyncio
async def test_dedupe_units_calls_rpc_and_defaults_to_zero():
    repo = SupabaseRepository()
    repo.client = make_chain(3)

    out = await repo.dedupeUnits("run-1", threshold=0.9)

    assert out == 3
    repo.client.rpc.assert_called_once_with(
        "dedupe_units", {"run_id": "run-1", "threshold": 0.9}
    )

    repo.client = make_chain(None)
    assert await repo.dedupeUnits("run-1") == 0


@pytest.mark.asyncio
async def test_get_units_by_sources_filters_out_null_content():
    repo = SupabaseRepository()
    repo.client = make_chain([
        {"content": "a fact"}, {"content": None}, {"content": "another"},
    ])

    out = await repo.getUnitsBySources(["s1"], limit=5)

    assert out == ["a fact", "another"]
    repo.client.in_.assert_called_once_with("extraction_runs.source_id", ["s1"])
    repo.client.limit.assert_called_once_with(5)


@pytest.mark.asyncio
async def test_create_extractions_wraps_units_and_usage_in_metadata():
    repo = SupabaseRepository()
    repo.client = make_chain([{"id": "run-1"}])
    units = [{"text": "t", "kind": "fact"}]

    await repo.createExtractions(
        "src-1", "top-1", units,
        status="completed", extraction_strategy="curl",
        started_at="2026-07-24T00:00:00", usage={"total_tokens": 42},
    )

    (row,), _ = repo.client.insert.call_args
    assert row["metadata"] == {"units": units, "usage": {"total_tokens": 42}}
    assert row["source_id"] == "src-1"
    assert row["topic_id"] == "top-1"
    assert row["status"] == "completed"
    assert row["extraction_strategy"] == "curl"
    assert row["started_at"] == "2026-07-24T00:00:00"
    assert row["completed_at"]          # set by the repo
