from db.supabaseRepository import SupabaseRepository

_repo: SupabaseRepository | None = None

async def init_repo() -> SupabaseRepository:
    global _repo
    if _repo is None:
        _repo = SupabaseRepository()
        await _repo.initialize()
    return _repo

def get_repo() -> SupabaseRepository:
    if _repo is None:
        raise RuntimeError("Repo not initialized — did lifespan run?")
    return _repo