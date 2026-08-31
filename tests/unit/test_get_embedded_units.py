"""Unit test for SupabaseRepository.getEmbeddedUnits (added in the Rocchio commit).

Verifies the query targets extracted_units joined to extraction_runs by
source_id, and that each row's `embedding` (stored as a JSON string) is
decoded back into a list of floats. The Supabase client is a fake chain.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.supabaseRepository import SupabaseRepository


def make_client(rows):
    """A fake Supabase client whose fluent chain returns `rows` on execute()."""
    chain = MagicMock()
    chain.table.return_value = chain
    chain.select.return_value = chain
    chain.in_.return_value = chain
    resp = MagicMock()
    resp.data = rows
    chain.execute = AsyncMock(return_value=resp)
    return chain


@pytest.mark.asyncio
async def test_parses_json_embeddings_and_filters_by_source_id():
    repo = SupabaseRepository()
    repo.client = make_client(
        [{"embedding": "[1.0, 2.0, 3.0]"}, {"embedding": "[4.0, 5.0, 6.0]"}]
    )

    out = await repo.getEmbeddedUnits(["src-1", "src-2"])

    assert out == [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
    repo.client.table.assert_called_once_with("extracted_units")
    repo.client.in_.assert_called_once_with(
        "extraction_runs.source_id", ["src-1", "src-2"]
    )


@pytest.mark.asyncio
async def test_empty_result_returns_empty_list():
    repo = SupabaseRepository()
    repo.client = make_client([])

    out = await repo.getEmbeddedUnits(["src-1"])

    assert out == []


def make_run_client(rows):
    """Fake client for the getUnitsByRun chain (select → eq → order)."""
    chain = MagicMock()
    chain.table.return_value = chain
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.order.return_value = chain
    resp = MagicMock()
    resp.data = rows
    chain.execute = AsyncMock(return_value=resp)
    return chain


@pytest.mark.asyncio
async def test_get_units_by_run_round_trips_vector_to_text():
    # Tier 0.1's "done when": a stored vector can be read back together with
    # the text it was computed from.
    repo = SupabaseRepository()
    repo.client = make_run_client(
        [
            {"id": "u-0", "unit_index": 0, "semantic_type": "fact",
             "content": "Cory Barlog directed God of War 2018.",
             "embedding": "[1.0, 2.0]"},
            {"id": "u-1", "unit_index": 1, "semantic_type": "claim",
             "content": "Kratos' journey is not over.",
             "embedding": [3.0, 4.0]},
        ]
    )

    out = await repo.getUnitsByRun("run-1")

    assert [u["content"] for u in out] == [
        "Cory Barlog directed God of War 2018.",
        "Kratos' journey is not over.",
    ]
    # embeddings decoded whether the driver hands back JSON text or a list
    assert [u["embedding"] for u in out] == [[1.0, 2.0], [3.0, 4.0]]
    repo.client.eq.assert_called_once_with("extraction_run_id", "run-1")
    repo.client.order.assert_called_once_with("unit_index")
