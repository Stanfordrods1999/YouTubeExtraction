"""Unit tests for reconcileSources (the re-extract loop's seeding node).

It seeds the next iteration's topic text — preferring an LLM research brief
written from the selected sources' actual evidence units, falling back to the
sources' discovery reasons — and resets the accumulating state channels
(write None → add_or_reset clears them).
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.app.graph.nodes.reconcileSources import reconcileSources

MODULE = "src.app.graph.nodes.reconcileSources"

SOURCE_ROWS = [
    {"id": "s1", "discovery_reason": "primary study"},
    {"id": "s3", "discovery_reason": "survey"},
]

RESET_KEYS = {
    "topicState": None,
    "topicIds": None,
    "sourceIds": None,
    "selectedSourceIds": None,
    "nonselectedSourceIds": None,
}


def make_repo(units):
    repo = MagicMock()
    repo.getSourcesbyId = AsyncMock(return_value=SOURCE_ROWS)
    repo.getUnitsBySources = AsyncMock(return_value=units)
    return repo


def make_llm(reply):
    message = MagicMock()
    message.content = reply
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=message)
    return llm


@pytest.mark.asyncio
async def test_brief_is_written_from_selected_sources_units():
    repo = make_repo(["fact one", "fact two"])
    llm = make_llm("  Focused brief. ")

    with patch(f"{MODULE}.get_repo", return_value=repo), \
         patch(f"{MODULE}.ChatOpenAI", return_value=llm):
        out = await reconcileSources({
            "selectedSourceIds": ["s1", "s3"],
            "sourceIds": ["s1", "s2", "s3"],
        })

    # Selected ids (not all ids) drive both lookups.
    repo.getSourcesbyId.assert_awaited_once_with(["s1", "s3"])
    repo.getUnitsBySources.assert_awaited_once_with(["s1", "s3"])
    # The evidence made it into the prompt.
    (messages,), _ = llm.ainvoke.await_args
    assert "- fact one" in messages[1]["content"]
    # Brief becomes the next topic text (stripped); channels reset.
    assert out["topicText"] == "Focused brief."
    for key, value in RESET_KEYS.items():
        assert out[key] is value


@pytest.mark.asyncio
async def test_no_units_falls_back_to_discovery_reasons_without_llm():
    repo = make_repo([])

    with patch(f"{MODULE}.get_repo", return_value=repo), \
         patch(f"{MODULE}.ChatOpenAI") as MockChat:
        out = await reconcileSources({"selectedSourceIds": ["s1", "s3"],
                                      "sourceIds": []})

    MockChat.assert_not_called()
    assert out["topicText"] == "primary study\n\nsurvey"


@pytest.mark.asyncio
async def test_llm_failure_falls_back_to_discovery_reasons():
    repo = make_repo(["fact one"])
    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=RuntimeError("model down"))

    with patch(f"{MODULE}.get_repo", return_value=repo), \
         patch(f"{MODULE}.ChatOpenAI", return_value=llm):
        out = await reconcileSources({"selectedSourceIds": ["s1"],
                                      "sourceIds": []})

    assert out["topicText"] == "primary study\n\nsurvey"


@pytest.mark.asyncio
async def test_empty_selection_falls_back_to_all_source_ids():
    repo = make_repo([])

    with patch(f"{MODULE}.get_repo", return_value=repo), \
         patch(f"{MODULE}.ChatOpenAI"):
        await reconcileSources({"selectedSourceIds": None,
                                "sourceIds": ["s1", "s2"]})

    repo.getSourcesbyId.assert_awaited_once_with(["s1", "s2"])
