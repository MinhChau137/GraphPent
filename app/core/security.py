"""Core security utilities – allowlist, request tracing, audit stub."""

from fastapi import Request, HTTPException, status
from uuid import uuid4
import time
from app.config.settings import settings
from app.core.logger import logger

async def get_request_id(request: Request) -> str:
    """Tạo hoặc lấy request ID cho tracing."""
    if "X-Request-ID" not in request.headers:
        request_id = str(uuid4())
        request.headers.__dict__["_list"].append((b"x-request-id", request_id.encode()))
    return request.headers.get("X-Request-ID")

async def validate_target(target: str):
    """Middleware-style check cho mọi tool call. Sẽ được dùng ở Phase 9."""
    if not settings.is_target_allowed(target):
        logger.warning("Target blocked by allowlist", target=target, allowed=settings.ALLOWED_TARGETS)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Target '{target}' not in ALLOWED_TARGETS. Lab safety enforced."
        )
    logger.info("Target validated", target=target)

# Audit log stub (sẽ ghi vào PostgreSQL từ Phase 4)
async def audit_log(action: str, details: dict, request: Request = None):
    """Ghi audit log – bắt buộc mọi tool/action quan trọng."""
    request_id = await get_request_id(request) if request else None
    logger.info(
        "AUDIT",
        action=action,
        details=details,
        request_id=request_id,
        timestamp=time.time()
    )