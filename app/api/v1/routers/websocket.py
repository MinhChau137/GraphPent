"""FastAPI WebSocket router for real-time job updates."""

import json
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends

from app.services.websocket_manager import (
    WebSocketConnectionManager,
    get_ws_manager,
)
from app.domain.schemas.websocket import WebSocketMessageTypeEnum

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/ws",
    tags=["WebSocket"],
)


@router.websocket("/jobs/{job_id}")
async def websocket_job_updates(
    websocket: WebSocket,
    job_id: str,
    client_id: Optional[str] = Query(None),
):
    """
    WebSocket endpoint for real-time job updates.
    
    **Connection URL**: `ws://localhost:8000/api/v1/ws/jobs/{job_id}`
    
    **Features**:
    - Real-time progress updates
    - Status change notifications
    - Result delivery
    - Keep-alive ping/pong
    - Auto-reconnect support
    
    **Example Client (JavaScript)**:
    ```javascript
    const ws = new WebSocket('ws://localhost:8000/api/v1/ws/jobs/job-uuid');
    
    ws.onopen = () => {
        console.log('Connected');
    };
    
    ws.onmessage = (event) => {
        const message = JSON.parse(event.data);
        console.log('Update:', message);
    };
    
    ws.onerror = (error) => {
        console.error('Error:', error);
    };
    
    ws.onclose = () => {
        console.log('Disconnected');
    };
    ```
    
    **Example Client (Python)**:
    ```python
    import asyncio
    import websockets
    import json
    
    async def listen():
        uri = "ws://localhost:8000/api/v1/ws/jobs/job-uuid"
        async with websockets.connect(uri) as websocket:
            while True:
                message = await websocket.recv()
                data = json.loads(message)
                print(f"Update: {data}")
    
    asyncio.run(listen())
    ```
    
    **Message Types**:
    - `progress_update`: Job progress changed
    - `status_update`: Job status changed
    - `result_ready`: Job completed (auto-disconnects)
    - `error`: Error occurred
    - `metrics_update`: Queue metrics updated
    - `pong`: Response to ping (keep-alive)
    """
    manager = await get_ws_manager()
    connection_id = await manager.connect(websocket, client_id)
    
    try:
        # Auto-subscribe to job
        await manager.subscribe_to_job(connection_id, job_id)
        
        # Listen for client messages
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            
            # Handle message
            await manager.handle_client_message(connection_id, data)
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {connection_id}")
        await manager.disconnect(connection_id)
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
        await manager.disconnect(connection_id)


@router.websocket("/metrics")
async def websocket_metrics(
    websocket: WebSocket,
    client_id: Optional[str] = Query(None),
):
    """
    WebSocket endpoint for queue metrics updates.
    
    **Connection URL**: `ws://localhost:8000/api/v1/ws/metrics`
    
    **Features**:
    - Real-time queue statistics
    - Active jobs count
    - Success rate tracking
    - Performance metrics
    
    **Example Client (JavaScript)**:
    ```javascript
    const ws = new WebSocket('ws://localhost:8000/api/v1/ws/metrics');
    
    ws.onmessage = (event) => {
        const metrics = JSON.parse(event.data);
        if (metrics.message_type === 'metrics_update') {
            console.log('Queue size:', metrics.data.pending_jobs);
            console.log('Success rate:', metrics.data.success_rate);
        }
    };
    ```
    
    **Message Type**: `metrics_update`
    - `total_jobs`: Total jobs ever submitted
    - `pending_jobs`: Jobs waiting in queue
    - `running_jobs`: Currently executing jobs
    - `completed_jobs`: Successfully completed jobs
    - `failed_jobs`: Failed jobs
    - `success_rate`: Percentage of successful completions
    - `average_completion_time_seconds`: Average job duration
    """
    manager = await get_ws_manager()
    connection_id = await manager.connect(websocket, client_id)
    
    try:
        while True:
            # Receive message from client (keep-alive)
            data = await websocket.receive_json()
            
            # Handle ping/pong for keep-alive
            if data.get("message_type") == WebSocketMessageTypeEnum.PING:
                await manager.handle_client_message(connection_id, data)
            
    except WebSocketDisconnect:
        logger.info(f"Metrics WebSocket disconnected: {connection_id}")
        await manager.disconnect(connection_id)
    except Exception as e:
        logger.error(f"Metrics WebSocket error: {str(e)}")
        await manager.disconnect(connection_id)


@router.websocket("/live")
async def websocket_live_updates(
    websocket: WebSocket,
    client_id: Optional[str] = Query(None),
):
    """
    WebSocket endpoint for subscribing to multiple jobs.
    
    **Connection URL**: `ws://localhost:8000/api/v1/ws/live`
    
    **Features**:
    - Subscribe/unsubscribe from multiple jobs dynamically
    - Real-time updates for all subscribed jobs
    - Queue metrics updates
    - Flexible job filtering
    
    **Message Protocol**:
    
    **Subscribe to job**:
    ```json
    {
        "message_type": "subscribe",
        "job_id": "job-uuid"
    }
    ```
    
    **Unsubscribe from job**:
    ```json
    {
        "message_type": "unsubscribe",
        "job_id": "job-uuid"
    }
    ```
    
    **Keep-alive**:
    ```json
    {
        "message_type": "ping"
    }
    ```
    
    **Example Client (Python)**:
    ```python
    import asyncio
    import websockets
    import json
    
    async def live_updates():
        uri = "ws://localhost:8000/api/v1/ws/live"
        async with websockets.connect(uri) as ws:
            # Subscribe to job
            await ws.send(json.dumps({
                "message_type": "subscribe",
                "job_id": "job-uuid"
            }))
            
            # Listen for updates
            while True:
                msg = await ws.recv()
                data = json.loads(msg)
                
                if data['message_type'] == 'progress_update':
                    print(f"Progress: {data['data']['progress']}%")
                elif data['message_type'] == 'result_ready':
                    print(f"Complete: {data['data']['findings_count']} findings")
                elif data['message_type'] == 'metrics_update':
                    print(f"Queue size: {data['data']['queue_size']}")
            
            # Unsubscribe from job
            await ws.send(json.dumps({
                "message_type": "unsubscribe",
                "job_id": "job-uuid"
            }))
    
    asyncio.run(live_updates())
    ```
    """
    manager = await get_ws_manager()
    connection_id = await manager.connect(websocket, client_id)
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            
            # Handle message (subscribe/unsubscribe/ping)
            await manager.handle_client_message(connection_id, data)
            
    except WebSocketDisconnect:
        logger.info(f"Live updates WebSocket disconnected: {connection_id}")
        await manager.disconnect(connection_id)
    except Exception as e:
        logger.error(f"Live updates WebSocket error: {str(e)}")
        await manager.disconnect(connection_id)


# Health check endpoint for WebSocket connections
import requests
from fastapi import Response


@router.get(
    "/health",
    summary="WebSocket service health",
    tags=["Health"],
)
async def ws_health(manager: WebSocketConnectionManager = Depends(get_ws_manager)):
    """
    Check WebSocket service health.
    
    Returns:
    - Active connections count
    - Service status
    - Last metrics update
    """
    return {
        "status": "healthy",
        "active_connections": manager.get_all_connections_count(),
        "service": "websocket",
    }
