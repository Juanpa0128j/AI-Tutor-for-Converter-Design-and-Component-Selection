"""Background worker for processing indexing tasks."""

import os
import sys
import logging
import time
import shutil
from pathlib import Path

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tutor_virtual.infrastructure.task_queue import RedisTaskQueue
from tutor_virtual.infrastructure.rag import get_rag_service
from tutor_virtual.shared.config import AppConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("worker")

def process_indexing_task(payload: dict, queue: RedisTaskQueue, job_id: str):
    """Execute document indexing logic."""
    file_path = payload.get("file_path")
    original_filename = payload.get("original_filename")
    
    if not file_path or not os.path.exists(file_path):
        queue.set_job_status(job_id, "failed", {"error": "File not found"})
        return

    try:
        queue.set_job_status(job_id, "processing", {"progress": 10, "message": "Initializing RAG service..."})
        rag_service = get_rag_service()
        
        strategy = payload.get("strategy", "fast")
        queue.set_job_status(job_id, "processing", {"progress": 30, "message": f"Processing document ({strategy})..."})
        
        # Process and index
        result = rag_service.process_and_index_file(file_path, original_filename, strategy=strategy)
        
        if result["status"] == "success":
            queue.set_job_status(job_id, "completed", {
                "progress": 100,
                "result": result
            })
            logger.info(f"Job {job_id} completed successfully")
            
            # Cleanup staging file
            try:
                os.remove(file_path)
            except Exception:
                pass
        else:
            queue.set_job_status(job_id, "failed", {"error": result.get("error")})
            logger.error(f"Job {job_id} failed: {result.get('error')}")
            
    except Exception as e:
        logger.error(f"Unexpected error in job {job_id}: {e}")
        queue.set_job_status(job_id, "failed", {"error": str(e)})

def main():
    """Main worker loop."""
    AppConfig.from_env()
    
    try:
        queue = RedisTaskQueue()
        logger.info("Worker started. Waiting for tasks...")
        
        while True:
            try:
                job = queue.pop_job(timeout=5)
                if job:
                    job_id = job["job_id"]
                    task_type = job["type"]
                    logger.info(f"Received job {job_id}: {task_type}")
                    
                    if task_type == "index_document":
                        process_indexing_task(job["payload"], queue, job_id)
                    else:
                        logger.warning(f"Unknown task type: {task_type}")
                        
            except Exception as e:
                logger.error(f"Error in worker loop: {e}")
                time.sleep(5)
                
    except KeyboardInterrupt:
        logger.info("Worker stopping...")
    except Exception as e:
        logger.critical(f"Worker crashed: {e}")

if __name__ == "__main__":
    main()
