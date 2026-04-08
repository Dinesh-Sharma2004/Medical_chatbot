---
title: Medical Chatbot
emoji: 🩺
colorFrom: blue
colorTo: green
sdk: docker
app_port: 8000
short_description: Medical chatbot with PDF upload and Groq RAG.
---

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

## Hugging Face Spaces

This project is set up to run as a Docker Space on Hugging Face.

1. Create a new Space on Hugging Face.
2. Choose `Docker` as the SDK.
3. Connect or upload this repository to the Space.
4. In the Space `Settings` page, add this secret:

- `GROQ_API_KEYS`

5. Let the Space build automatically after the push.

How this runs on the free Hugging Face tier:

- The app starts from the root `Dockerfile`.
- Hugging Face reads the YAML block at the top of this `README.md`.
- The app is exposed on port `8000`.
- FAISS data and model caches are stored under `/tmp`, which is ephemeral.

Important limitation:

- On free CPU Spaces, disk is not persistent. Uploaded PDFs, embeddings cache, and FAISS indexes will be lost when the Space rebuilds or restarts.

Recommended repo flow:

1. Create a Docker Space named something like `medical-chatbot`.
2. Push this repository to the Space repo, or duplicate the GitHub repo contents into the Space repo.
3. Add `GROQ_API_KEYS` in Hugging Face Space secrets.
4. Open the Space URL once the build finishes.

## Render Deployment

This repo is ready to deploy to Render as a single Docker web service. The container builds the React frontend, serves it from FastAPI, and stores uploaded PDFs plus the FAISS index on a persistent disk.

1. Push this project to GitHub.
2. In Render, create a new Blueprint service and point it at the repo.
3. Render will detect [`render.yaml`](render.yaml) and create:
   - one Docker web service
4. In Render, set the required secret:

- `GROQ_API_KEYS` required, comma-separated keys are supported

5. Deploy the service.

Recommended environment values are already defined in `render.yaml`:

- `DB_FAISS_BASE=/tmp/vectorstore`
- `EMBED_MODEL=BAAI/bge-small-en-v1.5`
- `EMBED_BATCH_SIZE=4`
- `RAG_MAX_PDF_PAGES=80`
- `GROQ_MODEL=llama-3.1-8b-instant`

After deploy:

- App: `https://<your-render-service>.onrender.com/`
- Health: `https://<your-render-service>.onrender.com/api/health`

Important notes:

- Render free instances spin down when idle, so the first request can be slow.
- On the free plan, uploaded PDFs and generated indexes are stored in ephemeral storage at `/tmp/vectorstore` and will be lost after restarts or redeploys.
- If you need persistent uploaded documents and FAISS indexes on Render, switch to a paid plan and add a disk, then set `DB_FAISS_BASE=/data/vectorstore`.
- Do not commit `backend/.env`; set secrets in Render instead.

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

- Render deploy fails because of large local files:
  - Ensure generated folders like `backend/data/` and `vectorstore/` are not committed.
  - This repo's `.dockerignore` excludes local runtime data and `.env` files from the build context.

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
