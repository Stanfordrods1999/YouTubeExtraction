import json
from datetime import datetime, timezone
from typing import List, Optional

from src.app.config import settings
from src.app.graph.state import TopicState, sourceDiscoveryState
from supabase import AsyncClient, create_async_client


class SupabaseRepository:

    def __init__(self):
        self.client: AsyncClient | None = None

    async def initialize(self):
        self.client = await create_async_client(
            supabase_url=settings.supabase_url,
            supabase_key=settings.supabase_secret_key,
        )
    
    async def getTopicMetadata(self, id: str):
        response = await (
            self.client
            .table("topics")
            .select("*")
            .eq("id", id)
            .single()
            .execute()
        )

        if not response.data:
            raise ValueError(f"Topic {id} not found")

        return response.data
    
    async def createTopic(self, data: List[TopicState]) -> list[str]:
        rows = [
            {
                "topic_text": item["topicText"],
                "status": item["status"],
                "created_by": item["createdBy"],
                "created_at": datetime.now(timezone.utc).isoformat(),
                "confidence": item["confidence"]
            }
            for item in data
        ]

        response = await (
            self.client
            .table("topics")
            .insert(rows)
            .execute()
        )

        if not response.data:
            raise ValueError("Insert failed: no data returned from Supabase")

        return [
            topic["id"] for topic in response.data
        ]
    
    async def createSources(self,data:List[sourceDiscoveryState]):
        # Upsert on (topic_id, source_url): node retries and re-runs must not
        # duplicate sources — the RetryPolicy re-executes the whole discovery
        # node on transient DB errors.
        response = (
            await self.client
            .table("sources")
            .upsert(data, on_conflict="topic_id,source_url")
            .execute()
        )

        if not response.data:
            raise ValueError("Failed to create sources")

        return response.data

    async def updateSourceStatus(self, source_ids: List[str], status: str,
                                 exclude_failed: bool = False):
        query = (self.client
                 .table("sources")
                 .update({"status": status})
                 .in_("id", source_ids))
        if exclude_failed:
            query = query.neq("status", "failed")
        response = await query.execute()
        return response.data
    

    async def getSources(self,topic_id:str):
        response = await (self.client
                          .table('sources')
                          .select('*')
                          .eq('topic_id',topic_id)
                          .execute())

        if not response.data:
            raise ValueError(f"No sources found for topic {topic_id}")

        return response.data

    async def getSourcesbyId(self,source_ids:List[str]) -> List:
        response = await (self.client
                          .table("sources")
                          .select("id, source_url, discovery_reason, priority_score, source_type")
                          .in_("id",source_ids)
                          .execute())

        if not response.data:
            raise ValueError(f"No sources found for ids {source_ids}")

        return response.data
    
    async def getExtractionMetadata(self,id):
        response = await (self.client
                          .table("extraction_runs")
                          .select("metadata")
                          .eq('id',id)
                          .execute())
        
        if not response.data:
            raise ValueError("Could not fetch the data for some reason")
        
        return response.data
    
    async def getUnEmbeddedUnits(self,e_run_id):
        response = await (self.client
                          .table("extraction_runs")
                          .select("metadata")
                          .eq("id",e_run_id).single()
                          .execute()
                          )

        if not response.data:
            raise ValueError(f"Extraction run {e_run_id} not found")

        return response.data

    async def hasEmbeddedUnits(self, e_run_id: str) -> bool:
        """True if this run's units were already embedded — makes
        embed_pending safe to re-run (retries, resumed threads)."""
        response = await (self.client
                          .table("extracted_units")
                          .select("id")
                          .eq("extraction_run_id", e_run_id)
                          .limit(1)
                          .execute())
        return bool(response.data)

    async def getUnitsBySources(self, source_ids: List[str],
                                limit: int = 30) -> List[str]:
        """Unit texts extracted from the given sources (for the re-extract
        brief). Follows the getEmbeddedUnits join pattern."""
        response = await (self.client
                          .table("extracted_units")
                          .select("content, extraction_runs!inner()")
                          .in_("extraction_runs.source_id", source_ids)
                          .limit(limit)
                          .execute())
        return [r["content"] for r in (response.data or []) if r.get("content")]

    async def dedupeUnits(self, e_run_id: str, threshold: float = 0.95) -> int:
        """Collapse this run's near-duplicate units into canonical ones
        (bumping corroboration_count) via the dedupe_units RPC."""
        response = await self.client.rpc("dedupe_units", {
            "run_id": e_run_id,
            "threshold": threshold,
        }).execute()
        return response.data if isinstance(response.data, int) else 0
    
    async def updateUnitEmbeddings(self,data):
        response = await (self.client
                          .table("extracted_units")
                          .insert(data)
                          .execute())

        if not response:
            raise ValueError("Cannot add embeddings")

        return response.data

    async def matchUnits(self, query_embedding: List[float], k: int = 10,
                         topic_id: Optional[str] = None) -> List[dict]:
        """Top-k nearest units with citation fields, via the match_units RPC
        (HNSW-indexed cosine search in Postgres)."""
        response = await self.client.rpc("match_units", {
            "query_embedding": query_embedding,
            "match_count": k,
            "filter_topic": topic_id,
        }).execute()
        return response.data or []

    async def saveCentroid(self, thread_id: str, kind: str,
                           centroid: List[float],
                           topic_text: Optional[str] = None,
                           iteration: int = 0):
        response = await (self.client
                          .table("topic_centroids")
                          .insert({
                              "thread_id": thread_id,
                              "kind": kind,
                              "centroid": centroid,
                              "topic_text": topic_text,
                              "iteration": iteration,
                          })
                          .execute())
        if not response.data:
            raise ValueError("Failed to save centroid")
        return response.data

    async def getLatestCentroid(self, thread_id: str,
                                kind: Optional[str] = None) -> Optional[List[float]]:
        query = (self.client
                 .table("topic_centroids")
                 .select("centroid")
                 .eq("thread_id", thread_id))
        if kind is not None:
            query = query.eq("kind", kind)
        response = await (query
                          .order("created_at", desc=True)
                          .limit(1)
                          .execute())
        if not response.data:
            return None
        centroid = response.data[0]["centroid"]
        return json.loads(centroid) if isinstance(centroid, str) else centroid

    async def getTopics(self) -> List[dict]:
        response = await (self.client
                          .table("topics")
                          .select("*")
                          .order("created_at", desc=True)
                          .execute())
        return response.data or []

    async def getEmbeddedUnits(self,source_ids:List[str]):
        response = await (
            self.client
            .table("extracted_units")
            .select("embedding, extraction_runs!inner()")
            .in_("extraction_runs.source_id", source_ids)
            .execute()
        )
        return [json.loads(r["embedding"]) for r in response.data]
    
    async def createExtractions(self, source_id, topic_id, units,
                                status: str = "completed",
                                failure_reason: Optional[str] = None,
                                extraction_strategy: Optional[str] = None,
                                started_at: Optional[str] = None,
                                usage: Optional[dict] = None):
        response  = await (self.client
                           .table("extraction_runs")
                           .insert({
                               "source_id": source_id,
                               "topic_id": topic_id,
                               "metadata": {"units": units, "usage": usage or {}},
                               "status": status,
                               "failure_reason": failure_reason,
                               "extraction_strategy": extraction_strategy,
                               "started_at": started_at,
                               "completed_at": datetime.now(timezone.utc).isoformat(),
                            })
                            .select("id")
                            .execute())

        if not response.data:
            raise ValueError("Failed to create extraction run")

        return response.data
