"""Redis-based task queue for background processing."""

import json
import logging
import os
import time
from typing import Dict, Any, Optional
from uuid import uuid4

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)

class RedisTaskQueue:
    """Simple Redis-based task queue implementation."""
    
    QUEUE_KEY = "tutor:tasks:indexing"
    STATUS_KEY_PREFIX = "tutor:tasks:status:"
    
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        db: Optional[int] = None,
        password: Optional[str] = None,
    ):
        if not REDIS_AVAILABLE:
            raise ImportError("redis package is required for task queue.")
            
        self.host = host or os.getenv("REDIS_HOST", "localhost")
        self.port = port or int(os.getenv("REDIS_PORT", "6379"))
        self.db = db or int(os.getenv("REDIS_DB", "0"))
        self.password = password or os.getenv("REDIS_PASSWORD")
        
        self.redis = redis.Redis(
            host=self.host,
            port=self.port,
            db=self.db,
            password=self.password,
            decode_responses=True
        )
        
    def enqueue_job(self, task_type: str, payload: Dict[str, Any]) -> str:
        """
        Add a job to the queue.
        
        Args:
            task_type: Type of task (e.g., 'index_document')
            payload: Data required for the task
            
        Returns:
            job_id: Unique identifier for the job
        """
        job_id = str(uuid4())
        job_data = {
            "job_id": job_id,
            "type": task_type,
            "payload": payload,
            "created_at": time.time()
        }
        
        # Set initial status
        self.set_job_status(job_id, "queued", {"progress": 0})
        
        # Push to queue
        self.redis.rpush(self.QUEUE_KEY, json.dumps(job_data))
        logger.info(f"Enqueued job {job_id} of type {task_type}")
        
        return job_id
    
    def pop_job(self, timeout: int = 0) -> Optional[Dict[str, Any]]:
        """
        Get next job from queue (blocking).
        
        Args:
            timeout: Seconds to wait. 0 for infinite.
            
        Returns:
            Job data dict or None if timeout
        """
        result = self.redis.blpop(self.QUEUE_KEY, timeout=timeout)
        if result:
            return json.loads(result[1])
        return None
        
    def set_job_status(self, job_id: str, status: str, metadata: Optional[Dict] = None):
        """Update job status and metadata."""
        data = {
            "status": status,
            "updated_at": time.time(),
            **(metadata or {})
        }
        key = f"{self.STATUS_KEY_PREFIX}{job_id}"
        self.redis.set(key, json.dumps(data), ex=86400)  # Expire after 24h
        
    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Get current job status."""
        key = f"{self.STATUS_KEY_PREFIX}{job_id}"
        data = self.redis.get(key)
        if data:
            return json.loads(data)
        return {"status": "unknown"}
