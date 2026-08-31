# tests/unit/test_embed_service.py
#
# Requires: pytest, pytest-asyncio
# Covers embed_pending after Tier 0.1: each stored row carries the text it was
# embedded from, and the pairing survives an out-of-order API response.
#
# AsyncOpenAI is instantiated inside __init__, so we patch it in the
# service's module namespace (patch where it's *used*).

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.app.services.embeddingServices import embeddingService, BATCH_SIZE

MODULE = "src.app.services.embeddingServices"


def make_row(i, kind="fact"):
    """A unit as it actually lives in extraction_runs.metadata."""
    return {
        "kind": kind,
        "text": f"some text {i}",
        "topic_id": "topic-1",
        "source_id": "source-1",
    }


def make_openai_mock(embeddings_per_call, shuffle=False):
    """embeddings_per_call: list of lists — one inner list per expected
    API call, each containing the embedding vectors to return, in input order.

    shuffle=True reverses `data` while keeping each item's `index` intact,
    which is what the API is permitted to do.
    """
    client = MagicMock()
    responses = []
    for vectors in embeddings_per_call:
        resp = MagicMock()
        data = [MagicMock(index=i, embedding=v) for i, v in enumerate(vectors)]
        resp.data = list(reversed(data)) if shuffle else data
        responses.append(resp)
    client.embeddings.create = AsyncMock(side_effect=responses)
    return client


def make_repo(rows):
    repo = MagicMock()
    repo.getUnEmbeddedUnits = AsyncMock(return_value={"metadata": rows})
    repo.updateUnitEmbeddings = AsyncMock()
    return repo


async def run_embed(repo, client):
    with patch(f"{MODULE}.AsyncOpenAI", return_value=client):
        svc = embeddingService(repo=repo, e_run_id="run-1")
        return await svc.embed_pending()


@pytest.mark.asyncio
async def test_no_pending_rows_returns_zero_and_never_calls_openai():
    repo = make_repo([])
    client = make_openai_mock([])
    result = await run_embed(repo, client)

    assert result == 0
    repo.getUnEmbeddedUnits.assert_awaited_once_with(e_run_id="run-1")
    client.embeddings.create.assert_not_awaited()
    repo.updateUnitEmbeddings.assert_not_awaited()


@pytest.mark.asyncio
async def test_each_row_is_stored_with_the_text_it_was_embedded_from():
    rows = [make_row(0), make_row(1, kind="claim")]
    repo = make_repo(rows)
    client = make_openai_mock([[[0.1, 0.2], [0.3, 0.4]]])

    result = await run_embed(repo, client)
    assert result == 2

    # Correct model and exact input texts, in order
    _, kwargs = client.embeddings.create.await_args
    assert kwargs["model"] == "text-embedding-3-small"
    assert kwargs["input"] == ["some text 0", "some text 1"]

    # THE critical assertion: the vector is written next to its own text, so a
    # nearest-neighbour hit can be read back instead of being an orphan id.
    (updates,), _ = repo.updateUnitEmbeddings.await_args
    assert updates == [
        {
            "extraction_run_id": "run-1",
            "unit_index": 0,
            "content": "some text 0",
            "semantic_type": "fact",
            "embedding": [0.1, 0.2],
        },
        {
            "extraction_run_id": "run-1",
            "unit_index": 1,
            "content": "some text 1",
            "semantic_type": "claim",
            "embedding": [0.3, 0.4],
        },
    ]


@pytest.mark.asyncio
async def test_pairing_survives_out_of_order_response_data():
    # The API guarantees `index`, not the order of `data`. Reversing `data`
    # must not change which text each vector is filed under.
    rows = [make_row(0), make_row(1)]
    repo = make_repo(rows)
    client = make_openai_mock([[[0.1, 0.2], [0.3, 0.4]]], shuffle=True)

    await run_embed(repo, client)

    (updates,), _ = repo.updateUnitEmbeddings.await_args
    assert [(u["content"], u["embedding"]) for u in updates] == [
        ("some text 0", [0.1, 0.2]),
        ("some text 1", [0.3, 0.4]),
    ]


@pytest.mark.asyncio
async def test_unit_index_is_global_across_batches():
    # unit_index is the unit's ordinal in the run's metadata array, not its
    # position in the batch — it is half the upsert key, so it must not reset.
    rows = [make_row(i) for i in range(BATCH_SIZE + 2)]
    repo = make_repo(rows)
    first = [[float(i)] for i in range(BATCH_SIZE)]
    second = [[float(BATCH_SIZE)], [float(BATCH_SIZE + 1)]]
    client = make_openai_mock([first, second])

    result = await run_embed(repo, client)
    assert result == BATCH_SIZE + 2

    (second_updates,), _ = repo.updateUnitEmbeddings.await_args
    assert [u["unit_index"] for u in second_updates] == [BATCH_SIZE, BATCH_SIZE + 1]
    assert [u["content"] for u in second_updates] == [
        f"some text {BATCH_SIZE}",
        f"some text {BATCH_SIZE + 1}",
    ]


@pytest.mark.asyncio
async def test_short_response_is_an_error_not_a_silent_misalignment():
    # zip(strict=True): a response with fewer vectors than inputs used to slide
    # every later text onto the wrong vector. It must raise instead.
    rows = [make_row(0), make_row(1)]
    repo = make_repo(rows)
    client = make_openai_mock([[[0.1, 0.2]]])

    with pytest.raises(ValueError):
        await run_embed(repo, client)

    repo.updateUnitEmbeddings.assert_not_awaited()
