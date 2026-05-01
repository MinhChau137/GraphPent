"""Authentication and Authorization schemas (Phase 5.4)."""

from typing import Optional, List
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, EmailStr, field_validator


class RoleEnum(str, Enum):
    """User roles for RBAC."""
    
    ADMIN = "admin"
    ANALYST = "analyst"
    OPERATOR = "operator"
    VIEWER = "viewer"
    
    @classmethod
    def get_description(cls, role: str) -> str:
        """Get role description."""
        descriptions = {
            "admin": "Full access - manage users, settings, all scans",
            "analyst": "Perform scans, view results, manage own jobs",
            "operator": "Submit and monitor scans only",
            "viewer": "View-only access to results",
        }
        return descriptions.get(role, "Unknown role")


class PermissionEnum(str, Enum):
    """API permissions for endpoints."""
    
    # Job management
    JOBS_CREATE = "jobs:create"
    JOBS_READ = "jobs:read"
    JOBS_UPDATE = "jobs:update"
    JOBS_DELETE = "jobs:delete"
    JOBS_BATCH = "jobs:batch"
    
    # Results/findings
    RESULTS_READ = "results:read"
    RESULTS_EXPORT = "results:export"
    RESULTS_IMPORT = "results:import"
    
    # Search
    SEARCH_BASIC = "search:basic"
    SEARCH_ADVANCED = "search:advanced"
    
    # User management
    USERS_MANAGE = "users:manage"
    USERS_READ = "users:read"
    
    # Settings
    SETTINGS_READ = "settings:read"
    SETTINGS_WRITE = "settings:write"


# Define role-permission mappings
ROLE_PERMISSIONS = {
    RoleEnum.ADMIN: [
        PermissionEnum.JOBS_CREATE,
        PermissionEnum.JOBS_READ,
        PermissionEnum.JOBS_UPDATE,
        PermissionEnum.JOBS_DELETE,
        PermissionEnum.JOBS_BATCH,
        PermissionEnum.RESULTS_READ,
        PermissionEnum.RESULTS_EXPORT,
        PermissionEnum.RESULTS_IMPORT,
        PermissionEnum.SEARCH_BASIC,
        PermissionEnum.SEARCH_ADVANCED,
        PermissionEnum.USERS_MANAGE,
        PermissionEnum.USERS_READ,
        PermissionEnum.SETTINGS_READ,
        PermissionEnum.SETTINGS_WRITE,
    ],
    RoleEnum.ANALYST: [
        PermissionEnum.JOBS_CREATE,
        PermissionEnum.JOBS_READ,
        PermissionEnum.JOBS_UPDATE,
        PermissionEnum.JOBS_DELETE,
        PermissionEnum.JOBS_BATCH,
        PermissionEnum.RESULTS_READ,
        PermissionEnum.RESULTS_EXPORT,
        PermissionEnum.SEARCH_BASIC,
        PermissionEnum.SEARCH_ADVANCED,
        PermissionEnum.USERS_READ,
        PermissionEnum.SETTINGS_READ,
    ],
    RoleEnum.OPERATOR: [
        PermissionEnum.JOBS_CREATE,
        PermissionEnum.JOBS_READ,
        PermissionEnum.JOBS_BATCH,
        PermissionEnum.RESULTS_READ,
        PermissionEnum.SEARCH_BASIC,
    ],
    RoleEnum.VIEWER: [
        PermissionEnum.JOBS_READ,
        PermissionEnum.RESULTS_READ,
        PermissionEnum.SEARCH_BASIC,
    ],
}


class UserBase(BaseModel):
    """Base user model."""
    
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    full_name: Optional[str] = Field(None, max_length=100)
    is_active: bool = True
    role: RoleEnum = RoleEnum.VIEWER


class UserCreate(UserBase):
    """User creation request."""
    
    password: str = Field(..., min_length=8, max_length=100)
    
    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        """Validate password strength."""
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        if not any(c in "!@#$%^&*" for c in v):
            raise ValueError("Password must contain at least one special character (!@#$%^&*)")
        return v


class UserUpdate(BaseModel):
    """User update request."""
    
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    role: Optional[RoleEnum] = None
    is_active: Optional[bool] = None


class UserResponse(UserBase):
    """User response model."""
    
    id: str = Field(..., description="User UUID")
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None
    permissions: List[str] = Field(default_factory=list, description="Calculated permissions based on role")
    
    class Config:
        from_attributes = True


class TokenPayload(BaseModel):
    """JWT token payload."""
    
    sub: str = Field(..., description="User ID (subject)")
    username: str
    email: str
    role: RoleEnum
    permissions: List[str]
    exp: int = Field(..., description="Expiration timestamp")
    iat: int = Field(..., description="Issued at timestamp")


class TokenResponse(BaseModel):
    """Token response."""
    
    access_token: str
    token_type: str = "Bearer"
    expires_in: int = Field(..., description="Seconds until expiration")
    refresh_token: Optional[str] = None
    user: UserResponse


class LoginRequest(BaseModel):
    """Login request."""
    
    username: str = Field(..., min_length=3)
    password: str = Field(..., min_length=8)


class RefreshTokenRequest(BaseModel):
    """Refresh token request."""
    
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    """Change password request."""
    
    old_password: str
    new_password: str
    
    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v):
        """Validate password strength."""
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class APIKeyCreate(BaseModel):
    """API key creation request."""
    
    name: str = Field(..., min_length=3, max_length=100)
    expiry_days: Optional[int] = Field(None, gt=0, le=365, description="Days until expiration")
    permissions: List[PermissionEnum] = Field(default_factory=list)


class APIKeyResponse(BaseModel):
    """API key response."""
    
    id: str
    name: str
    key: str = Field(..., description="Actual key shown only on creation")
    masked_key: str = Field(..., description="Key with first/last chars only for viewing")
    created_at: datetime
    expires_at: Optional[datetime] = None
    is_active: bool
    last_used: Optional[datetime] = None
    permissions: List[PermissionEnum]
    
    class Config:
        from_attributes = True


class APIKeyListResponse(BaseModel):
    """API key list response (no actual key)."""
    
    id: str
    name: str
    masked_key: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    is_active: bool
    last_used: Optional[datetime] = None
    permissions: List[PermissionEnum]


class AuditLogEntry(BaseModel):
    """Audit log entry."""
    
    id: str
    user_id: str
    username: str
    action: str = Field(..., description="Action performed (login, create_job, export_results, etc)")
    resource: Optional[str] = Field(None, description="Resource affected (job_id, user_id, etc)")
    status: str = Field(..., description="success or failure")
    details: Optional[dict] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    timestamp: datetime
    
    class Config:
        from_attributes = True


class AuthErrorResponse(BaseModel):
    """Authentication error response."""
    
    error: str
    message: str
    status_code: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class RoleInfo(BaseModel):
    """Role information."""
    
    name: RoleEnum
    description: str
    permissions: List[PermissionEnum]
    user_count: int = 0


class HealthCheckAuth(BaseModel):
    """Auth system health check."""
    
    status: str = "healthy"
    jwt_enabled: bool = True
    token_expiry: int = Field(..., description="Token lifetime in seconds")
    max_refresh_count: int = 5
