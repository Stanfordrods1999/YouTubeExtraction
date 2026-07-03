# tests/services/test_embedding_service.py
#
# Requires: pytest, pytest-asyncio
# Tests the FIXED embed_pending: updates keyed by row["id"], zip(strict=True).
#
# AsyncOpenAI is instantiated inside __init__, so we patch it in the
# service's module namespace (patch where it's *used*).

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.app.services.embeddingServices import embeddingService, BATCH_SIZE

MODULE = "src.app.services.embeddingServices"


def make_row(i):
    return {"id": f"unit-{i}", "text": f"some text {i}"}


def make_openai_mock(embeddings_per_call):
    """embeddings_per_call: list of lists — one inner list per expected
    API call, each containing the embedding vectors to return."""
    client = MagicMock()
    responses = []
    for vectors in embeddings_per_call:
        resp = MagicMock()
        resp.data = [MagicMock(embedding=v) for v in vectors]
        responses.append(resp)
    client.embeddings.create = AsyncMock(side_effect=responses)
    return client


def make_repo(rows):
    repo = MagicMock()
    repo.getUnEmbeddedUnits = AsyncMock(return_value=rows)
    repo.updateUnitEmbeddings = AsyncMock()
    return repo


@pytest.mark.asyncio
async def test_no_pending_rows_returns_zero_and_never_calls_openai():
    repo = make_repo([])
    client = make_openai_mock([])
    with patch(f"{MODULE}.AsyncOpenAI", return_value=client):
        svc = embeddingService(repo=repo, e_run_id="run-1")
        result = await svc.embed_pending()

    assert result == 0
    repo.getUnEmbeddedUnits.assert_awaited_once_with(e_run_id="run-1")
    client.embeddings.create.assert_not_awaited()
    repo.updateUnitEmbeddings.assert_not_awaited()


@pytest.mark.asyncio
async def test_single_batch_updates_keyed_by_unit_id():
    rows = [make_row(0), make_row(1)]
    vectors = [[0.1, 0.2], [0.3, 0.4]]
    repo = make_repo(rows)
    client = make_openai_mock([vectors])

    with patch(f"{MODULE}.AsyncOpenAI", return_value=client):
        svc = embeddingService(repo=repo, e_run_id="run-1")
        result = await svc.embed_pending()

    assert result == 2

    # Correct model and exact input texts, in order
    _, kwargs = client.embeddings.create.await_args
    assert kwargs["model"] == "text-embedding-3-small"
    assert kwargs["input"] == ["some text 0", "some text 1"]

    # THE critical assertion: each unit id paired with ITS embedding
    (updates,), _ = repo.updateUnitEmbeddings.await_args
    assert updates == [
        {"id": "unit-0", "embedding": [0.1, 0.2]},
        {"id": "unit-1", "embedding": [0.3, 0.4]},
    ]