from openai import AsyncOpenAI

from src.app.config import settings
from src.app.graph.state import GlobalState

client = AsyncOpenAI()

async def topicEmbed(state: GlobalState):
    # On a re-extract pass the centroid has already been refined by Rocchio;
    # re-embedding the (rewritten) topic text would overwrite that feedback.
    if state.get('userAction') == 'reextract':
        return {}

    response = await client.embeddings.create(
        model=settings.embed_model,
        input=state["topicText"],
    )
    return {"topicCentroid": response.data[0].embedding}
