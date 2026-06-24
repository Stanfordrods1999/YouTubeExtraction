import json
import trafilatura
from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

from db.supabaseRepository import SupabaseRepository

SCHEMA_TYPES = {"Article", "NewsArticle", "BlogPosting", "Product",
                "Review", "Recipe", "Report", "QAPage", "FAQPage"}

class extractionService:
    def __init__(self, topic_id: str, source_url: str, source_id: str, repo: SupabaseRepository):
        self.repo = repo
        self.topic_id = topic_id
        self.source_url = source_url
        self.source_id = source_id

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

    async def extract(self) -> dict:
        async with AsyncSession() as session:
            resp = await session.get(
                self.source_url,
                impersonate="chrome",   
                timeout=30,
            )
            resp.raise_for_status()
            html = resp.text                

        metadata = self.build_extraction_input(html, self.source_url)

        await self.repo.createExtractions(
            source_id=self.source_id,
            topic_id=self.topic_id,
            metadata=metadata,
        )
        return metadata