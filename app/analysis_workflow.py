"""Versioned analyst graph; existing draft-review-v1 threads retain their graph."""
from langgraph.graph import END, START, StateGraph

from .workflow import RunState, review

ANALYSIS_GRAPH_VERSION = "requirements-review-v1"


class AnalysisState(RunState):
    gateway_limits: dict
    requirements: dict | None
    llm_usage: dict
    analysis_error: str


def analysis_review(state: AnalysisState) -> dict:
    # LangGraph uses the node's annotated input schema. Preserve analyst fields
    # when delegating to the shared, narrower RunState review implementation.
    return review(state)


def build_analysis_graph(checkpointer, analyst):
    builder = StateGraph(AnalysisState)
    builder.add_node("analyst", analyst)
    builder.add_node("review", analysis_review)
    builder.add_edge(START, "analyst")
    builder.add_conditional_edges("analyst", lambda state: state["status"],
                                  {"awaiting_human_review": "review", "analysis_failed": END})
    builder.add_edge("review", END)
    return builder.compile(checkpointer=checkpointer)
