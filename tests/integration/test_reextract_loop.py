"""Two full iterations of the re-extract loop, against the real loop nodes.

Replicates graph.py's exact wiring (START fan-out, Send-based map, the
feedbackInterrupt → centroidEmbedding edge, routeAfterCentroid's Command
routing, reconcileSources' channel resets) with only the extraction pipeline
stubbed. This is the test that pins the loop's three failure modes:

  1. the join-edge stall — the second interrupt must actually fire;
  2. reducer no-op resets / full-state doubling — iteration 2 must fan out
     over ONLY iteration 2's topics and advertise only its sources;
  3. an unbounded loop — max_iterations must end the run even when the user
     keeps answering "reextract".
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send

from src.app.config import settings
from src.app.graph.nodes.centroidEmbedding import centroidEmbedding
from src.app.graph.nodes.interruptSelections import interruptSelections
from src.app.graph.nodes.reconcileSources import reconcileSources
from src.app.graph.nodes.routeAfterCentroid import route_after_centroid
from src.app.graph.state import GlobalState

CENTROID = "src.app.graph.nodes.centroidEmbedding"
INTERRUPT = "src.app.graph.nodes.interruptSelections"
RECONCILE = "src.app.graph.nodes.reconcileSources"


def build_loop_graph(fan_out_log):
    """graph.py's wiring with topicExtractor / sourceDiscovery stubbed.

    Each topicExtractor call mints one fresh topic id; fan_out_log records
    exactly which topicIds each fan-out covered — the doubling regression
    shows up here as old ids reappearing.
    """
    counter = {"n": 0}

    async def topicExtractor(state):
        counter["n"] += 1
        return {"topicIds": [f"t{counter['n']}"]}

    def fan_out_sources(state):
        fan_out_log.append(list(state["topicIds"]))
        return [Send("sourceDiscovery", {"topic_id": tid})
                for tid in state["topicIds"]]

    async def sourceDiscovery(state):
        return {"sourceIds": [f"src-{state['topic_id']}"]}

    async def embedTopic(state):
        if state.get("userAction") == "reextract":
            return {}
        return {"topicCentroid": [1.0, 0.0]}

    builder = StateGraph(GlobalState)
    builder.add_node("topicExtractor", topicExtractor)
    builder.add_node("sourceDiscovery", sourceDiscovery)
    builder.add_node("feedbackInterrupt", interruptSelections)
    builder.add_node("centroidEmbedding", centroidEmbedding)
    builder.add_node("routeAfterCentroid", route_after_centroid)
    builder.add_node("reconcileSources", reconcileSources)
    builder.add_node("embedTopic", embedTopic)
    builder.add_edge(START, "topicExtractor")
    builder.add_edge(START, "embedTopic")
    builder.add_conditional_edges("topicExtractor", fan_out_sources, ["sourceDiscovery"])
    builder.add_edge("sourceDiscovery", "feedbackInterrupt")
    builder.add_edge("feedbackInterrupt", "centroidEmbedding")
    builder.add_edge("embedTopic", END)
    builder.add_edge("centroidEmbedding", "routeAfterCentroid")
    builder.add_edge("reconcileSources", "topicExtractor")
    return builder.compile(checkpointer=MemorySaver())


def rows_for(ids):
    return [{"id": i, "source_url": f"https://{i}.example",
             "discovery_reason": f"reason for {i}", "priority_score": 0.5}
            for i in ids]


def make_repos():
    interrupt_repo = MagicMock()
    interrupt_repo.getSourcesbyId = AsyncMock(side_effect=lambda ids: rows_for(ids))
    centroid_repo = MagicMock()
    centroid_repo.saveCentroid = AsyncMock()
    reconcile_repo = MagicMock()
    reconcile_repo.getSourcesbyId = AsyncMock(side_effect=lambda ids: rows_for(ids))
    # No stored units → reconcile falls back to discovery reasons (no LLM).
    reconcile_repo.getUnitsBySources = AsyncMock(return_value=[])
    return interrupt_repo, centroid_repo, reconcile_repo


@pytest.mark.asyncio
async def test_two_iterations_no_duplication_then_clean_finish():
    fan_out_log = []
    graph = build_loop_graph(fan_out_log)
    config = {"configurable": {"thread_id": "loop-1"}}
    interrupt_repo, centroid_repo, reconcile_repo = make_repos()

    with patch(f"{INTERRUPT}.get_repo", return_value=interrupt_repo), \
         patch(f"{CENTROID}.get_repo", return_value=centroid_repo), \
         patch(f"{RECONCILE}.get_repo", return_value=reconcile_repo), \
         patch(f"{CENTROID}.TransformationService") as MockService:
        MockService.return_value.compute_query_vector = AsyncMock(
            return_value=[0.0, 1.0]
        )

        # Iteration 1: pause at the interrupt with iteration-1 sources.
        first = await graph.ainvoke({"topicText": "seed topic"}, config)
        payload = first["__interrupt__"][0].value
        assert payload["source_ids"] == ["src-t1"]

        # Resume with "reextract" → the loop must come back around and pause
        # again (a joined embedTopic+feedbackInterrupt edge would stall here).
        second = await graph.ainvoke(
            Command(resume={"action": "reextract", "selected_ids": ["src-t1"]}),
            config,
        )
        assert "__interrupt__" in second, "second interrupt never fired — loop stalled"
        payload2 = second["__interrupt__"][0].value

        # THE regression guards: iteration 2 covers only its own state.
        assert payload2["source_ids"] == ["src-t2"], "sourceIds not reset between iterations"
        assert fan_out_log == [["t1"], ["t2"]], "fan-out re-covered old topics"

        # Reconcile seeded the next topic text from the selected source.
        state = await graph.aget_state(config)
        assert state.values["topicText"] == "reason for src-t1"
        assert state.values["iteration"] == 1

        # Iteration 2: finish normally.
        final = await graph.ainvoke(
            Command(resume={"action": "end", "selected_ids": ["src-t2"]}),
            config,
        )

    assert "__interrupt__" not in final
    assert final["topicCentroid"] == [0.0, 1.0]
    # Rocchio ran once per iteration, with the refined q0 feeding iteration 2.
    assert MockService.return_value.compute_query_vector.await_count == 2
    saved = [c.kwargs for c in centroid_repo.saveCentroid.await_args_list]
    assert [s["kind"] for s in saved] == ["refined", "refined"]
    assert [s["iteration"] for s in saved] == [0, 1]


@pytest.mark.asyncio
async def test_max_iterations_ends_the_run_even_on_reextract(monkeypatch):
    monkeypatch.setattr(settings, "max_iterations", 1)
    fan_out_log = []
    graph = build_loop_graph(fan_out_log)
    config = {"configurable": {"thread_id": "loop-capped"}}
    interrupt_repo, centroid_repo, reconcile_repo = make_repos()

    with patch(f"{INTERRUPT}.get_repo", return_value=interrupt_repo), \
         patch(f"{CENTROID}.get_repo", return_value=centroid_repo), \
         patch(f"{RECONCILE}.get_repo", return_value=reconcile_repo), \
         patch(f"{CENTROID}.TransformationService") as MockService:
        MockService.return_value.compute_query_vector = AsyncMock(
            return_value=[0.0, 1.0]
        )

        await graph.ainvoke({"topicText": "seed topic"}, config)
        final = await graph.ainvoke(
            Command(resume={"action": "reextract", "selected_ids": ["src-t1"]}),
            config,
        )

    # The cap turned "reextract" into a clean end: no second pass ran.
    assert "__interrupt__" not in final
    assert fan_out_log == [["t1"]]
