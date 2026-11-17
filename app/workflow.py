"""Minimal LangGraph flow. No LLM or tool side effects; A0/A1 local demonstration."""
from typing import TypedDict
from langgraph.graph import StateGraph, START, END

class RunState(TypedDict):
    project_id: str
    run_id: str
    objective: str
    draft: str
    status: str

def draft(state: RunState) -> dict:
    return {"draft": f"DRAFT ONLY: {state['objective']}", "status": "awaiting_human_review"}

builder = StateGraph(RunState)
builder.add_node("draft", draft)
builder.add_edge(START, "draft")
builder.add_edge("draft", END)
graph = builder.compile()
