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
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

from rag_chain import Resources
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
MAX_WORKERS = max(1, int(os.getenv("INGEST_MAX_WORKERS", 1)))
RAG_WARMUP_ON_INGEST = os.getenv("RAG_WARMUP_ON_INGEST", "true").lower() in ("1", "true", "yes")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ---------------------------------------------------------
# Optional OCR
# ---------------------------------------------------------
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
        logging.warning("[OCR] OCR not available. Install pdf2image + pytesseract.")
        return docs

    try:
        filename = os.path.basename(pdf_path)
        logging.info("[OCR] Running OCR on %s", filename)

        pages = convert_from_path(pdf_path)
        for i, img in enumerate(pages):
            text = pytesseract.image_to_string(img).strip()
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
        logging.info("[OCR] OCR extracted %d pages", len(docs))

    except Exception:
        logging.exception("[OCR] Failed OCR")

    return docs


# =========================================================
# PDF → CHUNKS
# =========================================================
def process_pdf(pdf_path: str) -> List[Document]:
    filename = os.path.basename(pdf_path)
    logging.info("[INGEST] Processing PDF %s", filename)

    docs: List[Document] = []

    try:
        loader = PyPDFLoader(pdf_path)
        docs = loader.load()

        for d in docs:
            d.metadata = d.metadata or {}
            d.metadata.setdefault("source", pdf_path)
            d.metadata.setdefault("filename", filename)

    except Exception:
        logging.exception("[INGEST] Base PDF loader failed")
        docs = []

    if not docs or sum(len(d.page_content or "") for d in docs) < 400:
        logging.warning("[INGEST] Very little text → using OCR fallback")
        ocr_docs = ocr_pdf(pdf_path)
        if ocr_docs:
            docs = ocr_docs

    if not docs:
        logging.error("[INGEST] No text extracted")
        return []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ".", " ", ""],
    )

    try:
        chunks = splitter.split_documents(docs)
        logging.info("[INGEST] → %d chunks", len(chunks))
    except Exception:
        logging.exception("[INGEST] Split failed")
        return []

    for c in chunks:
        c.metadata = c.metadata or {}
        c.metadata.setdefault("filename", filename)
        c.metadata.setdefault("source", pdf_path)

    return chunks


# =========================================================
# Helper: batch iterator
# =========================================================
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
# VECTORSTORE CREATION WITH GROQ EMBEDDINGS
# =========================================================
def create_vector_store(
    pdf_paths: List[str],
    progress_cb: Optional[Callable[[int, str], None]] = None
) -> bool:

    try:
        if not pdf_paths:
            logging.warning("[INGEST] No PDFs provided")
            return False

        if progress_cb:
            progress_cb(5, "Starting ingestion...")

        os.makedirs(DB_FAISS_BASE, exist_ok=True)
        os.makedirs(FULLTEXT_DIR, exist_ok=True)

        # clear old vectorstore
        if os.path.exists(DB_FAISS_PATH):
            shutil.rmtree(DB_FAISS_PATH, ignore_errors=True)
        if os.path.exists(FULLTEXT_DIR):
            shutil.rmtree(FULLTEXT_DIR, ignore_errors=True)
        os.makedirs(FULLTEXT_DIR, exist_ok=True)

        # Extract text
        all_chunks: List[Document] = []

        if MAX_WORKERS <= 1:
            for p in pdf_paths:
                all_chunks.extend(process_pdf(p))
        else:
            with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(pdf_paths))) as ex:
                futures = {ex.submit(process_pdf, p): p for p in pdf_paths}
                for fut in as_completed(futures):
                    all_chunks.extend(fut.result() or [])

        if not all_chunks:
            logging.error("[INGEST] No chunks extracted")
            return False

        logging.info("[INGEST] Total chunks: %d", len(all_chunks))
        if progress_cb:
            progress_cb(30, "Embedding chunks via Groq...")

        # <-- USE GROQ EMBEDDINGS HERE -->
        embeddings = Resources.embeddings()

        docs_for_index: List[Document] = []
        next_id = 0
        total = len(all_chunks)
        processed = 0

        # Embed in batches
        for batch in _batch_iterable(all_chunks, EMBED_BATCH_SIZE):
            texts = []
            docs_batch = []

            for c in batch:
                metadata = c.metadata or {}
                page = metadata.get("page", "?")
                filename = metadata.get("filename")

                doc_id = f"{filename}_p{page}_i{next_id}"
                next_id += 1

                full_text = c.page_content or ""
                fullpath = os.path.join(FULLTEXT_DIR, f"{doc_id}.txt")

                # store full text for display
                try:
                    with open(fullpath, "w", encoding="utf-8") as f:
                        f.write(full_text)
                except Exception:
                    logging.exception("[INGEST] Failed fulltext write")

                snippet = full_text[:800]
                idx_doc = Document(
                    page_content=snippet,
                    metadata={**metadata, "doc_id": doc_id},
                )
                docs_batch.append(idx_doc)
                texts.append(snippet if snippet else " ")

            # --- GROQ EMBEDDINGS ---
            try:
                emb_batch = embeddings.embed_documents(texts)
            except Exception:
                logging.exception("[EMB] Batch failed, retrying per-document")
                emb_batch = [embeddings.embed_query(t) for t in texts]

            for d, vec in zip(docs_batch, emb_batch):
                docs_for_index.append(d)

            processed += len(batch)
            if progress_cb:
                pct = 30 + int(50 * processed / total)
                progress_cb(pct, f"Embedding {processed}/{total} chunks...")

        # Build FAISS
        try:
            logging.info("[INGEST] Building FAISS index...")
            faiss_store = FAISS.from_documents(docs_for_index, embedding=embeddings)
        except Exception:
            logging.exception("[INGEST] FAISS build failed")
            return False

        # Save vectorstore
        try:
            os.makedirs(DB_FAISS_PATH, exist_ok=True)
            faiss_store.save_local(DB_FAISS_PATH)
        except Exception:
            logging.exception("[INGEST] Failed to save FAISS")
            return False

        # Write manifest
        try:
            manifest = {
                "path": DB_FAISS_PATH,
                "chunks": len(docs_for_index),
                "embed_model": "groq:nomic-embed-text",
                "fulltext_dir": FULLTEXT_DIR,
                "index_type": "flat"
            }
            os.makedirs(os.path.dirname(MANIFEST_PATH), exist_ok=True)
            with tempfile.NamedTemporaryFile("w", delete=False, dir=os.path.dirname(MANIFEST_PATH)) as tf:
                json.dump(manifest, tf)
                temp = tf.name
            os.replace(temp, MANIFEST_PATH)
        except Exception:
            logging.exception("[INGEST] Manifest write failed")

        # Warmup embeddings/vectorstore
        if RAG_WARMUP_ON_INGEST:
            threading.Thread(
                target=lambda: rc.warmup_resources(load_llm=False),
                daemon=True
            ).start()

        if progress_cb:
            progress_cb(95, "Done")

        logging.info("[INGEST] Completed successfully.")
        return True

    except Exception:
        logging.exception("[INGEST] Fatal error")
        return False
