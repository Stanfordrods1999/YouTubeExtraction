import asyncio
import logging
from openai import AsyncOpenAI, APIConnectionError, APITimeoutError, RateLimitError, APIStatusError

from db.supabaseRepository import SupabaseRepository

logger = logging.getLogger(__name__)

EMBED_MODEL = "text-embedding-3-small"   
BATCH_SIZE = 512
MAX_ATTEMPTS = 4

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
        for offset in range(0, len(rows), BATCH_SIZE):
            batch = rows[offset : offset + BATCH_SIZE]
            texts = [r["text"] for r in batch]

            resp = None
            for attempt in range(MAX_ATTEMPTS):
                try:
                    resp = await self.client.embeddings.create(
                        model=EMBED_MODEL, input=texts, timeout=60
                    )
                    break
                except (RateLimitError, APIConnectionError, APITimeoutError) as e:
                    if attempt == MAX_ATTEMPTS - 1:
                        logger.error(
                            "Embedding failed after %d attempts at offset %d: %s",
                            MAX_ATTEMPTS, offset, e,
                        )
                    else:
                        await asyncio.sleep(2 ** attempt)
                except APIStatusError as e:
                    if e.status_code >= 500 and attempt < MAX_ATTEMPTS - 1:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        logger.error(
                            "Embedding rejected (%s) at offset %d: %s",
                            e.status_code, offset, e,
                        )
                        break

            if resp is None:
                logger.error("Skipping batch at offset %d for run %s", offset, self.e_run_id)
                continue

            # The API documents `index` precisely because the order of `data` is
            # not guaranteed to match the order of `input`. Sorting by it is what
            # makes the zip below a real pairing rather than a coincidence.
            vectors = [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]

            # `content` is the text that produced the vector, carried through so a
            # nearest-neighbour hit can be read back. Without it the embedding is
            # an orphan: findable, but unreadable.
            updates = [
                {
                    "extraction_run_id": self.e_run_id,
                    "unit_index":        offset + i,
                    "content":           row["text"],
                    "semantic_type":     row.get("kind"),
                    "embedding":         vector,
                }
                for i, (row, vector) in enumerate(zip(batch, vectors, strict=True))
            ]
            await self.repo.updateUnitEmbeddings(updates)
            done += len(updates)

        return done