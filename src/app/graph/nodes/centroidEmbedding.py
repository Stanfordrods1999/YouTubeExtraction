from typing import Optional

from langchain_core.runnables import RunnableConfig

from db.session import get_repo
from src.app.graph.state import GlobalState
from src.app.graph.utils import thread_id_from_config
from src.app.services.transformationService import TransformationService


async def centroidEmbedding(state: GlobalState, config: Optional[RunnableConfig] = None):
    repo = get_repo()
    t_service = TransformationService(repo)
    c_embedding = await t_service.compute_query_vector(state['topicCentroid'],
                                                       state['selectedSourceIds'],
                                                       state['nonselectedSourceIds'])

    # Persist the refined centroid: /query blends it into retrieval and the
    # eval harness compares it against the initial one.
    await repo.saveCentroid(
        thread_id=thread_id_from_config(config),
        kind="refined",
        centroid=c_embedding,
        topic_text=state.get("topicText"),
        iteration=state.get("iteration", 0),
    )

    # Partial update only — returning the whole state would double the
    # add-reducer channels (topicIds / sourceIds).
    return {"topicCentroid": c_embedding}
