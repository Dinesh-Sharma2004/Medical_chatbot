# rag_chain.py (Ollama + FAISS + Fulltext hybrid)
import os
import json
import logging
import threading
from typing import List, Tuple, Optional, Dict, Any

from dotenv import load_dotenv
import torch

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_core.documents import Document

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.llms import Ollama
from langchain_community.llms.huggingface_pipeline import HuggingFacePipeline
from transformers import pipeline, AutoTokenizer, AutoModelForCausalLM

load_dotenv()

# ============================
# CONFIG
# ============================
DB_FAISS_BASE = os.getenv("DB_FAISS_BASE", "vectorstore")
DB_FAISS_PATH_DEFAULT = os.path.join(DB_FAISS_BASE, "db_faiss")
MANIFEST_PATH = os.path.join(DB_FAISS_BASE, "manifest.json")
FULLTEXT_DIR = os.path.join(DB_FAISS_BASE, "fulltext")

EMBED_MODEL = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "phi3")  # default local LLM
MODEL_NAME = os.getenv("MODEL_NAME", "EleutherAI/gpt-neo-125M")

LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", 0.2))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", 256))

RETRIEVER_K = int(os.getenv("RETRIEVER_K", 6))
FETCH_K = int(os.getenv("FETCH_K", 18))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


# ============================
# THREAD-SAFE RESOURCE MANAGER
# ============================
class Resources:
    _lock = threading.Lock()
    _emb = None
    _vs = None
    _llm = None
    _tokenizer = None
    _use_ollama = True

    @classmethod
    def embeddings(cls):
        if cls._emb is None:
            with cls._lock:
                if cls._emb is None:
                    logging.info(f"[INFO] Loading embeddings... ({EMBED_MODEL})")
                    cls._emb = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
        return cls._emb

    @classmethod
    def _load_manifest_path(cls) -> str:
        if os.path.exists(MANIFEST_PATH):
            try:
                with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                return meta.get("path") or DB_FAISS_PATH_DEFAULT
            except Exception:
                logging.exception("[WARN] Failed reading manifest; using default path")
        return DB_FAISS_PATH_DEFAULT

    @classmethod
    def vectorstore(cls):
        if cls._vs is None:
            with cls._lock:
                if cls._vs is None:
                    path = cls._load_manifest_path()
                    if os.path.exists(path):
                        try:
                            logging.info(f"[INFO] Loading FAISS index: {path}")
                            cls._vs = FAISS.load_local(
                                path,
                                cls.embeddings(),
                                allow_dangerous_deserialization=True,
                            )
                            index = getattr(cls._vs, "index", None)
                            if index is not None and hasattr(index, "nprobe"):
                                nprobe = max(1, min(16, int(getattr(index, "nlist", 8) ** 0.5)))
                                index.nprobe = nprobe
                                logging.info(f"[INFO] Set FAISS index.nprobe={nprobe}")
                        except Exception:
                            logging.error("[ERROR] Could not load FAISS index", exc_info=True)
                    else:
                        logging.warning(f"[WARN] Vectorstore path not found: {path}")
        return cls._vs

    @classmethod
    def llm(cls):
        if cls._llm is None:
            with cls._lock:
                if cls._llm is None:
                    try:
                        logging.info(f"[INFO] Connecting to Ollama model: {OLLAMA_MODEL}")
                        cls._llm = Ollama(
                            model=OLLAMA_MODEL,
                            temperature=LLM_TEMPERATURE,
                            num_ctx=4096,
                        )
                        cls._use_ollama = True
                        logging.info("[INFO] Ollama LLM ready.")
                    except Exception as e:
                        logging.warning(f"[WARN] Ollama not available ({e}); falling back to HF pipeline.")
                        cls._use_ollama = False
                        cls._llm = cls._load_hf_fallback()
        return cls._llm

    @classmethod
    def _load_hf_fallback(cls):
        """Fallback: Hugging Face model pipeline for CPU testing"""
        try:
            device = 0 if torch.cuda.is_available() else -1
            tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
            model = AutoModelForCausalLM.from_pretrained(MODEL_NAME)
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token
            gen_pipe = pipeline(
                "text-generation",
                model=model,
                tokenizer=tokenizer,
                device=device,
                max_new_tokens=LLM_MAX_TOKENS,
                temperature=LLM_TEMPERATURE,
                do_sample=False,
            )
            cls._tokenizer = tokenizer
            return HuggingFacePipeline(pipeline=gen_pipe)
        except Exception:
            logging.error("[ERROR] Fallback LLM failed", exc_info=True)
            return None


# ============================
# PROMPTS
# ============================
BASE_RAG_PROMPT = PromptTemplate.from_template("""
You are a factual medical assistant. Use ONLY the provided context.
If you do not find an answer, reply: "I don't know from the uploaded documents."

Context:
{context}

Question:
{question}

Answer concisely and cite relevant page numbers if possible:
""")

COT_RAG_PROMPT = PromptTemplate.from_template("""
You are a reasoning-based medical assistant.
Use ONLY the provided context. If missing, say "I don't know from the uploaded documents."

Context:
{context}

Question:
{question}

Explain briefly, then give your final answer:
""")


# ============================
# FULLTEXT + CONTEXT HELPERS
# ============================
def load_fulltext_for_doc(doc: Document) -> str:
    meta = doc.metadata or {}
    doc_id = meta.get("doc_id")
    if not doc_id:
        return doc.page_content or ""
    path = os.path.join(FULLTEXT_DIR, f"{doc_id}.txt")
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
    except Exception:
        logging.exception(f"[WARN] Failed to read fulltext for doc_id={doc_id}")
    return doc.page_content or ""


def build_context_from_docs(docs: List[Document], question: str = "", reserve_for_generation: int = None) -> str:
    if not docs:
        return ""
    reserve = reserve_for_generation or LLM_MAX_TOKENS
    max_chars = 6000
    pieces, total = [], 0
    for d in docs:
        text = load_fulltext_for_doc(d).strip()
        if not text:
            continue
        if total + len(text) > max_chars:
            pieces.append(text[: max_chars - total] + " ...")
            break
        pieces.append(text)
        total += len(text)
    return "\n\n---\n\n".join(pieces)


# ============================
# RETRIEVAL
# ============================
def retrieve_with_scores(question: str, k: int = RETRIEVER_K, fetch_k: int = FETCH_K):
    vs = Resources.vectorstore()
    if not vs:
        return []
    try:
        docs_scores = vs.similarity_search_with_score(question, fetch_k)
        docs_scores.sort(key=lambda x: -x[1])
        return docs_scores[:k]
    except Exception:
        logging.error("[ERROR] Retrieval failed", exc_info=True)
        return []


def retrieve(question: str, k: int = RETRIEVER_K, fetch_k: int = FETCH_K):
    return [d for d, _ in retrieve_with_scores(question, k, fetch_k)]


# ============================
# CHAINS
# ============================
def build_chain(prompt: PromptTemplate):
    llm = Resources.llm()
    if llm is None:
        return None

    def context_builder(x):
        q = x.get("question", "")
        docs = retrieve(q)
        ctx = build_context_from_docs(docs, q, LLM_MAX_TOKENS)
        return ctx

    return (
        RunnablePassthrough.assign(context=context_builder)
        .assign(
            answer=(
                {
                    "context": lambda x: x["context"],
                    "question": lambda x: x["question"],
                }
                | prompt
                | llm
                | StrOutputParser()
            )
        )
    )


def get_rag_chain(mode="basic"):
    if Resources.vectorstore() is None:
        logging.warning("[WARN] No vectorstore loaded.")
        return None
    if Resources.llm() is None:
        logging.warning("[WARN] LLM unavailable.")
        return None
    mode = (mode or "basic").lower()
    if mode == "optimized":
        logging.info("[INFO] Using optimized RAG (CoT mode)")
        return build_chain(COT_RAG_PROMPT)
    logging.info("[INFO] Using basic RAG")
    return build_chain(BASE_RAG_PROMPT)


def answer_query(question: str, mode="basic"):
    chain = get_rag_chain(mode)
    if not chain:
        return {"error": "RAG not ready", "answer": None, "sources": []}
    docs_scores = retrieve_with_scores(question)
    docs = [d for d, _ in docs_scores]
    sources = []
    for d, score in docs_scores:
        meta = d.metadata or {}
        sources.append(
            {
                "source": meta.get("source"),
                "page": meta.get("page"),
                "filename": meta.get("filename"),
                "doc_id": meta.get("doc_id"),
                "score": float(score),
            }
        )
    try:
        ans = chain.run({"question": question})
    except Exception as e:
        logging.error("[ERROR] Chain failed", exc_info=True)
        return {"error": str(e), "answer": None, "sources": sources}
    return {"answer": ans, "sources": sources}


# ============================
# STATUS & WARMUP
# ============================
def status():
    info = {"embeddings": False, "vectorstore": False, "llm": False, "use_ollama": Resources._use_ollama}
    try:
        info["embeddings"] = Resources.embeddings() is not None
        info["vectorstore"] = Resources.vectorstore() is not None
        info["llm"] = Resources.llm() is not None
    except Exception:
        logging.exception("[STATUS] Failed to collect status")
    return info


def warmup_resources():
    try:
        Resources.embeddings()
        Resources.vectorstore()
        Resources.llm()
        logging.info("[WARMUP] Resources initialized.")
    except Exception:
        logging.exception("[WARMUP] Failed during warmup")


__all__ = [
    "Resources",
    "status",
    "warmup_resources",
    "get_rag_chain",
    "retrieve",
    "retrieve_with_scores",
    "build_context_from_docs",
    "answer_query",
]
