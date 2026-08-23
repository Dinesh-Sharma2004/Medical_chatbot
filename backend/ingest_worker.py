import logging
import time

from . import job_store
from .ingest import create_vector_store
from .queueing import INGEST_QUEUE_NAME, REDIS_URL, redis_connection


def run_ingest_job(job_id: str, pdf_paths: list[str]) -> bool:
    started = time.time()

    def progress(progress_value: int, detail: str):
        job_store.put_job(job_id, {"progress": progress_value, "detail": detail, "status": "processing"})

    job = job_store.get_job(job_id) or {}
    if job.get("status") == "canceled":
        job_store.put_job(job_id, {"status": "canceled", "detail": "Ingestion canceled"})
        return False

    try:
        job_store.put_job(job_id, {"status": "processing", "detail": "Worker indexing documents"})
        res = create_vector_store(pdf_paths, progress_cb=progress)
        stats = {}
        if isinstance(res, dict):
            ok = res.get("success", False)
            stats = {
                "failed_batches": res.get("failed_batches", []),
                "processed_pages": res.get("processed_pages", 0),
                "total_pages": res.get("total_pages", 0),
                "processed_chunks": res.get("processed_chunks", 0),
                "embedded_chunks": res.get("embedded_chunks", 0),
            }
        else:
            ok = res

        job_store.put_job(
            job_id,
            {
                "status": "completed" if ok else "error",
                "progress": 100 if ok else 0,
                "detail": "Ready to chat" if ok else "Ingestion failed",
                "duration": round(time.time() - started, 2),
                **stats
            },
        )
        return ok
    except Exception as exc:
        logging.exception("[WORKER] Ingest job failed")
        job_store.put_job(
            job_id,
            {
                "status": "error",
                "detail": str(exc),
                "duration": round(time.time() - started, 2),
            },
        )
        return False


def main():
    if not REDIS_URL:
        raise RuntimeError("REDIS_URL is required for ingest worker mode")
    from rq import Worker

    redis = redis_connection()
    worker = Worker([INGEST_QUEUE_NAME], connection=redis)
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
