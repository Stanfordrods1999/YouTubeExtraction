"""Unit tests for topicExtractionService.extract (repo mocked, no network)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.app.services.topicExtractionService import topicExtractionService


@pytest.mark.asyncio
async def test_extract_persists_chain_output_and_returns_ids():
    repo = MagicMock()
    repo.createTopic = AsyncMock(return_value=["id-1", "id-2"])

    service = topicExtractionService(repo)
    fake_topics = [
        {"topicText": "Cursor AI", "status": "pending", "createdBy": "system",
         "confidence": 0.91, "metadata": {}},
        {"topicText": "Bleh AI", "status": "pending", "createdBy": "system",
         "confidence": 0.91, "metadata": {}},
    ]
    service._run_extraction_chain = AsyncMock(return_value=fake_topics)

    result = await service.extract({"topicText": "AI coding agents"})

    assert result == ["id-1", "id-2"]
    service._run_extraction_chain.assert_awaited_once_with("AI coding agents")
    repo.createTopic.assert_awaited_once_with(fake_topics)
