from contextlib import asynccontextmanager
from fastapi import FastAPI
from db.session import init_repo
from db.supabaseRepository import SupabaseRepository

@asynccontextmanager
async def lifespan(app:FastAPI):
    repo = await init_repo()
    app.state.db_session = repo  
    yield

app = FastAPI(lifespan=lifespan)