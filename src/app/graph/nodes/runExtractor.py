from src.app.graph.state import sourceDiscoveryState
from db.session import get_repo
from src.app.services import extractionService 

async def runExtractor(state:sourceDiscoveryState):
