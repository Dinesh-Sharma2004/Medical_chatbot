import logging
import os
from typing import List
from redis import Redis

REDIS_URL = os.getenv("REDIS_URL", "").strip()
INGEST_QUEUE_NAME = os.getenv("INGEST_QUEUE_NAME", "ingest")
INGEST_QUEUE_REQUIRED = os.getenv("INGEST_QUEUE_REQUIRED", "false").lower() in ("1", "true", "yes")
REDIS_SOCKET_TIMEOUT_SECONDS = int(os.getenv("REDIS_SOCKET_TIMEOUT_SECONDS", "900"))
REDIS_CONNECT_TIMEOUT_SECONDS = int(os.getenv("REDIS_CONNECT_TIMEOUT_SECONDS", "5"))


def redis_connection():
    return Redis.from_url(
        REDIS_URL,
        socket_timeout=REDIS_SOCKET_TIMEOUT_SECONDS,
        socket_connect_timeout=REDIS_CONNECT_TIMEOUT_SECONDS,
        health_check_interval=30,
    )


def enqueue_ingest(job_id: str, pdf_paths: List[str]) -> bool:
    if not REDIS_URL:
        return False
    try:
        from rq import Queue
    except Exception:
        logging.exception("[QUEUE] Redis/RQ dependencies unavailable; falling back to local ingest")
        return False

    try:
        conn = redis_connection()
        queue = Queue(INGEST_QUEUE_NAME, connection=conn)
        queue.enqueue(
            "backend.ingest_worker.run_ingest_job",
            job_id,
            pdf_paths,
            job_timeout=int(os.getenv("INGEST_JOB_TIMEOUT_SECONDS", "3600")),
            result_ttl=int(os.getenv("INGEST_RESULT_TTL_SECONDS", "86400")),
            failure_ttl=int(os.getenv("INGEST_FAILURE_TTL_SECONDS", "86400")),
        )
        return True
    except Exception:
        logging.exception("[QUEUE] Failed to enqueue ingest job; falling back to local ingest")
        return False


def queue_status() -> dict:
    if not REDIS_URL:
        return {"enabled": False, "ready": False, "queue": INGEST_QUEUE_NAME}
    try:
        redis_connection().ping()
        return {"enabled": True, "ready": True, "queue": INGEST_QUEUE_NAME}
    except Exception as exc:
        return {"enabled": True, "ready": False, "queue": INGEST_QUEUE_NAME, "error": str(exc)}
