"""LangGraph Workflow Definition - Phase 8 Complete."""

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from .state import AgentState
from .nodes import (
    planner_node, retrieval_node, graph_reasoning_node,
    tool_node, report_node, human_approval_node
)
from app.core.logger import logger
from typing import Dict, Any, List

def should_execute_tools(state: Dict[str, Any]) -> str:
    """Conditional router: decide whether to execute tools."""
    needs_tools = state.get("plan", {}).get("needs_tools", False)
    if needs_tools and state.get("retrieval_results"):
        return "tool"
    else:
        return "report"

def should_request_approval(state: Dict[str, Any]) -> str:
    """Conditional router: decide whether to request human approval."""
    # In lab, always proceed; in production, would check if dangerous operations
    return "human_approval"

def build_graph():
    """Build the multi-agent workflow graph."""
    workflow = StateGraph(AgentState)

    # Add all nodes
    workflow.add_node("planner", planner_node)
    workflow.add_node("retrieval", retrieval_node)
    workflow.add_node("graph_reasoning", graph_reasoning_node)
    workflow.add_node("tool", tool_node)
    workflow.add_node("report", report_node)
    workflow.add_node("human_approval", human_approval_node)

    # Set entry point
    workflow.set_entry_point("planner")

    # Define edges (linear flow with conditionals)
    workflow.add_edge("planner", "retrieval")
    workflow.add_edge("retrieval", "graph_reasoning")
    
    # Conditional: tool execution or direct to report
    workflow.add_conditional_edges(
        "graph_reasoning",
        should_execute_tools,
        {
            "tool": "tool",
            "report": "report"
        }
    )
    
    # Tool always goes to report
    workflow.add_edge("tool", "report")
    
    # Report goes to approval
    workflow.add_edge("report", "human_approval")
    
    # Approval ends workflow
    workflow.add_edge("human_approval", END)

    # Compile the graph
    return workflow.compile()

# Build and export the graph
graph = build_graph()

async def run_workflow(query: str, user_id: str = "anonymous") -> Dict[str, Any]:
    """Execute the complete workflow."""
    logger.info("🚀 Starting multi-agent workflow", query=query[:100], user=user_id)
    
    # Initial state
    initial_state = {
        "query": query,
        "user_id": user_id,
        "current_step": "planner",
        "retrieval_results": [],
        "tool_results": [],
        "graph_context": {},
        "human_approval": False
    }
    
    # Run workflow
    try:
        final_state = await graph.ainvoke(initial_state)
        logger.info("✅ Workflow completed", final_step=final_state.get("current_step"))
        return final_state
    except Exception as e:
        logger.error(f"❌ Workflow failed: {e}")
        return {
            **initial_state,
            "error": str(e),
            "current_step": "error"
        }