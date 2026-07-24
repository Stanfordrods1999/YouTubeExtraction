# topicExtractor.py
from db.session import get_repo
from src.app.graph.state import TopicState
from src.app.services.topicExtractionService import TopicExtractionService


async def topicExtractor(state: TopicState):
    topic_service = TopicExtractionService(get_repo())
    ids = await topic_service.extract(state)
    return {"topicIds": ids}
