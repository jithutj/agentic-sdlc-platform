"""Minimal LangGraph flow. No LLM or tool side effects; A0/A1 local demonstration."""
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt

GRAPH_VERSION = "draft-review-v1"

class RunState(TypedDict):
    project_id: str
    run_id: str
    objective: str
    draft: str
    status: str
    thread_id: str
    graph_version: str
    approval_id: str

def draft(state: RunState) -> dict:
    return {"draft": f"DRAFT ONLY: {state['objective']}", "status": "awaiting_human_review"}

def review(state: RunState) -> dict:
    # No side effects before interrupt: LangGraph re-enters this node on resume.
    decision = interrupt({"kind": "human_review", "thread_id": state["thread_id"],
                          "draft": state["draft"]})
    # Only the internal service may supply a validated server-side approval ID.
    if not isinstance(decision, dict) or set(decision) != {"approval_id"}:
        raise ValueError("Invalid review decision")
    if not isinstance(decision["approval_id"], str) or not decision["approval_id"]:
        raise ValueError("Invalid review decision")
    return {"status": "human_reviewed", "approval_id": decision["approval_id"]}


def build_graph(checkpointer):
    builder = StateGraph(RunState)
    builder.add_node("draft", draft)
    builder.add_node("review", review)
    builder.add_edge(START, "draft")
    builder.add_edge("draft", "review")
    builder.add_edge("review", END)
    return builder.compile(checkpointer=checkpointer)
