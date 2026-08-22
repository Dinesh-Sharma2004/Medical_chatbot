import json
import os
import shutil
import unittest
import uuid
from unittest.mock import patch

from langchain_core.documents import Document

from backend import ingest


class MockEmbeddings:
    def embed_documents(self, texts):
        return [[0.0] * 384 for _ in texts]


class FakeFAISSStore:
    def __init__(self):
        self.docs = []

    @classmethod
    def from_documents(cls, docs, embedding):
        store = cls()
        store.docs.extend(docs)
        return store

    @classmethod
    def from_embeddings(cls, text_embeddings, embedding, metadatas=None, ids=None):
        return cls()

    def add_documents(self, docs):
        self.docs.extend(docs)

    def save_local(self, path):
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, "index.faiss"), "w", encoding="utf-8") as f:
            f.write("fake-index")
        with open(os.path.join(path, "index.pkl"), "w", encoding="utf-8") as f:
            f.write("fake-docstore")


class IngestIntegrityTests(unittest.TestCase):
    def setUp(self):
        scratch_root = os.path.join(os.getcwd(), "backend", "data")
        os.makedirs(scratch_root, exist_ok=True)
        self.tmp = os.path.join(scratch_root, f"ingest-integrity-{uuid.uuid4().hex}")
        os.makedirs(self.tmp, exist_ok=True)
        self.pdf = os.path.join(self.tmp, "sample.pdf")
        with open(self.pdf, "wb") as f:
            f.write(b"%PDF-1.4 test")

        self.patches = [
            patch.object(ingest, "DB_FAISS_BASE", self.tmp),
            patch.object(ingest, "DB_FAISS_PATH", os.path.join(self.tmp, "db_faiss")),
            patch.object(ingest, "FULLTEXT_DIR", os.path.join(self.tmp, "fulltext")),
            patch.object(ingest, "MANIFEST_PATH", os.path.join(self.tmp, "manifest.json")),
            patch.object(ingest, "INGEST_LOCK_PATH", os.path.join(self.tmp, ".ingest.lock")),
            patch.object(ingest.rc.Resources, "embeddings", return_value=MockEmbeddings()),
            patch.object(ingest.rc, "warmup_resources", return_value=None),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _docs(self):
        return [
            Document(
                page_content="Hypertension is elevated blood pressure.",
                metadata={
                    "source": self.pdf,
                    "filename": "sample.pdf",
                    "page": 0,
                    "page_label": 1,
                    "page_key": "sample.pdf__p1",
                },
            )
        ]

    def test_successful_ingest_commits_faiss_fulltext_and_manifest(self):
        with patch.object(ingest, "process_pdf", return_value=self._docs()):
            with patch.object(ingest, "FAISS", FakeFAISSStore):
                ok = ingest.create_vector_store([self.pdf])

        self.assertTrue(ok)
        self.assertTrue(os.path.exists(os.path.join(ingest.DB_FAISS_PATH, "index.faiss")))
        self.assertTrue(os.path.exists(os.path.join(ingest.FULLTEXT_DIR, "sample.pdf__p1.txt")))
        with open(ingest.MANIFEST_PATH, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        self.assertEqual(manifest["chunks"], 1)
        self.assertEqual(manifest["path"], ingest._portable_path(ingest.DB_FAISS_PATH))

    def test_failed_ingest_keeps_existing_live_index(self):
        os.makedirs(ingest.DB_FAISS_PATH, exist_ok=True)
        os.makedirs(ingest.FULLTEXT_DIR, exist_ok=True)
        with open(os.path.join(ingest.DB_FAISS_PATH, "index.faiss"), "w", encoding="utf-8") as f:
            f.write("old-index")
        with open(os.path.join(ingest.FULLTEXT_DIR, "old-page.txt"), "w", encoding="utf-8") as f:
            f.write("old-text")

        class FailingFAISS:
            @classmethod
            def from_documents(cls, docs, embedding):
                raise RuntimeError("embedding/indexing failed")

            @classmethod
            def from_embeddings(cls, text_embeddings, embedding, metadatas=None, ids=None):
                raise RuntimeError("embedding/indexing failed")

        with patch.object(ingest, "process_pdf", return_value=self._docs()):
            with patch.object(ingest, "FAISS", FailingFAISS):
                ok = ingest.create_vector_store([self.pdf])

        self.assertFalse(ok)
        with open(os.path.join(ingest.DB_FAISS_PATH, "index.faiss"), "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "old-index")
        with open(os.path.join(ingest.FULLTEXT_DIR, "old-page.txt"), "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "old-text")


if __name__ == "__main__":
    unittest.main()
