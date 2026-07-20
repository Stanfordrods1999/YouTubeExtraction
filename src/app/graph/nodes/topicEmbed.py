from src.app.services.extractionService import MODEL
from src.app.graph.state import GlobalState
from openai import AsyncOpenAI

client = AsyncOpenAI()

async def topicEmbed(state: GlobalState):
    if state.get('userAction') == 'reextract':
        return state

    response = await client.embeddings.create(
        model='text-embedding-3-small',
        input=state["topicText"],
    )
    return {"topicCentroid": response.data[0].embedding}