import os

from datetime import datetime, timezone
from typing import List
from supabase import AsyncClient, create_async_client

from src.app.graph.state import TopicState, sourceDiscoveryState


class SupabaseRepository:

    def __init__(self):
        self.client: AsyncClient | None = None

    async def initialize(self):
        url="http://127.0.0.1:54321"
        key="sb_secret_N7UND0UgjKTVK-Uodkm0Hg_xSvEMPvz"

        self.client = await create_async_client(
            supabase_url=url,
            supabase_key=key
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
            .insert(data)
            .execute()
        )

        if not response.data:
            raise ValueError("Failed to create sources")

        return response.data
    

    ## Something feels off here , I think since we bulk added all the sources and their ids , eah source does not really have it's own node, every node is built on the topic 
    ## now two things can be done one is an in memory queue , that means every node will have it memory to be managed 
    ## OR I don't know how to get this done but technically every topic node will open up it's own source node after all the sources have been bulked added 
    async def getSources(self,topic_id:str):
        response = await (self.client
                          .table('sources')
                          .select('*')
                          .eq('id',topic_id)
                          .gte('priority_score',0.60).execute())
        
        if not response.data:
            raise ValueError("Could not fetch the data for some reason")
        
        return response.data