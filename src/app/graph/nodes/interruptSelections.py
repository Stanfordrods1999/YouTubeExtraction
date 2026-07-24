import json
import logging

from langgraph.types import interrupt

from db.session import get_repo
from src.app.graph.state import GlobalState

logger = logging.getLogger(__name__)


async def interruptSelections(state: GlobalState) -> dict:
    source_ids = state["sourceIds"]

    # Give the human something reviewable: URL, reason, and score per source,
    # not a bare list of UUIDs. (Re-fetched on resume too — the node re-runs
    # from the top when the graph is resumed, so this read must stay cheap
    # and side-effect free.)
    sources = await get_repo().getSourcesbyId(source_ids) if source_ids else []

    response = interrupt({
        "type": "source_selection",
        "source_ids": source_ids,
        "sources": sources,
    })

    if isinstance(response, str):
        response = json.loads(response)

    try:
        decision = response["action"]
        selected = response["selected_ids"]
    except (KeyError, TypeError) as e:
        raise ValueError(
            "Resume payload must be "
            '{"action": "reextract" | "end", "selected_ids": [...]}, '
            f"got: {response!r}"
        ) from e

    return {
        "userAction": decision,
        "selectedSourceIds": selected,
        "nonselectedSourceIds": [s for s in source_ids if s not in selected],
    }
