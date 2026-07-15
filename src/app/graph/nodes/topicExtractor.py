# topicExtractor.py
from src.app.graph.state import TopicState
from db.session import get_repo
from src.app.services.topicExtractionService import topicExtractionService

async def topicExtractor(state: TopicState):
    topic_service = topicExtractionService(get_repo())
    ids = await topic_service.extract(state)
    return {"topicIds": ids}
