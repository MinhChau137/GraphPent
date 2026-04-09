"""LangGraph Nodes - Các agent chuyên trách."""

from langgraph.graph import StateGraph
from app.services.ingestion_service import IngestionService
from app.services.extraction_service import ExtractionService
from app.services.graph_service import GraphService
from app.services.retriever_service import HybridRetrieverService
from app.core.logger import logger

ingestion_service = IngestionService()
extraction_service = ExtractionService()
graph_service = GraphService()
retriever_service = HybridRetrieverService()

async def planner_node(state: dict):
    """Planner quyết định bước tiếp theo."""
    logger.info("Planner deciding next step", current_step=state.get("current_step"))
    # TODO: Có thể dùng LLM để dynamic planning ở phase sau
    return {"current_step": "retrieve"}

async def retrieval_node(state: dict):
    """Retrieval Agent."""
    results = await retriever_service.hybrid_retrieve(state["query"], limit=10)
    return {"retrieval_results": results, "current_step": "graph_reasoning"}

async def graph_reasoning_node(state: dict):
    """Graph Reasoning Agent."""
    # Simple traversal example
    return {"graph_context": {"nodes": 5, "relations": 3}, "current_step": "tool"}

async def tool_node(state: dict):
    """Pentest Tool Agent (stub - sẽ đầy đủ Phase 9)."""
    logger.info("Tool agent called", query=state["query"])
    return {"tool_results": [], "current_step": "report"}

async def report_node(state: dict):
    """Report Agent."""
    report = f"Report for query: {state['query']}\nRetrieval: {len(state.get('retrieval_results', []))} results"
    return {"report_draft": report, "final_answer": report, "current_step": "end"}

async def human_approval_node(state: dict):
    """Human Approval Agent (stub)."""
    state["human_approval"] = True
    return state