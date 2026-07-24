# src/app/graph/subgraphs/sourceDiscovery.py
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy, Send

from src.app.graph.nodes.embedUnits import embedUnits
from src.app.graph.nodes.runExtractor import runExtractor
from src.app.graph.nodes.sourceExtractor import sourceExtractor
from src.app.graph.state import sourceDiscoveryState


def fan_out_runs(state: sourceDiscoveryState):
    return [
        Send("runExtractor", {"source_id": sid['id'],"source_url":sid['source_url'], "topic_id": state["topic_id"]})
        for sid in state["source_ids"]
    ]

sourceDiscoveryGraph = (
    StateGraph(sourceDiscoveryState, output_schema=sourceDiscoveryState)
    .add_node("sourceExtractor", sourceExtractor, retry_policy=RetryPolicy(retry_on=ValueError))
    .add_node("runExtractor", runExtractor, retry_policy=RetryPolicy(retry_on=ValueError))
    .add_node("embedUnits", embedUnits)
    .add_edge(START, "sourceExtractor")
    .add_conditional_edges("sourceExtractor", fan_out_runs, ["runExtractor"])
    .add_edge("runExtractor", "embedUnits")   
    .add_edge("embedUnits", END)
    .compile(name="source-map-reduce")
)