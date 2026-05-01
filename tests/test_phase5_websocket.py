"""Integration tests for WebSocket real-time updates (Phase 5.2)."""

import asyncio
import json
import pytest
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

from fastapi.testclient import TestClient
from httpx import AsyncClient
from websockets.client import connect as ws_connect

from app.main import app
from app.adapters.postgres import AsyncSessionLocal, JobQueue, Base, engine
from app.domain.schemas.job_queue import JobStatusEnum, JobTypeEnum
from app.domain.schemas.websocket import WebSocketMessageTypeEnum
from app.services.websocket_manager import get_ws_manager, WebSocketConnectionManager
from app.services.job_progress_tracker import get_progress_tracker


# Test fixtures
@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def db():
    """Create test database."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def ws_manager():
    """Get WebSocket manager."""
    return await get_ws_manager()


@pytest.fixture
async def progress_tracker():
    """Get progress tracker."""
    return await get_progress_tracker()


@pytest.fixture
async def sample_job(db):
    """Create sample job in database."""
    job = JobQueue(
        job_id="test-job-001",
        job_type=JobTypeEnum.SCAN.value,
        status=JobStatusEnum.PENDING.value,
        priority=5,
        target_url="https://example.com",
        payload={},
        job_metadata={},
    )
    
    async with AsyncSessionLocal() as session:
        session.add(job)
        await session.commit()
        await session.refresh(job)
    
    return job


@pytest.fixture
async def running_job(db):
    """Create running job in database."""
    job = JobQueue(
        job_id="test-job-002",
        job_type=JobTypeEnum.SCAN.value,
        status=JobStatusEnum.RUNNING.value,
        priority=5,
        target_url="https://example.com",
        payload={},
        job_metadata={"progress": 50},
        started_at=datetime.utcnow(),
    )
    
    async with AsyncSessionLocal() as session:
        session.add(job)
        await session.commit()
        await session.refresh(job)
    
    return job


@pytest.fixture
async def completed_job(db):
    """Create completed job in database."""
    job = JobQueue(
        job_id="test-job-003",
        job_type=JobTypeEnum.SCAN.value,
        status=JobStatusEnum.COMPLETED.value,
        priority=5,
        target_url="https://example.com",
        payload={},
        result={
            "findings_count": 42,
            "severity_breakdown": {
                "critical": 5,
                "high": 15,
                "medium": 22,
                "low": 0,
            },
        },
        job_metadata={"progress": 100},
        started_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
    )
    
    async with AsyncSessionLocal() as session:
        session.add(job)
        await session.commit()
        await session.refresh(job)
    
    return job


# Test Classes
class TestWebSocketConnectionManager:
    """Tests for WebSocket connection management."""

    @pytest.mark.asyncio
    async def test_manager_initialization(self, ws_manager):
        """Test WebSocket manager initializes correctly."""
        assert ws_manager is not None
        assert ws_manager.active_connections == {}
        assert ws_manager.job_subscriptions == {}
        assert ws_manager.connection_jobs == {}

    @pytest.mark.asyncio
    async def test_get_manager_singleton(self):
        """Test get_ws_manager returns singleton."""
        manager1 = await get_ws_manager()
        manager2 = await get_ws_manager()
        assert manager1 is manager2

    @pytest.mark.asyncio
    async def test_connection_info_storage(self, ws_manager):
        """Test connection info is stored correctly."""
        # Create mock WebSocket
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        
        # Connect
        connection_id = await ws_manager.connect(mock_ws, "192.168.1.1")
        
        # Verify
        assert connection_id in ws_manager.active_connections
        assert connection_id in ws_manager.connection_info
        info = ws_manager.connection_info[connection_id]
        assert info["client_ip"] == "192.168.1.1"
        assert "connected_at" in info
        assert info["subscribed_jobs"] == []

    @pytest.mark.asyncio
    async def test_disconnect_removes_connection(self, ws_manager):
        """Test disconnect removes connection."""
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        
        connection_id = await ws_manager.connect(mock_ws, "192.168.1.1")
        assert connection_id in ws_manager.active_connections
        
        await ws_manager.disconnect(connection_id)
        assert connection_id not in ws_manager.active_connections


class TestJobSubscription:
    """Tests for job subscription functionality."""

    @pytest.mark.asyncio
    async def test_subscribe_to_job(self, ws_manager):
        """Test subscribing to job updates."""
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        
        connection_id = await ws_manager.connect(mock_ws)
        
        # Subscribe to job
        result = await ws_manager.subscribe_to_job(connection_id, "job-001")
        
        assert result is True
        assert "job-001" in ws_manager.job_subscriptions
        assert connection_id in ws_manager.job_subscriptions["job-001"]
        assert "job-001" in ws_manager.connection_jobs[connection_id]

    @pytest.mark.asyncio
    async def test_unsubscribe_from_job(self, ws_manager):
        """Test unsubscribing from job."""
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        
        connection_id = await ws_manager.connect(mock_ws)
        await ws_manager.subscribe_to_job(connection_id, "job-001")
        
        # Unsubscribe
        result = await ws_manager.unsubscribe_from_job(connection_id, "job-001")
        
        assert result is True
        assert "job-001" not in ws_manager.job_subscriptions
        assert "job-001" not in ws_manager.connection_jobs[connection_id]

    @pytest.mark.asyncio
    async def test_multiple_subscriptions(self, ws_manager):
        """Test subscribing to multiple jobs."""
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        
        connection_id = await ws_manager.connect(mock_ws)
        
        # Subscribe to multiple jobs
        await ws_manager.subscribe_to_job(connection_id, "job-001")
        await ws_manager.subscribe_to_job(connection_id, "job-002")
        await ws_manager.subscribe_to_job(connection_id, "job-003")
        
        # Verify
        assert len(ws_manager.connection_jobs[connection_id]) == 3
        assert "job-001" in ws_manager.connection_jobs[connection_id]
        assert "job-002" in ws_manager.connection_jobs[connection_id]
        assert "job-003" in ws_manager.connection_jobs[connection_id]


class TestBroadcasting:
    """Tests for broadcast functionality."""

    @pytest.mark.asyncio
    async def test_broadcast_progress_update(self, ws_manager):
        """Test broadcasting progress update."""
        from app.domain.schemas.websocket import JobProgressData
        
        # Setup connections
        mock_ws1 = AsyncMock()
        mock_ws1.accept = AsyncMock()
        mock_ws1.send_json = AsyncMock()
        
        mock_ws2 = AsyncMock()
        mock_ws2.accept = AsyncMock()
        mock_ws2.send_json = AsyncMock()
        
        conn1 = await ws_manager.connect(mock_ws1)
        conn2 = await ws_manager.connect(mock_ws2)
        
        # Subscribe to job
        await ws_manager.subscribe_to_job(conn1, "job-001")
        await ws_manager.subscribe_to_job(conn2, "job-001")
        
        # Broadcast progress
        progress_data = JobProgressData(
            job_id="job-001",
            status="running",
            progress=50,
        )
        
        await ws_manager.broadcast_progress_update("job-001", progress_data)
        
        # Verify both connections received message
        assert mock_ws1.send_json.called
        assert mock_ws2.send_json.called

    @pytest.mark.asyncio
    async def test_broadcast_only_to_subscribers(self, ws_manager):
        """Test broadcast only reaches subscribers."""
        from app.domain.schemas.websocket import JobProgressData
        
        # Setup connections
        mock_ws1 = AsyncMock()
        mock_ws1.accept = AsyncMock()
        mock_ws1.send_json = AsyncMock()
        
        mock_ws2 = AsyncMock()
        mock_ws2.accept = AsyncMock()
        mock_ws2.send_json = AsyncMock()
        
        conn1 = await ws_manager.connect(mock_ws1)
        conn2 = await ws_manager.connect(mock_ws2)
        
        # Only conn1 subscribes
        await ws_manager.subscribe_to_job(conn1, "job-001")
        
        # Broadcast progress
        progress_data = JobProgressData(
            job_id="job-001",
            status="running",
            progress=50,
        )
        
        await ws_manager.broadcast_progress_update("job-001", progress_data)
        
        # Verify only subscriber received message
        assert mock_ws1.send_json.called
        assert not mock_ws2.send_json.called

    @pytest.mark.asyncio
    async def test_broadcast_status_update(self, ws_manager):
        """Test broadcasting status update."""
        from app.domain.schemas.websocket import JobStatusData
        
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        
        conn = await ws_manager.connect(mock_ws)
        await ws_manager.subscribe_to_job(conn, "job-001")
        
        # Broadcast status change
        status_data = JobStatusData(
            job_id="job-001",
            previous_status="running",
            current_status="completed",
        )
        
        await ws_manager.broadcast_status_update("job-001", status_data)
        
        assert mock_ws.send_json.called


class TestMessageHandling:
    """Tests for handling client messages."""

    @pytest.mark.asyncio
    async def test_handle_subscribe_message(self, ws_manager):
        """Test handling subscribe message from client."""
        from app.domain.schemas.websocket import ClientMessage
        
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        
        conn = await ws_manager.connect(mock_ws)
        
        # Handle subscribe message
        message_data = {
            "message_type": WebSocketMessageTypeEnum.SUBSCRIBE,
            "job_id": "job-001",
        }
        
        result = await ws_manager.handle_client_message(conn, message_data)
        
        assert result is True
        assert "job-001" in ws_manager.connection_jobs[conn]

    @pytest.mark.asyncio
    async def test_handle_unsubscribe_message(self, ws_manager):
        """Test handling unsubscribe message."""
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        
        conn = await ws_manager.connect(mock_ws)
        await ws_manager.subscribe_to_job(conn, "job-001")
        
        # Handle unsubscribe message
        message_data = {
            "message_type": WebSocketMessageTypeEnum.UNSUBSCRIBE,
            "job_id": "job-001",
        }
        
        result = await ws_manager.handle_client_message(conn, message_data)
        
        assert result is True
        assert "job-001" not in ws_manager.connection_jobs[conn]

    @pytest.mark.asyncio
    async def test_handle_ping_message(self, ws_manager):
        """Test handling ping message for keep-alive."""
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        
        conn = await ws_manager.connect(mock_ws)
        
        # Handle ping message
        message_data = {
            "message_type": WebSocketMessageTypeEnum.PING,
        }
        
        result = await ws_manager.handle_client_message(conn, message_data)
        
        assert result is True
        assert mock_ws.send_json.called

    @pytest.mark.asyncio
    async def test_handle_invalid_message(self, ws_manager):
        """Test handling invalid message."""
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        
        conn = await ws_manager.connect(mock_ws)
        
        # Handle invalid message (no job_id for subscribe)
        message_data = {
            "message_type": WebSocketMessageTypeEnum.SUBSCRIBE,
            # Missing job_id
        }
        
        result = await ws_manager.handle_client_message(conn, message_data)
        
        assert result is False
        assert mock_ws.send_json.called


class TestProgressTracker:
    """Tests for job progress tracking."""

    @pytest.mark.asyncio
    async def test_update_job_progress(self, progress_tracker, db, running_job):
        """Test updating job progress."""
        with patch.object(progress_tracker, 'job_progress_cache') as mock_cache:
            await progress_tracker.update_job_progress(
                "test-job-002",
                progress=75,
                current_task="Scanning vulnerabilities",
                processed_items=150,
                total_items=200,
            )
            
            mock_cache.__setitem__.assert_called()

    @pytest.mark.asyncio
    async def test_update_job_status(self, progress_tracker, db, running_job):
        """Test updating job status."""
        await progress_tracker.update_job_status(
            "test-job-002",
            new_status=JobStatusEnum.COMPLETED.value,
        )
        
        # Verify in database
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(JobQueue).filter(JobQueue.job_id == "test-job-002")
            )
            job = result.scalars().first()
            assert job.status == JobStatusEnum.COMPLETED.value

    @pytest.mark.asyncio
    async def test_mark_job_complete(self, progress_tracker, db, running_job):
        """Test marking job as complete."""
        await progress_tracker.mark_job_complete(
            "test-job-002",
            target_url="https://example.com",
            findings_count=42,
            severity_breakdown={
                "critical": 5,
                "high": 15,
                "medium": 22,
                "low": 0,
            },
            neo4j_status="synced",
            neo4j_count=42,
            completion_time_seconds=120.5,
        )

    @pytest.mark.asyncio
    async def test_broadcast_metrics_update(self, progress_tracker, db):
        """Test broadcasting queue metrics."""
        # Create various jobs
        job1 = JobQueue(
            job_id="test-job-1",
            job_type=JobTypeEnum.SCAN.value,
            status=JobStatusEnum.PENDING.value,
            priority=5,
            target_url="https://example.com",
            payload={},
        )
        
        job2 = JobQueue(
            job_id="test-job-2",
            job_type=JobTypeEnum.SCAN.value,
            status=JobStatusEnum.RUNNING.value,
            priority=5,
            target_url="https://example.com",
            payload={},
        )
        
        job3 = JobQueue(
            job_id="test-job-3",
            job_type=JobTypeEnum.SCAN.value,
            status=JobStatusEnum.COMPLETED.value,
            priority=5,
            target_url="https://example.com",
            payload={},
        )
        
        async with AsyncSessionLocal() as session:
            session.add(job1)
            session.add(job2)
            session.add(job3)
            await session.commit()
        
        # Broadcast metrics
        with patch.object(progress_tracker, 'broadcast_metrics_update') as mock_broadcast:
            await progress_tracker.broadcast_metrics_update()


class TestConnectionInfo:
    """Tests for connection information retrieval."""

    @pytest.mark.asyncio
    async def test_get_connection_info(self, ws_manager):
        """Test retrieving connection info."""
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        
        conn = await ws_manager.connect(mock_ws, "192.168.1.100")
        
        info = ws_manager.get_connection_info(conn)
        assert info is not None
        assert info["client_ip"] == "192.168.1.100"
        assert "connected_at" in info

    @pytest.mark.asyncio
    async def test_get_all_connections_count(self, ws_manager):
        """Test getting active connections count."""
        mock_ws1 = AsyncMock()
        mock_ws1.accept = AsyncMock()
        mock_ws1.send_json = AsyncMock()
        
        mock_ws2 = AsyncMock()
        mock_ws2.accept = AsyncMock()
        mock_ws2.send_json = AsyncMock()
        
        await ws_manager.connect(mock_ws1)
        await ws_manager.connect(mock_ws2)
        
        count = ws_manager.get_all_connections_count()
        assert count == 2

    @pytest.mark.asyncio
    async def test_get_subscribed_connections_for_job(self, ws_manager):
        """Test getting subscribed connections for a job."""
        mock_ws1 = AsyncMock()
        mock_ws1.accept = AsyncMock()
        mock_ws1.send_json = AsyncMock()
        
        mock_ws2 = AsyncMock()
        mock_ws2.accept = AsyncMock()
        mock_ws2.send_json = AsyncMock()
        
        conn1 = await ws_manager.connect(mock_ws1)
        conn2 = await ws_manager.connect(mock_ws2)
        
        await ws_manager.subscribe_to_job(conn1, "job-001")
        await ws_manager.subscribe_to_job(conn2, "job-001")
        
        connections = ws_manager.get_subscribed_connections_for_job("job-001")
        assert len(connections) == 2
        assert conn1 in connections
        assert conn2 in connections


class TestDisconnectHandling:
    """Tests for handling disconnections."""

    @pytest.mark.asyncio
    async def test_unsubscribe_all_on_disconnect(self, ws_manager):
        """Test automatic unsubscription on disconnect."""
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        
        conn = await ws_manager.connect(mock_ws)
        await ws_manager.subscribe_to_job(conn, "job-001")
        await ws_manager.subscribe_to_job(conn, "job-002")
        
        # Disconnect
        await ws_manager.disconnect(conn)
        
        # Verify unsubscribed
        assert conn not in ws_manager.active_connections
        assert len(ws_manager.get_subscribed_connections_for_job("job-001")) == 0
        assert len(ws_manager.get_subscribed_connections_for_job("job-002")) == 0


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_handle_invalid_progress_value(self, progress_tracker):
        """Test handling invalid progress values."""
        with patch.object(progress_tracker, 'update_job_progress') as mock_update:
            # Should not call update with invalid progress
            await progress_tracker.update_job_progress("job-001", progress=-10)

    @pytest.mark.asyncio
    async def test_connection_failure_cleanup(self, ws_manager):
        """Test cleanup on connection failure."""
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json.side_effect = Exception("Connection lost")
        
        conn = await ws_manager.connect(mock_ws)
        
        # Try to send and handle error
        from app.domain.schemas.websocket import ServerMessage
        message = ServerMessage(
            message_type=WebSocketMessageTypeEnum.PONG,
        )
        
        await ws_manager._send_to_connection(conn, message)
        
        # Connection should be cleaned up
        assert conn not in ws_manager.active_connections
