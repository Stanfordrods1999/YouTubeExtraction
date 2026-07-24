import asyncio
from typing import List, Optional

import numpy as np

from db.supabaseRepository import SupabaseRepository
from src.app.config import settings


class TransformationService:
    def __init__(self, repo: SupabaseRepository):
        self.repo = repo

    async def compute_query_vector(
        self, q0: List[float], selected_ids: List[str], non_selected_ids: List[str]
    ) -> List[float]:
        rel_embs, nonrel_embs = await asyncio.gather(
            self._fetch(selected_ids),
            self._fetch(non_selected_ids),
        )
        return self.rocchio_embedding(
            q0, rel_embs, nonrel_embs,
            alpha=settings.rocchio_alpha,
            beta=settings.rocchio_beta,
            gamma=settings.rocchio_gamma,
        )

    async def _fetch(self, ids: List[str]) -> List[List[float]]:
        return await self.repo.getEmbeddedUnits(ids) if ids else []

    @staticmethod
    def rocchio_embedding(
        q0: List[float],
        rel_embs: List[List[float]],
        nonrel_embs: Optional[List[List[float]]] = None,
        alpha: float = 1.0,
        beta: float = 0.75,
        gamma: float = 0.15,
    ) -> List[float]:
        q = alpha * np.asarray(q0, dtype=np.float64)
        if rel_embs is not None and len(rel_embs) > 0:
            q += beta * np.mean(rel_embs, axis=0)
        if nonrel_embs is not None and len(nonrel_embs) > 0:
            q -= gamma * np.mean(nonrel_embs, axis=0)
        norm = np.linalg.norm(q)
        return (q / norm).tolist() if norm > 0 else list(q0)