from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

from src.app.graph.nodes.sourceExtractor import sourceExtractor
from src.app.graph.nodes.topicExtractor import topicExtractor
from src.app.graph.state import GlobalState


def fan_out_sources(state: GlobalState):
    """
    Creates one sourceExtractor execution per topic.
    Assumes topicExtractor returns:

    {
        "topics": [...]
    }
    """

    return [
        Send(
            "sourceExtractor",
            {
                "topic_id": topicId
            }
        )
        for topicId in state['topicIds']
    ]


builder = StateGraph(GlobalState)

builder.add_node("topicExtractor", topicExtractor)
builder.add_node("sourceExtractor", sourceExtractor)

builder.add_edge(START, "topicExtractor")

builder.add_conditional_edges(
    "topicExtractor",
    fan_out_sources,
    ["sourceExtractor"]
)

builder.add_edge("sourceExtractor", END)

graph = builder.compile(name="scrapingPipeline")