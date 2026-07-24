import logging

from langchain_openai import ChatOpenAI

from db.session import get_repo
from src.app.config import settings
from src.app.graph.state import GlobalState

logger = logging.getLogger(__name__)

BRIEF_SYSTEM = """You are a research lead planning the next iteration of a literature search.

Given evidence units extracted from sources a researcher marked as relevant,
write a focused research brief of 2-4 sentences: state what is now established
and, above all, which open questions or gaps the next round of research should
target. Output ONLY the brief text."""


async def reconcileSources(state: GlobalState):
    repo = get_repo()
    ids = state.get("selectedSourceIds") or state["sourceIds"]
    rows = await repo.getSourcesbyId(ids)
    reasons = [row["discovery_reason"] for row in rows]

    # Fallback seed: the selected sources' discovery reasons. Preferred seed:
    # an LLM brief written from the actual evidence those sources yielded.
    topic_text = "\n\n".join(reasons)
    try:
        units = await repo.getUnitsBySources(ids)
        if units:
            evidence = "\n".join(f"- {u}" for u in units)
            llm = ChatOpenAI(model=settings.chat_model, temperature=0)
            message = await llm.ainvoke([
                {"role": "system", "content": BRIEF_SYSTEM},
                {"role": "user", "content": f"Evidence units:\n{evidence}"},
            ])
            if message.content and message.content.strip():
                topic_text = message.content.strip()
    except Exception as e:
        logger.warning(
            "Research-brief generation failed (%s); using discovery reasons.", e
        )

    # Seed the next iteration, then clear the per-iteration channels.
    # topicIds / sourceIds use the add_or_reset reducer: writing None empties
    # them, so the next fan-out only covers this iteration's topics — the
    # reset must happen here (after the old ids were read), not upstream.
    return {
        "topicText": topic_text,
        "topicState": None,
        "topicIds": None,
        "sourceIds": None,
        "selectedSourceIds": None,
        "nonselectedSourceIds": None,
    }
