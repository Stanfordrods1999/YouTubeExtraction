from src.app.graph.state import sourceDiscoveryState
from src.app.services.embeddingServices import embeddingService
from db.session import get_repo

async def embedUnits(state: sourceDiscoveryState):
    repo = get_repo()
    for e_run_id in set(state["extraction_run_ids"]):
        svc = embeddingService(repo=repo, e_run_id=e_run_id)
        embedded = await svc.embed_pending()
        if embedded:
            # Collapse near-duplicates against units from other runs of the
            # same topic; corroborated facts keep a count instead of a copy.
            await repo.dedupeUnits(e_run_id)

    source_ids = [row["id"] for row in state.get("source_ids") or []]
    if source_ids:
        # Failed sources keep their failure status.
        await repo.updateSourceStatus(source_ids, "embedded", exclude_failed=True)

    # Surface plain source ids for the human-selection interrupt upstream.
    # Partial update only: returning the whole state would re-feed the
    # add-reducer channels (extraction_run_ids, and sourceIds in the parent)
    # back into themselves and duplicate their contents.
    return {"sourceIds": source_ids}
