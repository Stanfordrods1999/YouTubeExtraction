from datetime import datetime, timezone
from typing import List

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from db.supabaseRepository import SupabaseRepository
from src.app.config import settings
from src.app.graph.state import TopicState


class TopicExtractionService:

    def __init__(self, repo: SupabaseRepository):
        self.repo = repo
        self.llm = ChatOpenAI(
            model=settings.chat_model,
            temperature=0
        )

    async def extract(self, state: TopicState) -> list[tuple[str, str]]:
        raw_topics:List[TopicState] = await self._run_extraction_chain(state["topicText"])
        saved = await self.repo.createTopic(raw_topics)
        return saved ## Will return bunch of ids

    async def _run_extraction_chain(self, topic: str) -> List[TopicState]:
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a topic extraction assistant.
             Given a topic, generate related subtopics that can be researched independently.
             Return a JSON array of topics in this exact format:
             [
               {{
                 "topicText": "subtopic title",
                 "status": "pending",
                 "createdBy": "system",
                 "confidence": 0.95, // Confidence is how relevant the topic is to the current topic given 
                 "createdAt": "ISO datetime string",
                 "metadata": {{}}
               }}
             ]
             Return ONLY the JSON array, no extra text."""),
            ("human", "Extract related topics for: {topic}")
        ])

        chain = prompt | self.llm | JsonOutputParser()
        raw: list[dict] = await chain.ainvoke({"topic": topic})


        return [
            TopicState(
                topicText=item["topicText"],
                status=item.get("status", "pending"),
                createdBy=item.get("createdBy", "system"),
                confidence=item.get("confidence", 0.0),
                createdAt=datetime.now(timezone.utc),
                metadata=item.get("metadata", {})
            )
            for item in raw
        ]