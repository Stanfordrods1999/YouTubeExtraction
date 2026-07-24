import logging
from openai import AsyncOpenAI

from src.app.config import settings
from db.supabaseRepository import SupabaseRepository

logger = logging.getLogger(__name__)

BATCH_SIZE = 512

class embeddingService:
    def __init__(self,repo:SupabaseRepository,e_run_id:str):
        self.repo = repo
        self.e_run_id = e_run_id
        self.client = AsyncOpenAI()

    async def embed_pending(self) -> int:
        # Idempotency: retries and resumed threads re-enter this path; a run
        # whose units are already stored must not be embedded (and paid for)
        # twice.
        if await self.repo.hasEmbeddedUnits(self.e_run_id):
            logger.info("Run %s already embedded; skipping.", self.e_run_id)
            return 0

        run = await self.repo.getUnEmbeddedUnits(e_run_id=self.e_run_id)
        metadata = run['metadata']
        # Current shape: {"units": [...], "usage": {...}}; older rows stored
        # the bare unit list.
        rows = metadata.get("units", []) if isinstance(metadata, dict) else metadata
        if not rows:
            return 0

        done = 0
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i : i + BATCH_SIZE]
            texts = [r["text"] for r in batch]

            resp = await self.client.embeddings.create(
                model=settings.embed_model, input=texts
            )
            # zip(strict=True): a silent length mismatch here would misattribute
            # embeddings to the wrong sentences.
            updates = [
                {
                    "extraction_run_id": self.e_run_id,
                    "content": row["text"],
                    "semantic_type": row["kind"],
                    "embedding": embedding.embedding,
                }
                for row, embedding in zip(batch, resp.data, strict=True)
            ]
            await self.repo.updateUnitEmbeddings(updates)
            done += len(updates)

        return done
