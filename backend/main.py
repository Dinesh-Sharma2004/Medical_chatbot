# main.py — Docker-Ready FastAPI Backend (Groq + FAISS RAG)

import os
import uuid
import json
import logging
import asyncio
import threading
import re
import queue
import time
from time import perf_counter
from typing import Dict, Any, List

from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse, Response
from dotenv import load_dotenv

try:
    from .telemetry import (
        CONTENT_TYPE_LATEST,
        INFLIGHT_REQUESTS,
        REQUEST_COUNT,
        REQUEST_LATENCY,
        generate_latest,
    )
except ImportError:
    from telemetry import (
        CONTENT_TYPE_LATEST,
        INFLIGHT_REQUESTS,
        REQUEST_COUNT,
        REQUEST_LATENCY,
        generate_latest,
    )

try:
    from .ingest import create_vector_store
    from . import rag_chain as rc
    from . import job_store
    from .auth_core import init_auth_db, require_user, router as auth_router
    from .queueing import INGEST_QUEUE_REQUIRED, enqueue_ingest, queue_status
except ImportError:
    from ingest import create_vector_store
    import rag_chain as rc
    import job_store
    from auth_core import init_auth_db, require_user, router as auth_router
    from queueing import INGEST_QUEUE_REQUIRED, enqueue_ingest, queue_status


load_dotenv(override=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BACKEND_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DEFAULT_FRONTEND_DIST = os.path.normpath(
    os.path.join(BACKEND_DIR, "..", "frontend", "dist")
)
FRONTEND_DIST = os.getenv("FRONTEND_DIST", DEFAULT_FRONTEND_DIST)

app = FastAPI(title="MediBot Backend (Groq RAG)", version="4.0.0")
init_auth_db()
app.include_router(auth_router)


@app.get("/_frontend_info", include_in_schema=False)
def frontend_info():
    return {"frontend_dist": FRONTEND_DIST, "exists": os.path.isdir(FRONTEND_DIST)}

# ======================================================
# CORS
# ======================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    if request.url.path == "/metrics":
        return await call_next(request)

    INFLIGHT_REQUESTS.inc()
    started = perf_counter()
    response = None
    try:
        response = await call_next(request)
        return response
    finally:
        route = request.scope.get("route")
        path = getattr(route, "path", request.url.path)
        status = getattr(response, "status_code", 500)
        REQUEST_COUNT.labels(request.method, path, str(status)).inc()
        REQUEST_LATENCY.labels(request.method, path).observe(perf_counter() - started)
        INFLIGHT_REQUESTS.dec()

# ======================================================
# UPLOAD JOB STATE
# ======================================================
UPLOAD_JOBS: Dict[str, Dict[str, Any]] = {}
UPLOAD_CANCEL_EVENTS: Dict[str, threading.Event] = {}
UPLOAD_FILES: Dict[str, List[str]] = {}
UPLOAD_LOCK = threading.Lock()
CHUNK_BYTES = 1024 * 1024

# ======================================================
# HEALTH
# ======================================================
@app.get("/api/health")
def health():
    try:
        st = rc.status()
        qst = queue_status()
        return {
            "status": "ok",
            "vector_ready": bool(st.get("vectorstore")),
            "llm_ready": bool(st.get("llm")),
            "queue_ready": bool(qst.get("ready")),
            "detail": {**st, "queue": qst},
        }
    except Exception:
        logging.exception("Health endpoint failure")
        return {"status": "error", "vector_ready": False, "llm_ready": False}


@app.get("/metrics", include_in_schema=False)
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

# ======================================================
# UPLOAD → INGEST
# ======================================================
def _safe_filename(filename: str) -> str:
    name = os.path.basename(filename or "uploaded.pdf").replace("\x00", "")
    return re.sub(r"[^A-Za-z0-9._() -]+", "_", name).strip() or "uploaded.pdf"

async def _save_upload_file(file: UploadFile, dest: str) -> int:
    size = 0
    with open(dest, "wb") as out:
        while True:
            chunk = await file.read(CHUNK_BYTES)
            if not chunk:
                break
            size += len(chunk)
            out.write(chunk)
    return size

def _set_job(job_id: str, **updates):
    with UPLOAD_LOCK:
        if job_id in UPLOAD_JOBS:
            existing = UPLOAD_JOBS[job_id]
            if existing.get("status") == "canceled" and updates.get("status") not in (None, "canceled"):
                return
            UPLOAD_JOBS[job_id].update(updates)
            job_store.put_job(job_id, UPLOAD_JOBS[job_id])
            return
    existing = job_store.get_job(job_id)
    if existing:
        if existing.get("status") == "canceled" and updates.get("status") not in (None, "canceled"):
            return
        job_store.put_job(job_id, updates)

def _start_ingest_job(job_id: str, pdf_paths: List[str]):
    def _worker():
        started = time.time()
        cancel_event = UPLOAD_CANCEL_EVENTS.get(job_id)

        def cb(p, d):
            _set_job(job_id, progress=p, detail=d)

        try:
            ok = create_vector_store(pdf_paths, progress_cb=cb, cancel_event=cancel_event)
            if cancel_event is not None and cancel_event.is_set():
                _set_job(
                    job_id,
                    status="canceled",
                    detail="Ingestion canceled",
                    duration=round(time.time() - started, 2),
                )
                return
            _set_job(
                job_id,
                status="completed" if ok else "error",
                progress=100 if ok else 0,
                detail="Ready to chat" if ok else "Ingestion failed",
                duration=round(time.time() - started, 2),
            )
        except Exception as e:
            logging.exception("Ingest error")
            if cancel_event is not None and cancel_event.is_set():
                _set_job(
                    job_id,
                    status="canceled",
                    detail="Ingestion canceled",
                    duration=round(time.time() - started, 2),
                )
            else:
                _set_job(job_id, status="error", detail=str(e), duration=round(time.time() - started, 2))

        try:
            if cancel_event is None or not cancel_event.is_set():
                threading.Thread(
                    target=lambda: rc.warmup_resources(load_llm=False),
                    daemon=True
                ).start()
        except Exception:
            logging.exception("Warmup failed")

    threading.Thread(target=_worker, daemon=True).start()

def _dispatch_ingest_job(job_id: str, pdf_paths: List[str]):
    if enqueue_ingest(job_id, pdf_paths):
        _set_job(job_id, detail="Queued for ingestion worker")
        return
    if INGEST_QUEUE_REQUIRED:
        _set_job(job_id, status="error", progress=0, detail="Ingestion queue unavailable")
        raise HTTPException(status_code=503, detail="Ingestion queue unavailable")
    _start_ingest_job(job_id, pdf_paths)

@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...), user: Dict[str, Any] = Depends(require_user)):
    if not file.filename.lower().endswith(".pdf"):
        return JSONResponse({"ok": False, "detail": "Only PDF files allowed"}, status_code=400)

    job_id = str(uuid.uuid4())
    filename = _safe_filename(file.filename)
    dest = os.path.join(DATA_DIR, f"{job_id}_{filename}")

    size_bytes = await _save_upload_file(file, dest)
    if size_bytes == 0:
        return JSONResponse({"ok": False, "detail": "File empty"}, status_code=400)

    with UPLOAD_LOCK:
        UPLOAD_JOBS[job_id] = {
            "job_id": job_id,
            "filename": filename,
            "filenames": [filename],
            "size_bytes": size_bytes,
            "files": [dest],
            "status": "processing",
            "progress": 0,
            "detail": "Queued for indexing",
        }
        UPLOAD_CANCEL_EVENTS[job_id] = threading.Event()
        UPLOAD_FILES[job_id] = [dest]
        job_store.put_job(job_id, UPLOAD_JOBS[job_id])

    _dispatch_ingest_job(job_id, [dest])

    return {
        "ok": True,
        "job_id": job_id,
        "filename": filename,
        "filenames": [filename],
        "size_bytes": size_bytes,
        "status": "processing",
        "progress": 0,
        "detail": "Queued for indexing",
    }

@app.post("/api/upload/batch")
async def upload_pdfs(files: List[UploadFile] = File(...), user: Dict[str, Any] = Depends(require_user)):
    pdfs = [f for f in files if f.filename and f.filename.lower().endswith(".pdf")]
    if not pdfs or len(pdfs) != len(files):
        return JSONResponse({"ok": False, "detail": "Only PDF files allowed"}, status_code=400)

    job_id = str(uuid.uuid4())
    saved_paths: List[str] = []
    filenames: List[str] = []
    total_size = 0

    for file in pdfs:
        filename = _safe_filename(file.filename)
        dest = os.path.join(DATA_DIR, f"{job_id}_{len(saved_paths) + 1}_{filename}")
        size_bytes = await _save_upload_file(file, dest)
        if size_bytes == 0:
            return JSONResponse({"ok": False, "detail": f"{filename} is empty"}, status_code=400)
        saved_paths.append(dest)
        filenames.append(filename)
        total_size += size_bytes

    with UPLOAD_LOCK:
        UPLOAD_JOBS[job_id] = {
            "job_id": job_id,
            "filename": f"{len(filenames)} PDFs",
            "filenames": filenames,
            "size_bytes": total_size,
            "files": list(saved_paths),
            "status": "processing",
            "progress": 0,
            "detail": "Queued batch for indexing",
        }
        UPLOAD_CANCEL_EVENTS[job_id] = threading.Event()
        UPLOAD_FILES[job_id] = list(saved_paths)
        job_store.put_job(job_id, UPLOAD_JOBS[job_id])

    _dispatch_ingest_job(job_id, saved_paths)

    return {
        "ok": True,
        "job_id": job_id,
        "filename": f"{len(filenames)} PDFs",
        "filenames": filenames,
        "size_bytes": total_size,
        "status": "processing",
        "progress": 0,
        "detail": "Queued batch for indexing",
    }


@app.get("/api/upload/status/{job_id}")
def upload_status(job_id: str, user: Dict[str, Any] = Depends(require_user)):
    with UPLOAD_LOCK:
        job = UPLOAD_JOBS.get(job_id)
    stored_job = job_store.get_job(job_id)
    if stored_job and (
        not job or int(stored_job.get("updated_at", 0)) >= int(job.get("updated_at", 0))
    ):
        job = stored_job
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.post("/api/upload/cancel/{job_id}")
def cancel_upload(job_id: str, user: Dict[str, Any] = Depends(require_user)):
    with UPLOAD_LOCK:
        job = UPLOAD_JOBS.get(job_id)
        cancel_event = UPLOAD_CANCEL_EVENTS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if cancel_event is not None:
        cancel_event.set()

    _set_job(job_id, status="canceled", detail="Cancel requested")
    with UPLOAD_LOCK:
        return dict(UPLOAD_JOBS.get(job_id) or job_store.get_job(job_id) or {"job_id": job_id, "status": "canceled"})


@app.delete("/api/upload/{job_id}")
def delete_upload(job_id: str, user: Dict[str, Any] = Depends(require_user)):
    with UPLOAD_LOCK:
        job = UPLOAD_JOBS.pop(job_id, None)
        cancel_event = UPLOAD_CANCEL_EVENTS.pop(job_id, None)
        files = UPLOAD_FILES.pop(job_id, [])
    stored_job = job_store.delete_job(job_id)

    if not job and not stored_job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not files and stored_job:
        files = stored_job.get("files", [])

    if cancel_event is not None:
        cancel_event.set()

    data_root = os.path.abspath(DATA_DIR)
    deleted = []
    for path in files:
        abs_path = os.path.abspath(path)
        if not abs_path.startswith(data_root + os.sep):
            continue
        if os.path.exists(abs_path):
            try:
                os.remove(abs_path)
                deleted.append(os.path.basename(abs_path))
            except Exception:
                logging.exception("Failed deleting upload artifact %s", abs_path)

    return {"ok": True, "job_id": job_id, "deleted_files": deleted}

# ======================================================
# FULLTEXT DOCUMENT ACCESS
# ======================================================
@app.get("/api/source/{doc_id}")
def get_full_source(doc_id: str, user: Dict[str, Any] = Depends(require_user)):
    full_dir = getattr(rc, "FULLTEXT_DIR", "vectorstore/fulltext")
    full_root = os.path.abspath(full_dir)
    meta = rc.find_source_metadata(doc_id)
    candidate_keys = [
        meta.get("page_key") if meta else None,
        meta.get("doc_id") if meta else None,
        doc_id,
    ]

    seen = set()
    for key in candidate_keys:
        if not key or key in seen:
            continue
        seen.add(key)
        safe_key = os.path.basename(str(key).replace("\x00", ""))
        path = os.path.abspath(os.path.join(full_root, f"{safe_key}.txt"))
        if not (path == full_root or path.startswith(full_root + os.sep)):
            continue
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return {
                    "doc_id": doc_id,
                    "page_key": safe_key,
                    "text": f.read(),
                }

    raise HTTPException(404, "Fulltext not found")

@app.get("/api/pdf/{doc_id}")
def get_source_pdf(doc_id: str, user: Dict[str, Any] = Depends(require_user)):
    meta = rc.find_source_metadata(doc_id)
    if not meta or not meta.get("source"):
        raise HTTPException(404, "PDF source not found")

    path = os.path.abspath(meta["source"])
    data_root = os.path.abspath(DATA_DIR)
    if not (path == data_root or path.startswith(data_root + os.sep)):
        raise HTTPException(403, "PDF source outside upload directory")
    if not os.path.exists(path):
        raise HTTPException(404, "PDF file not found")

    return FileResponse(
        path,
        media_type="application/pdf",
        filename=os.path.basename(path),
        headers={"Content-Disposition": f'inline; filename="{os.path.basename(path)}"'},
    )

# ======================================================
# NON-STREAM ASK
# ======================================================
def check_exploit_guardrails(question: str) -> bool:
    q_lower = question.lower()
    disallowed_keywords = [
        "system prompt", "prompt template", "system instruction",
        "underlying pipeline", "rag pipeline", "vector database",
        "vectorstore", "faiss index", "rerank", "retrieval score",
        "expose code", "backend code", "main.py", "rag_chain.py",
        "groq model", "llama-3", "embedding model", "quantize",
        "similarity score", "chunk id", "python script", "dockerfile",
        "docker-compose", "nginx conf"
    ]
    for kw in disallowed_keywords:
        if kw in q_lower:
            return True
    
    if "prompt" in q_lower or "instruction" in q_lower or "constraint" in q_lower:
        if any(w in q_lower for w in ["what", "show", "tell", "reveal", "explain", "get"]):
            return True
            
    if "code" in q_lower or "implementation" in q_lower or "architecture" in q_lower:
        if any(w in q_lower for w in ["how", "show", "what", "reveal", "get"]):
            return True
            
    return False

# ======================================================
# NON-STREAM ASK
# ======================================================
@app.post("/api/ask")
async def ask(
    question: str = Form(...),
    mode: str = Form("basic"),
    user: Dict[str, Any] = Depends(require_user),
):
    question = question.strip()
    if not question:
        return {"answer": "Question is empty", "sources": [], "mode": mode}

    if check_exploit_guardrails(question):
        return {
            "answer": "I am a medical assistant. I can only answer medical questions or queries directly related to the uploaded document content.",
            "sources": [],
            "mode": mode,
        }

    if not await asyncio.to_thread(rc.get_rag_chain, mode):
        return {"answer": "RAG not ready. Upload documents first.", "sources": [], "mode": mode}

    try:
        result = await asyncio.to_thread(rc.answer_query, question, mode)
    except Exception as e:
        logging.exception("ask() failure")
        return {"answer": f"Error: {e}", "sources": [], "mode": mode}

    return {
        "answer": result.get("answer", ""),
        "sources": result.get("sources", []),
        "mode": mode,
    }

# ======================================================
# STREAMING ASK
# ======================================================
@app.post("/api/ask/stream")
async def ask_stream(request: Request, user: Dict[str, Any] = Depends(require_user)):
    data = await request.json()
    question = data.get("question", "").strip()
    mode = (data.get("mode") or "basic").lower()

    if not question:
        async def _err():
            yield json.dumps({
                "type": "error",
                "message": "Empty question"
            }) + "\n"
        return StreamingResponse(_err(), media_type="application/x-ndjson")

    if check_exploit_guardrails(question):
        async def _blocked():
            yield json.dumps({
                "type": "sources",
                "sources": [],
                "mode": mode,
            }) + "\n"
            yield json.dumps({
                "type": "partial",
                "text": "I am a medical assistant. I can only answer medical questions or queries directly related to the uploaded document content."
            }) + "\n"
            yield json.dumps({"type": "done"}) + "\n"
        return StreamingResponse(_blocked(), media_type="application/x-ndjson")

    st = rc.status()
    if not st.get("vectorstore") or not st.get("llm"):
        async def _not_ready():
            yield json.dumps({
                "type": "error",
                "message": "RAG not ready"
            }) + "\n"
        return StreamingResponse(_not_ready(), media_type="application/x-ndjson")

    retrieval_bundle = await asyncio.to_thread(rc.build_retrieval_bundle, question, mode)
    sources_meta = retrieval_bundle["sources"]
    generation_bundle = await asyncio.to_thread(rc.build_generation_bundle, question, retrieval_bundle, mode)
    prompt = generation_bundle["prompt"]

    async def generator():
        # first send sources
        yield json.dumps({
            "type": "sources",
            "sources": sources_meta,
            "mode": mode,
        }) + "\n"

        stream_queue: "queue.Queue[str | None]" = queue.Queue()

        def blocking_groq_stream():
            try:
                for chunk in rc.stream_groq(prompt):
                    if "text" in chunk:
                        stream_queue.put(json.dumps({
                            "type": "partial",
                            "text": chunk["text"]
                        }) + "\n")
                    if "done" in chunk:
                        stream_queue.put(json.dumps({"type": "done"}) + "\n")
                        break
            except Exception as e:
                logging.exception("Streaming error")
                stream_queue.put(json.dumps({
                    "type": "error",
                    "message": str(e)
                }) + "\n")
            finally:
                stream_queue.put(None)

        threading.Thread(target=blocking_groq_stream, daemon=True).start()
        while True:
            item = await asyncio.to_thread(stream_queue.get)
            if item is None:
                break
            yield item

    return StreamingResponse(
        generator(),
        media_type="application/x-ndjson"
    )

# ======================================================
# FRONTEND SERVING (Vite build)
# ======================================================
if os.path.isdir(FRONTEND_DIST):
    assets_dir = os.path.join(FRONTEND_DIST, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    app.mount("/spa", StaticFiles(directory=FRONTEND_DIST), name="spa")

    @app.get("/", include_in_schema=False)
    def serve_index():
        index = os.path.join(FRONTEND_DIST, "index.html")
        if os.path.exists(index):
            return FileResponse(index)
        return JSONResponse({"detail": "Frontend not found"}, status_code=404)

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa_routes(full_path: str):
        if full_path.startswith(("api/", "assets/", "spa/", "_frontend_info")):
            raise HTTPException(status_code=404, detail="Not Found")

        index = os.path.join(FRONTEND_DIST, "index.html")
        if os.path.exists(index):
            return FileResponse(index)
        return JSONResponse({"detail": "Frontend not found"}, status_code=404)
else:
    @app.get("/", include_in_schema=False)
    def root_no_frontend():
        return {"detail": f"Backend running. Frontend not found at {FRONTEND_DIST}"}
