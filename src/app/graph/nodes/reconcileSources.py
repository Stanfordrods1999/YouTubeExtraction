from src.app.graph.state import GlobalState
from db.session import get_repo


async def reconcileSources(state: GlobalState):
    ids = state.get("selectedSourceIds") or state["sourceIds"]
    rows = await get_repo().getSourcesbyId(ids)
    reasons = [row["discovery_reason"] for row in rows]

    # Seed the next iteration, then clear the per-iteration channels.
    # topicIds / sourceIds use the add_or_reset reducer: writing None empties
    # them, so the next fan-out only covers this iteration's topics — the
    # reset must happen here (after the old ids were read), not upstream.
    return {
        "topicText": "\n\n".join(reasons),
        "topicState": None,
        "topicIds": None,
        "sourceIds": None,
        "selectedSourceIds": None,
        "nonselectedSourceIds": None,
    }
