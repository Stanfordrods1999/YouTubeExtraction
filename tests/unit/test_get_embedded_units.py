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
