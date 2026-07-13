from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

from src.app.graph.nodes.topicEmbed import topicEmbed
from src.app.graph.nodes.topicExtractor import topicExtractor
from src.app.graph.subgraphs.sourceDiscovery import sourceDiscoveryGraph
from src.app.graph.state import GlobalState


def fan_out_sources(state: GlobalState):
    """One sourceDiscovery subgraph run per topic."""
    return [
        Send("sourceDiscovery", {"topic_id": topic_id})
        for topic_id in state["topicIds"]
    ]


builder = StateGraph(GlobalState)

builder.add_node("topicExtractor", topicExtractor)
builder.add_node("sourceDiscovery", sourceDiscoveryGraph) 
builder.add_node("embedTopic",topicEmbed)

builder.add_edge(START, "topicExtractor")
builder.add_edge(START,"embedTopic")
builder.add_conditional_edges("topicExtractor", fan_out_sources, ["sourceDiscovery"])
builder.add_edge("sourceDiscovery", END)

graph = builder.compile(name="scrapingPipeline")