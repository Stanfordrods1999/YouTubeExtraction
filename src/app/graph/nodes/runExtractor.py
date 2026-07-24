from db.session import get_repo
from src.app.graph.state import extractionState
from src.app.services.extractionService import ExtractionService


async def runExtractor(state: extractionState):
    metadata = await ExtractionService(
        state['topic_id'], state['source_url'], state['source_id'], get_repo()
    ).extract()

    return {"extraction_run_ids":[metadata[0]["id"]]}    

    
