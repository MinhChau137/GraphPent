"""LangGraph Workflow Definition - Phase 8 + Phase 10 (collection + feedback loop)."""

from langgraph.graph import StateGraph, END
from .state import AgentState
from .nodes import (
    collection_node,
    planner_node,
    retrieval_node,
    graph_reasoning_node,
    tool_node,
    report_node,
    human_approval_node,
)
from app.core.logger import logger
from app.config.settings import settings
from typing import Dict, Any

# ---------------------------------------------------------------- conditionals

def should_execute_tools(state: Dict[str, Any]) -> str:
    """Route to tool execution or directly to report."""
    needs_tools = state.get("plan", {}).get("needs_tools", False)
    if needs_tools and state.get("retrieval_results"):
        return "tool"
    return "report"


def should_continue_loop(state: Dict[str, Any]) -> str:
    """
    Feedback loop gate (Phase 10).

    After human_approval_node increments loop_iteration, check whether
    new findings were discovered in this pass. If yes (and we haven't
    hit the iteration cap), send the workflow back to planner so it can
    reason over the freshly-stored graph facts.
    """
    # human_approval_node already incremented loop_iteration
    loop_iteration = state.get("loop_iteration", 0)
    max_iterations = state.get("max_loop_iterations", 3)
    new_findings = state.get("new_findings_count", 0)

    if new_findings > 0 and loop_iteration < max_iterations:
        logger.info(
            "Feedback loop triggered",
            iteration=loop_iteration,
            new_findings=new_findings,
            max=max_iterations,
        )
        return "planner"

    logger.info(
        "Workflow ending",
        iteration=loop_iteration,
        new_findings=new_findings,
    )
    return END


# ---------------------------------------------------------------- graph builder

def build_graph():
    """Build the multi-agent workflow graph."""
    workflow = StateGraph(AgentState)

    # Register nodes
    workflow.add_node("collection", collection_node)   # Phase 10: Nmap scan
    workflow.add_node("planner", planner_node)
    workflow.add_node("retrieval", retrieval_node)
    workflow.add_node("graph_reasoning", graph_reasoning_node)
    workflow.add_node("tool", tool_node)
    workflow.add_node("report", report_node)
    workflow.add_node("human_approval", human_approval_node)

    # Entry point: always start with collection
    # collection_node is a no-op when scan_target is absent or iteration > 0
    workflow.set_entry_point("collection")

    # collection → planner (always)
    workflow.add_edge("collection", "planner")

    # planner → retrieval (always)
    workflow.add_edge("planner", "retrieval")

    # retrieval → graph_reasoning (always)
    workflow.add_edge("retrieval", "graph_reasoning")

    # graph_reasoning → tool OR report (conditional)
    workflow.add_conditional_edges(
        "graph_reasoning",
        should_execute_tools,
        {
            "tool": "tool",
            "report": "report",
        },
    )

    # tool → report (always)
    workflow.add_edge("tool", "report")

    # report → human_approval (always)
    workflow.add_edge("report", "human_approval")

    # human_approval → planner (feedback loop) OR END
    workflow.add_conditional_edges(
        "human_approval",
        should_continue_loop,
        {
            "planner": "planner",
            END: END,
        },
    )

    return workflow.compile()


# Build and export the graph
graph = build_graph()


async def run_workflow(
    query: str,
    user_id: str = "anonymous",
    scan_target: str = None,
    max_loop_iterations: int = None,  # None → read from settings
) -> Dict[str, Any]:
    """Execute the complete workflow.

    Args:
        query: Analysis query or objective.
        user_id: Caller identity for audit logging.
        scan_target: Optional Nmap target (IP / CIDR / hostname).
                     When provided, collection_node runs a live scan first.
        max_loop_iterations: Hard cap on feedback loop passes (default 3).
    """
    if max_loop_iterations is None:
        max_loop_iterations = getattr(settings, "MAX_LOOP_ITERATIONS", 3)

    logger.info(
        "🚀 Starting multi-agent workflow",
        query=query[:100],
        user=user_id,
        scan_target=scan_target,
        max_loop_iterations=max_loop_iterations,
    )

    initial_state = {
        # Input
        "query":        query,
        "user_id":      user_id,
        "current_step": "collection",
        # L3: GraphRAG
        "retrieval_results": [],
        # L4: KG Completion (populated by planner on iter 0)
        "kg_completion_result": {},
        # L5: GNN outputs
        "gnn_risk_summary":    {},
        "attack_paths":        [],
        "prioritized_targets": [],
        # L6: Reasoning
        "graph_context": {},
        # L7: Execution
        "tool_results":   [],
        "human_approval": False,
        # L1/L7: Collection + feedback loop
        "scan_target":          scan_target,
        "collection_results":   [],
        "new_findings_count":   0,
        "loop_iteration":       0,
        "max_loop_iterations":  max_loop_iterations,
    }

    try:
        final_state = await graph.ainvoke(initial_state)
        logger.info(
            "✅ Workflow completed",
            final_step=final_state.get("current_step"),
            total_iterations=final_state.get("loop_iteration", 0),
        )
        return final_state
    except Exception as exc:
        logger.error(f"❌ Workflow failed: {exc}")
        return {
            **initial_state,
            "error": str(exc),
            "current_step": "error",
        }
