from langgraph.types import Command, interrupt
import json
from src.app.graph.state import GlobalState

async def interruptSelections(state: GlobalState) -> dict:
    response = interrupt({
        "type": "topic_selection",
        "source_ids": state["sourceIds"],
    })

    if isinstance(response, str):          
        response = json.loads(response)
    
    print(repr(response)) 

    decision = response['action']
    selected = response['selected_ids']

    return {
        "userAction":decision,
        "selectedSourceIds": selected,
        "nonselectedSourceIds": [s for s in state["sourceIds"] if s not in selected],
    }