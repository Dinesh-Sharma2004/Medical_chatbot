import json
import logging
import os
import tempfile
import time
from typing import Any, Dict, Optional


BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_JOB_DIR = os.path.join(BACKEND_DIR, "data", "jobs")
JOB_DIR = os.getenv("UPLOAD_JOB_DIR", DEFAULT_JOB_DIR)

# Windows raises PermissionError (WinError 5/32) from os.replace and open() when
# another handle still has the job file open. The status endpoint polls these
# files a few times per second while ingestion writes progress, so brief
# collisions are expected and must not fail the surrounding work.
IO_ATTEMPTS = 5
IO_BACKOFF = 0.05


def _job_path(job_id: str) -> str:
    safe = os.path.basename(str(job_id or "").replace("\x00", ""))
    if not safe:
        raise ValueError("job_id required")
    return os.path.join(JOB_DIR, f"{safe}.json")


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    path = _job_path(job_id)
    last_error: Optional[Exception] = None
    for attempt in range(IO_ATTEMPTS):
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (PermissionError, json.JSONDecodeError) as exc:
            # A concurrent writer may be mid-replace, so the file can be briefly
            # locked or observed half-written. Retry rather than propagate.
            last_error = exc
            time.sleep(IO_BACKOFF * (attempt + 1))
    logging.warning("[JOBS] Could not read job %s: %s", job_id, last_error)
    return None


def put_job(job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    os.makedirs(JOB_DIR, exist_ok=True)
    current = get_job(job_id) or {}
    current.update(payload)
    current.setdefault("job_id", job_id)
    current["updated_at"] = int(time.time())

    with tempfile.NamedTemporaryFile("w", delete=False, dir=JOB_DIR, encoding="utf-8") as tf:
        json.dump(current, tf)
        tmp = tf.name

    dest = _job_path(job_id)
    last_error: Optional[Exception] = None
    for attempt in range(IO_ATTEMPTS):
        try:
            os.replace(tmp, dest)
            return current
        except PermissionError as exc:
            last_error = exc
            time.sleep(IO_BACKOFF * (attempt + 1))

    # Persisting progress is best effort: callers keep the authoritative copy in
    # memory, and failing here used to abort the whole ingestion run.
    try:
        os.remove(tmp)
    except OSError:
        pass
    logging.warning(
        "[JOBS] Could not persist job %s after %d attempts: %s",
        job_id,
        IO_ATTEMPTS,
        last_error,
    )
    return current


def delete_job(job_id: str) -> Optional[Dict[str, Any]]:
    job = get_job(job_id)
    path = _job_path(job_id)
    for attempt in range(IO_ATTEMPTS):
        if not os.path.exists(path):
            break
        try:
            os.remove(path)
            break
        except PermissionError:
            time.sleep(IO_BACKOFF * (attempt + 1))
    return job
