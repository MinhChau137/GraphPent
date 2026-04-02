"""FastAPI main application – Phase 2 skeleton."""

import structlog
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.config.settings import settings
from app.core.logger import logger, setup_logger
from app.core.security import get_request_id, audit_log
from app.api.v1.routers.ingest import router as ingest_router
from app.api.v1.routers.extract import router as extract_router

# Setup logger ngay khi import
setup_logger(settings.LOG_LEVEL)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan events – khởi tạo và dọn dẹp."""
    logger.info("🚀 Application starting", env=settings.APP_ENV, version="0.2.0")
    # TODO: Kết nối DB/Neo4j/Weaviate ở các phase sau
    yield
    logger.info("🛑 Application shutdown")

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
async def add_request_id_and_audit(request: Request, call_next):
    """Middleware: request ID + audit log cơ bản."""
    request_id = await get_request_id(request)
    start_time = structlog.contextvars.bind_contextvars(request_id=request_id)

    response = await call_next(request)

    process_time = (structlog.contextvars.get_contextvars().get("process_time", 0) or 0)
    logger.info(
        "Request completed",
        path=request.url.path,
        method=request.method,
        status_code=response.status_code,
        process_time_ms=round(process_time * 1000, 2)
    )
    return response

@app.get("/health")
async def health_check():
    """Healthcheck chi tiết Phase 2."""
    return {
        "status": "healthy",
        "phase": "2",
        "app_env": settings.APP_ENV,
        "log_level": settings.LOG_LEVEL,
        "allowed_targets_count": len(settings.ALLOWED_TARGETS),
        "services": ["postgres", "redis", "neo4j", "weaviate", "minio"],
        "message": "FastAPI skeleton + config + logging + security ready. Phase 3 sẽ bootstrap DBs."
    }

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")