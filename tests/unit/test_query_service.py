"""Unit tests for QueryService — the read path.

Retrieval embeds the question, optionally blends a thread's Rocchio-refined
centroid, and delegates the similarity search to the match_units RPC.
Answering formats numbered evidence and returns the units as citations.
All I/O (OpenAI, chat model, repo) is mocked.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from src.app.services.queryService import QueryService

MODULE = "src.app.services.queryService"


def make_openai(embedding):
    resp = MagicMock()
    resp.data = [MagicMock(embedding=embedding)]
    client = MagicMock()
    client.embeddings.create = AsyncMock(return_value=resp)
    return client


def make_repo(matches=None, centroid=None):
    repo = MagicMock()
    repo.matchUnits = AsyncMock(return_value=matches or [])
    repo.getLatestCentroid = AsyncMock(return_value=centroid)
    return repo


def make_service(repo, embedding, chat_reply="answer text"):
    """Builds a QueryService with patched OpenAI + chat clients."""
    message = MagicMock()
    message.content = chat_reply
    chat = MagicMock()
    chat.ainvoke = AsyncMock(return_value=message)
    with patch(f"{MODULE}.AsyncOpenAI", return_value=make_openai(embedding)), \
         patch(f"{MODULE}.ChatOpenAI", return_value=chat):
        svc = QueryService(repo)
    return svc, chat


@pytest.mark.asyncio
async def test_retrieve_without_thread_searches_with_raw_question_embedding():
    repo = make_repo(matches=[{"content": "a fact"}])
    svc, _ = make_service(repo, embedding=[1.0, 0.0])

    out = await svc.retrieve("what is X?", k=5, topic_id="top-1")

    assert out == [{"content": "a fact"}]
    repo.getLatestCentroid.assert_not_awaited()
    repo.matchUnits.assert_awaited_once_with([1.0, 0.0], k=5, topic_id="top-1")

    _, kwargs = svc.openai.embeddings.create.await_args
    assert kwargs["model"] == "text-embedding-3-small"
    assert kwargs["input"] == "what is X?"


@pytest.mark.asyncio
async def test_retrieve_with_thread_blends_refined_centroid():
    repo = make_repo(centroid=[0.0, 1.0])
    svc, _ = make_service(repo, embedding=[1.0, 0.0])

    await svc.retrieve("q", thread_id="run-42", centroid_weight=0.3)

    repo.getLatestCentroid.assert_awaited_once_with("run-42")
    (searched,), kwargs = repo.matchUnits.await_args
    expected = np.array([0.7, 0.3])
    expected = expected / np.linalg.norm(expected)
    assert np.allclose(searched, expected)
    assert np.isclose(np.linalg.norm(searched), 1.0)


@pytest.mark.asyncio
async def test_retrieve_with_thread_but_no_stored_centroid_uses_raw_embedding():
    repo = make_repo(centroid=None)
    svc, _ = make_service(repo, embedding=[1.0, 0.0])

    await svc.retrieve("q", thread_id="run-42")

    (searched,), _ = repo.matchUnits.await_args
    assert searched == [1.0, 0.0]


def test_blend_zero_norm_falls_back_to_query():
    out = QueryService.blend([0.0, 0.0], [0.0, 0.0], 0.3)
    assert out == [0.0, 0.0]


@pytest.mark.asyncio
async def test_answer_formats_numbered_evidence_and_returns_citations():
    units = [
        {"content": "fact one", "source_url": "https://a.example"},
        {"content": "fact two", "source_url": "https://b.example"},
    ]
    repo = make_repo(matches=units)
    svc, chat = make_service(repo, embedding=[1.0], chat_reply="It is so [1].")

    out = await svc.answer("why?")

    assert out == {"answer": "It is so [1].", "citations": units}
    (messages,), _ = chat.ainvoke.await_args
    user_msg = messages[1]["content"]
    assert "[1] fact one (source: https://a.example)" in user_msg
    assert "[2] fact two (source: https://b.example)" in user_msg


@pytest.mark.asyncio
async def test_answer_with_no_evidence_skips_the_llm():
    repo = make_repo(matches=[])
    svc, chat = make_service(repo, embedding=[1.0])

    out = await svc.answer("why?")

    assert out["citations"] == []
    assert "No evidence" in out["answer"]
    chat.ainvoke.assert_not_awaited()
