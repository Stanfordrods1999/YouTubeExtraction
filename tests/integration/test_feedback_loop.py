"""Integration test for the relevance-feedback slice of the pipeline.

Wires `interruptSelections` and `centroidEmbedding` into a real (small)
StateGraph with an in-memory checkpointer, then drives the
human-in-the-loop cycle:

    invoke → graph pauses at the interrupt
    resume(Command) → selection is partitioned → centroid is recomputed

Only the external I/O (repo + TransformationService) is mocked; the
interrupt/resume and state-passing are exercised for real.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command

from src.app.graph.nodes.centroidEmbedding import centroidEmbedding
from src.app.graph.nodes.interruptSelections import interruptSelections
from src.app.graph.state import GlobalState

CENTROID_MODULE = "src.app.graph.nodes.centroidEmbedding"
INTERRUPT_MODULE = "src.app.graph.nodes.interruptSelections"

SOURCE_ROWS = [
    {"id": "s1", "source_url": "https://one.example",
     "discovery_reason": "primary study", "priority_score": 0.9},
    {"id": "s2", "source_url": "https://two.example",
     "discovery_reason": "opinion piece", "priority_score": 0.4},
    {"id": "s3", "source_url": "https://three.example",
     "discovery_reason": "survey", "priority_score": 0.7},
]


def _build_graph():
    builder = StateGraph(GlobalState)
    builder.add_node("feedbackInterrupt", interruptSelections)
    builder.add_node("centroidEmbedding", centroidEmbedding)
    builder.add_edge(START, "feedbackInterrupt")
    builder.add_edge("feedbackInterrupt", "centroidEmbedding")
    builder.add_edge("centroidEmbedding", END)
    return builder.compile(checkpointer=MemorySaver())


@pytest.mark.asyncio
async def test_interrupt_then_resume_recomputes_centroid():
    graph = _build_graph()
    config = {"configurable": {"thread_id": "feedback-1"}}

    inputs = {
        "topicText": "quantum error correction",
        "topicCentroid": [1.0, 0.0],
        "sourceIds": ["s1", "s2", "s3"],
    }

    interrupt_repo = MagicMock()
    interrupt_repo.getSourcesbyId = AsyncMock(return_value=SOURCE_ROWS)
    centroid_repo = MagicMock()
    centroid_repo.saveCentroid = AsyncMock()

    with patch(f"{INTERRUPT_MODULE}.get_repo", return_value=interrupt_repo), \
         patch(f"{CENTROID_MODULE}.get_repo", return_value=centroid_repo), \
         patch(f"{CENTROID_MODULE}.TransformationService") as MockService:
        MockService.return_value.compute_query_vector = AsyncMock(
            return_value=[0.0, 1.0]
        )

        # First pass: the graph must pause at the human-in-the-loop interrupt,
        # advertising reviewable source rows (not bare UUIDs).
        first = await graph.ainvoke(inputs, config)
        assert "__interrupt__" in first
        payload = first["__interrupt__"][0].value
        assert payload["type"] == "source_selection"
        assert payload["source_ids"] == ["s1", "s2", "s3"]
        assert payload["sources"] == SOURCE_ROWS

        # Resume with the user's picks; the graph runs to completion.
        final = await graph.ainvoke(
            Command(resume={"action": "end", "selected_ids": ["s1", "s3"]}),
            config,
        )

    # Selection was partitioned correctly...
    assert final["userAction"] == "end"
    assert final["selectedSourceIds"] == ["s1", "s3"]
    assert final["nonselectedSourceIds"] == ["s2"]

    # ...and the refined centroid was computed from (q0, selected, non-selected).
    MockService.return_value.compute_query_vector.assert_awaited_once_with(
        [1.0, 0.0], ["s1", "s3"], ["s2"]
    )
    assert final["topicCentroid"] == [0.0, 1.0]
