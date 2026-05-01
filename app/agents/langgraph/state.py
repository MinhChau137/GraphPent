"""LangGraph State - Multi-Agent Workflow (Phase 8)."""

from typing import TypedDict, List, Optional, Dict, Any
from pydantic import BaseModel

class AgentState(TypedDict, total=False):
    """Shared state for multi-agent orchestration."""
    
    # Input
    query: str
    user_id: str
    
    # Planning
    plan: Dict[str, Any]
    current_step: str
    
    # Data flow
    ingested_documents: List[int]
    extracted_chunks: List[int]
    
    # Retrieval
    retrieval_results: List[Dict]
    search_mode: str
    
    # Graph reasoning
    graph_context: Dict[str, Any]
    
    # Tools
    tool_results: List[Dict]
    
    # Report
    report: Dict[str, Any]
    report_markdown: Optional[str]
    
    # Final output
    final_answer: Optional[str]
    
    # Human approval
    human_approval: bool
    approval_timestamp: Optional[str]
    
    # Metadata
    workflow_id: Optional[str]
    start_time: Optional[str]
    end_time: Optional[str]
    
    # Error handling
    error: Optional[str]
    error_step: Optional[str]