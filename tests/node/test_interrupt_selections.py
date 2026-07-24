"""Unit tests for the interruptSelections node (human-in-the-loop gate).

The node fetches reviewable source rows (URL, reason, score), pauses the
graph with `interrupt(...)`, then partitions the discovered sources into
selected / non-selected sets from the resume payload
`{"action": "reextract" | "end", "selected_ids": [...]}`.
`interrupt` is patched to stand in for the value injected on resume.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.app.graph.nodes.interruptSelections import interruptSelections

MODULE = "src.app.graph.nodes.interruptSelections"


def make_repo(rows):
    repo = MagicMock()
    repo.getSourcesbyId = AsyncMock(return_value=rows)
    return repo


@pytest.mark.asyncio
async def test_payload_advertises_reviewable_sources_not_just_ids():
    rows = [
        {"id": "a", "source_url": "https://a.example",
         "discovery_reason": "primary study", "priority_score": 0.9},
        {"id": "b", "source_url": "https://b.example",
         "discovery_reason": "survey", "priority_score": 0.6},
    ]
    state = {"sourceIds": ["a", "b"]}
    with patch(f"{MODULE}.get_repo", return_value=make_repo(rows)), \
         patch(f"{MODULE}.interrupt",
               return_value={"action": "end", "selected_ids": []}) as mock_int:
        await interruptSelections(state)

    (payload,), _ = mock_int.call_args
    assert payload["type"] == "source_selection"
    assert payload["source_ids"] == ["a", "b"]
    assert payload["sources"] == rows          # human sees URLs + reasons


@pytest.mark.asyncio
async def test_dict_resume_partitions_and_records_action():
    state = {"sourceIds": ["a", "b", "c"]}
    with patch(f"{MODULE}.get_repo", return_value=make_repo([])), \
         patch(f"{MODULE}.interrupt",
               return_value={"action": "reextract", "selected_ids": ["a", "c"]}):
        out = await interruptSelections(state)

    assert out["userAction"] == "reextract"
    assert out["selectedSourceIds"] == ["a", "c"]
    assert out["nonselectedSourceIds"] == ["b"]


@pytest.mark.asyncio
async def test_json_string_resume_is_parsed():
    state = {"sourceIds": ["a", "b"]}
    with patch(f"{MODULE}.get_repo", return_value=make_repo([])), \
         patch(f"{MODULE}.interrupt",
               return_value='{"action": "end", "selected_ids": ["b"]}'):
        out = await interruptSelections(state)

    assert out["userAction"] == "end"
    assert out["selectedSourceIds"] == ["b"]
    assert out["nonselectedSourceIds"] == ["a"]


@pytest.mark.asyncio
async def test_empty_selection_puts_everything_in_nonselected():
    state = {"sourceIds": ["a", "b"]}
    with patch(f"{MODULE}.get_repo", return_value=make_repo([])), \
         patch(f"{MODULE}.interrupt",
               return_value={"action": "end", "selected_ids": []}):
        out = await interruptSelections(state)

    assert out["selectedSourceIds"] == []
    assert out["nonselectedSourceIds"] == ["a", "b"]


@pytest.mark.asyncio
async def test_malformed_resume_payload_raises_with_expected_shape():
    state = {"sourceIds": ["a"]}
    with patch(f"{MODULE}.get_repo", return_value=make_repo([])), \
         patch(f"{MODULE}.interrupt", return_value=["a"]):
        with pytest.raises(ValueError, match="selected_ids"):
            await interruptSelections(state)


@pytest.mark.asyncio
async def test_no_discovered_sources_skips_the_repo():
    repo = make_repo([])
    state = {"sourceIds": []}
    with patch(f"{MODULE}.get_repo", return_value=repo), \
         patch(f"{MODULE}.interrupt",
               return_value={"action": "end", "selected_ids": []}) as mock_int:
        out = await interruptSelections(state)

    repo.getSourcesbyId.assert_not_awaited()
    (payload,), _ = mock_int.call_args
    assert payload["sources"] == []
    assert out["selectedSourceIds"] == []
