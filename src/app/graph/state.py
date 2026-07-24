import operator
from datetime import datetime
from typing import Annotated, Any, Dict, List, NotRequired, Optional, TypedDict


def add_or_reset(existing: Optional[List], new: Optional[List]) -> List:
    """Accumulating reducer that supports clearing.

    LangGraph applies reducers to *every* write, so `operator.add` channels can
    never be emptied — `existing + []` is a no-op. Writing `None` to a channel
    using this reducer resets it, which the re-extract loop relies on to avoid
    re-fanning-out over ids from previous iterations.
    """
    if new is None:
        return []
    return (existing or []) + new


class TopicState(TypedDict):
    id: str
    topicText: NotRequired[str]
    status: NotRequired[str]
    createdBy: NotRequired[str]
    confidence: NotRequired[float]
    createdAt: NotRequired[datetime]
    metadata: NotRequired[Dict[str, Any]]


class sourceDiscoveryState(TypedDict):
    topic_id: str
    source_ids: NotRequired[List[str]]
    source_type: NotRequired[str]
    source_url: NotRequired[str]
    discovery_reason: NotRequired[str]
    priority_score: NotRequired[float]
    status: NotRequired[str]
    sourceIds: NotRequired[List[str]]
    extraction_run_ids: Annotated[list[str], operator.add]


class extractionState(TypedDict):
    source_id: str
    source_url: str
    topic_id: str


class GlobalState(TypedDict):
    userAction: str
    topicText: str
    topicCentroid: Optional[List[float]]
    topicState: Optional[List[TopicState]]
    topicIds: Annotated[List[str], add_or_reset]
    sourceIds: Annotated[List[str], add_or_reset]
    selectedSourceIds: Optional[List[str]]
    nonselectedSourceIds: Optional[List[str]]
    iteration: NotRequired[int]
