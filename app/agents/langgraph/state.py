"""LangGraph State - Multi-Agent Workflow.

Follows the 7-layer architecture:
  L1 Data Sources → L2 Ingestion → L3 GraphRAG → L4 KG Completion
  → L5 GNN Reasoning → L6 Decision Engine → L7 Execution/Feedback
"""

from typing import TypedDict, List, Optional, Dict, Any


class AgentState(TypedDict, total=False):
    """Shared state across all 7 architectural layers."""

    # ── Input ────────────────────────────────────────────────────────────────
    query: str
    user_id: str

    # ── L2: Planning & normalisation ─────────────────────────────────────────
    plan: Dict[str, Any]
    current_step: str
    ingested_documents: List[int]
    extracted_chunks: List[int]

    # ── L3: GraphRAG retrieval ────────────────────────────────────────────────
    retrieval_results: List[Dict]
    search_mode: str

    # ── L4: KG Completion ────────────────────────────────────────────────────
    # Populated on iteration 0 when planner triggers KG completion
    kg_completion_result: Dict[str, Any]   # {entities_processed, relations_predicted, relations_stored}

    # ── L5: GNN / structural reasoning ───────────────────────────────────────
    gnn_risk_summary: Dict[str, Any]       # {severity_counts, top_risks[]}
    attack_paths: List[Dict]               # [{source, path_nodes, rel_types, hops, path_risk}]
    prioritized_targets: List[Dict]        # [{id, name, risk_score, risk_tier, open_ports}]

    # ── L6: Reasoning & decision ─────────────────────────────────────────────
    graph_context: Dict[str, Any]          # Expanded context: key_entities, attack_paths, recs

    # ── L7: Execution & feedback ─────────────────────────────────────────────
    tool_results: List[Dict]

    # ── Report / output ──────────────────────────────────────────────────────
    report: Dict[str, Any]
    report_markdown: Optional[str]
    final_answer: Optional[str]

    # ── Human approval ────────────────────────────────────────────────────────
    human_approval: bool
    approval_timestamp: Optional[str]

    # ── Metadata ─────────────────────────────────────────────────────────────
    workflow_id: Optional[str]
    start_time: Optional[str]
    end_time: Optional[str]

    # ── Error handling ────────────────────────────────────────────────────────
    error: Optional[str]
    error_step: Optional[str]

    # ── Collection / feedback loop (L1 + L7) ─────────────────────────────────
    scan_target: Optional[str]          # Nmap target (IP / CIDR / hostname)
    collection_results: List[Dict]      # Output from collection_node
    new_findings_count: int             # Entities added in last collection pass
    loop_iteration: int                 # How many feedback loops have run
    max_loop_iterations: int            # Hard cap to prevent infinite loops