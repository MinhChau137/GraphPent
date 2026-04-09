"""LangGraph State - Phase 8."""

from typing import TypedDict, List, Optional, Dict, Any
from pydantic import BaseModel

class AgentState(TypedDict):
    """Shared state giữa các agent."""
    query: str
    current_step: str
    ingested_documents: List[int]
    extracted_chunks: List[int]
    graph_context: Dict[str, Any]
    retrieval_results: List[Dict]
    tool_results: List[Dict]
    report_draft: Optional[str]
    human_approval: bool
    final_answer: Optional[str]
    error: Optional[str]