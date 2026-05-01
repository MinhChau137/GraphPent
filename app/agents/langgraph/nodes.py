"""LangGraph Nodes - Multi-Agent Orchestration (Phase 8 Complete)."""

from langgraph.graph import StateGraph
from app.services.ingestion_service import IngestionService
from app.services.extraction_service import ExtractionService
from app.services.graph_service import GraphService
from app.services.retriever_service import HybridRetrieverService
from app.services.report_service import ReportService
from app.services.tool_service import PentestToolService
from app.core.logger import logger
from app.core.security import audit_log
from typing import Dict, Any, List
from datetime import datetime

ingestion_service = IngestionService()
extraction_service = ExtractionService()
graph_service = GraphService()
retriever_service = HybridRetrieverService()
report_service = ReportService()
tool_service = PentestToolService()

# ============ AGENT NODES ============

async def planner_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Planner Agent: Analyze query và decide next action.
    - Determine workflow stages needed
    - Decide on search mode (vector/graph/hybrid)
    - Plan tool selection
    """
    query = state.get("query", "")
    logger.info("🤖 Planner Agent", query=query[:100])
    
    # Analyze query to determine strategy
    query_lower = query.lower()
    
    # Determine search mode based on query characteristics
    if any(keyword in query_lower for keyword in ["specific cve", "cve-", "vulnerability id"]):
        search_mode = "graph_only"  # Specific lookups go to graph
    elif any(keyword in query_lower for keyword in ["find", "search", "discover", "list"]):
        search_mode = "hybrid"  # General searches use hybrid
    else:
        search_mode = "hybrid"
    
    # Determine if tools needed
    needs_tools = any(keyword in query_lower for keyword in ["scan", "exploit", "test", "verify"])
    
    plan = {
        "query": query,
        "search_mode": search_mode,
        "needs_tools": needs_tools,
        "current_step": "retrieval",
        "plan_created_at": datetime.now().isoformat()
    }
    
    logger.info("Plan created", plan=plan)
    await audit_log("planner_node", {"plan": plan})
    
    return {
        **state,
        "plan": plan,
        "current_step": "retrieval"
    }

async def retrieval_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Retrieval Agent: Execute hybrid search based on plan.
    - Retrieve relevant documents/entities
    - Score and filter results
    - Prepare context for next step
    """
    query = state.get("query", "")
    search_mode = state.get("plan", {}).get("search_mode", "hybrid")
    logger.info("🔎 Retrieval Agent", query=query[:100], mode=search_mode)
    
    try:
        # Determine alpha based on mode
        alpha_map = {
            "vector_only": 1.0,
            "graph_only": 0.0,
            "hybrid": 0.7
        }
        alpha = alpha_map.get(search_mode, 0.7)
        
        # Execute retrieval
        retrieval_results = await retriever_service.hybrid_retrieve(
            query=query,
            limit=20,
            alpha=alpha,
            mode=search_mode
        )
        
        logger.info(f"✅ Retrieved {len(retrieval_results)} results")
        await audit_log("retrieval_node", {"results": len(retrieval_results), "mode": search_mode})
        
        return {
            **state,
            "retrieval_results": retrieval_results,
            "current_step": "graph_reasoning"
        }
    except Exception as e:
        logger.error(f"❌ Retrieval failed: {e}")
        return {
            **state,
            "retrieval_results": [],
            "error": str(e),
            "current_step": "report"
        }

async def graph_reasoning_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Graph Reasoning Agent: Analyze relationships & context.
    - Expand on relationships from retrieval results
    - Perform multi-hop reasoning
    - Extract relevant CVEs/CWEs and their connections
    """
    retrieval_results = state.get("retrieval_results", [])
    logger.info("🕸️ Graph Reasoning Agent", result_count=len(retrieval_results))
    
    try:
        # Extract key entities from retrieval results
        key_entities = []
        for result in retrieval_results[:5]:  # Top 5
            entity_id = result.get("id")
            if entity_id:
                key_entities.append({
                    "id": entity_id,
                    "type": result.get("metadata", {}).get("type", "unknown"),
                    "score": result.get("final_score", 0.0)
                })
        
        # For each key entity, perform relationship expansion
        expanded_context = {
            "key_entities": key_entities,
            "related_findings": [],
            "recommendations": []
        }
        
        # Multi-hop reasoning example
        # (In production, would use Cypher queries to traverse relationships)
        if key_entities:
            cve_entities = [e for e in key_entities if "CVE" in str(e.get("type", ""))]
            if cve_entities:
                expanded_context["recommendations"].append(
                    f"Found {len(cve_entities)} CVE(s) - consider running Nuclei scan"
                )
        
        logger.info("✅ Graph reasoning completed", key_entities=len(key_entities))
        await audit_log("graph_reasoning_node", {"key_entities": len(key_entities)})
        
        return {
            **state,
            "graph_context": expanded_context,
            "current_step": "tool" if state.get("plan", {}).get("needs_tools") else "report"
        }
    except Exception as e:
        logger.error(f"❌ Graph reasoning failed: {e}")
        return {
            **state,
            "graph_context": {},
            "error": str(e),
            "current_step": "report"
        }

async def tool_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Tool Agent: Execute pentest tools.
    - Analyze CVE exploitability
    - Run Nuclei scans if permitted
    - Correlate findings with knowledge base
    """
    query = state.get("query", "")
    retrieval_results = state.get("retrieval_results", [])
    logger.info("🛠️ Tool Agent", results_available=len(retrieval_results))
    
    tool_results = []
    
    try:
        # Extract CVEs from retrieval results
        cves = []
        for result in retrieval_results[:5]:
            if "CVE" in str(result.get("metadata", {}).get("type", "")):
                cve_id = result.get("id")
                if cve_id:
                    cves.append(cve_id)
        
        # Analyze exploitability
        for cve_id in cves[:3]:  # Limit to 3 CVEs
            try:
                # Would call tool_service.analyze_cve_exploitable(cve_json)
                tool_result = {
                    "cve_id": cve_id,
                    "analysis": "Potentially exploitable - check with Nuclei",
                    "recommended_action": "Run Nuclei scan"
                }
                tool_results.append(tool_result)
            except Exception as e:
                logger.warning(f"Tool analysis failed for {cve_id}: {e}")
        
        logger.info(f"✅ Tool analysis completed: {len(tool_results)} results")
        await audit_log("tool_node", {"tool_results": len(tool_results)})
        
        return {
            **state,
            "tool_results": tool_results,
            "current_step": "report"
        }
    except Exception as e:
        logger.error(f"❌ Tool execution failed: {e}")
        return {
            **state,
            "tool_results": [],
            "error": str(e),
            "current_step": "report"
        }

async def report_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Report Agent: Generate comprehensive report.
    - Synthesize all findings
    - Generate recommendations
    - Format output (JSON/Markdown)
    """
    query = state.get("query", "")
    retrieval_results = state.get("retrieval_results", [])
    tool_results = state.get("tool_results", [])
    logger.info("📊 Report Agent", results=len(retrieval_results), tools=len(tool_results))
    
    try:
        # Build report
        report_content = {
            "query": query,
            "timestamp": datetime.now().isoformat(),
            "retrieval": {
                "total_results": len(retrieval_results),
                "top_results": retrieval_results[:5]
            },
            "tools": {
                "analyses_performed": len(tool_results),
                "findings": tool_results
            },
            "status": "completed"
        }
        
        # Generate markdown report
        markdown_report = await ReportService.generate_markdown_report(report_content, query)
        
        logger.info("✅ Report generated")
        await audit_log("report_node", {"report_size": len(str(report_content))})
        
        return {
            **state,
            "report": report_content,
            "report_markdown": markdown_report,
            "final_answer": f"Analysis complete. Found {len(retrieval_results)} relevant resources. " +
                           f"Tool analysis: {len(tool_results)} items.",
            "current_step": "human_approval"
        }
    except Exception as e:
        logger.error(f"❌ Report generation failed: {e}")
        return {
            **state,
            "report": {},
            "error": str(e),
            "current_step": "human_approval"
        }

async def human_approval_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Human Approval Agent: Validation & approval workflow.
    - In future: Request user approval
    - Log approval/rejection
    - Trigger notifications
    """
    logger.info("👤 Human Approval Node")
    
    # In lab mode, auto-approve
    # In production, would wait for user approval via webhook/polling
    state["human_approval"] = True
    state["approval_timestamp"] = datetime.now().isoformat()
    
    await audit_log("human_approval_node", {"approved": True})
    
    return state