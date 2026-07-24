import json

from datetime import datetime, timezone
from typing import List, Optional
from supabase import AsyncClient, create_async_client

from src.app.config import settings
from src.app.graph.state import TopicState, sourceDiscoveryState


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
        response = (
            await self.client
            .table("sources")
            .insert(data).select('*')
            .execute()
        )

        if not response.data:
            raise ValueError("Failed to create sources")

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
            raise ValueError
        
        return response.data
    
    async def updateUnitEmbeddings(self,data):
        response = await (self.client
                          .table("extracted_units")
                          .insert(data)
                          .execute())

        if not response:
            raise ValueError("Cannot add embeddings")

        return response.data

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
                                started_at: Optional[str] = None):
        response  = await (self.client
                           .table("extraction_runs")
                           .insert({
                               "source_id": source_id,
                               "topic_id": topic_id,
                               "metadata": units,
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
