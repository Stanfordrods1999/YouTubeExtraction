from datetime import datetime, timezone
from typing import List
from unittest.mock import AsyncMock

import pytest

from src.app.services.topicExtractionService import topicExtractionService
from src.app.graph.state import TopicState
from db.supabaseRepository import SupabaseRepository


@pytest.mark.asyncio
async def test_extract_saves_topics():

    repo = SupabaseRepository()
    await repo.initialize()

    service = topicExtractionService(
        repo=repo,
        llm=None
    )

    fake_topics = [
        {
            "topicText": "Cursor AI",
            "status": "pending",
            "createdBy": "system",
            "confidence": 0.91,
            "createdAt": datetime.now(timezone.utc),
            "metadata": {}
        },
        {
            "topicText": "Bleh AI",
            "status": "pending",
            "createdBy": "system",
            "confidence": 0.91,
            "createdAt": datetime.now(timezone.utc),
            "metadata": {}
        }
    ]

    service._run_extraction_chain = AsyncMock(
        return_value=fake_topics
    )

    state: TopicState = {
        "topicText": "AI coding agents",
        "status": "pending",
        "createdBy": "user",
        "confidence": 1.0,
        "createdAt": datetime.now(timezone.utc),
        "metadata": {}
    }

    result = await service.extract(state)

    assert result is not None

    assert result is List[str]

    print(result)