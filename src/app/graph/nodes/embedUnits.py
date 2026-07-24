from src.app.graph.state import sourceDiscoveryState
from src.app.services.embeddingServices import embeddingService
from db.session import get_repo

async def embedUnits(state: sourceDiscoveryState):
    repo = get_repo()
    for e_run_id in set(state["extraction_run_ids"]):
        svc = embeddingService(repo=repo, e_run_id=e_run_id)
        await svc.embed_pending()

    # Surface plain source ids for the human-selection interrupt upstream.
    # Partial update only: returning the whole state would re-feed the
    # add-reducer channels (extraction_run_ids, and sourceIds in the parent)
    # back into themselves and duplicate their contents.
    return {"sourceIds": [row["id"] for row in state.get("source_ids") or []]}
