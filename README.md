# Medical Chatbot (FastAPI + React + RAG)

Medical Chatbot is a full-stack app that lets users upload PDF documents, build a FAISS vector index, and ask medical questions with Groq-powered responses.

## Stack

- Backend: FastAPI, LangChain, FAISS
- Frontend: React + Vite
- Embeddings: FastEmbed (`BAAI/bge-small-en-v1.5`)
- LLM: Groq API
- Deployment: Railway (single Docker service)

## Project Structure

- `backend/` FastAPI app, ingestion, RAG chain
- `frontend/` React app
- `Dockerfile` builds frontend and serves with backend
- `docker-compose.yml` local container orchestration

## Local Run

1. Create backend environment file at `backend/.env`.
2. Install backend dependencies:

```bash
pip install -r backend/requirements.txt
```

3. Install frontend dependencies:

```bash
cd frontend
npm install
npm run build
cd ..
```

4. Start API:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

5. Open:
- `http://localhost:8000/`
- Health: `http://localhost:8000/api/health`

## Docker

```bash
docker build -t medical-chatbot .
docker run --env-file backend/.env -p 8000:8000 medical-chatbot
```

## Railway Deployment

1. Login and initialize:

```bash
npx @railway/cli login
npx @railway/cli init --name Medical_chatbot
```

2. Create/link service and deploy:

```bash
npx @railway/cli service link backend
npx @railway/cli up --service backend
```

3. Set required variables:

- `GROQ_API_KEYS` (required, comma-separated keys supported)
- `GROQ_MODEL` (default: `llama-3.1-8b-instant`)
- `DB_FAISS_BASE` (recommended with volume: `/data/vectorstore`)
- `EMBED_MODEL` (default: `BAAI/bge-small-en-v1.5`)
- `EMBED_BATCH_SIZE` (recommended: `4` on small Railway plans)
- `RAG_MAX_PDF_PAGES` (recommended: `80` on small Railway plans)

4. Add persistent volume for vectorstore:

```bash
npx @railway/cli volume add
```

Mount path:

- `/data`

Then set:

```bash
npx @railway/cli variable set --service backend --environment production DB_FAISS_BASE=/data/vectorstore
```

Redeploy:

```bash
npx @railway/cli up --service backend
```

## API Endpoints

- `GET /api/health`
- `POST /api/upload`
- `GET /api/upload/status/{job_id}`
- `POST /api/ask`
- `POST /api/ask/stream`
- `GET /api/source/{doc_id}`

## Troubleshooting

- `{"detail":"Not Found"}` for `/app/health`:
  - Use `/api/health` instead.

- `RAG not ready`:
  - Upload at least one PDF first.
  - Ensure vectorstore exists in `DB_FAISS_BASE`.

- Frontend loads but blank/errors:
  - Ensure static assets are served from `/assets`.
  - Hard refresh browser after deploy.

- Railway OOM during ingest:
  - Reduce `EMBED_BATCH_SIZE` (e.g. `4`).
  - Reduce `RAG_MAX_PDF_PAGES` (e.g. `80`).
  - Upload smaller PDFs first.

## Security

- Never commit real API keys.
- Rotate keys immediately if leaked.
