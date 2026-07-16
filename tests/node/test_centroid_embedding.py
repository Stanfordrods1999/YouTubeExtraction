"""Unit tests for the centroidEmbedding node.

The node hands the current topic centroid plus the user's selected /
non-selected source ids to TransformationService and writes the refined
centroid back onto the state. Both the repo and the service are mocked.
"""
from unittest.mock import AsyncMock, patch

import pytest

from src.app.graph.nodes.centroidEmbedding import centroidEmbedding

MODULE = "src.app.graph.nodes.centroidEmbedding"


@pytest.mark.asyncio
async def test_refines_centroid_from_relevance_feedback():
    with patch(f"{MODULE}.get_repo", return_value=object()) as mock_get_repo, \
         patch(f"{MODULE}.TransformationService") as MockService:
        MockService.return_value.compute_query_vector = AsyncMock(
            return_value=[0.5, 0.5]
        )

        state = {
            "topicCentroid": [1.0, 0.0],
            "selectedSourceIds": ["s1"],
            "nonselectedSourceIds": ["s2"],
        }
        result = await centroidEmbedding(state)

    # Service built from the lazily-resolved repo.
    mock_get_repo.assert_called_once()
    MockService.assert_called_once_with(mock_get_repo.return_value)

    # Called with (q0, selected, non-selected) in that order.
    MockService.return_value.compute_query_vector.assert_awaited_once_with(
        [1.0, 0.0], ["s1"], ["s2"]
    )

    # Refined centroid is written back onto the state.
    assert result["topicCentroid"] == [0.5, 0.5]
