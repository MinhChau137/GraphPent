"""LangGraph Workflow Definition - Phase 8."""

from langgraph.graph import StateGraph, END
from .state import AgentState
from .nodes import (
    planner_node, retrieval_node, graph_reasoning_node,
    tool_node, report_node, human_approval_node
)

def build_graph():
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("planner", planner_node)
    workflow.add_node("retrieval", retrieval_node)
    workflow.add_node("graph_reasoning", graph_reasoning_node)
    workflow.add_node("tool", tool_node)
    workflow.add_node("report", report_node)
    workflow.add_node("human_approval", human_approval_node)

    # Edges
    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "retrieval")
    workflow.add_edge("retrieval", "graph_reasoning")
    workflow.add_edge("graph_reasoning", "tool")
    workflow.add_edge("tool", "report")
    workflow.add_edge("report", "human_approval")
    workflow.add_edge("human_approval", END)

    return workflow.compile()

graph = build_graph()