import json
import logging

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, ValidationError

from db.supabaseRepository import SupabaseRepository
from src.app.config import settings
from src.app.graph.state import sourceDiscoveryState

logger = logging.getLogger(__name__)


class DiscoveredSource(BaseModel):
    """Validates the discovery LLM's JSON before it reaches the database."""
    source_type: str
    source_url: str
    discovery_reason: str
    priority_score: float = Field(ge=0.0, le=1.0)
    status: str = "discovered"


class SourceDiscoveryService:
    def __init__(self, repo: SupabaseRepository):
        self.repo = repo
        self.llm = ChatOpenAI(model=settings.discovery_model).bind_tools([
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
            logger.warning(
                "Source discovery returned unparseable output for topic %s: %s",
                state["topic_id"], e,
            )
            return {"topic_id": state["topic_id"], "source_ids": []}

        rows = []
        for raw in result.get("sources", []):
            try:
                validated = DiscoveredSource.model_validate(raw)
            except ValidationError as e:
                logger.warning("Dropping invalid discovered source %r: %s", raw, e)
                continue
            rows.append({**validated.model_dump(), "topic_id": metadata["id"]})

        if not rows:
            return {"topic_id": state["topic_id"], "source_ids": []}

        source_ids = await self.repo.createSources(rows)

        return {"topic_id":state['topic_id'],"source_ids":source_ids}

    async def _run_source_prompt(self, metadata):
        prompt = f"""
        You are a research assistant.

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

        usage = getattr(response, "usage_metadata", None)
        if usage:
            logger.info("Source discovery for %r used %s tokens",
                        metadata.get("topic_text"), usage.get("total_tokens"))

        return response
