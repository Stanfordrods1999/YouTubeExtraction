# src/app/graph/subgraphs/sourceDiscovery.py
from langgraph.graph import StateGraph, START, END
from langgraph.types import RetryPolicy

from src.app.graph.state import sourceDiscoveryState
from src.app.graph.nodes.sourceExtractor import sourceExtractor
from src.app.graph.nodes.runExtractor import runExtractor

sourceDiscoveryGraph = (
    StateGraph(sourceDiscoveryState)
    .add_node("sourceExtractor", sourceExtractor,
              retry_policy=RetryPolicy(retry_on=ValueError))
    .add_node("runExtractor", runExtractor)
    .add_edge(START, "sourceExtractor")
    .add_edge("sourceExtractor", "runExtractor")
    .add_edge("runExtractor", END)          # add this — don't rely on the implicit dead-end
    .compile(name="source-map-reduce")
)