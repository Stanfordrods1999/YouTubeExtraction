import logging
from typing import Literal

from langgraph.graph import END
from langgraph.types import Command

from src.app.config import settings
from src.app.graph.state import GlobalState

logger = logging.getLogger(__name__)


async def route_after_centroid(
    state: GlobalState,
) -> Command[Literal["reconcileSources", "__end__"]]:
    iteration = state.get("iteration", 0)

    if state.get("userAction") == "reextract":
        if iteration + 1 >= settings.max_iterations:
            logger.info(
                "Re-extract requested but max_iterations=%s reached; ending run.",
                settings.max_iterations,
            )
            return Command(goto=END)
        return Command(goto="reconcileSources", update={"iteration": iteration + 1})

    return Command(goto=END)
