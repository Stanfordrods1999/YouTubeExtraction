import json
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
            .insert(data).select('*')
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
                          .execute())
        
        if not response.data:
            raise ValueError("Could not fetch the data for some reason")
        
        return response.data
    
    async def getSourcesbyId(self,source_ids:List[str]) -> List:
        response = await (self.client
                          .table("sources")
                          .select("discovery_reason")
                          .in_("id",source_ids)
                          .execute())
        
        if not response.data:
            raise ValueError("Data could not be fetched")
        
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
    ## TODO: Need to alter and migrate data in metadata to create a new column called text 
    # where text to be embedded is to be stored 

    async def getEmbeddedUnits(self,source_ids:List[str]):
        response = await (
            self.client
            .table("extracted_units")
            .select("embedding, extraction_runs!inner()")
            .in_("extraction_runs.source_id", source_ids)
            .execute()
        )
        return [json.loads(r["embedding"]) for r in response.data]
    
    async def createExtractions(self,source_id,topic_id,metadata):
        
        response  = await (self.client
                           .table("extraction_runs")
                           .insert({
                               "source_id":source_id,
                                "topic_id":topic_id,
                                "metadata":metadata
                            })
                            .select("id")
                            .execute())
        
        if not response.data:
            raise ValueError("Failed to create sources")

        return response.data
