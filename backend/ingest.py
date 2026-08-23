# ingest.py — PDF → Chunks → Embeddings → FAISS store (Docker-safe)

import os
import shutil
import json
import logging
import tempfile
import threading
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Callable, Optional, Dict, Any, Tuple

import numpy as np
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

try:
    from . import rag_chain as rc
    from .telemetry import (
        INGEST_ACTIVE_JOBS,
        INGEST_CHUNKS_TOTAL,
        INGEST_DURATION,
        INGEST_JOBS_TOTAL,
        INGEST_LAST_SUCCESS,
        INGEST_PDFS_TOTAL,
    )
except ImportError:
    import rag_chain as rc
    from telemetry import (
        INGEST_ACTIVE_JOBS,
        INGEST_CHUNKS_TOTAL,
        INGEST_DURATION,
        INGEST_JOBS_TOTAL,
        INGEST_LAST_SUCCESS,
        INGEST_PDFS_TOTAL,
    )

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
EMBED_BATCH_SIZE = max(1, int(os.getenv("EMBED_BATCH_SIZE", 32)))
EMBED_INDEX_WORKERS = max(1, int(os.getenv("EMBED_INDEX_WORKERS", min(4, os.cpu_count() or 4))))
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
MAX_PDF_PAGES = int(os.getenv("RAG_MAX_PDF_PAGES", 120))
RAG_WARMUP_ON_INGEST = os.getenv("RAG_WARMUP_ON_INGEST", "true").lower() in ("1", "true", "yes")
INGEST_MAX_WORKERS = max(1, int(os.getenv("INGEST_MAX_WORKERS", min(8, os.cpu_count() or 4))))
INGEST_EXECUTOR = os.getenv("INGEST_EXECUTOR", "threads").lower()
INGEST_LOCK_PATH = os.path.join(DB_FAISS_BASE, ".ingest.lock")

# Batching & Parallelization Configs
PAGE_BATCH_SIZE = int(os.getenv("PAGE_BATCH_SIZE", 15))
MAX_CONCURRENT_BATCHES = int(os.getenv("MAX_CONCURRENT_BATCHES", 3))
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", EMBED_BATCH_SIZE))
MAX_EMBEDDING_CONCURRENCY = int(os.getenv("MAX_EMBEDDING_CONCURRENCY", 3))

class IngestResult(dict):
    def __bool__(self) -> bool:
        return bool(self.get("success", False))


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


def _portable_path(path: str) -> str:
    return os.path.normpath(path).replace("\\", "/")

# Optional OCR
_ocr_err = None
try:
    from pdf2image import convert_from_path
    OCR_AVAILABLE = True
except Exception as e:
    OCR_AVAILABLE = False
    _ocr_err = e

_rapidocr_err = None
try:
    from rapidocr_onnxruntime import RapidOCR
    RAPIDOCR_AVAILABLE = True
except Exception as e:
    RAPIDOCR_AVAILABLE = False
    _rapidocr_err = e

_pdfium_err = None
try:
    import pypdfium2 as pdfium
    PDFIUM_AVAILABLE = True
except Exception as e:
    PDFIUM_AVAILABLE = False
    _pdfium_err = e

_RAPIDOCR_ENGINE = None

def _safe_key(value: str) -> str:
    value = os.path.basename(value or "document")
    value = re.sub(r"[^A-Za-z0-9._() -]+", "_", value).strip()
    return value or "document"


def _safe_fulltext_key(value: str) -> str:
    return _safe_key(str(value or "page"))


def _remove_tree(path: str):
    if os.path.exists(path):
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        else:
            try:
                os.remove(path)
            except OSError:
                pass


def _replace_directory(staged_path: str, live_path: str, backup_path: str):
    if os.path.exists(backup_path):
        shutil.rmtree(backup_path, ignore_errors=True)
    if os.path.exists(live_path):
        os.replace(live_path, backup_path)
    try:
        os.replace(staged_path, live_path)
    except Exception:
        if os.path.exists(backup_path) and not os.path.exists(live_path):
            os.replace(backup_path, live_path)
        raise


def _commit_staged_store(staged_db_path: str, staged_fulltext_dir: str, manifest: Dict[str, Any]):
    stamp = f"{int(time.time())}-{os.getpid()}-{threading.get_ident()}"
    db_backup = os.path.join(DB_FAISS_BASE, f".backup-db_faiss-{stamp}")
    fulltext_backup = os.path.join(DB_FAISS_BASE, f".backup-fulltext-{stamp}")
    manifest_backup = os.path.join(DB_FAISS_BASE, f".backup-manifest-{stamp}.json")
    manifest_tmp = os.path.join(DB_FAISS_BASE, f".manifest-{stamp}.tmp")

    with open(manifest_tmp, "w", encoding="utf-8") as f:
        json.dump(manifest, f)

    db_swapped = False
    fulltext_swapped = False
    manifest_swapped = False
    try:
        _replace_directory(staged_db_path, DB_FAISS_PATH, db_backup)
        db_swapped = True
        _replace_directory(staged_fulltext_dir, FULLTEXT_DIR, fulltext_backup)
        fulltext_swapped = True

        if os.path.exists(MANIFEST_PATH):
            os.replace(MANIFEST_PATH, manifest_backup)
        os.replace(manifest_tmp, MANIFEST_PATH)
        manifest_swapped = True
    except Exception:
        logging.exception("[INGEST] Failed committing staged vectorstore; attempting rollback")
        if manifest_swapped and os.path.exists(manifest_backup):
            os.replace(manifest_backup, MANIFEST_PATH)
        elif not manifest_swapped:
            _remove_tree(manifest_tmp)
            if os.path.exists(manifest_backup) and not os.path.exists(MANIFEST_PATH):
                os.replace(manifest_backup, MANIFEST_PATH)

        if fulltext_swapped:
            _remove_tree(FULLTEXT_DIR)
            if os.path.exists(fulltext_backup):
                os.replace(fulltext_backup, FULLTEXT_DIR)
        if db_swapped:
            _remove_tree(DB_FAISS_PATH)
            if os.path.exists(db_backup):
                os.replace(db_backup, DB_FAISS_PATH)
        raise
    finally:
        _remove_tree(db_backup)
        _remove_tree(fulltext_backup)
        if os.path.exists(manifest_backup):
            os.remove(manifest_backup)
        if os.path.exists(manifest_tmp):
            os.remove(manifest_tmp)


class IngestCancelled(Exception):
    pass


class CrossProcessFileLock:
    def __init__(self, path: str):
        self.path = path
        self.handle = None

    def __enter__(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        if os.path.exists(self.path):
            self.handle = open(self.path, "r+b")
        else:
            self.handle = open(self.path, "w+b")
        self.handle.seek(0)
        if os.path.getsize(self.path) == 0:
            self.handle.write(b"0")
            self.handle.flush()
        self.handle.seek(0)

        if os.name == "nt":
            import msvcrt

            while True:
                try:
                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_LOCK, 1)
                    break
                except OSError:
                    time.sleep(0.1)
        else:
            import fcntl

            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)

        return self

    def __exit__(self, exc_type, exc, tb):
        if not self.handle:
            return

        self.handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        self.handle.close()
        self.handle = None


def _raise_if_cancelled(cancel_event: Optional[threading.Event]):
    if cancel_event is not None and cancel_event.is_set():
        raise IngestCancelled("Ingestion canceled")

# =========================================================
# OCR
# =========================================================
def ocr_pdf(
    pdf_path: str,
    first_page: int = 1,
    last_page: Optional[int] = None,
    progress_cb: Optional[Callable[[int, str], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> List[Document]:
    docs: List[Document] = []
    if not OCR_AVAILABLE or not RAPIDOCR_AVAILABLE:
        logging.warning(
            "[OCR] OCR not available. Install pdf2image + rapidocr-onnxruntime. "
            f"Import errors: {_ocr_err} / {_rapidocr_err}"
        )
        return docs
    try:
        filename = os.path.basename(pdf_path)
        actual_last_page = last_page if last_page is not None else (MAX_PDF_PAGES if MAX_PDF_PAGES > 0 else None)
        logging.info("[OCR] Running OCR on %s (pages %d-%s)", filename, first_page, str(actual_last_page))
        pages = convert_from_path(
            pdf_path,
            first_page=first_page,
            last_page=actual_last_page,
            thread_count=4,
        )

        global _RAPIDOCR_ENGINE
        if _RAPIDOCR_ENGINE is None:
            _RAPIDOCR_ENGINE = RapidOCR()

        for i, img in enumerate(pages):
            _raise_if_cancelled(cancel_event)
            actual_page_num = first_page + i
            if progress_cb and pages:
                pct = 25 + int(65 * (i + 1) / max(1, len(pages)))
                progress_cb(pct, f"OCR page {actual_page_num}...")
            try:
                ocr_result = _RAPIDOCR_ENGINE(np.array(img))
                lines = ocr_result[0] if isinstance(ocr_result, tuple) else ocr_result
            except Exception:
                logging.exception("[OCR] RapidOCR failed on page %d of %s", actual_page_num, filename)
                continue

            text_parts: List[str] = []
            if isinstance(lines, list):
                for item in lines:
                    if isinstance(item, (list, tuple)) and len(item) >= 2 and item[1]:
                        text_parts.append(str(item[1]))
                    elif isinstance(item, dict) and item.get("text"):
                        text_parts.append(str(item["text"]))

            text = "\n".join(text_parts).strip()
            if not text:
                continue
            docs.append(
                Document(
                    page_content=text,
                    metadata={
                        "source": pdf_path,
                        "filename": filename,
                        "page": actual_page_num,
                        "page_label": actual_page_num,
                        "page_key": f"{_safe_key(filename)}__p{actual_page_num}",
                        "ocr": True,
                    },
                )
            )
        logging.info("[OCR] Extracted OCR text from %d page(s) in %s (range %d-%s)", len(docs), filename, first_page, str(actual_last_page))
    except IngestCancelled:
        raise
    except Exception:
        logging.exception("[OCR] Failed OCR on %s", pdf_path)
    return docs

_PDFIUM_LOCK = threading.Lock()

def pdfium_pdf(pdf_path: str, cancel_event: Optional[threading.Event] = None) -> List[Document]:
    if not PDFIUM_AVAILABLE:
        logging.warning(
            "[PDFium] Not available. Install pypdfium2. "
            f"Import error: {_pdfium_err}"
        )
        return []

    with _PDFIUM_LOCK:
        docs: List[Document] = []
        try:
            filename = os.path.basename(pdf_path)
            logging.info("[PDFium] Extracting text from %s", filename)
            pdf = pdfium.PdfDocument(pdf_path)
            try:
                for i, page in enumerate(pdf):
                    _raise_if_cancelled(cancel_event)
                    textpage = page.get_textpage()
                    text = (textpage.get_text_range() or "").strip()
                    if not text:
                        continue
                    docs.append(
                        Document(
                            page_content=text,
                            metadata={
                                "source": pdf_path,
                                "filename": filename,
                                "page": i,
                                "page_label": i + 1,
                                "page_key": f"{_safe_key(filename)}__p{i + 1}",
                                "pdfium": True,
                            },
                        )
                    )
            finally:
                try:
                    pdf.close()
                except Exception:
                    pass
            logging.info("[PDFium] Extracted text from %d page(s) in %s", len(docs), filename)
        except IngestCancelled:
            raise
        except Exception:
            logging.exception("[PDFium] Failed extraction on %s", pdf_path)
        return docs

def get_pdf_page_count(pdf_path: str) -> int:
    if PDFIUM_AVAILABLE:
        try:
            pdf = pdfium.PdfDocument(pdf_path)
            cnt = len(pdf)
            pdf.close()
            return cnt
        except Exception:
            logging.exception("Failed getting page count via PDFium for %s", pdf_path)
    try:
        import pypdf
        with open(pdf_path, 'rb') as f:
            reader = pypdf.PdfReader(f)
            return len(reader.pages)
    except Exception:
        logging.exception("Failed getting page count via pypdf for %s", pdf_path)
    return 1

def pdfium_pdf_range(
    pdf_path: str,
    start_page_idx: int,
    end_page_idx: int,
    cancel_event: Optional[threading.Event] = None
) -> List[Document]:
    if not PDFIUM_AVAILABLE:
        logging.warning("[PDFium] Not available.")
        return []

    with _PDFIUM_LOCK:
        docs: List[Document] = []
        try:
            filename = os.path.basename(pdf_path)
            logging.info("[PDFium] Extracting text from %s pages %d-%d", filename, start_page_idx + 1, end_page_idx)
            pdf = pdfium.PdfDocument(pdf_path)
            try:
                limit = min(end_page_idx, len(pdf))
                for i in range(start_page_idx, limit):
                    _raise_if_cancelled(cancel_event)
                    page = pdf[i]
                    textpage = page.get_textpage()
                    text = (textpage.get_text_range() or "").strip()
                    if not text:
                        continue
                    docs.append(
                        Document(
                            page_content=text,
                            metadata={
                                "source": pdf_path,
                                "filename": filename,
                                "page": i,
                                "page_label": i + 1,
                                "page_key": f"{_safe_key(filename)}__p{i + 1}",
                                "pdfium": True,
                            },
                        )
                    )
            finally:
                try:
                    pdf.close()
                except Exception:
                    pass
            logging.info("[PDFium] Extracted text from %d page(s) in %s (range %d-%d)", len(docs), filename, start_page_idx + 1, end_page_idx)
        except IngestCancelled:
            raise
        except Exception:
            logging.exception("[PDFium] Failed extraction on %s (range %d-%d)", pdf_path, start_page_idx + 1, end_page_idx)
        return docs

def pypdf_pdf_range(
    pdf_path: str,
    start_page_idx: int,
    end_page_idx: int,
    cancel_event: Optional[threading.Event] = None
) -> List[Document]:
    try:
        filename = os.path.basename(pdf_path)
        logging.info("[PyPDF] Fallback extracting text from %s pages %d-%d", filename, start_page_idx + 1, end_page_idx)
        loader = PyPDFLoader(pdf_path)
        all_docs = loader.load()
        docs: List[Document] = []
        for idx, d in enumerate(all_docs):
            _raise_if_cancelled(cancel_event)
            p = d.metadata.get("page", idx)
            if start_page_idx <= p < end_page_idx:
                docs.append(d)
        return docs
    except IngestCancelled:
        raise
    except Exception:
        logging.exception("[PyPDF] Failed extraction on %s (range %d-%d)", pdf_path, start_page_idx + 1, end_page_idx)
        return []

def _write_range_fulltext(
    docs: List[Document],
    pdf_path: str,
    filename: str,
    fulltext_dir: Optional[str],
    cancel_event: Optional[threading.Event] = None
):
    target_fulltext_dir = fulltext_dir or FULLTEXT_DIR
    os.makedirs(target_fulltext_dir, exist_ok=True)
    for d in docs:
        _raise_if_cancelled(cancel_event)
        if not isinstance(d.metadata, dict):
            d.metadata = {}
        d.metadata.setdefault("source", pdf_path)
        d.metadata.setdefault("filename", filename)
        page_label = rc.display_page(d.metadata.get("page"), d.metadata)
        if page_label is None:
            continue
        d.metadata["page_label"] = page_label
        page_key = _safe_fulltext_key(d.metadata.get("page_key") or f"{_safe_key(filename)}__p{page_label}")
        d.metadata["page_key"] = page_key
        try:
            with open(os.path.join(target_fulltext_dir, f"{page_key}.txt"), "w", encoding="utf-8") as f:
                f.write(d.page_content or "")
        except Exception:
            logging.exception("[INGEST] Failed writing page text for %s page %s", filename, page_label)

def process_pdf_range(
    pdf_path: str,
    start_page_idx: int,
    end_page_idx: int,
    cancel_event: Optional[threading.Event] = None,
    fulltext_dir: Optional[str] = None,
) -> List[Document]:
    filename = os.path.basename(pdf_path)
    logging.info("[INGEST] Processing PDF range: %s (pages %d-%d)", filename, start_page_idx + 1, end_page_idx)

    _raise_if_cancelled(cancel_event)
    docs = []
    
    # 1. PDFium primary range extraction
    try:
        docs = pdfium_pdf_range(pdf_path, start_page_idx, end_page_idx, cancel_event=cancel_event)
        _write_range_fulltext(docs, pdf_path, filename, fulltext_dir, cancel_event)
    except IngestCancelled:
        raise
    except Exception:
        logging.exception("[INGEST] PDFium range loader failed for %s", filename)
        docs = []

    # 2. PyPDF fallback range extraction
    if not docs or sum(len(d.page_content or "") for d in docs) < 400:
        logging.warning("[INGEST] Trying PyPDFLoader fallback for %s (range %d-%d)", filename, start_page_idx + 1, end_page_idx)
        try:
            docs = pypdf_pdf_range(pdf_path, start_page_idx, end_page_idx, cancel_event=cancel_event)
            _write_range_fulltext(docs, pdf_path, filename, fulltext_dir, cancel_event)
        except IngestCancelled:
            raise
        except Exception:
            logging.exception("[INGEST] PyPDFLoader range fallback failed for %s", filename)
            docs = []

    # 3. OCR fallback range extraction
    if not docs or sum(len(d.page_content or "") for d in docs) < 400:
        logging.warning("[INGEST] Very little text from %s, trying OCR fallback (range %d-%d)...", filename, start_page_idx + 1, end_page_idx)
        # ocr_pdf takes 1-based page index. So first_page is start_page_idx + 1, last_page is end_page_idx
        try:
            ocr_docs = ocr_pdf(pdf_path, first_page=start_page_idx + 1, last_page=end_page_idx, cancel_event=cancel_event)
            if ocr_docs:
                docs = ocr_docs
                _write_range_fulltext(docs, pdf_path, filename, fulltext_dir, cancel_event)
        except IngestCancelled:
            raise
        except Exception:
            logging.exception("[INGEST] OCR range fallback failed for %s", filename)

    if not docs:
        logging.error("[INGEST] No usable text from %s (range %d-%d), skipping.", filename, start_page_idx + 1, end_page_idx)
        return []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ".", " ", ""],
    )

    try:
        _raise_if_cancelled(cancel_event)
        chunks = splitter.split_documents(docs)
        logging.info("[INGEST] → %d chunks from %s (range %d-%d)", len(chunks), filename, start_page_idx + 1, end_page_idx)
        for c in chunks:
            if not isinstance(c.metadata, dict):
                c.metadata = {}
            c.metadata.setdefault("filename", filename)
            c.metadata.setdefault("source", pdf_path)
    except IngestCancelled:
        raise
    except Exception:
        logging.exception("[INGEST] Failed splitting documents for %s (range %d-%d)", filename, start_page_idx + 1, end_page_idx)
        return []

    return chunks

# =========================================================
# PDF → CHUNKS
# =========================================================
def process_pdf(
    pdf_path: str,
    progress_cb: Optional[Callable[[int, str], None]] = None,
    cancel_event: Optional[threading.Event] = None,
    fulltext_dir: Optional[str] = None,
    start_page_idx: int = 0,
    end_page_idx: Optional[int] = None,
) -> List[Document]:
    filename = os.path.basename(pdf_path)
    total_pages = get_pdf_page_count(pdf_path)
    actual_end_page = end_page_idx if end_page_idx is not None else total_pages
    
    logging.info("[INGEST] Processing PDF: %s (range %d-%d)", filename, start_page_idx + 1, actual_end_page)

    _raise_if_cancelled(cancel_event)
    docs = []
    
    # 1. PDFium primary range extraction
    try:
        docs = pdfium_pdf_range(pdf_path, start_page_idx, actual_end_page, cancel_event=cancel_event)
        _write_range_fulltext(docs, pdf_path, filename, fulltext_dir, cancel_event)
    except IngestCancelled:
        raise
    except Exception:
        logging.exception("[INGEST] PDFium range loader failed for %s", filename)
        docs = []

    # 2. PyPDF fallback range extraction
    if not docs or sum(len(d.page_content or "") for d in docs) < 400:
        logging.warning("[INGEST] Trying PyPDFLoader fallback for %s (range %d-%d)", filename, start_page_idx + 1, actual_end_page)
        try:
            docs = pypdf_pdf_range(pdf_path, start_page_idx, actual_end_page, cancel_event=cancel_event)
            _write_range_fulltext(docs, pdf_path, filename, fulltext_dir, cancel_event)
        except IngestCancelled:
            raise
        except Exception:
            logging.exception("[INGEST] PyPDFLoader range fallback failed for %s", filename)
            docs = []

    # 3. OCR fallback range extraction
    if not docs or sum(len(d.page_content or "") for d in docs) < 400:
        logging.warning("[INGEST] Very little text from %s, trying OCR fallback (range %d-%d)...", filename, start_page_idx + 1, actual_end_page)
        try:
            ocr_docs = ocr_pdf(pdf_path, first_page=start_page_idx + 1, last_page=actual_end_page, cancel_event=cancel_event)
            if ocr_docs:
                docs = ocr_docs
                _write_range_fulltext(docs, pdf_path, filename, fulltext_dir, cancel_event)
        except IngestCancelled:
            raise
        except Exception:
            logging.exception("[INGEST] OCR range fallback failed for %s", filename)

    if not docs:
        logging.error("[INGEST] No usable text from %s (range %d-%d), skipping.", filename, start_page_idx + 1, actual_end_page)
        return []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ".", " ", ""],
    )

    try:
        _raise_if_cancelled(cancel_event)
        chunks = splitter.split_documents(docs)
        logging.info("[INGEST] → %d chunks from %s (range %d-%d)", len(chunks), filename, start_page_idx + 1, actual_end_page)
        for c in chunks:
            if not isinstance(c.metadata, dict):
                c.metadata = {}
            c.metadata.setdefault("filename", filename)
            c.metadata.setdefault("source", pdf_path)
    except IngestCancelled:
        raise
    except Exception:
        logging.exception("[INGEST] Failed splitting documents for %s (range %d-%d)", filename, start_page_idx + 1, actual_end_page)
        return []

    return chunks

def extract_pdf_task(path: str):
    return path, process_pdf(path, progress_cb=None, cancel_event=None)

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


def _extract_pdfs_parallel(
    pdf_paths: List[str],
    staged_fulltext_dir: str,
    progress_cb: Optional[Callable[[int, str], None]],
    cancel_event: Optional[threading.Event],
) -> List[tuple[str, List[Document]]]:
    total_pdfs = max(1, len(pdf_paths))

    def _extract_single(path: str):
        return path, process_pdf(
            path,
            progress_cb=progress_cb,
            cancel_event=cancel_event,
            fulltext_dir=staged_fulltext_dir,
        )

    if len(pdf_paths) == 1:
        return [_extract_single(pdf_paths[0])]

    if INGEST_EXECUTOR == "spark":
        logging.warning("[INGEST] Spark executor disabled for transactional ingest; using threads")

    extracted: List[tuple[str, List[Document]]] = []
    with ThreadPoolExecutor(max_workers=min(len(pdf_paths), INGEST_MAX_WORKERS)) as ex:
        future_map = {ex.submit(_extract_single, p): p for p in pdf_paths}
        for idx, fut in enumerate(as_completed(future_map), start=1):
            _raise_if_cancelled(cancel_event)
            try:
                extracted.append(fut.result())
            except IngestCancelled:
                raise
            except Exception:
                logging.exception("[INGEST] Failed extracting %s", future_map[fut])
            if progress_cb:
                progress_cb(
                    10 + int(20 * idx / total_pdfs),
                    f"Extracting text {idx}/{total_pdfs} PDFs...",
                )

    order = {path: idx for idx, path in enumerate(pdf_paths)}
    extracted.sort(key=lambda item: order.get(item[0], len(order)))
    return extracted


def _embed_documents_parallel(
    docs: List[Document],
    embeddings,
    progress_cb: Optional[Callable[[int, str], None]],
    cancel_event: Optional[threading.Event],
) -> FAISS:
    batches: List[Tuple[int, List[Document]]] = []
    cursor = 0
    for batch in _batch_iterable(docs, EMBEDDING_BATCH_SIZE):
        batches.append((cursor, batch))
        cursor += len(batch)

    texts: List[Optional[str]] = [None] * len(docs)
    vectors: List[Optional[List[float]]] = [None] * len(docs)
    metadatas: List[Optional[Dict[str, Any]]] = [None] * len(docs)
    ids: List[Optional[str]] = [None] * len(docs)
    total_batches = max(1, len(batches))
    total_chunks = len(docs)
    embedded_chunks = 0
    embedded_chunks_lock = threading.Lock()

    def _embed_batch(start: int, batch_docs: List[Document]):
        _raise_if_cancelled(cancel_event)
        batch_texts = [d.page_content or " " for d in batch_docs]
        batch_vectors = embeddings.embed_documents(batch_texts)
        batch_metadatas = [dict(d.metadata or {}) for d in batch_docs]
        batch_ids = [
            str((d.metadata or {}).get("doc_id") or f"chunk-{start + offset}")
            for offset, d in enumerate(batch_docs)
        ]
        return start, batch_texts, batch_vectors, batch_metadatas, batch_ids

    max_workers = min(MAX_EMBEDDING_CONCURRENCY, total_batches)
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        future_map = {ex.submit(_embed_batch, start, batch): start for start, batch in batches}
        for done, fut in enumerate(as_completed(future_map), start=1):
            _raise_if_cancelled(cancel_event)
            start, batch_texts, batch_vectors, batch_metadatas, batch_ids = fut.result()
            for offset, text in enumerate(batch_texts):
                pos = start + offset
                texts[pos] = text
                vectors[pos] = batch_vectors[offset]
                metadatas[pos] = batch_metadatas[offset]
                ids[pos] = batch_ids[offset]
            
            with embedded_chunks_lock:
                embedded_chunks += len(batch_texts)
                if progress_cb:
                    pct = 50 + int(40 * embedded_chunks / total_chunks)
                    progress_cb(
                        pct,
                        f"Embedding: {embedded_chunks} / {total_chunks} chunks",
                    )

    embedded_pairs = [
        (text or " ", vector)
        for text, vector in zip(texts, vectors)
        if vector is not None
    ]
    final_metadatas = [m or {} for m, vector in zip(metadatas, vectors) if vector is not None]
    final_ids = [i or f"chunk-{idx}" for idx, (i, vector) in enumerate(zip(ids, vectors)) if vector is not None]
    if not embedded_pairs:
        raise ValueError("No embeddings were produced")
    return FAISS.from_embeddings(
        embedded_pairs,
        embedding=embeddings,
        metadatas=final_metadatas,
        ids=final_ids,
    )

# =========================================================
# VECTORSTORE CREATION
# =========================================================
def create_vector_store(
    pdf_paths: List[str],
    progress_cb: Optional[Callable[[int, str], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> IngestResult:
    started = time.perf_counter()
    staging_root: Optional[str] = None
    INGEST_ACTIVE_JOBS.inc()
    try:
        if not pdf_paths:
            logging.warning("[INGEST] No PDF paths given.")
            INGEST_JOBS_TOTAL.labels("empty").inc()
            return IngestResult(
                success=False,
                processed_pages=0,
                total_pages=0,
                processed_chunks=0,
                embedded_chunks=0,
                failed_batches=["No PDF paths provided."]
            )
        missing_paths = [p for p in pdf_paths if not p or not os.path.isfile(p)]
        if missing_paths:
            logging.error("[INGEST] Missing PDF path(s): %s", missing_paths)
            INGEST_JOBS_TOTAL.labels("missing_file").inc()
            return IngestResult(
                success=False,
                processed_pages=0,
                total_pages=0,
                processed_chunks=0,
                embedded_chunks=0,
                failed_batches=[f"Missing file: {p}" for p in missing_paths]
            )
        INGEST_PDFS_TOTAL.inc(len(pdf_paths))

        if progress_cb:
            progress_cb(5, "Starting ingestion...")

        os.makedirs(DB_FAISS_BASE, exist_ok=True)
        staging_root = os.path.join(
            DB_FAISS_BASE,
            f"staging-{time.time_ns()}-{os.getpid()}-{threading.get_ident()}",
        )
        os.makedirs(staging_root, exist_ok=False)
        staged_db_path = os.path.join(staging_root, "db_faiss")
        staged_fulltext_dir = os.path.join(staging_root, "fulltext")
        os.makedirs(staged_fulltext_dir, exist_ok=True)

        if progress_cb:
            progress_cb(10, "Extracting text from PDFs in parallel...")

        logging.info("[INGEST] Loading embeddings: %s", EMBED_MODEL)
        embeddings = rc.Resources.embeddings()

        # Build global batch schedule across all PDFs
        all_batches = []
        total_pages = 0
        
        pdf_page_counts = {}
        for path in pdf_paths:
            cnt = get_pdf_page_count(path)
            pdf_page_counts[path] = cnt
            total_pages += cnt
            
            # Slice into batches
            num_batches = (cnt + PAGE_BATCH_SIZE - 1) // PAGE_BATCH_SIZE
            for b_idx in range(num_batches):
                start_page = b_idx * PAGE_BATCH_SIZE
                end_page = min(start_page + PAGE_BATCH_SIZE, cnt)
                all_batches.append({
                    "pdf_path": path,
                    "filename": os.path.basename(path),
                    "start_page_idx": start_page,
                    "end_page_idx": end_page,
                    "batch_idx": b_idx,
                })

        if total_pages == 0:
            logging.error("[INGEST] Total pages across all PDFs is 0.")
            INGEST_JOBS_TOTAL.labels("no_pages").inc()
            return IngestResult(
                success=False,
                processed_pages=0,
                total_pages=0,
                processed_chunks=0,
                embedded_chunks=0,
                failed_batches=["All PDFs had 0 pages or could not be read."]
            )

        processed_pages = 0
        all_chunks: List[Document] = []
        failed_batches: List[str] = []
        
        processed_lock = threading.Lock()
        chunks_lock = threading.Lock()
        failed_lock = threading.Lock()
        
        def _process_batch_task(batch_info):
            _raise_if_cancelled(cancel_event)
            pdf_path = batch_info["pdf_path"]
            filename = batch_info["filename"]
            start_page = batch_info["start_page_idx"]
            end_page = batch_info["end_page_idx"]
            b_idx = batch_info["batch_idx"]
            
            try:
                batch_chunks = process_pdf(
                    pdf_path=pdf_path,
                    cancel_event=cancel_event,
                    fulltext_dir=staged_fulltext_dir,
                    start_page_idx=start_page,
                    end_page_idx=end_page,
                )
                
                with chunks_lock:
                    all_chunks.extend(batch_chunks)
            except IngestCancelled:
                raise
            except Exception as e:
                logging.exception("[INGEST] Batch failed: %s (pages %d-%d)", filename, start_page+1, end_page)
                with failed_lock:
                    failed_batches.append(f"{filename} batch {b_idx+1} (pages {start_page+1}-{end_page}): {str(e)}")
            finally:
                with processed_lock:
                    nonlocal processed_pages
                    processed_pages += (end_page - start_page)
                    if progress_cb:
                        pct = 10 + int(40 * processed_pages / total_pages)
                        progress_cb(
                            pct,
                            f"OCR / Text Extraction: {processed_pages} / {total_pages} pages",
                        )

        # Stage 1: Bounded concurrent OCR / Native Text Extraction
        max_batch_workers = min(MAX_CONCURRENT_BATCHES, len(all_batches))
        with ThreadPoolExecutor(max_workers=max_batch_workers) as ex:
            futures = [ex.submit(_process_batch_task, b) for b in all_batches]
            for fut in as_completed(futures):
                _raise_if_cancelled(cancel_event)
                fut.result()

        if not all_chunks:
            logging.error("[INGEST] No chunks produced from any PDF.")
            INGEST_JOBS_TOTAL.labels("no_chunks").inc()
            return IngestResult(
                success=False,
                processed_pages=processed_pages,
                total_pages=total_pages,
                processed_chunks=0,
                embedded_chunks=0,
                failed_batches=failed_batches + ["No chunks produced from any PDF."]
            )

        if progress_cb:
            progress_cb(50, "Preparing chunks for embedding...")

        def _prepare_doc(c: Document, seq: int):
            _raise_if_cancelled(cancel_event)
            metadata = c.metadata or {}
            page = metadata.get("page", "?")
            filename = metadata.get("filename") or os.path.basename(metadata.get("source", ""))
            doc_id = f"{filename}_p{page}_i{seq}"

            page_key = metadata.get("page_key") or f"{_safe_key(filename)}__p{metadata.get('page_label') or metadata.get('page') or '?'}"
            full_text = c.page_content or ""
            page_key = _safe_fulltext_key(page_key)
            full_path = os.path.join(staged_fulltext_dir, f"{page_key}.txt")
            try:
                if not os.path.exists(full_path):
                    with open(full_path, "w", encoding="utf-8") as f:
                        f.write(full_text)
            except Exception:
                logging.exception("[INGEST] Failed writing fulltext for %s", doc_id)

            snippet = full_text[:800]
            idx_meta: Dict[str, Any] = dict(metadata)
            idx_meta["doc_id"] = doc_id
            idx_meta["page_key"] = page_key
            idx_meta.setdefault("page_label", metadata.get("page_label") or rc.display_page(metadata.get("page"), metadata))
            idx_meta.setdefault("filename", filename)
            return seq, Document(page_content=snippet if snippet else " ", metadata=idx_meta)

        docs_for_index = []
        for idx, chunk in enumerate(all_chunks):
            _raise_if_cancelled(cancel_event)
            _, prepared = _prepare_doc(chunk, idx)
            docs_for_index.append(prepared)

        indexed_chunks = len(docs_for_index)
        if indexed_chunks == 0:
            logging.error("[INGEST] No chunks produced after preparation.")
            INGEST_JOBS_TOTAL.labels("no_chunks").inc()
            return IngestResult(
                success=False,
                processed_pages=processed_pages,
                total_pages=total_pages,
                processed_chunks=0,
                embedded_chunks=0,
                failed_batches=failed_batches + ["No chunks produced after preparation."]
            )

        if progress_cb:
            progress_cb(50, f"Embedding {indexed_chunks} chunks in parallel...")

        try:
            faiss_store = _embed_documents_parallel(
                docs_for_index,
                embeddings,
                progress_cb,
                cancel_event,
            )
        except Exception:
            logging.exception("[INGEST] Failed while parallel indexing")
            INGEST_JOBS_TOTAL.labels("index_error").inc()
            return IngestResult(
                success=False,
                processed_pages=processed_pages,
                total_pages=total_pages,
                processed_chunks=len(all_chunks),
                embedded_chunks=0,
                failed_batches=failed_batches + ["Failed during embedding generation."]
            )

        if progress_cb:
            progress_cb(90, "Waiting for index commit lock...")

        with CrossProcessFileLock(INGEST_LOCK_PATH):
            _raise_if_cancelled(cancel_event)

            # Save FAISS
            try:
                _raise_if_cancelled(cancel_event)
                logging.info("[INGEST] Saving staged FAISS to %s", staged_db_path)
                os.makedirs(staged_db_path, exist_ok=True)
                faiss_store.save_local(staged_db_path)
            except IngestCancelled:
                raise
            except Exception:
                logging.exception("[INGEST] Failed saving FAISS store")
                INGEST_JOBS_TOTAL.labels("save_error").inc()
                return IngestResult(
                    success=False,
                    processed_pages=processed_pages,
                    total_pages=total_pages,
                    processed_chunks=len(all_chunks),
                    embedded_chunks=indexed_chunks,
                    failed_batches=failed_batches + ["Failed saving FAISS store."]
                )

            try:
                files = os.listdir(staged_db_path)
                if not files:
                    logging.error("[INGEST] FAISS directory empty at %s", staged_db_path)
                    INGEST_JOBS_TOTAL.labels("empty_index").inc()
                    return IngestResult(
                        success=False,
                        processed_pages=processed_pages,
                        total_pages=total_pages,
                        processed_chunks=len(all_chunks),
                        embedded_chunks=indexed_chunks,
                        failed_batches=failed_batches + ["FAISS directory was empty after save."]
                    )
                logging.info("[INGEST] FAISS saved. Sample files: %s", files[:10])
            except Exception:
                logging.exception("[INGEST] Could not list FAISS directory")
                INGEST_JOBS_TOTAL.labels("list_error").inc()
                return IngestResult(
                    success=False,
                    processed_pages=processed_pages,
                    total_pages=total_pages,
                    processed_chunks=len(all_chunks),
                    embedded_chunks=indexed_chunks,
                    failed_batches=failed_batches + ["Could not list FAISS directory."]
                )

            # Manifest
            try:
                manifest = {
                    "path": _portable_path(DB_FAISS_PATH),
                    "chunks": indexed_chunks,
                    "pdf_count": len(pdf_paths),
                    "embed_model": EMBED_MODEL,
                    "embed_batch_size": EMBEDDING_BATCH_SIZE,
                    "embed_index_workers": MAX_EMBEDDING_CONCURRENCY,
                    "ingest_workers": MAX_CONCURRENT_BATCHES,
                    "fulltext_dir": _portable_path(FULLTEXT_DIR),
                    "index_type": "flat",
                    "created_at": int(time.time()),
                }
                _commit_staged_store(staged_db_path, staged_fulltext_dir, manifest)
                staging_root = None
                logging.info("[INGEST] Manifest written to %s", MANIFEST_PATH)

                try:
                    with rc.Resources._lock:
                        rc.Resources._vs = None
                        rc.Resources._vs_signature = None
                except Exception:
                    logging.exception("[INGEST] Failed to invalidate in-memory vectorstore")
                try:
                    rc.clear_fulltext_cache()
                except Exception:
                    logging.exception("[INGEST] Failed to clear fulltext cache")

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
                INGEST_JOBS_TOTAL.labels("manifest_error").inc()
                return IngestResult(
                    success=False,
                    processed_pages=processed_pages,
                    total_pages=total_pages,
                    processed_chunks=len(all_chunks),
                    embedded_chunks=indexed_chunks,
                    failed_batches=failed_batches + ["Failed writing manifest."]
                )

            if progress_cb:
                progress_cb(95, "FAISS saved. Finalizing...")

            INGEST_CHUNKS_TOTAL.inc(indexed_chunks)
            INGEST_JOBS_TOTAL.labels("success").inc()
            INGEST_LAST_SUCCESS.set_to_current_time()
            logging.info("[INGEST] Ingestion finished successfully.")
            return IngestResult(
                success=(len(failed_batches) == 0),
                processed_pages=processed_pages,
                total_pages=total_pages,
                processed_chunks=len(all_chunks),
                embedded_chunks=indexed_chunks,
                failed_batches=failed_batches
            )

    except IngestCancelled:
        logging.info("[INGEST] Ingestion canceled.")
        INGEST_JOBS_TOTAL.labels("canceled").inc()
        return IngestResult(
            success=False,
            processed_pages=processed_pages if 'processed_pages' in locals() else 0,
            total_pages=total_pages if 'total_pages' in locals() else 0,
            processed_chunks=len(all_chunks) if 'all_chunks' in locals() else 0,
            embedded_chunks=indexed_chunks if 'indexed_chunks' in locals() else 0,
            failed_batches=failed_batches if 'failed_batches' in locals() else [],
            canceled=True
        )
    except Exception as e:
        logging.exception("[INGEST] Unexpected failure in create_vector_store")
        INGEST_JOBS_TOTAL.labels("error").inc()
        return IngestResult(
            success=False,
            processed_pages=processed_pages if 'processed_pages' in locals() else 0,
            total_pages=total_pages if 'total_pages' in locals() else 0,
            processed_chunks=len(all_chunks) if 'all_chunks' in locals() else 0,
            embedded_chunks=indexed_chunks if 'indexed_chunks' in locals() else 0,
            failed_batches=(failed_batches if 'failed_batches' in locals() else []) + [str(e)]
        )
    finally:
        if staging_root:
            _remove_tree(staging_root)
        INGEST_DURATION.observe(time.perf_counter() - started)
        INGEST_ACTIVE_JOBS.dec()
