from langchain_openai import ChatOpenAI

from src.app.graph.state import sourceDiscoveryState
from db.supabaseRepository import SupabaseRepository
import json

class sourceDiscoveryService:
    def __init__(self, repo: SupabaseRepository):
        self.repo = repo
        self.llm = ChatOpenAI(model="gpt-5.4").bind_tools([
            {"type": "web_search_preview"},
            ])

    async def extract(self, state: sourceDiscoveryState):
        metadata = await self.repo.getTopicMetadata(state["topic_id"])
        sources = await self._run_source_prompt(metadata)

        try:
            text = next(
                block["text"] for block in sources.content
                if isinstance(block, dict) and block.get("type") == "text"
            )
            result = json.loads(text)
        except (StopIteration, json.JSONDecodeError) as e:
            print("Result is", sources.content)
            print(e)
            return {"source_ids": []}

        rows = [{**source, "topic_id": metadata["id"]} for source in result.get("sources", [])]
        source_ids = await self.repo.createSources(rows)

        return {"topic_id":state['topic_id'],"source_ids":source_ids}

    async def _run_source_prompt(self, metadata):
        metadata["topic_text"]

        prompt = f"""
        You are a research assistant.
s
        Topic:
        {metadata["topic_text"]}

        Search the web and identify the most relevant sources for researching this topic.

        Return ONLY valid JSON.

        Schema:

        {{
        "sources": [
            {{
            "source_type": "article|research_paper|website|government_report|news|video|other",
            "source_url": "https://example.com",
            "discovery_reason": "Why this source is relevant to the topic",
            "priority_score": 0.95,
            "status": "discovered"
            }}
        ]
        }}

        Rules:
        - Return between 5 and 15 sources.
        - priority_score must be between 0 and 1.
        - source_url must be a valid URL.
        - discovery_reason should be concise (1-2 sentences).
        - status must always be "discovered".
        - Do NOT include topic_id, id, or created_at.
        - Return ONLY JSON with no markdown fences.
        """

        response = await self.llm.ainvoke(prompt)

        return response