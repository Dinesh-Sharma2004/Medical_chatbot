# ingest.py — PDF → Chunks → Embeddings → FAISS store (Docker-safe)

import os
import shutil
import json
import logging
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Callable, Optional, Dict, Any

from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

import rag_chain as rc

# =========================================================
# CONFIG
# =========================================================
load_dotenv()

DB_FAISS_BASE = os.getenv("DB_FAISS_BASE", "vectorstore")
DB_FAISS_PATH = os.path.join(DB_FAISS_BASE, "db_faiss")
MANIFEST_PATH = os.path.join(DB_FAISS_BASE, "manifest.json")
FULLTEXT_DIR = os.path.join(DB_FAISS_BASE, "fulltext")

CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", 800))
CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", 120))
EMBED_BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", 32))
EMBED_MODEL = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
MAX_WORKERS = max(1, int(os.getenv("INGEST_MAX_WORKERS", 1)))
RAG_WARMUP_ON_INGEST = os.getenv("RAG_WARMUP_ON_INGEST", "true").lower() in ("1", "true", "yes")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Optional OCR
try:
    from pdf2image import convert_from_path
    import pytesseract
    OCR_AVAILABLE = True
except Exception as e:
    OCR_AVAILABLE = False
    _ocr_err = e

# =========================================================
# OCR
# =========================================================
def ocr_pdf(pdf_path: str) -> List[Document]:
    docs: List[Document] = []
    if not OCR_AVAILABLE:
        logging.warning(
            "[OCR] OCR not available. Install pdf2image + pytesseract. "
            f"Import error: {_ocr_err}"
        )
        return docs
    try:
        filename = os.path.basename(pdf_path)
        logging.info("[OCR] Running OCR on %s", filename)
        pages = convert_from_path(pdf_path)
        for i, img in enumerate(pages):
            text = pytesseract.image_to_string(img)
            text = (text or "").strip()
            if not text:
                continue
            docs.append(
                Document(
                    page_content=text,
                    metadata={
                        "source": pdf_path,
                        "filename": filename,
                        "page": i + 1,
                        "ocr": True,
                    },
                )
            )
        logging.info("[OCR] Extracted OCR text from %d page(s) in %s", len(docs), filename)
    except Exception:
        logging.exception("[OCR] Failed OCR on %s", pdf_path)
    return docs

# =========================================================
# PDF → CHUNKS
# =========================================================
def process_pdf(pdf_path: str) -> List[Document]:
    filename = os.path.basename(pdf_path)
    logging.info("[INGEST] Processing PDF: %s", filename)

    docs: List[Document] = []

    try:
        loader = PyPDFLoader(pdf_path)
        docs = loader.load()
        for d in docs:
            if not isinstance(d.metadata, dict):
                d.metadata = {}
            d.metadata.setdefault("source", pdf_path)
            d.metadata.setdefault("filename", filename)
        total_chars = sum(len(d.page_content or "") for d in docs)
        logging.info("[INGEST] Base loader extracted ~%d chars from %s", total_chars, filename)
    except Exception:
        logging.exception("[INGEST] PyPDFLoader failed for %s", filename)
        docs = []

    if not docs or sum(len(d.page_content or "") for d in docs) < 400:
        logging.warning("[INGEST] Very little text from %s, trying OCR...", filename)
        ocr_docs = ocr_pdf(pdf_path)
        if ocr_docs:
            docs = ocr_docs

    if not docs:
        logging.error("[INGEST] No usable text from %s, skipping.", filename)
        return []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ".", " ", ""],
    )

    try:
        chunks = splitter.split_documents(docs)
        logging.info("[INGEST] → %d chunks from %s", len(chunks), filename)
        for c in chunks:
            if not isinstance(c.metadata, dict):
                c.metadata = {}
            c.metadata.setdefault("filename", filename)
            c.metadata.setdefault("source", pdf_path)
    except Exception:
        logging.exception("[INGEST] Failed splitting documents for %s", filename)
        return []

    return chunks

def _batch_iterable(iterable, batch_size):
    it = iter(iterable)
    while True:
        batch = []
        try:
            for _ in range(batch_size):
                batch.append(next(it))
        except StopIteration:
            if batch:
                yield batch
            break
        yield batch

# =========================================================
# VECTORSTORE CREATION
# =========================================================
def create_vector_store(
    pdf_paths: List[str],
    progress_cb: Optional[Callable[[int, str], None]] = None,
) -> bool:
    try:
        if not pdf_paths:
            logging.warning("[INGEST] No PDF paths given.")
            return False

        if progress_cb:
            progress_cb(5, "Starting ingestion...")

        # Ensure directories exist
        os.makedirs(DB_FAISS_BASE, exist_ok=True)
        os.makedirs(FULLTEXT_DIR, exist_ok=True)

        # Clear *only* FAISS and fulltext inside vectorstore volume
        if os.path.exists(DB_FAISS_PATH):
            logging.info("[INGEST] Removing old FAISS path → %s", DB_FAISS_PATH)
            shutil.rmtree(DB_FAISS_PATH, ignore_errors=True)
        if os.path.exists(FULLTEXT_DIR):
            logging.info("[INGEST] Clearing FULLTEXT_DIR → %s", FULLTEXT_DIR)
            shutil.rmtree(FULLTEXT_DIR, ignore_errors=True)
            os.makedirs(FULLTEXT_DIR, exist_ok=True)

        if progress_cb:
            progress_cb(10, "Extracting text from PDFs...")

        all_chunks: List[Document] = []

        if MAX_WORKERS <= 1:
            for p in pdf_paths:
                chunks = process_pdf(p)
                if chunks:
                    all_chunks.extend(chunks)
        else:
            with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(pdf_paths))) as executor:
                futures = {executor.submit(process_pdf, p): p for p in pdf_paths}
                for fut in as_completed(futures):
                    p = futures[fut]
                    try:
                        chunks = fut.result()
                        if chunks:
                            all_chunks.extend(chunks)
                    except Exception:
                        logging.exception("[INGEST] Error while processing %s", p)

        if not all_chunks:
            logging.error("[INGEST] No chunks produced from any PDF.")
            return False

        logging.info("[INGEST] Total chunks: %d", len(all_chunks))
        if progress_cb:
            progress_cb(30, f"Total chunks: {len(all_chunks)} - embedding...")

        logging.info("[INGEST] Loading embeddings: %s", EMBED_MODEL)
        embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)

        docs_for_index: List[Document] = []
        next_id = 0
        total = len(all_chunks)
        processed = 0

        for batch in _batch_iterable(all_chunks, EMBED_BATCH_SIZE):
            texts: List[str] = []
            docs_batch: List[Document] = []

            for c in batch:
                metadata = c.metadata or {}
                page = metadata.get("page", "?")
                filename = metadata.get("filename") or os.path.basename(metadata.get("source", ""))
                doc_id = f"{filename}_p{page}_i{next_id}"
                next_id += 1

                full_text = c.page_content or ""
                full_path = os.path.join(FULLTEXT_DIR, f"{doc_id}.txt")
                try:
                    with open(full_path, "w", encoding="utf-8") as f:
                        f.write(full_text)
                except Exception:
                    logging.exception("[INGEST] Failed writing fulltext for %s", doc_id)

                snippet = full_text[:800]
                idx_meta: Dict[str, Any] = dict(metadata)
                idx_meta["doc_id"] = doc_id
                idx_meta.setdefault("filename", filename)
                idx_doc = Document(page_content=snippet, metadata=idx_meta)
                docs_batch.append(idx_doc)
                texts.append(snippet if snippet else " ")

            try:
                emb_batch = embeddings.embed_documents(texts)
            except Exception:
                logging.exception("[EMB] Batch failed, trying per-document")
                emb_batch = []
                for t in texts:
                    try:
                        emb_batch.append(embeddings.embed_query(t))
                    except Exception:
                        emb_batch.append([0.0] * 384)

            for d, vec in zip(docs_batch, emb_batch):
                docs_for_index.append(d)

            processed += len(batch)
            if progress_cb:
                pct = 30 + int(50 * processed / total)
                progress_cb(pct, f"Embedding {processed}/{total} chunks...")

        del all_chunks

        # Build FAISS
        try:
            logging.info("[INGEST] Building FAISS vectorstore...")
            faiss_store = FAISS.from_documents(docs_for_index, embedding=embeddings)
        except Exception:
            logging.exception("[INGEST] Failed building FAISS vectorstore")
            return False

        # Save FAISS
        try:
            logging.info("[INGEST] Saving FAISS to %s", DB_FAISS_PATH)
            os.makedirs(DB_FAISS_PATH, exist_ok=True)
            faiss_store.save_local(DB_FAISS_PATH)
        except Exception:
            logging.exception("[INGEST] Failed saving FAISS store")
            return False

        try:
            files = os.listdir(DB_FAISS_PATH)
            if not files:
                logging.error("[INGEST] FAISS directory empty at %s", DB_FAISS_PATH)
                return False
            logging.info("[INGEST] FAISS saved. Sample files: %s", files[:10])
        except Exception:
            logging.exception("[INGEST] Could not list FAISS directory")
            return False

        # Manifest
        try:
            manifest = {
                "path": DB_FAISS_PATH,
                "chunks": len(docs_for_index),
                "embed_model": EMBED_MODEL,
                "fulltext_dir": FULLTEXT_DIR,
                "index_type": "flat",
            }
            dirpath = os.path.dirname(MANIFEST_PATH)
            os.makedirs(dirpath, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", delete=False, dir=dirpath, encoding="utf-8") as tf:
                json.dump(manifest, tf)
                tempname = tf.name
            os.replace(tempname, MANIFEST_PATH)
            logging.info("[INGEST] Manifest written to %s", MANIFEST_PATH)

            if RAG_WARMUP_ON_INGEST:
                def _warm():
                    try:
                        rc.warmup_resources(load_llm=False)
                    except Exception:
                        logging.exception("[INGEST] Warmup failed after manifest")
                threading.Thread(target=_warm, daemon=True).start()
            else:
                logging.info("[INGEST] Skipping warmup after ingest.")

        except Exception:
            logging.exception("[INGEST] Failed writing manifest")

        if progress_cb:
            progress_cb(95, "FAISS saved. Finalizing...")

        logging.info("[INGEST] Ingestion finished successfully.")
        return True

    except Exception:
        logging.exception("[INGEST] Unexpected failure in create_vector_store")
        return False
