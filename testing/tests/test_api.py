import io
import os
import shutil
import unittest
import uuid
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend import main


class ApiSmokeTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = os.path.join(os.getcwd(), "backend", "data", f"test-uploads-{uuid.uuid4().hex}")
        os.makedirs(self.tmpdir, exist_ok=True)
        self.data_dir_patch = patch.object(main, "DATA_DIR", self.tmpdir)
        self.data_dir_patch.start()
        self.job_dir_patch = patch.object(main.job_store, "JOB_DIR", os.path.join(self.tmpdir, "jobs"))
        self.job_dir_patch.start()
        os.makedirs(main.DATA_DIR, exist_ok=True)

        main.UPLOAD_JOBS.clear()
        main.UPLOAD_CANCEL_EVENTS.clear()
        main.UPLOAD_FILES.clear()
        main.app.dependency_overrides[main.require_user] = lambda: {
            "id": "test-user",
            "email": "tester@example.com",
            "name": "Tester",
            "provider": "password",
            "picture": None,
        }
        self.client = TestClient(main.app)

    def tearDown(self):
        self.job_dir_patch.stop()
        self.data_dir_patch.stop()
        main.UPLOAD_JOBS.clear()
        main.UPLOAD_CANCEL_EVENTS.clear()
        main.UPLOAD_FILES.clear()
        main.app.dependency_overrides.clear()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch("backend.main.rc.status")
    def test_health_reflects_rag_status(self, mock_status):
        mock_status.return_value = {"vectorstore": True, "llm": False}

        response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["vector_ready"])
        self.assertFalse(payload["llm_ready"])

    def test_metrics_endpoint_is_available(self):
        response = self.client.get("/metrics")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/plain", response.headers["content-type"])

    @patch("backend.main.rc.find_source_metadata")
    def test_source_endpoint_resolves_doc_id_to_page_key(self, mock_find_source_metadata):
        fulltext_dir = os.path.join(self.tmpdir, "fulltext")
        os.makedirs(fulltext_dir, exist_ok=True)
        page_key = "sample__p3"
        with open(os.path.join(fulltext_dir, f"{page_key}.txt"), "w", encoding="utf-8") as f:
            f.write("full page text")
        mock_find_source_metadata.return_value = {
            "doc_id": "sample_p2_i7",
            "page_key": page_key,
        }

        with patch.object(main.rc, "FULLTEXT_DIR", fulltext_dir):
            response = self.client.get("/api/source/sample_p2_i7")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["doc_id"], "sample_p2_i7")
        self.assertEqual(payload["page_key"], page_key)
        self.assertEqual(payload["text"], "full page text")

    @patch("backend.main.rc.stream_groq")
    @patch("backend.main.rc.build_generation_bundle")
    @patch("backend.main.rc.build_retrieval_bundle")
    @patch("backend.main.rc.status")
    def test_streaming_ask_emits_sources_partials_and_done(
        self,
        mock_status,
        mock_build_retrieval_bundle,
        mock_build_generation_bundle,
        mock_stream_groq,
    ):
        mock_status.return_value = {"vectorstore": True, "llm": True}
        mock_build_retrieval_bundle.return_value = {
            "sources": [{"doc_id": "doc1", "page_key": "doc__p1", "page": 1}],
        }
        mock_build_generation_bundle.return_value = {
            "prompt": "prompt",
        }
        mock_stream_groq.return_value = iter([
            {"text": "hello"},
            {"text": " hello"},
            {"done": True},
        ])

        with self.client.stream(
            "POST",
            "/api/ask/stream",
            json={"question": "What is it?", "mode": "basic"},
        ) as response:
            body = response.read().decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn('"type": "sources"', body)
        self.assertIn('"text": "hello"', body)
        self.assertIn('"text": " hello"', body)
        self.assertIn('"type": "done"', body)

    def test_upload_rejects_non_pdf(self):
        response = self.client.post(
            "/api/upload",
            files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Only PDF files allowed", response.text)

    @patch("backend.main._save_upload_file", new_callable=AsyncMock)
    @patch("backend.main._start_ingest_job")
    def test_cancel_and_delete_upload_job(self, mock_start_ingest_job, mock_save_upload_file):
        mock_save_upload_file.return_value = 12
        response = self.client.post(
            "/api/upload",
            files={"file": ("sample.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")},
        )
        self.assertEqual(response.status_code, 200)
        job = response.json()
        job_id = job["job_id"]

        cancel_response = self.client.post(f"/api/upload/cancel/{job_id}")
        self.assertEqual(cancel_response.status_code, 200)
        self.assertEqual(cancel_response.json()["status"], "canceled")

        delete_response = self.client.delete(f"/api/upload/{job_id}")
        self.assertEqual(delete_response.status_code, 200)
        self.assertTrue(delete_response.json()["ok"])
        self.assertEqual(main.UPLOAD_JOBS, {})
        self.assertEqual(main.UPLOAD_FILES, {})
        mock_start_ingest_job.assert_called_once()

    @patch("backend.main._save_upload_file", new_callable=AsyncMock)
    @patch("backend.main._start_ingest_job")
    def test_upload_status_survives_api_memory_loss(self, mock_start_ingest_job, mock_save_upload_file):
        mock_save_upload_file.return_value = 12
        response = self.client.post(
            "/api/upload",
            files={"file": ("sample.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")},
        )
        self.assertEqual(response.status_code, 200)
        job_id = response.json()["job_id"]

        main.UPLOAD_JOBS.clear()
        status_response = self.client.get(f"/api/upload/status/{job_id}")

        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.json()["job_id"], job_id)
        self.assertEqual(status_response.json()["status"], "processing")

    @patch("backend.main._save_upload_file", new_callable=AsyncMock)
    @patch("backend.main._start_ingest_job")
    def test_upload_status_prefers_newer_persisted_worker_state(self, mock_start_ingest_job, mock_save_upload_file):
        mock_save_upload_file.return_value = 12
        response = self.client.post(
            "/api/upload",
            files={"file": ("sample.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")},
        )
        self.assertEqual(response.status_code, 200)
        job_id = response.json()["job_id"]
        main.job_store.put_job(job_id, {"status": "error", "progress": 0, "detail": "Ingestion failed"})

        status_response = self.client.get(f"/api/upload/status/{job_id}")

        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.json()["status"], "error")
        self.assertEqual(status_response.json()["detail"], "Ingestion failed")


if __name__ == "__main__":
    unittest.main()
