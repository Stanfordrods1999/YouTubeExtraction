from typing import Literal

from langgraph.graph import END, START
from langgraph.types import Command

from src.app.graph.state import GlobalState


async def route_after_centroid(
    state: GlobalState,
) -> Command[Literal["reconcileSources", "__end__"]]:
    print(f"userAction: {state.get('userAction')!r}")
    if state["userAction"] == "reextract":
        return Command(
            goto="reconcileSources",
            update={
                "topicText": "",
                "topicState": None,
                "topicIds": [],
                "selectedSourceIds": None,
                "nonselectedSourceIds": None,
            },
        )
    return Command(goto=END)