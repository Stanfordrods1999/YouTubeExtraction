from typing import Literal

from langgraph.graph import END, START
from langgraph.types import Command, Overwrite

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
                "topicIds": Overwrite([]),
                "sourceIds": Overwrite([]),
            },
        )
    return Command(goto=END)