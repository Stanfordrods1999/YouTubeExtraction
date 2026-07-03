import logging
from openai import AsyncOpenAI

from db.supabaseRepository import SupabaseRepository

logger = logging.getLogger(__name__)

EMBED_MODEL = "text-embedding-3-small"   
BATCH_SIZE = 512

class embeddingService:
    def __init__(self,repo:SupabaseRepository,e_run_id:str):
        self.repo = repo
        self.e_run_id = e_run_id
        self.client = AsyncOpenAI()

    async def embed_pending(self) -> int:
        rows = await self.repo.getUnEmbeddedUnits(e_run_id=self.e_run_id)
        rows = rows['metadata']
        if not rows:
            return 0
        
        done = 0
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i : i + BATCH_SIZE]
            texts = [r["text"] for r in batch]

            resp = await self.client.embeddings.create(model=EMBED_MODEL, input=texts)
            updates = [
                {"extraction_run_id": self.e_run_id, "embedding": embedding.embedding}
                for embedding in resp.data
            ]
            await self.repo.updateUnitEmbeddings(updates)
            done += len(updates)

        return done
        