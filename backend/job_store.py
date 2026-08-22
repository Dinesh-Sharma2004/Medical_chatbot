import json
import os
import tempfile
import time
from typing import Any, Dict, Optional


BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_JOB_DIR = os.path.join(BACKEND_DIR, "data", "jobs")
JOB_DIR = os.getenv("UPLOAD_JOB_DIR", DEFAULT_JOB_DIR)


def _job_path(job_id: str) -> str:
    safe = os.path.basename(str(job_id or "").replace("\x00", ""))
    if not safe:
        raise ValueError("job_id required")
    return os.path.join(JOB_DIR, f"{safe}.json")


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    path = _job_path(job_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def put_job(job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    os.makedirs(JOB_DIR, exist_ok=True)
    current = get_job(job_id) or {}
    current.update(payload)
    current.setdefault("job_id", job_id)
    current["updated_at"] = int(time.time())

    with tempfile.NamedTemporaryFile("w", delete=False, dir=JOB_DIR, encoding="utf-8") as tf:
        json.dump(current, tf)
        tmp = tf.name
    os.replace(tmp, _job_path(job_id))
    return current


def delete_job(job_id: str) -> Optional[Dict[str, Any]]:
    job = get_job(job_id)
    path = _job_path(job_id)
    if os.path.exists(path):
        os.remove(path)
    return job
