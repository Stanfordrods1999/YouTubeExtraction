from typing import List

from db.session import get_repo
from src.app.graph.state import sourceDiscoveryState
from src.app.services.sourceDiscoveryService import sourceDiscoveryService

async def sourceExtractor(state:sourceDiscoveryState):
    result = await sourceDiscoveryService(get_repo()).extract(state)
    return result