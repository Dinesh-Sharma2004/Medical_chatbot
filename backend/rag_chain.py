# rag_chain.py — Groq + FAISS + Fulltext (Docker-ready)

import os
import json
import logging
import threading
import time
from typing import List, Tuple, Optional, Dict, Any

import httpx
from dotenv import load_dotenv

from langchain_core.prompts import PromptTemplate
from langchain_core.documents import Document
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

# =========================================================
# ENV + CONFIG
# =========================================================
load_dotenv()

DB_FAISS_BASE = os.getenv("DB_FAISS_BASE", "vectorstore")
DB_FAISS_PATH = os.path.join(DB_FAISS_BASE, "db_faiss")
MANIFEST_PATH = os.path.join(DB_FAISS_BASE, "manifest.json")
FULLTEXT_DIR = os.path.join(DB_FAISS_BASE, "fulltext")


GROQ_KEYS = [
    k.strip() for k in os.getenv("GROQ_API_KEYS", "").split(",")
    if k.strip()
]
if not GROQ_KEYS:
    raise ValueError("No GROQ_API_KEYS found in environment.")

# Recommended default model
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_ENDPOINT = os.getenv(
    "GROQ_ENDPOINT",
    "https://api.groq.com/openai/v1/chat/completions"
)

LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", 0.2))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", 256))
RETRIEVER_K = int(os.getenv("RETRIEVER_K", 6))
FETCH_K = int(os.getenv("FETCH_K", 18))
REQUEST_RETRY_BACKOFF = float(os.getenv("REQUEST_RETRY_BACKOFF", 1.0))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# =========================================================
# KEY ROTATOR
# =========================================================
class KeyRotator:
    def __init__(self, keys: List[str]):
        if not keys:
            raise ValueError("GROQ_API_KEYS missing")
        self.keys = keys
        self._idx = 0
        self._lock = threading.Lock()

    def get(self) -> str:
        with self._lock:
            return self.keys[self._idx]

    def rotate(self) -> str:
        with self._lock:
            self._idx = (self._idx + 1) % len(self.keys)
            logging.warning(f"[KEY_ROTATE] Switched to key index {self._idx}")
            return self.keys[self._idx]

# ===========================================
# UPDATED EMBEDDINGS USING GROQ
# ===========================================
import httpx

class GroqEmbeddings:
    """
    Drop-in replacement for HuggingFaceEmbeddings.
    Provides:
    - embed_documents(list[str]) -> List[List[float]]
    - embed_query(str) -> List[float]
    """
    def __init__(self, api_key: str, model: str = "nomic-embed-text"):
        self.api_key = api_key
        self.model = model
        self.url = "https://api.groq.com/v1/embeddings"
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

    def embed_documents(self, texts):
        out = []
        for t in texts:
            out.append(self.embed_query(t))
        return out

    def embed_query(self, text: str):
        payload = {
            "model": self.model,
            "input": text
        }
        try:
            r = httpx.post(self.url, headers=self.headers, json=payload, timeout=30)
            j = r.json()
            return j["data"][0]["embedding"]
        except Exception:
            return [0.0] * 768  # fallback

# =========================================================
# RESOURCES
# =========================================================
class Resources:
    _emb = None
    _vs = None
    _rotator = None
    _lock = threading.Lock()

    @classmethod
    def embeddings(cls):
        if cls._emb is None:
            with cls._lock:
                if cls._emb is None:
                    logging.info("[EMB] Using GROQ embeddings")
                    key = Resources.key()
                    cls._emb = GroqEmbeddings(api_key=key, model="nomic-embed-text")
        return cls._emb


    @classmethod
    def _load_manifest_path(cls) -> str:
        if os.path.exists(MANIFEST_PATH):
            try:
                with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                return meta.get("path", DB_FAISS_PATH)
            except Exception:
                logging.exception("[WARN] Failed to read manifest")
        return DB_FAISS_PATH

    @classmethod
    def vectorstore(cls):
        if cls._vs is None:
            with cls._lock:
                if cls._vs is None:
                    path = cls._load_manifest_path()
                    if not os.path.exists(path):
                        logging.warning(f"[VS] Vectorstore path missing: {path}")
                        return None
                    try:
                        logging.info(f"[VS] Loading FAISS from {path}")
                        cls._vs = FAISS.load_local(
                            path,
                            cls.embeddings(),
                            allow_dangerous_deserialization=True
                        )
                        idx = getattr(cls._vs, "index", None)
                        if idx is not None and hasattr(idx, "nprobe"):
                            idx.nprobe = max(1, min(10, int((getattr(idx, "nlist", 8)) ** 0.5)))
                            logging.info(f"[VS] nprobe set to {idx.nprobe}")
                    except Exception:
                        logging.exception("[ERROR] Could not load FAISS index")
                        cls._vs = None
        return cls._vs

    @classmethod
    def init_groq(cls):
        if cls._rotator is None:
            with cls._lock:
                if cls._rotator is None:
                    cls._rotator = KeyRotator(GROQ_KEYS)
                    logging.info("[GROQ] Key rotator initialized.")
        return cls._rotator

    @classmethod
    def key(cls):
        if cls._rotator is None:
            cls.init_groq()
        return cls._rotator.get()

    @classmethod
    def rotate_key(cls):
        if cls._rotator is None:
            cls.init_groq()
        return cls._rotator.rotate()

# =========================================================
# FULLTEXT HELPERS
# =========================================================
def load_fulltext_for_doc(doc: Document) -> str:
    meta = doc.metadata or {}
    doc_id = meta.get("doc_id")
    if not doc_id:
        return doc.page_content or ""

    fp = os.path.join(FULLTEXT_DIR, f"{doc_id}.txt")
    try:
        if os.path.exists(fp):
            with open(fp, "r", encoding="utf-8") as f:
                return f.read()
    except Exception:
        logging.exception(f"[WARN] Failed fulltext read: {fp}")
    return doc.page_content or ""

def build_context_from_docs(
    docs: List[Document],
    question: str = "",
    reserve_for_generation: int = None
) -> str:
    if not docs:
        return ""
    limit = 6000
    cur = 0
    out: List[str] = []
    for d in docs:
        t = load_fulltext_for_doc(d).strip()
        if not t:
            continue
        if cur + len(t) > limit:
            out.append(t[: limit - cur] + " …")
            break
        out.append(t)
        cur += len(t)
    return "\n\n---\n\n".join(out)

# =========================================================
# RETRIEVAL
# =========================================================
def retrieve_with_scores(q: str, k: int = RETRIEVER_K, fetch_k: int = FETCH_K):
    vs = Resources.vectorstore()
    if not vs:
        return []
    try:
        docs_scores = vs.similarity_search_with_score(q, fetch_k)
        docs_scores.sort(key=lambda x: -x[1])
        return docs_scores[:k]
    except Exception:
        logging.exception("[RETRIEVE] Failed")
        return []

def retrieve(q: str, k: int = RETRIEVER_K, fetch_k: int = FETCH_K):
    return [d for d, _ in retrieve_with_scores(q, k, fetch_k)]

# =========================================================
# PROMPTS
# =========================================================
BASE_RAG_PROMPT = PromptTemplate.from_template("""
You are a factual medical assistant. Use ONLY the provided context.
If information is missing, say: "I don't know from the uploaded documents."

Context:
{context}

Question:
{question}

Answer clearly:
""")

COT_RAG_PROMPT = PromptTemplate.from_template("""
You are a reasoning medical assistant.
Use ONLY the provided context. If missing → say "I don't know from the uploaded documents."

Context:
{context}

Question:
{question}

Explain briefly, then answer:
""")

def build_prompt_from_context(context, question, mode="basic"):
    if (mode or "basic").lower() == "optimized":
        return COT_RAG_PROMPT.format(context=context, question=question)
    return BASE_RAG_PROMPT.format(context=context, question=question)

# =========================================================
# GROQ (Non-Streaming)
# =========================================================
def _groq_payload(prompt: str, stream: bool = False) -> Dict[str, Any]:
    return {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": LLM_TEMPERATURE,
        "max_tokens": LLM_MAX_TOKENS,
        "stream": stream,
    }

def generate_with_groq(prompt: str, retry_on_429: bool = True):
    Resources.init_groq()
    key = Resources.key()
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    try:
        resp = httpx.post(GROQ_ENDPOINT, json=_groq_payload(prompt), headers=headers, timeout=90)
    except Exception as e:
        logging.exception("[GROQ] Request failed")
        return None, str(e)

    if resp.status_code == 429 and retry_on_429:
        Resources.rotate_key()
        time.sleep(REQUEST_RETRY_BACKOFF)
        return generate_with_groq(prompt, retry_on_429=False)

    if resp.status_code >= 400:
        return None, f"HTTP {resp.status_code}: {resp.text}"

    try:
        j = resp.json()
        if "choices" in j and j["choices"]:
            msg = j["choices"][0]["message"].get("content")
            return msg, None
        return j.get("text"), None
    except Exception:
        logging.exception("[GROQ] JSON parse error")
        return None, resp.text

# =========================================================
# GROQ STREAMING (SSE)
# =========================================================
def stream_groq(prompt: str):
    """
    Yields dicts:
      {"text": "..."}  for content deltas
      {"done": True}   when streaming is finished
    """
    Resources.init_groq()
    key = Resources.key()

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    payload = _groq_payload(prompt, stream=True)

    client = httpx.Client(timeout=None)

    def _post_with_key(api_key: str):
        h = dict(headers)
        h["Authorization"] = f"Bearer {api_key}"
        return client.post(GROQ_ENDPOINT, headers=h, json=payload)

    resp = _post_with_key(key)

    if resp.status_code == 429:
        Resources.rotate_key()
        time.sleep(REQUEST_RETRY_BACKOFF)
        resp = _post_with_key(Resources.key())

    resp.raise_for_status()

    # SSE stream: lines such as "data: {...}"
    for line in resp.iter_lines():
        if not line:
            continue

        if not line.startswith("data:"):
            continue

        data_str = line[len("data:"):].strip()

        if data_str == "[DONE]":
            yield {"done": True}
            break

        try:
            payload = json.loads(data_str)
            delta = payload["choices"][0]["delta"].get("content")
            if delta:
                yield {"text": delta}
        except Exception:
            continue

# =========================================================
# MAIN RAG CHAIN
# =========================================================
def get_rag_chain(mode: str = "basic"):
    return (Resources.vectorstore() is not None) and (Resources.init_groq() is not None)

def answer_query(question: str, mode: str = "basic") -> Dict[str, Any]:
    if Resources.vectorstore() is None:
        return {"error": "No vectorstore", "answer": None, "sources": []}

    docs_scores = retrieve_with_scores(question)
    docs = [d for d, _ in docs_scores]

    sources = [{
        "source": (d.metadata or {}).get("source"),
        "page": (d.metadata or {}).get("page"),
        "filename": (d.metadata or {}).get("filename"),
        "doc_id": (d.metadata or {}).get("doc_id"),
        "score": float(score),
    } for d, score in docs_scores]

    context = build_context_from_docs(docs, question)
    prompt = build_prompt_from_context(context, question, mode)

    ans, err = generate_with_groq(prompt)
    if err:
        return {"error": err, "answer": None, "sources": sources}
    return {"answer": ans, "sources": sources}

# =========================================================
# STATUS + WARMUP
# =========================================================
def status():
    info = {
        "embeddings": False,
        "vectorstore": False,
        "llm": False,
        "provider": "groq",
    }
    try:
        info["embeddings"] = Resources.embeddings() is not None
    except Exception:
        info["embeddings"] = False
    try:
        info["vectorstore"] = Resources.vectorstore() is not None
    except Exception:
        info["vectorstore"] = False
    try:
        info["llm"] = Resources.init_groq() is not None
    except Exception:
        info["llm"] = False
    return info

def warmup_resources(load_llm: bool = True):
    try:
        Resources.embeddings()
        Resources.vectorstore()
        if load_llm:
            Resources.init_groq()
        logging.info("[WARMUP] Completed.")
    except Exception:
        logging.exception("[WARMUP] Failure.")

__all__ = [
    "retrieve",
    "retrieve_with_scores",
    "Resources",
    "status",
    "warmup_resources",
    "answer_query",
    "stream_groq",
    "build_context_from_docs",
    "GROQ_MODEL",
    "GROQ_ENDPOINT",
    "FULLTEXT_DIR",
    "LLM_MAX_TOKENS",
]
