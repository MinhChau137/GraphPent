"""Authentication endpoints (Phase 5.4)."""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import select

from app.adapters.postgres import AsyncSessionLocal, User
from app.services.auth_service import AuthService, get_auth_service
from app.domain.schemas.auth import (
    UserCreate,
    UserResponse,
    TokenResponse,
    LoginRequest,
    RefreshTokenRequest,
    ChangePasswordRequest,
    APIKeyCreate,
    APIKeyResponse,
    APIKeyListResponse,
    AuthErrorResponse,
    RoleInfo,
    RoleEnum,
    ROLE_PERMISSIONS,
    PermissionEnum,
    AuditLogEntry,
    HealthCheckAuth,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


async def get_current_user(request: Request) -> dict:
    """Dependency to get current user from request."""
    user_data = {
        "user_id": getattr(request.state, "user_id", None),
        "username": getattr(request.state, "username", None),
        "role": getattr(request.state, "role", None),
        "permissions": getattr(request.state, "permissions", []),
    }

    if not user_data["user_id"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    return user_data


# ==================== Authentication Endpoints ====================


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Register new user."""
    try:
        user = await auth_service.create_user(user_data)
        logger.info(f"New user registered: {user.username}")
        return user
    except ValueError as e:
        logger.warning(f"Registration failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/login", response_model=TokenResponse)
async def login(
    login_data: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Login user and return JWT tokens."""
    user = await auth_service.authenticate_user(login_data)

    if not user:
        logger.warning(f"Failed login attempt for user: {login_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Create tokens
    access_token, expires_in = auth_service.create_access_token(
        user_id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
    )

    refresh_token = auth_service.create_refresh_token(user_id=user.id)

    logger.info(f"User logged in: {user.username}")

    return TokenResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=expires_in,
        refresh_token=refresh_token,
        user=user,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    refresh_data: RefreshTokenRequest,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Refresh access token using refresh token."""
    payload = auth_service.verify_token(refresh_data.refresh_token)

    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    # Get user to update tokens
    user = await auth_service.get_user(payload.sub)

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # Create new access token
    access_token, expires_in = auth_service.create_access_token(
        user_id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
    )

    # Create new refresh token
    new_refresh_token = auth_service.create_refresh_token(user_id=user.id)

    return TokenResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=expires_in,
        refresh_token=new_refresh_token,
        user=user,
    )


@router.post("/change-password", response_model=dict)
async def change_password(
    password_data: ChangePasswordRequest,
    auth_service: AuthService = Depends(get_auth_service),
    current_user: dict = Depends(get_current_user),
):
    """Change user password."""
    user_id = current_user["user_id"]

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).filter(User.id == user_id))
        db_user = result.scalars().first()

        if not db_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        # Verify old password
        if not auth_service.verify_password(password_data.old_password, db_user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect password",
            )

        # Update password
        new_hash = auth_service.hash_password(password_data.new_password)
        db_user.password_hash = new_hash
        session.add(db_user)
        await session.commit()

        logger.info(f"User {db_user.username} changed password")

        return {"message": "Password changed successfully"}


# ==================== User Management Endpoints ====================


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    auth_service: AuthService = Depends(get_auth_service),
    current_user: dict = Depends(get_current_user),
):
    """Get current user information."""
    user = await auth_service.get_user(current_user["user_id"])

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return user


@router.get("/users", response_model=List[UserResponse])
async def list_users(
    auth_service: AuthService = Depends(get_auth_service),
    current_user: dict = Depends(get_current_user),
):
    """List all users (admin only)."""
    # Check permission
    if not any(p == PermissionEnum.USERS_MANAGE for p in current_user.get("permissions", [])):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied",
        )

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).order_by(User.created_at.desc()))
        db_users = result.scalars().all()

        users = []
        for db_user in db_users:
            permissions = [p.value for p in ROLE_PERMISSIONS.get(RoleEnum(db_user.role), [])]
            users.append(
                UserResponse(
                    id=db_user.id,
                    username=db_user.username,
                    email=db_user.email,
                    full_name=db_user.full_name,
                    is_active=db_user.is_active,
                    role=RoleEnum(db_user.role),
                    created_at=db_user.created_at,
                    updated_at=db_user.updated_at,
                    last_login=db_user.last_login,
                    permissions=permissions,
                )
            )

        return users


# ==================== API Key Management ====================


@router.post("/api-keys", response_model=APIKeyResponse)
async def create_api_key(
    key_data: APIKeyCreate,
    auth_service: AuthService = Depends(get_auth_service),
    current_user: dict = Depends(get_current_user),
):
    """Create new API key for authenticated user."""
    api_key = await auth_service.create_api_key(
        user_id=current_user["user_id"],
        key_data=key_data,
    )

    logger.info(f"API key created for user {current_user['username']}: {key_data.name}")
    return api_key


@router.get("/api-keys", response_model=List[APIKeyListResponse])
async def list_api_keys(
    auth_service: AuthService = Depends(get_auth_service),
    current_user: dict = Depends(get_current_user),
):
    """List API keys for authenticated user (without actual keys)."""
    keys = await auth_service.list_api_keys(current_user["user_id"])
    return keys


@router.delete("/api-keys/{key_id}")
async def delete_api_key(
    key_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete API key."""
    async with AsyncSessionLocal() as session:
        from sqlalchemy import delete
        from app.adapters.postgres import APIKey

        result = await session.execute(
            select(APIKey).filter(
                (APIKey.id == key_id) & (APIKey.user_id == current_user["user_id"])
            )
        )
        db_key = result.scalars().first()

        if not db_key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found",
            )

        await session.delete(db_key)
        await session.commit()

        logger.info(f"API key deleted for user {current_user['username']}: {db_key.name}")

        return {"message": "API key deleted"}


# ==================== Role Management ====================


@router.get("/roles", response_model=List[RoleInfo])
async def list_roles():
    """List all available roles and their permissions."""
    roles = []

    for role_enum, permissions in ROLE_PERMISSIONS.items():
        roles.append(
            RoleInfo(
                name=role_enum,
                description=RoleEnum.get_description(role_enum.value),
                permissions=permissions,
            )
        )

    return roles


# ==================== Health Check ====================


@router.get("/health", response_model=HealthCheckAuth)
async def auth_health_check():
    """Check authentication system health."""
    return HealthCheckAuth(
        status="healthy",
        jwt_enabled=True,
        token_expiry=AuthService.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        max_refresh_count=5,
    )
