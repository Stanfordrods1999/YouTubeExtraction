from typing import Optional

from langchain_core.runnables import RunnableConfig


def thread_id_from_config(config: Optional[RunnableConfig]) -> str:
    return ((config or {}).get("configurable") or {}).get("thread_id", "default")
