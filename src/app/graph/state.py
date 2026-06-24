import operator
from typing import Annotated, List,Any,Dict, Optional, TypedDict,NotRequired
from datetime import datetime

class TopicState(TypedDict):
    id:str
    topicText:NotRequired[str]
    status:NotRequired[str]
    createdBy:NotRequired[str]
    confidence:NotRequired[float]
    createdAt:NotRequired[datetime]
    metadata:NotRequired[Dict[str,any]]
    
class sourceDiscoveryState(TypedDict):
    topic_id:str
    source_ids:NotRequired[List[str]]
    source_type:NotRequired[str]
    source_url:NotRequired[str]
    discovery_reason:NotRequired[str]
    priority_score:NotRequired[float]
    status:NotRequired[str]

class extractionState(TypedDict):
    source_id:str
    source_url:str
    topic_id:str

class GlobalState(TypedDict):
    topicText:str
    topicState:Optional[List[TopicState]]
    topicIds: Annotated[List[str], operator.add]