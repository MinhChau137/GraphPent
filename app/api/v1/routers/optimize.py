"""Optimization API - Parameter benchmarking endpoints (Phase 13)."""

from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from app.services.optimization_service import OptimizationService
from app.core.logger import logger

router = APIRouter(prefix="/optimize", tags=["optimization"])

# ── Request / Response models ──────────────────────────────────────────────

class GenerateTestSetRequest(BaseModel):
    n_queries: int = Field(30, ge=5, le=200, description="Number of retrieval queries to generate")
    holdout_n: int = Field(20, ge=5, le=100, description="Number of relations to hold out for KG benchmark")

class BenchmarkAlphaRequest(BaseModel):
    alpha_range: Optional[List[float]] = Field(
        None, description="Alpha values to test. Defaults to [0.0, 0.2, 0.4, 0.6, 0.7, 0.8, 1.0]"
    )
    k: int = Field(5, ge=1, le=20, description="Precision@k cutoff")

class GNNScenario(BaseModel):
    name: str
    w_pr: float = Field(..., ge=0.0, le=1.0)
    w_sev: float = Field(..., ge=0.0, le=1.0)
    w_bc: float = Field(..., ge=0.0, le=1.0)

class BenchmarkGNNRequest(BaseModel):
    scenarios: Optional[List[GNNScenario]] = Field(
        None, description="Weight scenarios to evaluate. Defaults to 4 preset scenarios."
    )

class HoldoutRelation(BaseModel):
    source_id: str
    target_id: str
    rel_type: str

class BenchmarkKGRequest(BaseModel):
    holdout_relations: Optional[List[HoldoutRelation]] = Field(
        None, description="Held-out relations to predict. If omitted, loads from cached test set."
    )


# ── Helpers ────────────────────────────────────────────────────────────────

def _svc() -> OptimizationService:
    return OptimizationService()


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.post("/generate-test-set", summary="Build synthetic evaluation dataset from graph")
async def generate_test_set(req: GenerateTestSetRequest) -> Dict:
    """
    Sample entities and relations from Neo4j to create a benchmark dataset.
    Results are persisted in Redis and reused by subsequent benchmarks.
    """
    try:
        return await _svc().generate_test_set(
            n_queries=req.n_queries,
            holdout_n=req.holdout_n,
        )
    except Exception as exc:
        logger.error("generate_test_set failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/benchmark-alpha", summary="Find optimal RRF alpha via Precision@k")
async def benchmark_alpha(req: BenchmarkAlphaRequest) -> Dict:
    """
    Test each alpha value in the range, measure Precision@k on synthetic queries.
    Returns per-alpha results and the recommended alpha to set in .env.
    """
    try:
        return await _svc().benchmark_alpha(
            alpha_range=req.alpha_range,
            k=req.k,
        )
    except Exception as exc:
        logger.error("benchmark_alpha failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/benchmark-gnn-weights", summary="Find optimal GNN blending weights via Spearman correlation")
async def benchmark_gnn_weights(req: BenchmarkGNNRequest) -> Dict:
    """
    Test weight scenarios for PageRank / Severity / Betweenness blending.
    Uses Spearman rank correlation against severity-based ground truth.
    Returns the scenario with highest correlation and suggested .env values.
    """
    try:
        scenarios = None
        if req.scenarios:
            scenarios = [s.dict() for s in req.scenarios]
        return await _svc().benchmark_gnn_weights(scenarios=scenarios)
    except Exception as exc:
        logger.error("benchmark_gnn_weights failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/benchmark-kg-completion", summary="Measure KG completion precision/recall")
async def benchmark_kg_completion(req: BenchmarkKGRequest) -> Dict:
    """
    Predict held-out relations and measure precision, recall, and F1.
    If holdout_relations is omitted, loads from the cached test set (generate first).
    """
    try:
        holdout = None
        if req.holdout_relations:
            holdout = [r.dict() for r in req.holdout_relations]
        return await _svc().benchmark_kg_completion(holdout_relations=holdout)
    except Exception as exc:
        logger.error("benchmark_kg_completion failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/run-all", summary="Run full benchmark suite (generate + all 3 benchmarks)")
async def run_all(background_tasks: BackgroundTasks) -> Dict:
    """
    Generates a test set then runs all three benchmarks sequentially.
    Returns a summary with recommended .env changes as action_items.

    Note: This can take several minutes depending on graph size and LLM speed.
    """
    try:
        return await _svc().run_all()
    except Exception as exc:
        logger.error("run_all failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/last-results", summary="Retrieve last benchmark results from Redis")
async def get_last_results() -> Dict:
    """
    Returns the most recently completed benchmark results (persisted in Redis).
    Returns 404 if no results have been stored yet.
    """
    results = _svc().get_last_results()
    if results is None:
        raise HTTPException(
            status_code=404,
            detail="No benchmark results found. Run /optimize/run-all first."
        )
    return results
