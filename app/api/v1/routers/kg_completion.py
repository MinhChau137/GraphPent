"""KG Completion Router — L4: LLM-based + CSNT structural/neural/template completion."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional

from app.services.kg_completion_service import KGCompletionService
from app.services.csnt_kg_completion import CSNTKGCompletion
from app.core.security import audit_log
from app.core.logger import logger

router = APIRouter(prefix="/kg", tags=["KG Completion (L4)"])

kg_service   = KGCompletionService()
csnt_service = CSNTKGCompletion()


# ── Request / Response models ─────────────────────────────────────────────────

class CompletionRequest(BaseModel):
    max_entities: int = 10
    max_degree:   int = 2


class CompletionResponse(BaseModel):
    entities_processed:  int
    relations_predicted: int
    relations_stored:    int


class ConflictRequest(BaseModel):
    entity_ids: Optional[List[str]] = None
    limit:      int = 20


class CSNTRequest(BaseModel):
    min_confidence:     float = 0.60
    max_edges_per_rule: int   = 500
    run_neural:         bool  = True
    run_anomaly:        bool  = True


# ── LLM-based endpoints (Phase 11) ───────────────────────────────────────────

@router.post("/complete", response_model=CompletionResponse)
async def complete_graph(request: CompletionRequest):
    """
    L4.1 — LLM link prediction.
    Finds low-degree entities and uses the LLM to predict missing relationships.
    Predicted relations stored with inferred=True.
    """
    try:
        result = await kg_service.complete_graph(
            max_entities=request.max_entities,
            max_degree=request.max_degree,
        )
        await audit_log("kg_complete_endpoint", result)
        return result
    except Exception as exc:
        logger.error(f"KG completion failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/conflicts")
async def detect_conflicts(request: ConflictRequest):
    """
    L4.2 — LLM conflict detection.
    Audits entities for contradictory or suspicious relations.
    """
    try:
        conflicts = await kg_service.detect_conflicts(
            entity_ids=request.entity_ids,
            limit=request.limit,
        )
        await audit_log("kg_conflict_endpoint", {"conflicts_found": len(conflicts)})
        return {"conflicts": conflicts, "total": len(conflicts)}
    except Exception as exc:
        logger.error(f"Conflict detection failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


# ── CSNT endpoints ────────────────────────────────────────────────────────────

@router.post("/csnt/complete")
async def csnt_complete(request: CSNTRequest):
    """
    L4.3 — CSNT full completion pass.

    Runs 4 components:
    - T (Template): rule-based link prediction (product sharing, TTP chains, bridges)
    - S (Structural): graph-topology scoring (common neighbors, path scan)
    - N (Neural): GNN embedding cosine similarity (if gnn_embedding available)
    - C (Confidence): multi-factor confidence scoring + propagation

    Plus anomaly detection.
    All predicted edges written to Neo4j with inferred=True.
    """
    try:
        result = await csnt_service.run_completion_pass(
            min_confidence=request.min_confidence,
            max_edges_per_rule=request.max_edges_per_rule,
            run_neural=request.run_neural,
            run_anomaly=request.run_anomaly,
        )
        return {
            "summary":          result.summary,
            "anomalies":        [
                {
                    "entity_id":    a.entity_id,
                    "anomaly_type": a.anomaly_type,
                    "detail":       a.detail,
                    "severity":     a.severity,
                }
                for a in result.anomalies
            ],
            "sample_predictions": [
                {
                    "src":        e.src,
                    "dst":        e.dst,
                    "rel_type":   e.rel_type,
                    "confidence": e.confidence,
                    "method":     e.method,
                }
                for e in result.predicted_edges[:20]
            ],
        }
    except Exception as exc:
        logger.error(f"CSNT completion failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/csnt/score-triples")
async def csnt_score_triples():
    """
    L4.4 — Re-score all existing edges with structural confidence.
    Non-destructive: only updates confidence properties.
    """
    try:
        result = await csnt_service.score_triples()
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/csnt/anomalies")
async def csnt_anomalies():
    """
    L4.5 — Run anomaly detection.
    Flags: vuln-count outliers, orphaned high-CVSS CVEs,
           services with no CVE links, low-confidence inferred edges.
    """
    try:
        flags = await csnt_service.detect_anomalies()
        by_type: dict = {}
        for f in flags:
            by_type.setdefault(f.anomaly_type, []).append({
                "entity_id": f.entity_id,
                "detail":    f.detail,
                "severity":  f.severity,
            })
        return {
            "total":    len(flags),
            "by_type":  by_type,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/health")
async def kg_health():
    return {"status": "healthy", "version": "L4-CSNT"}
