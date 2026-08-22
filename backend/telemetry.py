import time

try:
    from prometheus_client import Counter, Gauge, Histogram, CONTENT_TYPE_LATEST, generate_latest
except Exception:  # pragma: no cover - metrics are optional at runtime
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"

    def generate_latest():
        return b""

    class _NullMetric:
        def labels(self, *args, **kwargs):
            return self

        def inc(self, amount=1):
            return None

        def dec(self, amount=1):
            return None

        def observe(self, value):
            return None

        def set(self, value):
            return None

        def set_to_current_time(self):
            return self.set(time.time())

    def Counter(*args, **kwargs):  # type: ignore[misc]
        return _NullMetric()

    def Gauge(*args, **kwargs):  # type: ignore[misc]
        return _NullMetric()

    def Histogram(*args, **kwargs):  # type: ignore[misc]
        return _NullMetric()


REQUEST_COUNT = Counter(
    "medical_chatbot_requests_total",
    "Total HTTP requests handled by the API",
    ["method", "path", "status"],
)
REQUEST_LATENCY = Histogram(
    "medical_chatbot_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 3, 5, 10, 20, 30),
)
INFLIGHT_REQUESTS = Gauge(
    "medical_chatbot_inflight_requests",
    "Number of requests currently in flight",
)

INGEST_ACTIVE_JOBS = Gauge(
    "medical_chatbot_ingest_active_jobs",
    "Number of ingestion jobs currently running",
)
INGEST_JOBS_TOTAL = Counter(
    "medical_chatbot_ingest_jobs_total",
    "Number of ingestion jobs by outcome",
    ["status"],
)
INGEST_DURATION = Histogram(
    "medical_chatbot_ingest_duration_seconds",
    "End-to-end ingestion duration",
    buckets=(1, 2, 5, 10, 20, 30, 60, 120, 300, 600),
)
INGEST_PDFS_TOTAL = Counter(
    "medical_chatbot_ingest_pdfs_total",
    "Number of PDFs submitted for ingestion",
)
INGEST_CHUNKS_TOTAL = Counter(
    "medical_chatbot_ingest_chunks_total",
    "Number of chunks added to the vector index",
)
INGEST_LAST_SUCCESS = Gauge(
    "medical_chatbot_ingest_last_success_unixtime",
    "Unix timestamp of the last successful ingestion",
)

RETRIEVAL_LATENCY = Histogram(
    "medical_chatbot_retrieval_duration_seconds",
    "Time spent retrieving candidate documents",
    ["mode"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)
RETRIEVAL_RESULTS = Histogram(
    "medical_chatbot_retrieval_results",
    "Number of retrieval results selected",
    ["mode"],
    buckets=(0, 1, 2, 4, 6, 8, 10, 20, 40),
)

LLM_REQUESTS_TOTAL = Counter(
    "medical_chatbot_llm_requests_total",
    "Number of LLM requests by result",
    ["status"],
)
LLM_LATENCY = Histogram(
    "medical_chatbot_llm_request_duration_seconds",
    "Time spent waiting on the LLM provider",
    ["streaming"],
    buckets=(0.1, 0.25, 0.5, 1, 2, 3, 5, 10, 20, 30, 60),
)

VECTORSTORE_RELOAD_TOTAL = Counter(
    "medical_chatbot_vectorstore_reloads_total",
    "Number of vectorstore reload attempts",
    ["reason", "status"],
)
VECTORSTORE_LAST_RELOAD = Gauge(
    "medical_chatbot_vectorstore_last_reload_unixtime",
    "Unix timestamp of the last successful vectorstore reload",
)
