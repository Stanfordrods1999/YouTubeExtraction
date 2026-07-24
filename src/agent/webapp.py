from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from db.session import get_repo, init_repo
from src.app.services.queryService import QueryService


@asynccontextmanager
async def lifespan(app: FastAPI):
    repo = await init_repo()
    app.state.db_session = repo
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Research Pipeline API",
    description="Query the extracted knowledge base: retrieve atomic facts "
                "with citations, or synthesize cited answers.",
)


class QueryRequest(BaseModel):
    question: str
    k: int = Field(default=10, ge=1, le=50)
    topic_id: Optional[str] = None
    # Graph thread id of a pipeline run; blends its Rocchio-refined centroid
    # into retrieval so results lean toward what the human marked relevant.
    thread_id: Optional[str] = None


@app.post("/query")
async def query(req: QueryRequest):
    svc = QueryService(get_repo())
    results = await svc.retrieve(
        req.question, k=req.k, topic_id=req.topic_id, thread_id=req.thread_id
    )
    return {"question": req.question, "results": results}


@app.post("/answer")
async def answer(req: QueryRequest):
    svc = QueryService(get_repo())
    return await svc.answer(
        req.question, k=req.k, topic_id=req.topic_id, thread_id=req.thread_id
    )


@app.get("/topics")
async def topics():
    return await get_repo().getTopics()


@app.get("/topics/{topic_id}/sources")
async def topic_sources(topic_id: str):
    try:
        return await get_repo().getSources(topic_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"No sources for topic {topic_id}")
