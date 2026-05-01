"""Authentication & Authorization service (Phase 5.4)."""

import logging
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
from functools import lru_cache

import jwt
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from passlib.context import CryptContext

from app.adapters.postgres import AsyncSessionLocal, User, APIKey, AuditLog
from app.domain.schemas.auth import (
    UserCreate,
    UserUpdate,
    UserResponse,
    TokenPayload,
    TokenResponse,
    LoginRequest,
    APIKeyCreate,
    APIKeyResponse,
    APIKeyListResponse,
    RoleEnum,
    ROLE_PERMISSIONS,
    PermissionEnum,
    AuditLogEntry,
)
from app.config.settings import settings

logger = logging.getLogger(__name__)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """Authentication & Authorization service."""

    # JWT Configuration
    SECRET_KEY = settings.JWT_SECRET_KEY if hasattr(settings, 'JWT_SECRET_KEY') else "dev-secret-key-change-in-production"
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = 60
    REFRESH_TOKEN_EXPIRE_DAYS = 7

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password using bcrypt."""
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify password against hash."""
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def hash_api_key(api_key: str) -> str:
        """Hash API key using SHA-256."""
        return hashlib.sha256(api_key.encode()).hexdigest()

    @staticmethod
    def generate_api_key() -> str:
        """Generate a secure random API key."""
        return secrets.token_urlsafe(32)

    @classmethod
    def create_access_token(
        cls,
        user_id: str,
        username: str,
        email: str,
        role: RoleEnum,
        expires_delta: Optional[timedelta] = None,
    ) -> Tuple[str, int]:
        """Create JWT access token.
        
        Returns:
            Tuple of (token, expiration_seconds)
        """
        if expires_delta is None:
            expires_delta = timedelta(minutes=cls.ACCESS_TOKEN_EXPIRE_MINUTES)

        # Get permissions for role
        permissions = [p.value for p in ROLE_PERMISSIONS.get(role, [])]

        expire = datetime.utcnow() + expires_delta
        now = datetime.utcnow()

        payload = {
            "sub": user_id,
            "username": username,
            "email": email,
            "role": role.value,
            "permissions": permissions,
            "exp": int(expire.timestamp()),
            "iat": int(now.timestamp()),
        }

        encoded_jwt = jwt.encode(payload, cls.SECRET_KEY, algorithm=cls.ALGORITHM)
        return encoded_jwt, int(expires_delta.total_seconds())

    @classmethod
    def create_refresh_token(
        cls,
        user_id: str,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """Create JWT refresh token."""
        if expires_delta is None:
            expires_delta = timedelta(days=cls.REFRESH_TOKEN_EXPIRE_DAYS)

        expire = datetime.utcnow() + expires_delta

        payload = {
            "sub": user_id,
            "type": "refresh",
            "exp": int(expire.timestamp()),
        }

        encoded_jwt = jwt.encode(payload, cls.SECRET_KEY, algorithm=cls.ALGORITHM)
        return encoded_jwt

    @classmethod
    def verify_token(cls, token: str) -> Optional[TokenPayload]:
        """Verify JWT token and return payload.
        
        Returns:
            TokenPayload if valid, None if invalid
        """
        try:
            payload = jwt.decode(token, cls.SECRET_KEY, algorithms=[cls.ALGORITHM])
            return TokenPayload(**payload)
        except jwt.ExpiredSignatureError:
            logger.warning(f"Token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None

    @classmethod
    def verify_api_key(cls, api_key: str) -> Optional[Dict]:
        """Verify API key (to be called from sync context).
        
        Returns dict with user_id, permissions, or None if invalid
        """
        # This should be called from async context via wrapper
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(cls._verify_api_key_async(api_key))

    @staticmethod
    async def _verify_api_key_async(api_key: str) -> Optional[Dict]:
        """Async API key verification."""
        key_hash = AuthService.hash_api_key(api_key)

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(APIKey)
                .filter(APIKey.key_hash == key_hash)
                .filter(APIKey.is_active == True)
            )
            db_key = result.scalars().first()

            if not db_key:
                return None

            # Check expiration
            if db_key.expires_at and db_key.expires_at < datetime.utcnow():
                return None

            # Update last_used
            await session.execute(
                update(APIKey)
                .where(APIKey.id == db_key.id)
                .values(last_used=datetime.utcnow())
            )
            await session.commit()

            return {
                "user_id": db_key.user_id,
                "permissions": db_key.permissions,
                "api_key_id": db_key.id,
            }

    async def create_user(self, user_data: UserCreate) -> UserResponse:
        """Create new user."""
        async with AsyncSessionLocal() as session:
            # Check if user exists
            result = await session.execute(
                select(User).filter(
                    (User.username == user_data.username) | (User.email == user_data.email)
                )
            )
            if result.scalars().first():
                raise ValueError("User already exists")

            # Hash password
            password_hash = self.hash_password(user_data.password)

            # Create user
            db_user = User(
                username=user_data.username,
                email=user_data.email,
                full_name=user_data.full_name,
                password_hash=password_hash,
                role=user_data.role.value,
            )

            session.add(db_user)
            await session.commit()
            await session.refresh(db_user)

            # Log action
            await self._audit_log(
                session=session,
                user_id=db_user.id,
                action="user_created",
                resource=f"user:{db_user.id}",
            )

            permissions = [p.value for p in ROLE_PERMISSIONS.get(RoleEnum(db_user.role), [])]

            return UserResponse(
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

    async def get_user(self, user_id: str) -> Optional[UserResponse]:
        """Get user by ID."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User).filter(User.id == user_id))
            db_user = result.scalars().first()

            if not db_user:
                return None

            permissions = [p.value for p in ROLE_PERMISSIONS.get(RoleEnum(db_user.role), [])]

            return UserResponse(
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

    async def authenticate_user(self, login_data: LoginRequest) -> Optional[UserResponse]:
        """Authenticate user and return user data if successful."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(User).filter(User.username == login_data.username)
            )
            db_user = result.scalars().first()

            if not db_user or not self.verify_password(login_data.password, db_user.password_hash):
                return None

            if not db_user.is_active:
                return None

            # Update last_login
            await session.execute(
                update(User)
                .where(User.id == db_user.id)
                .values(last_login=datetime.utcnow())
            )
            await session.commit()
            await session.refresh(db_user)

            # Log login
            await self._audit_log(
                session=session,
                user_id=db_user.id,
                action="login",
                status="success",
            )

            permissions = [p.value for p in ROLE_PERMISSIONS.get(RoleEnum(db_user.role), [])]

            return UserResponse(
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

    async def create_api_key(
        self,
        user_id: str,
        key_data: APIKeyCreate,
    ) -> APIKeyResponse:
        """Create new API key for user."""
        async with AsyncSessionLocal() as session:
            # Verify user exists
            result = await session.execute(select(User).filter(User.id == user_id))
            if not result.scalars().first():
                raise ValueError("User not found")

            # Generate API key
            api_key = self.generate_api_key()
            key_hash = self.hash_api_key(api_key)

            # Determine expiration
            expires_at = None
            if key_data.expiry_days:
                expires_at = datetime.utcnow() + timedelta(days=key_data.expiry_days)

            # Create API key record
            db_key = APIKey(
                user_id=user_id,
                name=key_data.name,
                key_hash=key_hash,
                permissions=[p.value for p in key_data.permissions],
                expires_at=expires_at,
            )

            session.add(db_key)
            await session.commit()
            await session.refresh(db_key)

            # Mask key for display (show first and last 4 chars)
            masked_key = f"{api_key[:4]}...{api_key[-4:]}"

            return APIKeyResponse(
                id=db_key.id,
                name=db_key.name,
                key=api_key,  # Only shown on creation
                masked_key=masked_key,
                created_at=db_key.created_at,
                expires_at=db_key.expires_at,
                is_active=db_key.is_active,
                last_used=db_key.last_used,
                permissions=[PermissionEnum(p) for p in db_key.permissions],
            )

    async def list_api_keys(self, user_id: str) -> List[APIKeyListResponse]:
        """List API keys for user (without actual keys)."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(APIKey)
                .filter(APIKey.user_id == user_id)
                .order_by(APIKey.created_at.desc())
            )
            db_keys = result.scalars().all()

            return [
                APIKeyListResponse(
                    id=key.id,
                    name=key.name,
                    masked_key=f"{key.key_hash[:4]}...{key.key_hash[-4:]}",
                    created_at=key.created_at,
                    expires_at=key.expires_at,
                    is_active=key.is_active,
                    last_used=key.last_used,
                    permissions=[PermissionEnum(p) for p in key.permissions],
                )
                for key in db_keys
            ]

    async def has_permission(self, user_id: str, permission: str) -> bool:
        """Check if user has specific permission."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User).filter(User.id == user_id))
            db_user = result.scalars().first()

            if not db_user:
                return False

            permissions = ROLE_PERMISSIONS.get(RoleEnum(db_user.role), [])
            return PermissionEnum(permission) in permissions

    async def _audit_log(
        self,
        session,
        user_id: Optional[str],
        action: str,
        resource: Optional[str] = None,
        status: str = "success",
        details: Optional[dict] = None,
    ):
        """Create audit log entry."""
        try:
            log = AuditLog(
                user_id=user_id,
                action=action,
                resource=resource,
                status=status,
                details=details,
            )
            session.add(log)
            await session.commit()
        except Exception as e:
            logger.error(f"Failed to create audit log: {e}")


@lru_cache(maxsize=1)
async def get_auth_service() -> AuthService:
    """Get or create auth service singleton."""
    return AuthService()
