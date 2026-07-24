import logging
from typing import List, Optional

import numpy as np
from langchain_openai import ChatOpenAI
from openai import AsyncOpenAI

from db.supabaseRepository import SupabaseRepository
from src.app.config import settings

logger = logging.getLogger(__name__)

ANSWER_SYSTEM = """You answer research questions using ONLY the numbered evidence units provided.

Rules:
- Cite every claim with [n] markers matching the evidence numbering.
- Do not introduce facts that are not in the evidence.
- If the evidence is insufficient to answer, say so explicitly.
- Be concise and direct."""


class QueryService:
    """The read path: embed a question, search the unit store in Postgres
    (match_units RPC over the HNSW index), optionally blending the query with
    a session's Rocchio-refined centroid, and synthesize a cited answer."""

    def __init__(self, repo: SupabaseRepository):
        self.repo = repo
        self.openai = AsyncOpenAI()
        self.chat = ChatOpenAI(model=settings.chat_model, temperature=0)

    async def retrieve(
        self,
        question: str,
        k: int = 10,
        topic_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        centroid_weight: float = 0.3,
    ) -> List[dict]:
        resp = await self.openai.embeddings.create(
            model=settings.embed_model, input=question
        )
        query_embedding = resp.data[0].embedding

        if thread_id:
            centroid = await self.repo.getLatestCentroid(thread_id)
            if centroid:
                query_embedding = self.blend(
                    query_embedding, centroid, centroid_weight
                )

        return await self.repo.matchUnits(query_embedding, k=k, topic_id=topic_id)

    @staticmethod
    def blend(query: List[float], centroid: List[float], weight: float) -> List[float]:
        """(1-w)·query + w·centroid, L2-normalised — pulls retrieval toward
        what the human marked relevant without discarding the question."""
        q = (1.0 - weight) * np.asarray(query, dtype=np.float64) \
            + weight * np.asarray(centroid, dtype=np.float64)
        norm = np.linalg.norm(q)
        return (q / norm).tolist() if norm > 0 else list(query)

    async def answer(
        self,
        question: str,
        k: int = 10,
        topic_id: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> dict:
        units = await self.retrieve(question, k=k, topic_id=topic_id, thread_id=thread_id)
        if not units:
            return {
                "answer": "No evidence found in the knowledge base for this question.",
                "citations": [],
            }

        evidence = "\n".join(
            f"[{i}] {u['content']} (source: {u['source_url']})"
            for i, u in enumerate(units, start=1)
        )
        message = await self.chat.ainvoke([
            {"role": "system", "content": ANSWER_SYSTEM},
            {"role": "user", "content": f"Question: {question}\n\nEvidence:\n{evidence}"},
        ])

        return {"answer": message.content, "citations": units}
