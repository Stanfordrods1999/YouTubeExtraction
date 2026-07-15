from langgraph.types import interrupt

from src.app.graph.state import GlobalState

def interruptSelections(state: GlobalState) -> dict:
    selected_ids = interrupt({
        "type": "topic_selection",
        "source_ids": state["sourceIds"],
    })


    if isinstance(selected_ids, str):          
        selected = [s.strip() for s in selected_ids.split(",") if s.strip()]
    else:
        selected = list(selected_ids)

    return {
        "selectedSourceIds": selected,
        "nonselectedSourceIds": [s for s in state["sourceIds"] if s not in selected],
    }