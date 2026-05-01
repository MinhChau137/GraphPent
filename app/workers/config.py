"""Celery configuration and setup."""

import os
from celery import Celery
from kombu import Exchange, Queue

# Get Redis URL from environment or use default
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

# Initialize Celery app
celery_app = Celery(
    "graphpent",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
)

# Task routing configuration
default_exchange = Exchange("graphpent", type="direct")
default_queue = Queue("default", exchange=default_exchange, routing_key="default")
priority_queue = Queue("priority", exchange=default_exchange, routing_key="priority")
scan_queue = Queue("scans", exchange=default_exchange, routing_key="scans")

# Celery configuration
celery_app.conf.update(
    # Broker settings
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=10,
    
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    
    # Task execution
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour hard limit
    task_soft_time_limit=3300,  # 55 minutes soft limit
    
    # Result backend
    result_expires=3600,  # Results expire after 1 hour
    result_compression="gzip",
    
    # Queue configuration
    task_queues=(default_queue, priority_queue, scan_queue),
    task_default_queue="default",
    task_default_exchange="graphpent",
    task_default_routing_key="default",
    
    # Worker settings
    worker_max_tasks_per_child=1000,
    worker_prefetch_multiplier=4,
    worker_disable_rate_limits=False,
    
    # Retry settings
    task_autoretry_for=(Exception,),
    task_default_retry_delay=60,  # 1 minute initial retry
    task_default_max_retries=3,
    
    # Error handling
    task_ignore_result=False,
    task_store_eager_result=True,
)

# Task routing configuration
celery_app.conf.task_routes = {
    "app.workers.nuclei_tasks.scan_target_async": {"queue": "scans", "priority": 5},
    "app.workers.nuclei_tasks.process_scan_results": {"queue": "default"},
    "app.workers.nuclei_tasks.upsert_to_neo4j_async": {"queue": "default"},
    "app.workers.nuclei_tasks.generate_report": {"queue": "default"},
}

# Application instance
if __name__ == "__main__":
    celery_app.start()
