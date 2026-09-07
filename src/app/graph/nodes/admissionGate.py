import logging

from numpy.typing import NDArray
from openai import AsyncOpenAI

from db.session import get_repo
from src.app.graph.state import GlobalState

import numpy as np

logger = logging.getLogger(__name__)
client = AsyncOpenAI()


## Admission gate runs only on reextract — on the first pass there is no
## centroid to gate against.
from typing import Literal
from langgraph.types import Command, Overwrite, Send


async def admissionGate(state: GlobalState) -> Command[Literal["sourceDiscovery"]]:
    def fanOut(topicIds, admitted=None):
        return Command(
            update={"topicIds":Overwrite(topicIds)},
            goto=[Send("sourceDiscovery", {"topic_id": id}) for id in topicIds],
        )

    if state.get("userAction") != "reextract":
        return fanOut(state["topicIds"])

    topicData = await get_repo().getTopicsMetadata(state["topicIds"])
    if not topicData:
        return fanOut(state["topicIds"])

    ids, texts = zip(*topicData.items())

    response = await client.embeddings.create(
        model="text-embedding-3-small",
        input=list(texts),
    )

    topicEmbedding = np.array(
        [d.embedding for d in sorted(response.data, key=lambda x: x.index)],
        dtype=np.float32,
    )

    centroid = np.asarray(state["topicCentroid"], dtype=np.float32)
    scores = computeSimilarities(topicEmbedding, centroid)

    ranked = sorted(zip(ids, scores), key=lambda pair: pair[1], reverse=True)
    logger.info("gate scores: %s", [(id, round(float(s), 4)) for id, s in ranked])

    admitted = [id for id, _ in ranked[:5]]
    await get_repo().rejectTopics(set(state["topicIds"]) - set(admitted))

    return fanOut(admitted)

def computeSimilarities(topicEmbedding: NDArray, centroid: NDArray) -> NDArray:
    centroid = np.asarray(centroid, dtype=np.float32).ravel()

    norms = np.linalg.norm(topicEmbedding, axis=1) * np.linalg.norm(centroid)
    norms = np.where(norms == 0, 1e-12, norms)

    return (topicEmbedding @ centroid) / norms