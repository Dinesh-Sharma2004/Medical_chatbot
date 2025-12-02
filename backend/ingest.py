# ingest.py
import os
import shutil
import json
import logging
import tempfile
import threading
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Callable, Optional, Dict, Any

from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_core.documents import Document

# Optional OCR imports
try:
    from pdf2image import convert_from_path
    import pytesseract

    OCR_AVAILABLE = True
except Exception as e:
    OCR_AVAILABLE = False
    ocr_import_error = e

# Optional low-level faiss (for IVFPQ quantization)
try:
    import faiss  # type: ignore
    FAISS_NATIVE_AVAILABLE = True
except Exception:
    faiss = None
    FAISS_NATIVE_AVAILABLE = False

# Import rag_chain to trigger warmup after manifest write (warmup function should exist)
import rag_chain as rc

# --- CONFIGURATION ---
load_dotenv()

DB_FAISS_BASE = os.getenv("DB_FAISS_BASE", "vectorstore")
DB_FAISS_PATH = os.path.join(DB_FAISS_BASE, "db_faiss")
MANIFEST_PATH = os.path.join(DB_FAISS_BASE, "manifest.json")
FULLTEXT_DIR = os.path.join(DB_FAISS_BASE, "fulltext")

# Ingest tuning for low-resource environments
CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", 800))
CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", 120))

EMBED_BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", 32))
EMBED_MODEL = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

MAX_WORKERS = max(1, int(os.getenv("INGEST_MAX_WORKERS", 1)))

# Respect ingest-time warmup toggle; default true
RAG_WARMUP_ON_INGEST = os.getenv("RAG_WARMUP_ON_INGEST", "true").lower() in ("1", "true", "yes")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


def ocr_pdf(pdf_path: str) -> List[Document]:
    """
    Fallback OCR for scanned / image-only PDFs.
    Returns list[Document]
    """
    docs: List[Document] = []

    if not OCR_AVAILABLE:
        logging.warning(
            "[OCR] OCR not available. Install pdf2image + pytesseract. "
            f"Import error: {ocr_import_error}"
        )
        return docs

    try:
        filename = os.path.basename(pdf_path)
        logging.info("[OCR] Running OCR on %s ...", filename)

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


def process_pdf(pdf_path: str) -> List[Document]:
    """
    Load and split a single PDF into chunk Documents.
    """
    filename = os.path.basename(pdf_path)
    logging.info("[INGEST] Processing PDF: %s", filename)

    docs: List[Document] = []

    # 1) Base extraction
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

    # 2) OCR fallback
    if not docs or sum(len(d.page_content or "") for d in docs) < 400:
        logging.warning(
            "[INGEST] Very little text extracted from %s. Attempting OCR fallback...", filename
        )
        ocr_docs = ocr_pdf(pdf_path)
        if ocr_docs:
            docs = ocr_docs
        else:
            logging.warning("[INGEST] OCR also failed or returned no text for %s.", filename)

    if not docs:
        logging.error("[INGEST] No usable text from %s. Skipping.", filename)
        return []

    # 3) Chunking
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


def _choose_ivfpq_m(d: int) -> int:
    """
    Choose a reasonable 'm' (number of sub-vectors) for IndexIVFPQ given dimension d.
    Prefer divisors of d roughly around 16; fall back to 8,4.
    """
    for cand in (16, 12, 8, 4):
        if d % cand == 0 and d // cand >= 1:
            return cand
    # worst case
    return max(1, min(16, d))


def create_vector_store(
    pdf_paths: List[str],
    progress_cb: Optional[Callable[[int, str], None]] = None,
) -> bool:
    """
    Build FAISS vectorstore from PDFs, using:
    - full chunk text on disk under FULLTEXT_DIR
    - short snippet in-memory for FAISS
    - IVFPQ quantized index if faiss-native is available
    """
    try:
        if not pdf_paths:
            logging.warning("[INGEST] No PDF paths provided.")
            return False

        if progress_cb:
            progress_cb(5, "Starting ingestion...")

        # Clear old stores
        if os.path.exists(DB_FAISS_BASE):
            try:
                logging.info("[INGEST] Removing old FAISS base → %s", DB_FAISS_BASE)
                shutil.rmtree(DB_FAISS_BASE)
            except Exception:
                logging.exception("[INGEST] Could not clear old FAISS store")
                return False

        os.makedirs(DB_FAISS_BASE, exist_ok=True)
        os.makedirs(FULLTEXT_DIR, exist_ok=True)

        if progress_cb:
            progress_cb(10, "Extracting text from PDFs...")

        # Process PDFs (sequential by default for low RAM)
        all_chunks: List[Document] = []
        if MAX_WORKERS <= 1:
            for p in pdf_paths:
                chunks = process_pdf(p)
                if chunks:
                    all_chunks.extend(chunks)
                else:
                    logging.warning("[INGEST] No chunks produced for %s", os.path.basename(p))
        else:
            with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(pdf_paths))) as executor:
                future_to_path = {executor.submit(process_pdf, p): p for p in pdf_paths}
                for fut in as_completed(future_to_path):
                    p = future_to_path[fut]
                    try:
                        chunks = fut.result()
                        if chunks:
                            all_chunks.extend(chunks)
                        else:
                            logging.warning("[INGEST] No chunks produced for %s", os.path.basename(p))
                    except Exception:
                        logging.exception("[INGEST] Exception while processing %s", p)

        if not all_chunks:
            logging.error("[INGEST] No content extracted from any document. FAISS not created.")
            return False

        logging.info("[INGEST] Total extracted chunks: %d", len(all_chunks))
        if progress_cb:
            progress_cb(30, f"Total chunks: {len(all_chunks)} - preparing embeddings...")

        # Load embeddings
        try:
            logging.info("[INGEST] Loading embeddings model: %s", EMBED_MODEL)
            embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
        except Exception:
            logging.exception("[ERROR] Could not load embeddings model")
            return False

        docs_for_index: List[Document] = []
        embeddings_list: List[List[float]] = []

        # assign stable doc_ids and write full text to disk
        next_id = 0
        total = len(all_chunks)
        processed = 0

        for batch in _batch_iterable(all_chunks, EMBED_BATCH_SIZE):
            texts = []
            docs_batch: List[Document] = []

            for c in batch:
                metadata = c.metadata or {}
                page = metadata.get("page", "?")
                filename = metadata.get("filename") or os.path.basename(metadata.get("source", ""))
                # unique-ish id: file + page + counter
                doc_id = f"{filename}_p{page}_i{next_id}"
                next_id += 1

                full_text = c.page_content or ""
                # write full text to disk
                try:
                    full_path = os.path.join(FULLTEXT_DIR, f"{doc_id}.txt")
                    with open(full_path, "w", encoding="utf-8") as f:
                        f.write(full_text)
                except Exception:
                    logging.exception("[INGEST] Failed to write fulltext for %s", doc_id)

                snippet = full_text[:800]

                # metadata for index doc
                idx_meta: Dict[str, Any] = dict(metadata)
                idx_meta["doc_id"] = doc_id
                idx_meta.setdefault("filename", filename)

                idx_doc = Document(page_content=snippet, metadata=idx_meta)
                docs_batch.append(idx_doc)
                texts.append(snippet if snippet else " ")

            # embed snippets batch
            try:
                emb_batch = embeddings.embed_documents(texts)
            except Exception:
                logging.exception("[ERROR] Embedding batch failed; retry singly")
                emb_batch = []
                for t in texts:
                    try:
                        emb_batch.append(embeddings.embed_query(t))
                    except Exception:
                        logging.exception("[ERROR] Embedding single text failed")
                        # fallback zero-vector of typical MiniLM size (384) – safe but approximate
                        emb_batch.append([0.0] * 384)

            for doc_obj, vec in zip(docs_batch, emb_batch):
                docs_for_index.append(doc_obj)
                embeddings_list.append(vec)

            processed += len(batch)
            if progress_cb:
                pct = 30 + int(50 * processed / total)
                progress_cb(pct, f"Embedding documents... ({processed}/{total})")

        # free original full chunk list quickly
        del all_chunks

        # Build FAISS index (prefer IVFPQ quantized when native faiss available)
        try:
            os.makedirs(DB_FAISS_PATH, exist_ok=True)
            logging.info("[INGEST] Building FAISS vectorstore (may take a moment)...")

            if FAISS_NATIVE_AVAILABLE and embeddings_list:
                import numpy as np

                vecs = np.array(embeddings_list).astype("float32")
                n, d = vecs.shape
                # normalize for IP ~ cosine
                norms = np.linalg.norm(vecs, axis=1, keepdims=True)
                norms[norms == 0] = 1.0
                vecs = vecs / norms

                # choose nlist & m
                nlist = min(max(1, int(math.sqrt(n))), 4096)
                m = _choose_ivfpq_m(d)
                logging.info("[INGEST] Using IndexIVFPQ with d=%d, nlist=%d, m=%d", d, nlist, m)

                quantizer = faiss.IndexFlatIP(d)
                index = faiss.IndexIVFPQ(quantizer, d, nlist, m, 8)
                index.train(vecs)
                index.add(vecs)

                # build LangChain FAISS wrapper
                id_to_doc: Dict[str, Document] = {}
                index_to_docstore_id: Dict[int, str] = {}

                for i, doc in enumerate(docs_for_index):
                    doc_id = doc.metadata.get("doc_id") or str(i)
                    id_to_doc[doc_id] = doc
                    index_to_docstore_id[i] = doc_id

                docstore = InMemoryDocstore(id_to_doc)
                faiss_store = FAISS(
                    embedding_function=embeddings,
                    index=index,
                    docstore=docstore,
                    index_to_docstore_id=index_to_docstore_id,
                )
                index_type = "ivfpq"
            else:
                # fallback: simpler index from documents
                logging.info("[INGEST] Native faiss not available or no embeddings; using FAISS.from_documents")
                faiss_store = FAISS.from_documents(docs_for_index, embedding=embeddings)
                index_type = "flat"

        except Exception:
            logging.exception("[ERROR] Failed to build FAISS vectorstore")
            return False

        # Save vectorstore
        try:
            logging.info("[INGEST] Saving FAISS to %s", DB_FAISS_PATH)
            faiss_store.save_local(DB_FAISS_PATH)
        except Exception:
            logging.exception("[ERROR] Failed to save FAISS vectorstore to %s", DB_FAISS_PATH)
            return False

        # Basic verification
        try:
            files = os.listdir(DB_FAISS_PATH)
            if not files:
                logging.error("[ERROR] FAISS directory saved but appears empty: %s", DB_FAISS_PATH)
                return False
            logging.info("[INGEST] FAISS saved. Files: %s", files[:10])
        except Exception:
            logging.exception("[ERROR] Could not list FAISS directory %s", DB_FAISS_PATH)
            return False

        # Write manifest
        try:
            manifest = {
                "path": DB_FAISS_PATH,
                "chunks": len(docs_for_index),
                "embed_model": EMBED_MODEL,
                "fulltext_dir": FULLTEXT_DIR,
                "index_type": index_type,
            }
            dirpath = os.path.dirname(MANIFEST_PATH)
            os.makedirs(dirpath, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", delete=False, dir=dirpath, encoding="utf-8") as tf:
                json.dump(manifest, tf)
                tempname = tf.name
            os.replace(tempname, MANIFEST_PATH)
            logging.info("[INGEST] Manifest written to %s", MANIFEST_PATH)

            # Trigger background warmup (embeddings + vectorstore; skip LLM for low resource)
            if RAG_WARMUP_ON_INGEST:
                try:
                    def _warm():
                        try:
                            rc.warmup_resources(load_llm=False)
                        except Exception:
                            logging.exception("[INGEST] RAG warmup failed after manifest write")
                    tw = threading.Thread(target=_warm, daemon=True)
                    tw.start()
                except Exception:
                    logging.exception("[INGEST] Failed to spawn warmup thread after manifest write")
            else:
                logging.info("[INGEST] Skipping RAG warmup (RAG_WARMUP_ON_INGEST=false)")

        except Exception:
            logging.exception("[INGEST] Failed to write manifest to %s", MANIFEST_PATH)

        if progress_cb:
            progress_cb(95, "FAISS saved. Finalizing...")

        logging.info("[INGEST] Successfully saved FAISS at %s", DB_FAISS_PATH)
        return True
    except Exception:
        logging.exception("[INGEST] Unexpected failure in create_vector_store")
        return False
