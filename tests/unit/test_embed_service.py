"""Unit tests for EmbeddingService.embed_pending.

Contract: read the pending unit dicts from the run's metadata blob, embed
their texts in batches, and insert *complete* extracted_units rows —
content and semantic_type travel WITH the embedding, so a similarity hit
can always show the sentence it encodes. zip(strict=True) guards against
misattributing embeddings to the wrong sentences.

AsyncOpenAI is instantiated inside __init__, so we patch it in the
service's module namespace (patch where it's *used*).
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.app.services.embeddingServices import BATCH_SIZE, EmbeddingService

MODULE = "src.app.services.embeddingServices"


def make_unit(i, kind="fact"):
    return {"text": f"some text {i}", "kind": kind,
            "source_id": "src-1", "topic_id": "top-1"}


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


def make_repo(units, already_embedded=False, legacy_shape=False):
    repo = MagicMock()
    repo.hasEmbeddedUnits = AsyncMock(return_value=already_embedded)
    # getUnEmbeddedUnits returns the run row; units live under
    # metadata["units"] (older rows stored the bare list).
    metadata = units if legacy_shape else {"units": units, "usage": {}}
    repo.getUnEmbeddedUnits = AsyncMock(return_value={"metadata": metadata})
    repo.updateUnitEmbeddings = AsyncMock()
    return repo


@pytest.mark.asyncio
async def test_no_pending_units_returns_zero_and_never_calls_openai():
    repo = make_repo([])
    client = make_openai_mock([])
    with patch(f"{MODULE}.AsyncOpenAI", return_value=client):
        svc = EmbeddingService(repo=repo, e_run_id="run-1")
        result = await svc.embed_pending()

    assert result == 0
    repo.getUnEmbeddedUnits.assert_awaited_once_with(e_run_id="run-1")
    client.embeddings.create.assert_not_awaited()
    repo.updateUnitEmbeddings.assert_not_awaited()


@pytest.mark.asyncio
async def test_already_embedded_run_is_skipped_idempotently():
    # Retries / resumed threads must not embed (and pay for) a run twice.
    repo = make_repo([make_unit(0)], already_embedded=True)
    client = make_openai_mock([])
    with patch(f"{MODULE}.AsyncOpenAI", return_value=client):
        svc = EmbeddingService(repo=repo, e_run_id="run-1")
        result = await svc.embed_pending()

    assert result == 0
    repo.getUnEmbeddedUnits.assert_not_awaited()
    client.embeddings.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_bare_list_metadata_still_embeds():
    repo = make_repo([make_unit(0)], legacy_shape=True)
    client = make_openai_mock([[[0.1]]])
    with patch(f"{MODULE}.AsyncOpenAI", return_value=client):
        svc = EmbeddingService(repo=repo, e_run_id="run-1")
        result = await svc.embed_pending()

    assert result == 1


@pytest.mark.asyncio
async def test_inserts_content_and_semantic_type_with_each_embedding():
    units = [make_unit(0, kind="fact"), make_unit(1, kind="statistic")]
    vectors = [[0.1, 0.2], [0.3, 0.4]]
    repo = make_repo(units)
    client = make_openai_mock([vectors])

    with patch(f"{MODULE}.AsyncOpenAI", return_value=client):
        svc = EmbeddingService(repo=repo, e_run_id="run-1")
        result = await svc.embed_pending()

    assert result == 2

    # Correct model and exact input texts, in order.
    _, kwargs = client.embeddings.create.await_args
    assert kwargs["model"] == "text-embedding-3-small"
    assert kwargs["input"] == ["some text 0", "some text 1"]

    # THE critical assertion: each row carries its own text + type + vector.
    (updates,), _ = repo.updateUnitEmbeddings.await_args
    assert updates == [
        {"extraction_run_id": "run-1", "content": "some text 0",
         "semantic_type": "fact", "embedding": [0.1, 0.2]},
        {"extraction_run_id": "run-1", "content": "some text 1",
         "semantic_type": "statistic", "embedding": [0.3, 0.4]},
    ]


@pytest.mark.asyncio
async def test_batches_split_at_batch_size():
    n = BATCH_SIZE + 3
    units = [make_unit(i) for i in range(n)]
    repo = make_repo(units)
    client = make_openai_mock([
        [[float(i)] for i in range(BATCH_SIZE)],
        [[float(i)] for i in range(3)],
    ])

    with patch(f"{MODULE}.AsyncOpenAI", return_value=client):
        svc = EmbeddingService(repo=repo, e_run_id="run-1")
        result = await svc.embed_pending()

    assert result == n
    assert client.embeddings.create.await_count == 2
    assert repo.updateUnitEmbeddings.await_count == 2


@pytest.mark.asyncio
async def test_embedding_count_mismatch_raises_instead_of_misattributing():
    # If OpenAI returned fewer vectors than texts, silently zipping would
    # pair sentences with the wrong embeddings; strict zip must raise.
    units = [make_unit(0), make_unit(1)]
    repo = make_repo(units)
    client = make_openai_mock([[[0.1, 0.2]]])   # only ONE vector for two texts

    with patch(f"{MODULE}.AsyncOpenAI", return_value=client):
        svc = EmbeddingService(repo=repo, e_run_id="run-1")
        with pytest.raises(ValueError):
            await svc.embed_pending()

    repo.updateUnitEmbeddings.assert_not_awaited()
