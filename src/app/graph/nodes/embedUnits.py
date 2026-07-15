from src.app.graph.state import sourceDiscoveryState
from src.app.services.embeddingServices import embeddingService
from db.session import get_repo   

async def embedUnits(state: sourceDiscoveryState):
    repo = get_repo()
    total = 0
    for e_run_id in set(state["extraction_run_ids"]):
        svc = embeddingService(repo=repo, e_run_id=e_run_id)
        total += await svc.embed_pending()
    
    state['sourceIds']=[X['id'] for X in state['source_ids']]
    return state