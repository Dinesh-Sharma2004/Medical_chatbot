# Development

## Quick Start

## Prerequisites

You will need:

* Python **3.11 or 3.12**
* Node.js
* Docker
* Groq API key

---

## 1. Clone

```bash
git clone <your-repository-url>
cd medical-chatbot
```

---

## 2. Configure the backend

Create:

```text
backend/.env
```

Minimum configuration:

```env
GROQ_API_KEYS=your_groq_api_key
```

For production authentication:

```env
AUTH_SECRET=your_secure_secret
AUTH_DATABASE_URL=postgresql://...
GOOGLE_CLIENT_ID=your_google_client_id
GROQ_API_KEYS=key1,key2
```

> 🔒 Never commit `.env` files or real credentials.

---

## 3. Install backend dependencies

Create a virtual environment:

```bash
python -m venv .venv
```

### Windows

```bash
.venv\Scripts\activate
```

### Linux / macOS

```bash
source .venv/bin/activate
```

Install:

```bash
pip install -r backend/requirements.txt
```

---

## 4. Install frontend dependencies

```bash
cd frontend
npm install
npm run build
cd ..
```

---

## 5. Start the API

```bash
uvicorn backend.main:app \
  --host 0.0.0.0 \
  --port 8000
```

Open:

| Service        | URL                                |
| -------------- | ---------------------------------- |
| 🩺 Application | `http://localhost:8000/`           |
| ❤️ Health      | `http://localhost:8000/api/health` |
| 📊 Metrics     | `http://localhost:8000/metrics`    |

---

## Docker

Build the application:

```bash
docker build -t medical-chatbot .
```

Run:

```bash
docker run \
  --env-file backend/.env \
  -p 8000:8000 \
  medical-chatbot
```

---

## Full Local Stack

For the complete multi-service environment:

```bash
docker compose up --build
```

This starts:

```text
                         ┌──────────────┐
                         │   Frontend   │
                         │    :8080     │
                         └──────┬───────┘
                                │
                                ▼
                         ┌──────────────┐
                         │   Gateway    │
                         │    :8000     │
                         └──────┬───────┘
                                │
                ┌───────────────┼───────────────┐
                │               │               │
                ▼               ▼               ▼
           Backend 1       Backend 2       Backend 3
                │               │               │
                └───────────────┼───────────────┘
                                │
                                ▼
                         ┌──────────────┐
                         │    Redis     │
                         └──────┬───────┘
                                │
                                ▼
                       ┌────────────────┐
                       │ Ingest Worker  │
                       └───────┬────────┘
                               │
                               ▼
                         ┌────────────┐
                         │   FAISS    │
                         └────────────┘
```

### Services

| Service         |     Port | Purpose        |
| --------------- | -------: | -------------- |
| Backend gateway |   `8000` | API            |
| Frontend        |   `8080` | Web UI         |
| Prometheus      |   `9090` | Metrics        |
| Grafana         |   `3000` | Monitoring     |
| Redis           | Internal | Job queue      |
| Ingest worker   | Internal | PDF processing |

### Grafana

Default local credentials:

```text
Username: admin
Password: admin
```

Change these before exposing Grafana externally.

---

## Alternate Ports

If port `8000` is already occupied:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.ports.override.yml \
  up --build
```

This exposes:

```text
Backend   → http://localhost:8010
Frontend  → http://localhost:8081
```

Telemetry ports can be overridden with:

```env
PROMETHEUS_HOST_PORT=
GRAFANA_HOST_PORT=
```

---

## Ingestion Configuration

Recommended local indexing settings:

```env
EMBED_BATCH_SIZE=32
EMBED_THREADS=4
EMBED_PARALLEL=2
INGEST_MAX_WORKERS=8
```

For memory-constrained environments:

```env
EMBED_BATCH_SIZE=4
RAG_MAX_PDF_PAGES=80
```

---

## Model Configuration

## Embeddings

Default model:

```text
BAAI/bge-small-en-v1.5
```

Configure:

```env
EMBED_MODEL=BAAI/bge-small-en-v1.5
```

## Groq

Default model:

```env
GROQ_MODEL=llama-3.1-8b-instant
```

Multiple API keys are supported:

```env
GROQ_API_KEYS=key1,key2,key3
```

---
