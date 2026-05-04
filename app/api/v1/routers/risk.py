"""Risk Router - Phase 12: GNN-based risk scoring + attack-path endpoints."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional

from app.services.gnn_service import GNNService
from app.core.security import audit_log
from app.core.logger import logger

router = APIRouter(prefix="/risk", tags=["Risk & Attack Paths (Phase 12)"])

gnn_service = GNNService()


class AttackPathRequest(BaseModel):
    source_id: str
    target_label: str = "CVE"
    max_hops: int = 4


@router.post("/compute-scores")
async def compute_risk_scores():
    """
    Phase 12.1: Run PageRank + Betweenness Centrality via Neo4j GDS,
    then write a blended risk_score to every node.
    Falls back to degree-based scoring when GDS is not installed.
    """
    try:
        result = await gnn_service.compute_risk_scores()
        await audit_log("risk_compute_endpoint", result)
        return result
    except Exception as exc:
        logger.error(f"Risk scoring failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/high-risk-nodes")
async def get_high_risk_nodes(limit: int = Query(default=20, ge=1, le=100)):
    """
    Phase 12.2: Return top-N nodes by blended risk_score.
    Each node includes its risk_tier (CRITICAL / HIGH / MEDIUM / LOW).
    Run /risk/compute-scores first to populate scores.
    """
    try:
        nodes = await gnn_service.get_high_risk_nodes(limit=limit)
        await audit_log("risk_nodes_endpoint", {"count": len(nodes)})
        return {"nodes": nodes, "total": len(nodes)}
    except Exception as exc:
        logger.error(f"High-risk nodes query failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/attack-paths")
async def find_attack_paths(request: AttackPathRequest):
    """
    Phase 12.3: Find Cypher-based attack paths from a source node
    (e.g. a Host IP) to nodes of the specified target label (e.g. CVE).
    Paths are ranked by path_risk = target_risk / hops.
    """
    try:
        paths = await gnn_service.find_attack_paths(
            source_id=request.source_id,
            target_label=request.target_label,
            max_hops=request.max_hops,
        )
        await audit_log("attack_path_endpoint", {
            "source": request.source_id,
            "paths": len(paths),
        })
        return {"source_id": request.source_id, "paths": paths, "total": len(paths)}
    except Exception as exc:
        logger.error(f"Attack path query failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/summary")
async def risk_summary():
    """
    Phase 12.4: Overall risk snapshot.
    Returns severity counts, nodes scored, and top-5 highest-risk nodes.
    """
    try:
        summary = await gnn_service.get_risk_summary()
        return summary
    except Exception as exc:
        logger.error(f"Risk summary failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/prioritized-targets")
async def get_prioritized_targets(limit: int = Query(default=10, ge=1, le=50)):
    """
    Phase 12.5 / Phase 13: Return Host nodes sorted by risk_score.
    Used by the planner agent to decide which target to scan next.
    """
    try:
        targets = await gnn_service.get_prioritized_targets(limit=limit)
        return {"targets": targets, "total": len(targets)}
    except Exception as exc:
        logger.error(f"Prioritized targets failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/health")
async def risk_health():
    return {"status": "healthy", "version": "Phase 12"}
