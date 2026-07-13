from src.app.services.extractionService import MODEL
from src.app.graph.state import GlobalState
from openai import AsyncOpenAI

client = AsyncOpenAI()

async def topicEmbed(state: GlobalState):
    response = await client.embeddings.create(
        model=MODEL,
        input=state["topicText"],
    )
    return {"topicEmbedding": response.data[0].embedding}