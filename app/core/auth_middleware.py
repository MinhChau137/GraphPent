"""Authentication middleware (Phase 5.4)."""

import logging
from typing import Optional
from datetime import datetime

from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.services.auth_service import AuthService
from app.domain.schemas.auth import PermissionEnum

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware for authentication and audit logging."""

    # Routes that don't require authentication
    PUBLIC_ROUTES = {
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/auth/refresh",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/health",
        "/config",
    }

    # Route prefixes that don't require authentication (lab/dev mode)
    PUBLIC_PREFIXES = {
        "/api/v1/graph",
        "/api/v1/retrieve",
        "/retrieve",
        "/ingest",
        "/extract",
        "/workflow",
        "/tools",
        "/dashboard",
        "/nuclei",
        "/jobs",
        "/ws",
        "/search",
        "/batch",
        "/collect",
        "/kg",
        "/risk",
        "/optimize",
    } if True else set()  # set True=lab, False=production

    async def dispatch(self, request: Request, call_next):
        """Process request and handle authentication."""
        # Skip auth for public routes
        if self._is_public_route(request.url.path):
            return await call_next(request)

        # Extract token or API key
        auth_header = request.headers.get("Authorization", "")
        api_key = request.headers.get("X-API-Key", "")

        if not auth_header and not api_key:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Missing credentials"},
            )

        # Validate authentication
        user_data = None

        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            auth_service = AuthService()
            token_payload = auth_service.verify_token(token)

            if not token_payload:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Invalid or expired token"},
                )

            user_data = {
                "user_id": token_payload.sub,
                "username": token_payload.username,
                "role": token_payload.role,
                "permissions": token_payload.permissions,
            }

        elif api_key:
            auth_service = AuthService()
            key_data = await auth_service._verify_api_key_async(api_key)

            if not key_data:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Invalid or expired API key"},
                )

            user_data = key_data

        # Attach user data to request state
        if user_data:
            request.state.user_id = user_data.get("user_id")
            request.state.username = user_data.get("username")
            request.state.role = user_data.get("role")
            request.state.permissions = user_data.get("permissions", [])

        response = await call_next(request)
        return response

    @staticmethod
    def _is_public_route(path: str) -> bool:
        """Check if route is public."""
        if path in AuthMiddleware.PUBLIC_ROUTES or path.startswith("/static/"):
            return True
        return any(path.startswith(prefix) for prefix in AuthMiddleware.PUBLIC_PREFIXES)


class PermissionMiddleware(BaseHTTPMiddleware):
    """Middleware for permission-based access control."""

    # Route to required permissions mapping
    ROUTE_PERMISSIONS = {
        "POST /api/v1/jobs": PermissionEnum.JOBS_CREATE,
        "GET /api/v1/jobs": PermissionEnum.JOBS_READ,
        "PUT /api/v1/jobs": PermissionEnum.JOBS_UPDATE,
        "DELETE /api/v1/jobs": PermissionEnum.JOBS_DELETE,
        "POST /api/v1/jobs/batch": PermissionEnum.JOBS_BATCH,
        "GET /api/v1/search": PermissionEnum.SEARCH_BASIC,
        "POST /api/v1/search": PermissionEnum.SEARCH_ADVANCED,
        "POST /api/v1/export": PermissionEnum.RESULTS_EXPORT,
        "POST /api/v1/import": PermissionEnum.RESULTS_IMPORT,
        "GET /api/v1/users": PermissionEnum.USERS_READ,
        "POST /api/v1/users": PermissionEnum.USERS_MANAGE,
        "PUT /api/v1/users": PermissionEnum.USERS_MANAGE,
        "DELETE /api/v1/users": PermissionEnum.USERS_MANAGE,
        "GET /api/v1/settings": PermissionEnum.SETTINGS_READ,
        "PUT /api/v1/settings": PermissionEnum.SETTINGS_WRITE,
    }

    async def dispatch(self, request: Request, call_next):
        """Check permissions before processing request."""
        # Skip permission check for public/auth routes
        if self._is_public_route(request.url.path):
            return await call_next(request)

        # Get user permissions from state
        permissions = getattr(request.state, "permissions", [])

        if not permissions:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "No permissions assigned"},
            )

        # Check route permission
        method_path = f"{request.method} {request.url.path}"
        required_permission = self._get_required_permission(method_path)

        if required_permission and required_permission not in permissions:
            username = getattr(request.state, "username", "unknown")
            logger.warning(
                f"User {username} tried to access {method_path} without permission {required_permission}"
            )

            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": f"Missing permission: {required_permission}"},
            )

        response = await call_next(request)
        return response

    @classmethod
    def _get_required_permission(cls, method_path: str) -> Optional[str]:
        """Get required permission for route."""
        for route, permission in cls.ROUTE_PERMISSIONS.items():
            if method_path.startswith(route.split()[0] + " "):
                return permission.value
        return None

    @staticmethod
    def _is_public_route(path: str) -> bool:
        """Check if route is public."""
        public_routes = {
            "/api/v1/auth",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/health",
            "/config",
        }
        if any(path.startswith(route) for route in public_routes):
            return True
        return any(path.startswith(prefix) for prefix in AuthMiddleware.PUBLIC_PREFIXES)
