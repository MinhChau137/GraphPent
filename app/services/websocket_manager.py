"""WebSocket connection manager for handling real-time updates."""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Set, List, Optional, Callable, Any
from uuid import uuid4

from fastapi import WebSocket, WebSocketDisconnect
import redis.asyncio as redis

from app.domain.schemas.websocket import (
    ServerMessage,
    ClientMessage,
    WebSocketMessageTypeEnum,
    WebSocketErrorEnum,
    JobProgressData,
    JobStatusData,
    JobResultData,
    ErrorData,
    QueueMetricsData,
)

logger = logging.getLogger(__name__)


class WebSocketConnectionManager:
    """Manages WebSocket connections and message broadcasting."""

    def __init__(self, redis_url: str = "redis://localhost:6379/2"):
        """
        Initialize WebSocket connection manager.
        
        Args:
            redis_url: Redis URL for pub/sub and persistence
        """
        self.redis_url = redis_url
        self.redis_client: Optional[redis.Redis] = None
        
        # In-memory connection tracking
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_info: Dict[str, Dict[str, Any]] = {}
        self.job_subscriptions: Dict[str, Set[str]] = {}  # job_id -> connection_ids
        self.connection_jobs: Dict[str, Set[str]] = {}  # connection_id -> job_ids

    async def connect(
        self,
        websocket: WebSocket,
        client_ip: Optional[str] = None,
    ) -> str:
        """
        Accept WebSocket connection.
        
        Args:
            websocket: WebSocket connection
            client_ip: Client IP address
            
        Returns:
            Connection ID
        """
        await websocket.accept()
        connection_id = str(uuid4())
        
        # Store connection
        self.active_connections[connection_id] = websocket
        self.connection_info[connection_id] = {
            "client_ip": client_ip,
            "connected_at": datetime.utcnow(),
            "subscribed_jobs": [],
        }
        self.connection_jobs[connection_id] = set()
        
        logger.info(f"WebSocket connected: {connection_id} from {client_ip}")
        
        # Send connected message
        await self._send_to_connection(
            connection_id,
            ServerMessage(
                message_type=WebSocketMessageTypeEnum.CONNECTED,
                data={"connection_id": connection_id},
            ),
        )
        
        return connection_id

    async def disconnect(self, connection_id: str):
        """
        Close WebSocket connection.
        
        Args:
            connection_id: Connection ID to close
        """
        # Unsubscribe from all jobs
        subscribed_jobs = list(self.connection_jobs.get(connection_id, set()))
        for job_id in subscribed_jobs:
            await self.unsubscribe_from_job(connection_id, job_id)
        
        # Remove connection
        self.active_connections.pop(connection_id, None)
        self.connection_info.pop(connection_id, None)
        self.connection_jobs.pop(connection_id, None)
        
        logger.info(f"WebSocket disconnected: {connection_id}")

    async def subscribe_to_job(
        self,
        connection_id: str,
        job_id: str,
    ) -> bool:
        """
        Subscribe connection to job updates.
        
        Args:
            connection_id: Connection ID
            job_id: Job ID to subscribe to
            
        Returns:
            True if successful
        """
        try:
            # Add to tracking
            if job_id not in self.job_subscriptions:
                self.job_subscriptions[job_id] = set()
            
            self.job_subscriptions[job_id].add(connection_id)
            
            if connection_id not in self.connection_jobs:
                self.connection_jobs[connection_id] = set()
            
            self.connection_jobs[connection_id].add(job_id)
            
            # Update connection info
            if connection_id in self.connection_info:
                jobs = self.connection_info[connection_id].get("subscribed_jobs", [])
                if job_id not in jobs:
                    jobs.append(job_id)
                    self.connection_info[connection_id]["subscribed_jobs"] = jobs
            
            logger.info(f"Connection {connection_id} subscribed to job {job_id}")
            
            # Send subscription confirmation
            await self._send_to_connection(
                connection_id,
                ServerMessage(
                    message_type=WebSocketMessageTypeEnum.SUBSCRIBED,
                    job_id=job_id,
                    data={"message": f"Subscribed to job {job_id}"},
                ),
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Subscription failed: {str(e)}")
            await self._send_error(
                connection_id,
                WebSocketErrorEnum.SUBSCRIPTION_FAILED,
                f"Failed to subscribe: {str(e)}",
                job_id,
            )
            return False

    async def unsubscribe_from_job(
        self,
        connection_id: str,
        job_id: str,
    ) -> bool:
        """
        Unsubscribe connection from job updates.
        
        Args:
            connection_id: Connection ID
            job_id: Job ID to unsubscribe from
            
        Returns:
            True if successful
        """
        try:
            # Remove from tracking
            if job_id in self.job_subscriptions:
                self.job_subscriptions[job_id].discard(connection_id)
                if not self.job_subscriptions[job_id]:
                    del self.job_subscriptions[job_id]
            
            if connection_id in self.connection_jobs:
                self.connection_jobs[connection_id].discard(job_id)
            
            # Update connection info
            if connection_id in self.connection_info:
                jobs = self.connection_info[connection_id].get("subscribed_jobs", [])
                self.connection_info[connection_id]["subscribed_jobs"] = [
                    j for j in jobs if j != job_id
                ]
            
            logger.info(f"Connection {connection_id} unsubscribed from job {job_id}")
            
            # Send unsubscription confirmation
            await self._send_to_connection(
                connection_id,
                ServerMessage(
                    message_type=WebSocketMessageTypeEnum.UNSUBSCRIBED,
                    job_id=job_id,
                    data={"message": f"Unsubscribed from job {job_id}"},
                ),
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Unsubscription failed: {str(e)}")
            await self._send_error(
                connection_id,
                WebSocketErrorEnum.UNSUBSCRIPTION_FAILED,
                f"Failed to unsubscribe: {str(e)}",
                job_id,
            )
            return False

    async def broadcast_progress_update(
        self,
        job_id: str,
        progress_data: JobProgressData,
    ):
        """
        Broadcast job progress update to all subscribed connections.
        
        Args:
            job_id: Job ID
            progress_data: Progress data
        """
        if job_id not in self.job_subscriptions:
            return
        
        message = ServerMessage(
            message_type=WebSocketMessageTypeEnum.PROGRESS_UPDATE,
            job_id=job_id,
            data=progress_data.model_dump(),
        )
        
        # Send to all subscribed connections
        for connection_id in self.job_subscriptions[job_id]:
            await self._send_to_connection(connection_id, message)

    async def broadcast_status_update(
        self,
        job_id: str,
        status_data: JobStatusData,
    ):
        """
        Broadcast job status change to all subscribed connections.
        
        Args:
            job_id: Job ID
            status_data: Status data
        """
        if job_id not in self.job_subscriptions:
            return
        
        message = ServerMessage(
            message_type=WebSocketMessageTypeEnum.STATUS_UPDATE,
            job_id=job_id,
            data=status_data.model_dump(),
        )
        
        for connection_id in self.job_subscriptions[job_id]:
            await self._send_to_connection(connection_id, message)

    async def broadcast_result_ready(
        self,
        job_id: str,
        result_data: JobResultData,
    ):
        """
        Broadcast job completion to all subscribed connections.
        
        Args:
            job_id: Job ID
            result_data: Result data
        """
        if job_id not in self.job_subscriptions:
            return
        
        message = ServerMessage(
            message_type=WebSocketMessageTypeEnum.RESULT_READY,
            job_id=job_id,
            data=result_data.model_dump(),
        )
        
        for connection_id in self.job_subscriptions[job_id]:
            await self._send_to_connection(connection_id, message)
            # Automatically unsubscribe after result
            await self.unsubscribe_from_job(connection_id, job_id)

    async def broadcast_metrics_update(
        self,
        metrics_data: QueueMetricsData,
    ):
        """
        Broadcast queue metrics to all connections.
        
        Args:
            metrics_data: Metrics data
        """
        message = ServerMessage(
            message_type=WebSocketMessageTypeEnum.METRICS_UPDATE,
            data=metrics_data.model_dump(),
        )
        
        for connection_id in list(self.active_connections.keys()):
            await self._send_to_connection(connection_id, message)

    async def _send_to_connection(
        self,
        connection_id: str,
        message: ServerMessage,
    ):
        """
        Send message to specific connection.
        
        Args:
            connection_id: Connection ID
            message: Message to send
        """
        if connection_id not in self.active_connections:
            return
        
        try:
            websocket = self.active_connections[connection_id]
            await websocket.send_json(message.model_dump())
            
            # Update last activity
            if connection_id in self.connection_info:
                self.connection_info[connection_id]["last_activity"] = datetime.utcnow()
                
        except Exception as e:
            logger.error(
                f"Failed to send to {connection_id}: {str(e)}"
            )
            # Connection might be dead, disconnect it
            await self.disconnect(connection_id)

    async def _send_error(
        self,
        connection_id: str,
        error_type: WebSocketErrorEnum,
        error_message: str,
        job_id: Optional[str] = None,
    ):
        """
        Send error message to connection.
        
        Args:
            connection_id: Connection ID
            error_type: Error type
            error_message: Error message
            job_id: Associated job ID (optional)
        """
        error = ErrorData(
            error_type=error_type,
            error_message=error_message,
            job_id=job_id,
        )
        
        message = ServerMessage(
            message_type=WebSocketMessageTypeEnum.ERROR,
            job_id=job_id,
            data=error.model_dump(),
        )
        
        await self._send_to_connection(connection_id, message)

    async def handle_client_message(
        self,
        connection_id: str,
        message_data: Dict[str, Any],
    ) -> bool:
        """
        Handle client message.
        
        Args:
            connection_id: Connection ID
            message_data: Message data
            
        Returns:
            True if handled successfully
        """
        try:
            message = ClientMessage(**message_data)
            
            if message.message_type == WebSocketMessageTypeEnum.SUBSCRIBE:
                if not message.job_id:
                    await self._send_error(
                        connection_id,
                        WebSocketErrorEnum.INVALID_MESSAGE,
                        "job_id required for subscribe",
                    )
                    return False
                
                return await self.subscribe_to_job(connection_id, message.job_id)
            
            elif message.message_type == WebSocketMessageTypeEnum.UNSUBSCRIBE:
                if not message.job_id:
                    await self._send_error(
                        connection_id,
                        WebSocketErrorEnum.INVALID_MESSAGE,
                        "job_id required for unsubscribe",
                    )
                    return False
                
                return await self.unsubscribe_from_job(connection_id, message.job_id)
            
            elif message.message_type == WebSocketMessageTypeEnum.PING:
                await self._send_to_connection(
                    connection_id,
                    ServerMessage(message_type=WebSocketMessageTypeEnum.PONG),
                )
                return True
            
            else:
                await self._send_error(
                    connection_id,
                    WebSocketErrorEnum.INVALID_MESSAGE,
                    f"Unknown message type: {message.message_type}",
                )
                return False
                
        except Exception as e:
            logger.error(f"Error handling message: {str(e)}")
            await self._send_error(
                connection_id,
                WebSocketErrorEnum.INVALID_MESSAGE,
                f"Invalid message: {str(e)}",
            )
            return False

    def get_connection_info(self, connection_id: str) -> Optional[Dict[str, Any]]:
        """Get connection information."""
        return self.connection_info.get(connection_id)

    def get_all_connections_count(self) -> int:
        """Get count of active connections."""
        return len(self.active_connections)

    def get_subscribed_connections_for_job(self, job_id: str) -> Set[str]:
        """Get all connections subscribed to a job."""
        return self.job_subscriptions.get(job_id, set())


# Singleton instance
_ws_manager_instance: Optional[WebSocketConnectionManager] = None


async def get_ws_manager() -> WebSocketConnectionManager:
    """Get or create WebSocket manager singleton."""
    global _ws_manager_instance
    if _ws_manager_instance is None:
        _ws_manager_instance = WebSocketConnectionManager()
    return _ws_manager_instance
