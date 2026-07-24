from typing import Optional

from langchain_core.runnables import RunnableConfig
from openai import AsyncOpenAI

from db.session import get_repo
from src.app.config import settings
from src.app.graph.state import GlobalState
from src.app.graph.utils import thread_id_from_config

client = AsyncOpenAI()

async def topicEmbed(state: GlobalState, config: Optional[RunnableConfig] = None):
    # On a re-extract pass the centroid has already been refined by Rocchio;
    # re-embedding the (rewritten) topic text would overwrite that feedback.
    if state.get('userAction') == 'reextract':
        return {}

    response = await client.embeddings.create(
        model=settings.embed_model,
        input=state["topicText"],
    )
    centroid = response.data[0].embedding

    # Persist so retrieval blending and the eval harness can compare this
    # pre-feedback centroid against the Rocchio-refined one.
    await get_repo().saveCentroid(
        thread_id=thread_id_from_config(config),
        kind="initial",
        centroid=centroid,
        topic_text=state["topicText"],
    )

    return {"topicCentroid": centroid}
