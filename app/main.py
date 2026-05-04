"""FastAPI main application – Phase 2 skeleton."""

from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.config.settings import settings
from app.core.logger import logger, setup_logger
from app.core.security import get_request_id, audit_log
from app.api.v1.routers.ingest import router as ingest_router
from app.api.v1.routers.extract import router as extract_router
from app.api.v1.routers.graph import router as graph_router
from app.api.v1.routers.retrieve import router as retrieve_router  
from app.api.v1.routers.workflow import router as workflow_router  # Enabled  
from app.api.v1.routers.tools import router as tools_router
from app.api.v1.routers.dashboard import router as dashboard_router
from app.api.v1.routers.nuclei import router as nuclei_router
from app.api.v1.routers.job_queue import router as job_queue_router
from app.api.v1.routers.websocket import router as websocket_router
from app.api.v1.routers.search import router as search_router
from app.api.v1.routers.auth import router as auth_router  # Phase 5.4 - Authentication
from app.core.auth_middleware import AuthMiddleware, PermissionMiddleware  # Phase 5.4 - Auth middleware
from app.api.v1.routers.batch import router as batch_router  # Phase 5.5 - Batch Operations
from app.api.v1.routers.export_import import router as export_import_router  # Phase 5.6 - Export/Import
from app.api.v1.routers.collect import router as collect_router            # Phase 10 - Data Collection
from app.api.v1.routers.kg_completion import router as kg_completion_router  # Phase 11 - KG Completion
from app.api.v1.routers.risk import router as risk_router                    # Phase 12 - Risk & Attack Paths
from app.api.v1.routers.optimize import router as optimize_router            # Phase 13 - Parameter Optimization
# Setup logger ngay khi import
setup_logger(settings.LOG_LEVEL)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan events – startup and graceful shutdown."""
    logger.info("🚀 Application starting", env=settings.APP_ENV, version="0.2.0")
    yield
    logger.info("🛑 Application shutdown — closing shared connections")
    from app.adapters.neo4j_client import close_neo4j_driver
    from app.adapters.weaviate_client import close_weaviate_client
    await close_neo4j_driver()
    close_weaviate_client()
    logger.info("✅ Connections closed")

app = FastAPI(
    title=settings.APP_NAME,
    description="Hybrid GraphRAG + Vector DB for Semi-Automated Penetration Testing (Lab only)",
    version="0.2.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(ingest_router)
app.include_router(extract_router)
app.include_router(graph_router)
app.include_router(retrieve_router)  
app.include_router(workflow_router)  # Enabled 
app.include_router(tools_router)  # Enabled - CVE-focused tools 
app.include_router(dashboard_router)
app.include_router(nuclei_router)  # Phase 4 - Nuclei API endpoints
app.include_router(job_queue_router)  # Phase 5.1 - Async Job Queue
app.include_router(websocket_router)  # Phase 5.2 - WebSocket real-time updates
app.include_router(search_router)  # Phase 5.3 - Advanced filtering with Elasticsearch
app.include_router(auth_router)  # Phase 5.4 - Authentication & Authorization
app.include_router(batch_router)  # Phase 5.5 - Batch Operations
app.include_router(export_import_router)  # Phase 5.6 - Export/Import
app.include_router(collect_router)        # Phase 10 - Data Collection
app.include_router(kg_completion_router)  # Phase 11 - KG Completion
app.include_router(risk_router)           # Phase 12 - Risk & Attack Paths
app.include_router(optimize_router)       # Phase 13 - Parameter Optimization

# Add authentication middleware (Phase 5.4)
app.add_middleware(PermissionMiddleware)
app.add_middleware(AuthMiddleware)

# CORS lab
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Add request ID to all responses."""
    request_id = await get_request_id(request)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "0.2.0"}

@app.get("/config")
async def get_config():
    """Expose config an toàn (không password)."""
    return {
        "app_name": settings.APP_NAME,
        "env": settings.APP_ENV,
        "allowed_targets": settings.ALLOWED_TARGETS,
        "max_tool_timeout": settings.MAX_TOOL_TIMEOUT,
    }

# Example protected endpoint (sẽ dùng cho tool wrappers sau)
@app.post("/test/validate-target")
async def test_target_validation(target: str):
    """Demo security check."""
    await audit_log("test_target_validation", {"target": target})
    await validate_target(target)  # sẽ raise nếu không allow
    return {"status": "allowed", "target": target}

async def validate_target(target: str):
    """Validate target against ALLOWED_TARGETS. Raise 403 if not allowed."""
    if not settings.is_target_allowed(target):
        raise HTTPException(
            status_code=403,
            detail=f"Target '{target}' is not in allowed targets list"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")