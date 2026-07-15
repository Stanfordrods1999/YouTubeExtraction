from src.app.services.transformationService import TransformationService
from src.app.graph.state import GlobalState
from db.session import get_repo

async def centroidEmbedding(state:GlobalState):
    t_service = TransformationService(get_repo())
    c_embedding = await t_service.compute_query_vector(state['topicCentroid'],
                                                       state['selectedSourceIds'],
                                                       state['nonselectedSourceIds'])
    state['topicCentroid'] = c_embedding
    return state