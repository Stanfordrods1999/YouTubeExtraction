from src.app.graph.state import GlobalState
from db.session import get_repo


async def reconcileSources(state: GlobalState):
    ids = state.get("selectedSourceIds") or state["sourceIds"]
    rows = await get_repo().getSourcesbyId(ids)
    rows = [row['discovery_reason'] for row in rows]
    return {"topicText": "\n\n".join(rows)}