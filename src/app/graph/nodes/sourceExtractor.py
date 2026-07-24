
from db.session import get_repo
from src.app.graph.state import sourceDiscoveryState
from src.app.services.sourceDiscoveryService import SourceDiscoveryService


async def sourceExtractor(state:sourceDiscoveryState):
    result = await SourceDiscoveryService(get_repo()).extract(state)
    return result