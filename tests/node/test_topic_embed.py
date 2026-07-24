"""Unit tests for the topicEmbed node.

Embeds the topic text with the configured embedding model, persists the
initial centroid for the thread (retrieval blending + evals read it back),
and returns `topicCentroid`. On a re-extract pass it must do nothing —
the refined centroid would otherwise be overwritten.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.app.graph.nodes.topicEmbed import topicEmbed

MODULE = "src.app.graph.nodes.topicEmbed"


def make_repo():
    repo = MagicMock()
    repo.saveCentroid = AsyncMock()
    return repo


@pytest.mark.asyncio
async def test_embeds_topic_text_persists_initial_centroid_and_returns_it():
    resp = MagicMock()
    resp.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
    fake_client = MagicMock()
    fake_client.embeddings.create = AsyncMock(return_value=resp)
    repo = make_repo()

    with patch(f"{MODULE}.client", fake_client), \
         patch(f"{MODULE}.get_repo", return_value=repo):
        result = await topicEmbed(
            {"topicText": "quantum error correction"},
            config={"configurable": {"thread_id": "run-42"}},
        )

    # Returns under the key GlobalState defines.
    assert result == {"topicCentroid": [0.1, 0.2, 0.3]}

    _, kwargs = fake_client.embeddings.create.await_args
    # Uses an embedding model, not a chat model.
    assert kwargs["model"] == "text-embedding-3-small"
    assert kwargs["input"] == "quantum error correction"

    # Initial centroid persisted for this thread.
    repo.saveCentroid.assert_awaited_once_with(
        thread_id="run-42",
        kind="initial",
        centroid=[0.1, 0.2, 0.3],
        topic_text="quantum error correction",
    )


@pytest.mark.asyncio
async def test_missing_config_falls_back_to_default_thread():
    resp = MagicMock()
    resp.data = [MagicMock(embedding=[0.5])]
    fake_client = MagicMock()
    fake_client.embeddings.create = AsyncMock(return_value=resp)
    repo = make_repo()

    with patch(f"{MODULE}.client", fake_client), \
         patch(f"{MODULE}.get_repo", return_value=repo):
        await topicEmbed({"topicText": "x"})

    assert repo.saveCentroid.await_args.kwargs["thread_id"] == "default"


@pytest.mark.asyncio
async def test_reextract_pass_is_a_noop():
    fake_client = MagicMock()
    fake_client.embeddings.create = AsyncMock()
    repo = make_repo()

    with patch(f"{MODULE}.client", fake_client), \
         patch(f"{MODULE}.get_repo", return_value=repo):
        result = await topicEmbed({"topicText": "x", "userAction": "reextract"})

    assert result == {}
    fake_client.embeddings.create.assert_not_awaited()
    repo.saveCentroid.assert_not_awaited()
