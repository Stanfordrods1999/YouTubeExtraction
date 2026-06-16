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