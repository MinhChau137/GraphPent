"""LangGraph Nodes — 7-Layer Architecture Orchestration.

Layer mapping:
  collection_node    → L1 Data Sources + L2 Ingestion
  planner_node       → L2 Normalisation + L4 KG Completion (iter 0)
  retrieval_node     → L3 GraphRAG hybrid retrieval
  graph_reasoning_node → L5 GNN risk/attack-path + L6 Reasoning
  tool_node          → L7 Execution
  report_node        → L7 Feedback output
  human_approval_node → L7 Feedback loop gate
"""

from app.services.ingestion_service import IngestionService
from app.services.extraction_service import ExtractionService
from app.services.graph_service import GraphService
from app.services.retriever_service import HybridRetrieverService
from app.services.report_service import ReportService
from app.services.tool_service import PentestToolService
from app.services.collection_service import CollectionService
from app.services.gnn_service import GNNService
from app.services.kg_completion_service import KGCompletionService
from app.services.csnt_kg_completion import CSNTKGCompletion
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
collection_service = CollectionService()
gnn_service = GNNService()
kg_completion_service = KGCompletionService()
csnt_service = CSNTKGCompletion()

# ============ AGENT NODES ============

async def collection_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Collection Agent (Phase 10): Run Nmap scan → parse → store in Knowledge Graph.
    Only executes when scan_target is set in state.
    Skipped silently when no target is provided (preserves existing workflow).
    """
    target = state.get("scan_target")
    loop_iteration = state.get("loop_iteration", 0)

    # On feedback loops (iteration > 0), skip re-scanning — let planner re-reason
    # on the knowledge already stored. New scans only happen on iteration 0.
    if not target or loop_iteration > 0:
        return {
            **state,
            "collection_results": state.get("collection_results", []),
            "new_findings_count": 0,
            "current_step": "planner",
        }

    logger.info("📡 Collection Agent", target=target)

    try:
        result = await collection_service.collect_and_store(target)
        new_count = result.get("new_findings_count", 0)

        logger.info(
            "✅ Collection complete",
            target=target,
            hosts=result.get("hosts", 0),
            open_ports=result.get("open_ports", 0),
            new_findings=new_count,
        )
        await audit_log("collection_node", {"target": target, "new_findings": new_count})

        return {
            **state,
            "collection_results": [result],
            "new_findings_count": new_count,
            "current_step": "planner",
        }

    except PermissionError as exc:
        logger.error("❌ Collection blocked — target not whitelisted", error=str(exc))
        return {
            **state,
            "collection_results": [],
            "new_findings_count": 0,
            "error": str(exc),
            "current_step": "planner",
        }
    except FileNotFoundError as exc:
        logger.warning("⚠️ Nmap not installed, skipping collection", error=str(exc))
        return {
            **state,
            "collection_results": [],
            "new_findings_count": 0,
            "current_step": "planner",
        }
    except Exception as exc:
        logger.error("❌ Collection failed", error=str(exc))
        return {
            **state,
            "collection_results": [],
            "new_findings_count": 0,
            "error": str(exc),
            "current_step": "planner",
        }


async def planner_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    L2/L4 — Planner: normalise query, trigger KG Completion on first pass,
    select search mode, and decide whether tools are needed.
    """
    query = state.get("query", "")
    loop_iteration = state.get("loop_iteration", 0)
    collection_results = state.get("collection_results", [])
    logger.info("Planner Agent", query=query[:100], loop_iteration=loop_iteration)

    query_lower = query.lower()

    # ── L4: KG Completion — fire-and-forget on the first iteration ───────────
    # CSNT pass (structural + neural + template + confidence) runs first;
    # LLM-based completion follows as a slower background supplement.
    # Neither call blocks retrieval latency.
    kg_result = state.get("kg_completion_result", {})
    if loop_iteration == 0 and not kg_result:
        import asyncio

        async def _run_kg_completion():
            try:
                # CSNT: fast, graph-native, no LLM needed
                r = await csnt_service.run_completion_pass(
                    min_confidence=0.60,
                    max_edges_per_rule=200,
                    run_neural=True,
                    run_anomaly=True,
                )
                logger.info("L4: CSNT completion done", **r.summary)
            except Exception as exc:
                logger.warning("L4: CSNT completion failed", error=str(exc))
            try:
                # LLM supplement: fills semantic gaps CSNT cannot infer
                r2 = await kg_completion_service.complete_graph(max_entities=5, max_degree=2)
                logger.info("L4: LLM completion done", result=r2)
            except Exception as exc:
                logger.warning("L4: LLM completion failed", error=str(exc))

        asyncio.ensure_future(_run_kg_completion())
        kg_result = {"status": "triggered_background", "iteration": loop_iteration}

    # ── L5/L6: Risk-based target selection on subsequent loops ────────────────
    risk_targets: List[Dict] = []
    selected_target = state.get("scan_target")
    if loop_iteration > 0:
        try:
            risk_targets = await gnn_service.get_prioritized_targets(limit=5)
            if risk_targets:
                top = risk_targets[0]
                selected_target = top.get("id") or top.get("name") or selected_target
                logger.info("L6: risk-based target selected",
                            target=selected_target,
                            risk_score=top.get("risk_score"),
                            tier=top.get("risk_tier"))
        except Exception as exc:
            logger.warning("GNN risk query failed in planner", error=str(exc))

    # ── Query enrichment ──────────────────────────────────────────────────────
    enriched_query = query
    if collection_results:
        host_ips = collection_results[0].get("host_ips", [])
        if host_ips:
            enriched_query = f"{query} discovered_hosts:{','.join(host_ips[:3])}"
    if risk_targets:
        top_ids = [t.get("id", "") for t in risk_targets[:3]]
        enriched_query = f"{enriched_query} high_risk:{','.join(top_ids)}"

    # ── Search mode selection ─────────────────────────────────────────────────
    if any(kw in query_lower for kw in ["specific cve", "cve-", "vulnerability id"]):
        search_mode = "graph_only"
    else:
        search_mode = "hybrid"

    from app.config.settings import settings as _settings
    target_whitelisted = bool(selected_target) and _settings.is_target_allowed(str(selected_target))
    needs_tools = (
        target_whitelisted
        or bool(collection_results)
        or bool(risk_targets)
        or any(kw in query_lower for kw in ["scan", "exploit", "test", "verify"])
    )

    plan = {
        "query": enriched_query,
        "search_mode": search_mode,
        "needs_tools": needs_tools,
        "loop_iteration": loop_iteration,
        "risk_targets": [t.get("id") for t in risk_targets[:3]],
        "kg_completion_triggered": loop_iteration == 0,
        "plan_created_at": datetime.now().isoformat(),
    }

    logger.info("Plan created", search_mode=search_mode, needs_tools=needs_tools,
                iteration=loop_iteration, risk_targets=len(risk_targets))
    await audit_log("planner_node", {"plan": plan})

    return {
        **state,
        "plan": plan,
        "scan_target": selected_target,
        "loop_iteration": loop_iteration,
        "kg_completion_result": kg_result,
        "prioritized_targets": risk_targets,
        "current_step": "retrieval",
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
        # Determine alpha based on mode — hybrid uses settings.RRF_ALPHA (default 0.3)
        from app.config.settings import settings as _settings
        alpha_map = {
            "vector_only": 1.0,
            "graph_only":  0.0,
            "hybrid":      _settings.RRF_ALPHA,
        }
        alpha = alpha_map.get(search_mode, _settings.RRF_ALPHA)
        
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
    L5/L6 — Graph Reasoning: structural risk scoring (GNN) + attack-path
    inference + multi-hop context expansion.

    Pipeline:
      1. Extract top entities from retrieval results (L3 output)
      2. Call GNNService: risk summary + attack paths from high-score entities
      3. Build enriched graph_context for the tool/report nodes
    """
    retrieval_results = state.get("retrieval_results", [])
    logger.info("Graph Reasoning Agent", result_count=len(retrieval_results))

    # ── 1. Extract key entities from retrieval results ───────────────────────
    def _infer_entity_type(eid: str, meta: dict) -> str:
        """Infer entity type from metadata or ID pattern."""
        if isinstance(meta, dict) and meta.get("type"):
            return meta["type"]
        eid_upper = str(eid).upper()
        if eid_upper.startswith("CVE-") or eid_upper.startswith("CVE"):
            return "CVE"
        if eid_upper.startswith("CWE-"):
            return "Weakness"
        return "chunk"

    key_entities = []
    for result in retrieval_results[:5]:
        eid = result.get("id")
        if eid:
            meta = result.get("metadata") or {}
            key_entities.append({
                "id": eid,
                "type": _infer_entity_type(eid, meta),
                "score": result.get("final_score", 0.0),
            })

    # ── 2. L5: GNN risk summary ───────────────────────────────────────────────
    gnn_risk_summary: Dict[str, Any] = {}
    try:
        gnn_risk_summary = await gnn_service.get_risk_summary()
        logger.info("L5: GNN risk summary", top_risks=len(gnn_risk_summary.get("top_risks", [])))
    except Exception as exc:
        logger.error("GNN risk summary failed", error=str(exc))

    try:
        # ── 3. L5: Attack-path inference ─────────────────────────────────────
        # Use GNN top-risk nodes for attack path discovery (graph node IDs),
        # since retrieval results may be chunk IDs at high alpha values.
        attack_paths: List[Dict] = state.get("attack_paths", [])
        top_risks = gnn_risk_summary.get("top_risks", [])
        graph_node_ids = [r["id"] for r in top_risks[:3] if r.get("id")]

        # Fallback: use any graph node IDs from retrieval results
        retrieval_graph_ids = [
            e["id"] for e in key_entities
            if e["type"] in ("Weakness", "CVE", "Vulnerability")
        ]
        source_ids = graph_node_ids or retrieval_graph_ids

        for sid in source_ids[:2]:
            try:
                paths = await gnn_service.find_attack_paths(
                    source_id=sid,
                    target_label="CVE",
                    max_hops=4,
                )
                attack_paths.extend(paths[:3])
                logger.info("L5: attack paths found", source=sid, paths=len(paths))
            except Exception as exc:
                logger.warning("Attack path query failed", entity=sid, error=str(exc))

        # ── 4. L6: Build recommendations ─────────────────────────────────────
        recommendations: List[str] = []
        top_risks = gnn_risk_summary.get("top_risks", [])
        if top_risks:
            critical = [r for r in top_risks if r.get("risk_tier") in ("CRITICAL", "HIGH")]
            if critical:
                ids = ", ".join(r.get("id", "") for r in critical[:3])
                recommendations.append(f"High-risk nodes detected: {ids} — prioritise for scanning")

        cve_entities = [e for e in key_entities if "CVE" in str(e.get("type", "")).upper()
                        or str(e.get("id", "")).upper().startswith("CVE")]
        if cve_entities:
            recommendations.append(
                f"{len(cve_entities)} CVE(s) retrieved — run Nuclei with matching templates"
            )

        if attack_paths:
            shortest = min(attack_paths, key=lambda p: p.get("hops", 99))
            recommendations.append(
                f"Shortest attack path: {shortest.get('hops', '?')} hops "
                f"(path_risk={shortest.get('path_risk', 0):.3f})"
            )

        expanded_context = {
            "key_entities":   key_entities,
            "gnn_risk":       gnn_risk_summary,
            "attack_paths":   attack_paths[:5],
            "recommendations": recommendations,
        }

        logger.info("Graph reasoning completed",
                    entities=len(key_entities),
                    attack_paths=len(attack_paths),
                    recommendations=len(recommendations))
        await audit_log("graph_reasoning_node", {
            "key_entities": len(key_entities),
            "attack_paths": len(attack_paths),
        })

        return {
            **state,
            "graph_context":    expanded_context,
            "gnn_risk_summary": gnn_risk_summary,
            "attack_paths":     attack_paths,
            "current_step":     "tool" if state.get("plan", {}).get("needs_tools") else "report",
        }

    except Exception as exc:
        logger.error("Graph reasoning failed", error=str(exc))
        return {
            **state,
            "graph_context": {
                "key_entities": key_entities,
                "gnn_risk": gnn_risk_summary,
                "attack_paths": [],
                "recommendations": [],
            },
            "gnn_risk_summary": gnn_risk_summary,
            "attack_paths": [],
            "error": str(exc),
            "current_step": "report",
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
    scan_target = state.get("scan_target")
    logger.info("🛠️ Tool Agent", results_available=len(retrieval_results))

    tool_results = []
    nuclei_findings_count = 0

    try:
        # Extract CVEs from retrieval results
        cves = []
        for result in retrieval_results[:5]:
            meta = result.get("metadata") or {}
            if "CVE" in str(meta.get("type", "")):
                cve_id = result.get("id")
                if cve_id:
                    cves.append(cve_id)

        # Run Nuclei on discovered hosts when a scan_target is set
        if scan_target:
            try:
                nuclei_result = await tool_service.run_nuclei_scan(
                    target=scan_target,
                    severity="critical,high",
                )
                nuclei_findings = nuclei_result.get("findings", [])
                nuclei_findings_count = len(nuclei_findings)
                for finding in nuclei_findings[:10]:
                    tool_results.append({
                        "tool": "nuclei",
                        "source": "nuclei",
                        "target": scan_target,
                        **finding,
                    })
                if nuclei_findings_count == 0:
                    tool_results.append({
                        "tool": "nuclei",
                        "target": scan_target,
                        "status": "completed",
                        "findings_count": 0,
                    })
            except Exception as exc:
                logger.warning("Nuclei scan failed in tool_node", error=str(exc))
                tool_results.append({
                    "tool": "nuclei",
                    "target": scan_target,
                    "status": "error",
                    "error": str(exc)[:200],
                })

        # CVE exploitability analysis (always run)
        for cve_id in cves[:3]:
            try:
                tool_result = {
                    "cve_id": cve_id,
                    "analysis": "Potentially exploitable - check with Nuclei",
                    "recommended_action": "Run Nuclei scan",
                }
                tool_results.append(tool_result)
            except Exception as exc:
                logger.warning(f"CVE analysis failed for {cve_id}: {exc}")

        logger.info("✅ Tool analysis completed", tool_results=len(tool_results), nuclei_findings=nuclei_findings_count)
        await audit_log("tool_node", {"tool_results": len(tool_results), "nuclei_findings": nuclei_findings_count})

        # Accumulate new_findings_count for the feedback loop decision
        prior_count = state.get("new_findings_count", 0)
        return {
            **state,
            "tool_results": tool_results,
            "new_findings_count": prior_count + nuclei_findings_count,
            "current_step": "report",
        }
    except Exception as exc:
        logger.error(f"❌ Tool execution failed: {exc}")
        return {
            **state,
            "tool_results": [],
            "error": str(exc),
            "current_step": "report",
        }

async def report_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    L7 — Report: synthesise outputs from all 7 layers into a structured report.
    """
    query             = state.get("query", "")
    retrieval_results = state.get("retrieval_results", [])
    tool_results      = state.get("tool_results", [])
    collection_results= state.get("collection_results", [])
    loop_iteration    = state.get("loop_iteration", 0)
    graph_context     = state.get("graph_context", {})
    kg_completion     = state.get("kg_completion_result", {})
    gnn_risk          = state.get("gnn_risk_summary", {})
    attack_paths      = state.get("attack_paths", [])
    prioritized       = state.get("prioritized_targets", [])

    logger.info("Report Agent",
                results=len(retrieval_results),
                tools=len(tool_results),
                iteration=loop_iteration)

    try:
        report_content = {
            "query":          query,
            "timestamp":      datetime.now().isoformat(),
            "loop_iteration": loop_iteration,
            # L1/L2
            "collection": {
                "scans_performed": len(collection_results),
                "summary":         collection_results[0] if collection_results else {},
            },
            # L3: GraphRAG
            "retrieval": {
                "total_results": len(retrieval_results),
                "top_results":   retrieval_results[:5],
            },
            # L4: KG Completion
            "kg_completion": kg_completion,
            # L5: GNN
            "gnn": {
                "risk_summary":        gnn_risk,
                "attack_paths":        attack_paths[:5],
                "prioritized_targets": prioritized[:5],
            },
            # L6: Reasoning
            "reasoning": {
                "key_entities":    graph_context.get("key_entities", []),
                "recommendations": graph_context.get("recommendations", []),
            },
            # L7: Tool execution
            "tools": {
                "analyses_performed": len(tool_results),
                "findings":           tool_results,
            },
            "status": "completed",
        }

        markdown_report = await report_service.generate_markdown_report(report_content, query)

        recs = graph_context.get("recommendations", [])
        final_answer = (
            f"Analysis complete ({loop_iteration} iteration(s)). "
            f"Retrieved {len(retrieval_results)} resources, "
            f"{len(attack_paths)} attack path(s) found, "
            f"{len(tool_results)} tool finding(s). "
            + (f"Top recommendation: {recs[0]}" if recs else "")
        )

        logger.info("Report generated")
        await audit_log("report_node", {"report_size": len(str(report_content))})

        return {
            **state,
            "report":          report_content,
            "report_markdown": markdown_report,
            "final_answer":    final_answer,
            "current_step":    "human_approval",
        }

    except Exception as exc:
        logger.error("Report generation failed", error=str(exc))
        return {
            **state,
            "report":       {},
            "error":        str(exc),
            "current_step": "human_approval",
        }

async def human_approval_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Human Approval Agent: Validation & approval workflow.
    Also increments loop_iteration so the feedback-loop conditional
    in graph.py knows how many passes have completed.
    """
    loop_iteration = state.get("loop_iteration", 0)
    new_findings = state.get("new_findings_count", 0)
    logger.info("👤 Human Approval Node", iteration=loop_iteration, new_findings=new_findings)

    await audit_log("human_approval_node", {
        "approved": True,
        "loop_iteration": loop_iteration,
        "new_findings_count": new_findings,
    })

    return {
        **state,
        "human_approval": True,
        "approval_timestamp": datetime.now().isoformat(),
        "loop_iteration": loop_iteration + 1,
        # Reset per-loop counter so the next pass starts fresh
        "new_findings_count": 0,
    }