"""Unit tests for the centroidEmbedding node.

The node hands the current topic centroid plus the user's selected /
non-selected source ids to TransformationService, persists the refined
centroid for the thread, and returns a *partial* `{"topicCentroid": ...}`
update (returning the whole state would double the add-reducer channels).
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.app.graph.nodes.centroidEmbedding import centroidEmbedding

MODULE = "src.app.graph.nodes.centroidEmbedding"


@pytest.mark.asyncio
async def test_refines_persists_and_returns_partial_update():
    repo = MagicMock()
    repo.saveCentroid = AsyncMock()

    with patch(f"{MODULE}.get_repo", return_value=repo) as mock_get_repo, \
         patch(f"{MODULE}.TransformationService") as MockService:
        MockService.return_value.compute_query_vector = AsyncMock(
            return_value=[0.5, 0.5]
        )

        state = {
            "topicText": "quantum error correction",
            "topicCentroid": [1.0, 0.0],
            "selectedSourceIds": ["s1"],
            "nonselectedSourceIds": ["s2"],
            "iteration": 1,
        }
        result = await centroidEmbedding(
            state, config={"configurable": {"thread_id": "run-42"}}
        )

    # Service built from the lazily-resolved repo.
    mock_get_repo.assert_called_once()
    MockService.assert_called_once_with(repo)

    # Called with (q0, selected, non-selected) in that order.
    MockService.return_value.compute_query_vector.assert_awaited_once_with(
        [1.0, 0.0], ["s1"], ["s2"]
    )

    # Refined centroid persisted for this thread + iteration.
    repo.saveCentroid.assert_awaited_once_with(
        thread_id="run-42",
        kind="refined",
        centroid=[0.5, 0.5],
        topic_text="quantum error correction",
        iteration=1,
    )

    # Partial update only.
    assert result == {"topicCentroid": [0.5, 0.5]}
