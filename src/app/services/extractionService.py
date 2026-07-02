import json
import logging
from typing import Literal
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ValidationError
import trafilatura
from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

from src.app.prompts.transformation import build_atomic_unit_messages
from db.supabaseRepository import SupabaseRepository

SCHEMA_TYPES = {"Article", "NewsArticle", "BlogPosting", "Product",
                "Review", "Recipe", "Report", "QAPage", "FAQPage"}

logger = logging.getLogger(__name__)

MODEL = "gpt-4.1-mini"


class AtomicUnit(BaseModel):
    text: str
    kind: Literal["fact", "definition", "statistic", "claim", "opinion"]


class UnitsResponse(BaseModel):
    units: list[AtomicUnit]

class extractionService:
    def __init__(self, topic_id: str, source_url: str, source_id: str, repo: SupabaseRepository):
        self.repo = repo
        self.topic_id = topic_id
        self.source_url = source_url
        self.source_id = source_id
        self.client = ChatOpenAI(model=MODEL, temperature=0)
        self.decomposer = self.client.with_structured_output(
            UnitsResponse, method="json_mode"
        )

    def _extract_jsonld(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        out = []
        for tag in soup.find_all("script", type="application/ld+json"):
            raw = tag.string or tag.get_text()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            items = data if isinstance(data, list) else data.get("@graph", [data])
            for item in items:
                if not isinstance(item, dict):
                    continue
                t = item.get("@type")
                t = t[0] if isinstance(t, list) else t
                if t in SCHEMA_TYPES:
                    out.append(item)
        return out

    def build_extraction_input(self, html: str, url: str) -> dict:
        body = trafilatura.extract(html, include_comments=False,
                                   include_tables=True, url=url) or ""
        return {"readable_text": body, "structured": self._extract_jsonld(html)}
    
    def _title_from_structured(self, structured: list[dict]) -> str | None:
        for item in structured:
            if item.get("headline") or item.get("name"):
                return item.get("headline") or item.get("name")
        return None

    async def _make_atomic_units(self, metadata: dict) -> list[dict]:
        messages = build_atomic_unit_messages(
            metadata["readable_text"],
            title=self._title_from_structured(metadata["structured"]),
            url=self.source_url,
            topic=None,
        )
        try:
            result: UnitsResponse = await self.decomposer.ainvoke(messages)
        except Exception as e:
            logger.warning("Decomposition failed for %s: %s", self.source_url, e)
            return []

        return [{
            "source_id": self.source_id,
            "topic_id": self.topic_id,
            "text": u.text,
            "kind": u.kind,
        } for u in result.units]

    async def extract(self) -> dict:
        try:
            async with AsyncSession() as session:
                resp = await session.get(
                    self.source_url,
                    impersonate="chrome146",   
                    timeout=60,
                    headers={
                        "Referer": "https://www.google.com/",
                        "Accept-Language": "en-US,en;q=0.9",
                    },
                )
                resp.raise_for_status()
                html = resp.text

        except Exception as e:
            logger.warning("Fetch failed for %s: %s", self.source_url, e)
            self.repo.createExtractions(self.source_id,self.topic_id,{"sourced":False})
            return None

        metadata = self.build_extraction_input(html, self.source_url)

        unit_rows = await self._make_atomic_units(metadata)
        if unit_rows:
            await self.repo.createExtractions(self.source_id,self.topic_id,unit_rows)   # was createExtractions

        return metadata