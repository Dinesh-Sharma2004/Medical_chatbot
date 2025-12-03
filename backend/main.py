# main.py — Docker-Ready FastAPI Backend (Groq + FAISS RAG)

import os
import uuid
import json
import logging
import asyncio
import threading
from typing import Dict, Any

from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from dotenv import load_dotenv

from ingest import create_vector_store
import rag_chain as rc

# ======================================================
# INITIAL SETUP
# ======================================================
load_dotenv()
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

# ======================================================
# UPLOAD JOB STATE
# ======================================================
UPLOAD_JOBS: Dict[str, Dict[str, Any]] = {}
UPLOAD_LOCK = threading.Lock()

# ======================================================
# HEALTH
# ======================================================
@app.get("/api/health")
def health():
    try:
        st = rc.status()
        return {
            "status": "ok",
            "vector_ready": bool(st.get("vectorstore")),
            "llm_ready": bool(st.get("llm")),
            "detail": st,
        }
    except Exception:
        logging.exception("Health endpoint failure")
        return {"status": "error", "vector_ready": False, "llm_ready": False}

# ======================================================
# UPLOAD → INGEST
# ======================================================
@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        return JSONResponse({"ok": False, "detail": "Only PDF files allowed"}, status_code=400)

    job_id = str(uuid.uuid4())
    dest = os.path.join(DATA_DIR, f"{job_id}_{file.filename}")

    content = await file.read()
    if not content:
        return JSONResponse({"ok": False, "detail": "File empty"}, status_code=400)

    with open(dest, "wb") as f:
        f.write(content)

    with UPLOAD_LOCK:
        UPLOAD_JOBS[job_id] = {
            "job_id": job_id,
            "filename": file.filename,
            "status": "processing",
            "progress": 0,
        }

    def _worker():
        def cb(p, d):
            with UPLOAD_LOCK:
                if job_id in UPLOAD_JOBS:
                    UPLOAD_JOBS[job_id].update({"progress": p, "detail": d})

        try:
            ok = create_vector_store([dest], progress_cb=cb)
            with UPLOAD_LOCK:
                UPLOAD_JOBS[job_id]["status"] = "completed" if ok else "error"
                UPLOAD_JOBS[job_id]["progress"] = 100 if ok else 0
        except Exception as e:
            logging.exception("Ingest error")
            with UPLOAD_LOCK:
                UPLOAD_JOBS[job_id]["status"] = "error"
                UPLOAD_JOBS[job_id]["detail"] = str(e)

        # Warmup embeddings + vectorstore (no LLM, we already hit Groq lazily)
        try:
            threading.Thread(
                target=lambda: rc.warmup_resources(load_llm=False),
                daemon=True
            ).start()
        except Exception:
            logging.exception("Warmup failed")

    threading.Thread(target=_worker, daemon=True).start()

    return {"ok": True, "job_id": job_id, "filename": file.filename}


@app.get("/api/upload/status/{job_id}")
def upload_status(job_id: str):
    with UPLOAD_LOCK:
        job = UPLOAD_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

# ======================================================
# FULLTEXT DOCUMENT ACCESS
# ======================================================
@app.get("/api/source/{doc_id}")
def get_full_source(doc_id: str):
    full_dir = getattr(rc, "FULLTEXT_DIR", "vectorstore/fulltext")
    path = os.path.join(full_dir, f"{doc_id}.txt")
    if not os.path.exists(path):
        raise HTTPException(404, "Fulltext not found")
    with open(path, "r", encoding="utf-8") as f:
        return {"doc_id": doc_id, "text": f.read()}

# ======================================================
# NON-STREAM ASK
# ======================================================
@app.post("/api/ask")
async def ask(question: str = Form(...), mode: str = Form("basic")):
    question = question.strip()
    if not question:
        return {"answer": "Question is empty", "sources": [], "mode": mode}

    if not rc.get_rag_chain(mode):
        return {"answer": "RAG not ready. Upload documents first.", "sources": [], "mode": mode}

    try:
        result = rc.answer_query(question, mode)
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
async def ask_stream(request: Request):
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

    st = rc.status()
    if not st.get("vectorstore") or not st.get("llm"):
        async def _not_ready():
            yield json.dumps({
                "type": "error",
                "message": "RAG not ready"
            }) + "\n"
        return StreamingResponse(_not_ready(), media_type="application/x-ndjson")

    docs_scores = rc.retrieve_with_scores(question)
    docs = [d for d, _ in docs_scores]

    sources_meta = [{
        "filename": (d.metadata or {}).get("filename"),
        "page": (d.metadata or {}).get("page"),
        "doc_id": (d.metadata or {}).get("doc_id"),
        "score": float(score),
    } for d, score in docs_scores]

    try:
        context = rc.build_context_from_docs(
            docs,
            question,
            reserve_for_generation=rc.LLM_MAX_TOKENS
        )
    except Exception:
        context = " ".join((d.page_content or "")[:1000] for d in docs)

    prompt = (
        f"### CONTEXT ###\n{context}\n\n"
        f"### QUESTION ###\n{question}\n\n"
        f"### ANSWER ###\n"
    )

    async def generator():
        # first send sources
        yield json.dumps({
            "type": "sources",
            "sources": sources_meta
        }) + "\n"

        def blocking_groq_stream():
            try:
                for chunk in rc.stream_groq(prompt):
                    if "text" in chunk:
                        yield json.dumps({
                            "type": "partial",
                            "text": chunk["text"]
                        }) + "\n"
                    if "done" in chunk:
                        yield json.dumps({"type": "done"}) + "\n"
                        break
            except Exception as e:
                logging.exception("Streaming error")
                yield json.dumps({
                    "type": "error",
                    "message": str(e)
                }) + "\n"

        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(lambda: list(blocking_groq_stream()))
            for item in fut.result():
                yield item

    return StreamingResponse(
        generator(),
        media_type="application/x-ndjson"
    )

# ======================================================
# FRONTEND SERVING (Vite build)
# ======================================================
if os.path.isdir(FRONTEND_DIST):
    app.mount("/spa", StaticFiles(directory=FRONTEND_DIST), name="spa")

    @app.get("/", include_in_schema=False)
    def serve_index():
        index = os.path.join(FRONTEND_DIST, "index.html")
        if os.path.exists(index):
            return FileResponse(index)
        return JSONResponse({"detail": "Frontend not found"}, status_code=404)
else:
    @app.get("/", include_in_schema=False)
    def root_no_frontend():
        return {"detail": f"Backend running. Frontend not found at {FRONTEND_DIST}"}


@app.get("/_frontend_info", include_in_schema=False)
def frontend_info():
    return {"frontend_dist": FRONTEND_DIST, "exists": os.path.isdir(FRONTEND_DIST)}
