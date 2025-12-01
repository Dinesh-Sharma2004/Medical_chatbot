# backend/main.py
import os
import threading
import json, asyncio, httpx, logging
import uuid
import time
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from transformers import TextIteratorStreamer
import torch

from ingest import create_vector_store
import rag_chain as rc  # RAG chain logic

# ==================================================
# SETUP
# ==================================================
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BACKEND_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DEFAULT_FRONTEND_DIST = os.path.normpath(os.path.join(BACKEND_DIR, "..", "frontend", "dist"))
FRONTEND_DIST = os.getenv("FRONTEND_DIST", DEFAULT_FRONTEND_DIST)

app = FastAPI(title="MediBot Backend (Optimized RAG)", version="3.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================================================
# UPLOAD JOB STATE
# ==================================================
UPLOAD_JOBS: Dict[str, Dict[str, Any]] = {}
UPLOAD_JOBS_LOCK = threading.Lock()
UPLOAD_THREADS: Dict[str, threading.Thread] = {}


class AskResponseSource(BaseModel):
    title: Optional[str] = None
    snippet: Optional[str] = None
    doc_id: Optional[str] = None


class AskResponse(BaseModel):
    answer: str
    sources: List[AskResponseSource] = []
    mode: str


class AskStreamRequest(BaseModel):
    question: str
    mode: Optional[str] = "basic"


chat_history: List = []

# ==================================================
# HEALTH
# ==================================================
@app.get("/api/health")
def health():
    try:
        st = rc.status() if hasattr(rc, "status") else {}
        return {
            "status": "ok",
            "vector_ready": bool(st.get("vectorstore")),
            "llm_ready": bool(st.get("llm")),
            "detail": st,
        }
    except Exception:
        logging.exception("Health check failed")
        return {"status": "error", "vector_ready": False, "llm_ready": False}


# ==================================================
# UPLOAD & INGEST
# ==================================================
@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        return JSONResponse({"ok": False, "detail": "Only PDF files allowed"}, status_code=400)

    job_id = str(uuid.uuid4())
    dest = os.path.join(DATA_DIR, f"{job_id}_{file.filename}")
    content = await file.read()
    if not content:
        return JSONResponse({"ok": False, "detail": "Empty file"}, status_code=400)
    with open(dest, "wb") as f:
        f.write(content)

    with UPLOAD_JOBS_LOCK:
        UPLOAD_JOBS[job_id] = {"job_id": job_id, "filename": file.filename, "status": "processing", "progress": 0}

    def _worker():
        def cb(p, d):
            with UPLOAD_JOBS_LOCK:
                if job_id in UPLOAD_JOBS:
                    UPLOAD_JOBS[job_id].update({"progress": p, "detail": d})

        try:
            success = create_vector_store([dest], progress_cb=cb)
            with UPLOAD_JOBS_LOCK:
                UPLOAD_JOBS[job_id]["status"] = "completed" if success else "error"
                UPLOAD_JOBS[job_id]["progress"] = 100 if success else 0
                UPLOAD_JOBS[job_id]["detail"] = "Ingestion done" if success else "Failed"
        except Exception as e:
            logging.exception("Ingest error")
            with UPLOAD_JOBS_LOCK:
                UPLOAD_JOBS[job_id]["status"] = "error"
                UPLOAD_JOBS[job_id]["detail"] = str(e)

        try:
            threading.Thread(target=lambda: rc.warmup_resources(load_llm=False), daemon=True).start()
        except Exception:
            logging.exception("Warmup failed")

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    UPLOAD_THREADS[job_id] = t
    return {"ok": True, "job_id": job_id, "filename": file.filename}


@app.get("/api/upload/status/{job_id}")
def upload_status(job_id: str):
    with UPLOAD_JOBS_LOCK:
        job = UPLOAD_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# ==================================================
# FULLTEXT RETRIEVAL (NEW)
# ==================================================
@app.get("/api/source/{doc_id}")
def get_full_source(doc_id: str):
    """Fetch full text of a stored chunk on disk."""
    fulltext_dir = getattr(rc, "FULLTEXT_DIR", "vectorstore/fulltext")
    path = os.path.join(fulltext_dir, f"{doc_id}.txt")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Not found")
    with open(path, "r", encoding="utf-8") as f:
        return {"doc_id": doc_id, "text": f.read()}


# ==================================================
# NON-STREAMING ASK (NEW)
# ==================================================
@app.post("/api/ask", response_model=AskResponse)
async def ask(question: str = Form(...), mode: str = Form("basic")):
    question = question.strip()
    if not question:
        return AskResponse(answer="Question is empty.", sources=[], mode=mode)

    mode = mode.lower()
    chain = rc.get_rag_chain(mode)
    if not chain:
        return AskResponse(answer="RAG not ready. Upload documents first.", sources=[], mode=mode)

    try:
        result = rc.answer_query(question, mode=mode)
    except Exception as e:
        logging.exception("ask() failed")
        return AskResponse(answer=f"Error: {e}", sources=[], mode=mode)

    answer = result.get("answer", "I could not find an answer.")
    srcs = result.get("sources", [])

    # Format citations
    formatted = []
    for i, s in enumerate(srcs, start=1):
        doc_id = s.get("doc_id")
        snippet = s.get("snippet") or ""
        title = s.get("filename") or f"Doc{i}"
        formatted.append(
            AskResponseSource(
                title=f"[{i}] {title}",
                snippet=snippet[:250] + "...",
                doc_id=doc_id
            )
        )

    # Clean + format answer into readable paragraphs
    answer_clean = " ".join(answer.split())
    paragraphs = []
    while len(answer_clean) > 500:
        cut = answer_clean[:500].rfind(".")
        if cut == -1:
            cut = 500
        paragraphs.append(answer_clean[:cut + 1])
        answer_clean = answer_clean[cut + 1:].strip()
    if answer_clean:
        paragraphs.append(answer_clean)
    formatted_answer = "\n\n".join(paragraphs)

    # Append citations section
    if formatted:
        formatted_answer += "\n\nSources:\n" + "\n".join(
            f"[{i+1}] {s.title} (doc_id={s.doc_id})" for i, s in enumerate(formatted)
        )

    return AskResponse(answer=formatted_answer, sources=formatted, mode=mode)


# ==================================================
# STREAMING ASK (unchanged)
# ==================================================
@app.post("/api/ask/stream")
async def ask_stream(req: Request):
    data = await req.json()
    question = data.get("question", "").strip()
    mode = (data.get("mode") or "basic").lower()

    if not question:
        async def _err():
            yield json.dumps({"type": "error", "message": "Empty question"}) + "\n"
        return StreamingResponse(_err(), media_type="application/x-ndjson")

    try:
        st = rc.status()
        ready = st.get("vectorstore", False)
        chain_ready = rc.get_rag_chain(mode) if ready else None
    except Exception:
        chain_ready = None

    if not chain_ready:
        async def _not_ready():
            yield json.dumps({"type": "error", "message": "RAG not ready"}) + "\n"
        return StreamingResponse(_not_ready(), media_type="application/x-ndjson")

    # Retrieve relevant context
    docs_scores = rc.retrieve_with_scores(question)
    docs = [d for d, _ in docs_scores]
    sources_meta = [
        {
            "filename": (d.metadata or {}).get("filename"),
            "page": (d.metadata or {}).get("page"),
            "doc_id": (d.metadata or {}).get("doc_id"),
            "score": float(score),
        }
        for d, score in docs_scores
    ]

    # Build context for RAG prompt
    try:
        context = rc.build_context_from_docs(docs, question, reserve_for_generation=rc.LLM_MAX_TOKENS)
    except Exception:
        context = rc.format_docs(docs)

    # Create final RAG prompt
    prompt_text = f"### CONTEXT ###\n{context}\n\n### QUESTION ###\n{question}\n\n### ANSWER ###\n"

    # Stream from Ollama if available
    if rc.Resources._use_ollama:
        async def stream_from_ollama():
            async with httpx.AsyncClient(timeout=None) as client:
                yield json.dumps({"type": "sources", "sources": sources_meta}) + "\n"
                try:
                    async with client.stream(
                        "POST",
                        "http://localhost:11434/api/generate",
                        json={
                            "model": rc.OLLAMA_MODEL,
                            "prompt": prompt_text,
                            "stream": True,
                            "options": {
                                "temperature": rc.LLM_TEMPERATURE,
                                "num_predict": rc.LLM_MAX_TOKENS
                            }
                        },
                    ) as response:
                        async for line in response.aiter_lines():
                            if not line.strip():
                                continue
                            try:
                                data = json.loads(line)
                                if data.get("done"):
                                    yield json.dumps({"type": "done"}) + "\n"
                                    break
                                chunk = data.get("response", "")
                                if chunk:
                                    yield json.dumps({"type": "partial", "text": chunk}) + "\n"
                            except Exception:
                                continue
                except Exception as e:
                    logging.exception("[STREAM] Ollama stream failed: %s", e)
                    yield json.dumps({"type": "error", "message": str(e)}) + "\n"

        return StreamingResponse(stream_from_ollama(), media_type="application/x-ndjson")

    # Fallback to HF LLM (non-streaming)
    async def fallback_sync():
        try:
            yield json.dumps({"type": "sources", "sources": sources_meta}) + "\n"
            res = rc.answer_query(question, mode)
            yield json.dumps({"type": "done", "text": res.get("answer", ""), "sources": sources_meta}) + "\n"
        except Exception as e:
            yield json.dumps({"type": "error", "message": str(e)}) + "\n"

    return StreamingResponse(fallback_sync(), media_type="application/x-ndjson")

# ==================================================
# FRONTEND ROUTES
# ==================================================
if os.path.isdir(FRONTEND_DIST):
    app.mount("/spa", StaticFiles(directory=FRONTEND_DIST), name="spa")

    @app.get("/", include_in_schema=False)
    def serve_index():
        path = os.path.join(FRONTEND_DIST, "index.html")
        if os.path.exists(path):
            return FileResponse(path)
        return JSONResponse({"detail": "Frontend not found"}, status_code=404)
else:
    @app.get("/", include_in_schema=False)
    def root_only():
        return {"detail": f"Backend running. Frontend not found at {FRONTEND_DIST}"}


@app.get("/_frontend_info", include_in_schema=False)
def frontend_info():
    return {"frontend_dist": FRONTEND_DIST, "exists": os.path.isdir(FRONTEND_DIST)}
