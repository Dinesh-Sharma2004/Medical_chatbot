# Architecture

```mermaid
flowchart TB

    USER["👤 User"]

    FRONTEND["⚛️ React + Vite"]

    API["⚡ FastAPI"]

    AUTH["🔐 Authentication"]

    DB[("🐘 PostgreSQL")]

    REDIS["🔴 Redis"]

    WORKER["⚙️ Ingestion Worker"]

    PDF["📄 PDF Extraction"]

    EMBED["🧠 FastEmbed"]

    FAISS[("🔎 FAISS Vectorstore")]

    GROQ["🤖 Groq LLM"]

    PROM["📊 Prometheus"]

    GRAF["📈 Grafana"]

    USER --> FRONTEND
    FRONTEND --> API

    API --> AUTH
    AUTH --> DB

    API --> REDIS
    REDIS --> WORKER

    WORKER --> PDF
    PDF --> EMBED
    EMBED --> FAISS

    API --> FAISS
    API --> GROQ

    API --> PROM
    PROM --> GRAF
```

---

## Key Design Decision

The ingestion pipeline is intentionally **decoupled from the chat API**.

A simpler implementation could process everything inside the upload request:

```text
Upload
  │
  ▼
Extract
  │
  ▼
Embed
  │
  ▼
Build FAISS
  │
  ▼
Return
```

This can become problematic when processing large documents.

Medibot instead uses:

```text
                    PDF Upload
                        │
                        ▼
                  ┌───────────┐
                  │  FastAPI  │
                  └─────┬─────┘
                        │
                        ▼
                  ┌───────────┐
                  │   Redis   │
                  │   Queue   │
                  └─────┬─────┘
                        │
                        ▼
                ┌───────────────┐
                │ Ingest Worker │
                └───────┬───────┘
                        │
                        ▼
              PDF → Embed → FAISS
```

This allows the system to scale **chat traffic and document processing independently**.

---

## Scaling Philosophy

Medibot separates **chat traffic** from **document ingestion**.

```text
                    MEDIBOT
                       │
          ┌────────────┴────────────┐
          │                         │
          ▼                         ▼
      CHAT PATH               INGESTION PATH
          │                         │
          ▼                         ▼
       FastAPI                    Redis
          │                         │
          ▼                         ▼
        Groq                  RQ Workers
                                    │
                                    ▼
                           PDF + Embeddings
                                    │
                                    ▼
                                  FAISS
```

This architecture allows:

```text
API replicas        → scale independently
Ingestion workers   → scale independently
Redis               → decouple workloads
Vector storage      → persist knowledge
Monitoring          → observe the system
```

---
