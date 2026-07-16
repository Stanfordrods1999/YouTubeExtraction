"""Unit tests for the topicEmbed node.

The Rocchio commit fixed two bugs here: it now uses a real embedding model
(`text-embedding-3-small`, not the chat model `MODEL`) and returns the value
under `topicCentroid` (the key GlobalState actually defines) rather than the
dropped `topicEmbedding`.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.app.graph.nodes.topicEmbed import topicEmbed

MODULE = "src.app.graph.nodes.topicEmbed"


@pytest.mark.asyncio
async def test_embeds_topic_text_and_returns_centroid():
    resp = MagicMock()
    resp.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
    fake_client = MagicMock()
    fake_client.embeddings.create = AsyncMock(return_value=resp)

    with patch(f"{MODULE}.client", fake_client):
        result = await topicEmbed({"topicText": "quantum error correction"})

    # Returns under the key GlobalState defines.
    assert result == {"topicCentroid": [0.1, 0.2, 0.3]}

    _, kwargs = fake_client.embeddings.create.await_args
    # Uses an embedding model, not a chat model.
    assert kwargs["model"] == "text-embedding-3-small"
    assert kwargs["input"] == "quantum error correction"
