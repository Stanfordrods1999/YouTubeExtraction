import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Literal

import trafilatura
from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from seleniumbase import SB

from db.supabaseRepository import SupabaseRepository
from src.app.config import settings
from src.app.prompts.transformation import build_atomic_unit_messages

SCHEMA_TYPES = {"Article", "NewsArticle", "BlogPosting", "Product",
                "Review", "Recipe", "Report", "QAPage", "FAQPage"}

logger = logging.getLogger(__name__)

# Module-level: Chrome is heavy; cap concurrent browser instances.
_BROWSER_SEM = asyncio.Semaphore(2)

_MIN_HTML_LEN = 500
_BLOCK_MARKERS = ("cf-chl", "Just a moment", "Checking your browser")


class AtomicUnit(BaseModel):
    text: str
    kind: Literal["fact", "definition", "statistic", "claim", "opinion"]


class UnitsResponse(BaseModel):
    units: list[AtomicUnit]

class ExtractionService:
    def __init__(self, topic_id: str, source_url: str, source_id: str, repo: SupabaseRepository):
        self.repo = repo
        self.topic_id = topic_id
        self.source_url = source_url
        self.source_id = source_id
        self.client = ChatOpenAI(model=settings.chat_model, temperature=0)
        # include_raw=True keeps the AIMessage so token usage can be recorded
        # on the run alongside the parsed units.
        self.decomposer = self.client.with_structured_output(
            UnitsResponse, method="json_mode", include_raw=True
        )

    def _extract_jsonld(self, html: str) -> list[dict]:
        try:
            soup = BeautifulSoup(html, "html.parser")
        except TypeError:
            return []
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

    async def _make_atomic_units(self, metadata: dict) -> tuple[list[dict], dict]:
        """Returns (unit rows, token usage for the decomposition call)."""
        messages = build_atomic_unit_messages(
            metadata["readable_text"],
            title=self._title_from_structured(metadata["structured"]),
            url=self.source_url,
            topic=None,
        )
        try:
            result = await self.decomposer.ainvoke(messages)
        except Exception as e:
            logger.warning("Decomposition failed for %s: %s", self.source_url, e)
            return [], {}

        usage = dict(getattr(result.get("raw"), "usage_metadata", None) or {})
        parsed: UnitsResponse | None = result.get("parsed")
        if parsed is None:
            logger.warning("Decomposition unparseable for %s: %s",
                           self.source_url, result.get("parsing_error"))
            return [], usage

        return [{
            "source_id": self.source_id,
            "topic_id": self.topic_id,
            "text": u.text,
            "kind": u.kind,
        } for u in parsed.units], usage

    async def extract(self) -> dict:
        started_at = datetime.now(timezone.utc).isoformat()
        html, strategy = await self.sourceHTML()

        if html is None:
            # Every fetch tier failed: record the failure instead of burning an
            # LLM call on empty text and storing a junk run.
            run = await self.repo.createExtractions(
                self.source_id, self.topic_id, [],
                status="failed", failure_reason="fetch_failed",
                started_at=started_at,
            )
            await self.repo.updateSourceStatus([self.source_id], "failed")
            return run

        metadata = self.build_extraction_input(html, self.source_url)
        unit_rows, usage = await self._make_atomic_units(metadata)

        run = await self.repo.createExtractions(
            self.source_id, self.topic_id, unit_rows,
            status="completed", extraction_strategy=strategy,
            started_at=started_at, usage=usage,
        )
        await self.repo.updateSourceStatus([self.source_id], "extracted")
        return run



    def _looks_like_content(self,html: str | None) -> bool:
        """Validate the artifact, not the process."""
        if not html or len(html) < _MIN_HTML_LEN:
            return False
        head = html[:3000]
        return not any(marker in head for marker in _BLOCK_MARKERS)

    async def sourceHTML(self) -> tuple[str | None, str | None]:
        """Returns (html, strategy) where strategy names the tier that won."""
        html = await self._curl_fetch()
        if self._looks_like_content(html):
            return html, "curl"

        logger.info("Falling back to browser fetch for %s", self.source_url)
        async with _BROWSER_SEM:
            html = await asyncio.to_thread(self._browser_fetch)
        if self._looks_like_content(html):
            return html, "browser"

        logger.error("All fetch tiers failed for %s", self.source_url)
        return None, None

    async def _curl_fetch(self) -> str | None:
        try:
            async with AsyncSession() as session:
                resp = await session.get(
                    self.source_url,
                    impersonate="chrome",
                    timeout=60,
                    headers={
                        "Referer": "https://www.google.com/",
                        "Accept-Language": "en-US,en;q=0.9",
                    },
                )
                resp.raise_for_status()
                return resp.text
        except Exception as e:
            logger.warning("curl_cffi fetch failed for %s: %s", self.source_url, e)
            return None

    def _browser_fetch(self) -> str | None:
        """Sync on purpose — runs in a thread via asyncio.to_thread."""
        try:
            with SB(uc=True, xvfb=True) as sb:
                sb.activate_cdp_mode(self.source_url)

                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    if sb.cdp.evaluate("document.readyState") == "complete":
                        break
                    sb.sleep(0.5)
                sb.sleep(1)  # hydration settle

                return sb.cdp.get_page_source()
        except Exception as e:
            logger.warning("Browser fetch failed for %s: %s", self.source_url, e)
            return None
