"""WebSocket message models and schemas for real-time updates."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class WebSocketMessageTypeEnum(str, Enum):
    """WebSocket message types."""

    # Client messages
    CONNECT = "connect"
    DISCONNECT = "disconnect"
    SUBSCRIBE = "subscribe"  # Subscribe to job updates
    UNSUBSCRIBE = "unsubscribe"  # Unsubscribe from job updates
    PING = "ping"  # Keep-alive

    # Server messages
    PONG = "pong"
    STATUS_UPDATE = "status_update"  # Job status changed
    PROGRESS_UPDATE = "progress_update"  # Job progress changed
    RESULT_READY = "result_ready"  # Job completed
    ERROR = "error"  # Error occurred
    CONNECTED = "connected"  # Client connected
    SUBSCRIBED = "subscribed"  # Subscribed to job
    UNSUBSCRIBED = "unsubscribed"  # Unsubscribed from job
    METRICS_UPDATE = "metrics_update"  # Queue metrics updated


class WebSocketErrorEnum(str, Enum):
    """WebSocket error types."""

    INVALID_JOB_ID = "invalid_job_id"
    JOB_NOT_FOUND = "job_not_found"
    SUBSCRIPTION_FAILED = "subscription_failed"
    UNSUBSCRIPTION_FAILED = "unsubscription_failed"
    INVALID_MESSAGE = "invalid_message"
    SERVER_ERROR = "server_error"


class ClientMessage(BaseModel):
    """Message from client to server."""

    message_type: WebSocketMessageTypeEnum = Field(..., description="Message type")
    job_id: Optional[str] = Field(
        default=None,
        description="Job ID for subscription/unsubscription",
    )
    data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional message data",
    )

    class Config:
        schema_extra = {
            "examples": [
                {
                    "message_type": "connect",
                    "data": {"client_id": "client-123"},
                },
                {
                    "message_type": "subscribe",
                    "job_id": "job-uuid",
                },
                {
                    "message_type": "ping",
                },
            ]
        }


class JobProgressData(BaseModel):
    """Job progress information."""

    job_id: str
    status: str
    progress: Optional[int] = Field(
        default=None,
        ge=0,
        le=100,
        description="Progress percentage",
    )
    current_task: Optional[str] = Field(
        default=None,
        description="Current task description",
    )
    estimated_remaining_seconds: Optional[int] = Field(
        default=None,
        description="Estimated seconds until completion",
    )
    processed_items: Optional[int] = None
    total_items: Optional[int] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        schema_extra = {
            "example": {
                "job_id": "job-uuid",
                "status": "running",
                "progress": 65,
                "current_task": "Processing findings...",
                "estimated_remaining_seconds": 120,
                "processed_items": 13,
                "total_items": 20,
                "timestamp": "2026-04-29T10:05:00Z",
            }
        }


class JobStatusData(BaseModel):
    """Job status change information."""

    job_id: str
    previous_status: str
    current_status: str
    error_message: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        schema_extra = {
            "example": {
                "job_id": "job-uuid",
                "previous_status": "running",
                "current_status": "completed",
                "timestamp": "2026-04-29T10:15:00Z",
            }
        }


class JobResultData(BaseModel):
    """Job result information."""

    job_id: str
    target_url: str
    findings_count: int
    severity_breakdown: Dict[str, int] = Field(
        default_factory=dict,
        description="Count by severity",
    )
    neo4j_status: str
    neo4j_count: Optional[int] = None
    completion_time_seconds: Optional[float] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        schema_extra = {
            "example": {
                "job_id": "job-uuid",
                "target_url": "http://localhost:3000",
                "findings_count": 24,
                "severity_breakdown": {
                    "CRITICAL": 2,
                    "HIGH": 5,
                    "MEDIUM": 12,
                    "LOW": 5,
                    "INFO": 0,
                },
                "neo4j_status": "upserted",
                "neo4j_count": 24,
                "completion_time_seconds": 125.5,
                "timestamp": "2026-04-29T10:15:00Z",
            }
        }


class ErrorData(BaseModel):
    """Error information."""

    error_type: WebSocketErrorEnum
    error_message: str
    job_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        schema_extra = {
            "example": {
                "error_type": "job_not_found",
                "error_message": "Job uuid-123 not found",
                "job_id": "uuid-123",
                "timestamp": "2026-04-29T10:05:00Z",
            }
        }


class QueueMetricsData(BaseModel):
    """Queue metrics snapshot."""

    total_jobs: int
    pending_jobs: int
    running_jobs: int
    completed_jobs: int
    failed_jobs: int
    success_rate: Optional[float] = None
    average_completion_time_seconds: Optional[float] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        schema_extra = {
            "example": {
                "total_jobs": 1500,
                "pending_jobs": 45,
                "running_jobs": 12,
                "completed_jobs": 1380,
                "failed_jobs": 53,
                "success_rate": 92.3,
                "average_completion_time_seconds": 125.5,
                "timestamp": "2026-04-29T10:05:00Z",
            }
        }


class ServerMessage(BaseModel):
    """Message from server to client."""

    message_type: WebSocketMessageTypeEnum = Field(..., description="Message type")
    job_id: Optional[str] = Field(default=None, description="Associated job ID")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Message data")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        schema_extra = {
            "examples": [
                {
                    "message_type": "connected",
                    "data": {"connection_id": "conn-123"},
                    "timestamp": "2026-04-29T10:00:00Z",
                },
                {
                    "message_type": "subscribed",
                    "job_id": "job-uuid",
                    "data": {"message": "Subscribed to job updates"},
                    "timestamp": "2026-04-29T10:00:00Z",
                },
                {
                    "message_type": "progress_update",
                    "job_id": "job-uuid",
                    "data": {
                        "status": "running",
                        "progress": 65,
                        "current_task": "Processing findings...",
                    },
                    "timestamp": "2026-04-29T10:05:00Z",
                },
                {
                    "message_type": "result_ready",
                    "job_id": "job-uuid",
                    "data": {
                        "findings_count": 24,
                        "neo4j_status": "upserted",
                    },
                    "timestamp": "2026-04-29T10:15:00Z",
                },
            ]
        }


class ConnectionInfo(BaseModel):
    """Information about a WebSocket connection."""

    connection_id: str
    client_ip: Optional[str] = None
    connected_at: datetime
    subscribed_jobs: List[str] = Field(default_factory=list)
    last_activity: datetime

    class Config:
        schema_extra = {
            "example": {
                "connection_id": "conn-123",
                "client_ip": "192.168.1.100",
                "connected_at": "2026-04-29T10:00:00Z",
                "subscribed_jobs": ["job-uuid-1", "job-uuid-2"],
                "last_activity": "2026-04-29T10:05:00Z",
            }
        }
