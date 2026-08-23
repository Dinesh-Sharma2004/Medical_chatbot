---
title: Medical Chatbo
sdk: docker
app_port: 8000
short_description: Medical chatbot with PDF upload and Groq RAG.
---

# Medical Chatbot (FastAPI + React + RAG)

Medical Chatbot is a full-stack, microservice-oriented app that lets users upload PDF documents, build a FAISS vector index asynchronously, and ask medical questions with Groq-powered responses.

## Stack

- API service: FastAPI, LangChain, FAISS retrieval, Groq chat
- Auth service: FastAPI, Postgres-backed accounts, Google Sign-In, signed bearer tokens
- Ingestion worker service: Redis/RQ jobs, PDF extraction, embeddings, FAISS rebuilds
- Queue: Redis
- Frontend: React + Vite
- Embeddings: FastEmbed (`BAAI/bge-small-en-v1.5`)
- LLM: Groq API
- Deployment: Docker, Kubernetes, GitLab CI/CD, AWS EKS

## Project Structure

- `backend/` FastAPI app, ingestion, RAG chain
- `backend/ingest_worker.py` background ingestion worker entrypoint
- `backend/job_store.py` shared upload job status store
- `frontend/` React app
- `docker/` production Dockerfiles for backend and frontend
- `k8s/` Kubernetes manifests for backend, frontend, ingress, HPA, and alerting
- `testing/` automated tests plus evaluation and verification reports
- `.gitlab-ci.yml` GitLab pipeline for test, image build/push, and EKS deploy
- `ops/production-guide.md` end-to-end production deployment guide
- `docker-compose.yml` local container orchestration

## Local Run

1. Create backend environment file at `backend/.env`.
2. Use Python `3.11` or `3.12` for the backend virtual environment.
3. Install backend dependencies:

```bash
pip install -r backend/requirements.txt
```

4. Install frontend dependencies:

```bash
cd frontend
npm install
npm run build
cd ..
```

5. Start API:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

6. Open:
- `http://localhost:8000/`
- Health: `http://localhost:8000/api/health`
- Metrics: `http://localhost:8000/metrics`

Recommended local indexing settings:

- `EMBED_BATCH_SIZE=32`
- `EMBED_THREADS=4`
- `EMBED_PARALLEL=2`
- `INGEST_MAX_WORKERS=8`

## Testing

Tests and generated reports live under `testing/`.

```bash
python -m unittest testing.tests.test_api
```

LLM evaluation reports are written to `testing/reports/evaluations/` by default.

## Docker

```bash
docker build -t medical-chatbot .
docker run --env-file backend/.env -p 8000:8000 medical-chatbot
```

For the full local product stack with multiple backend nodes, a gateway, and telemetry:

```bash
docker compose up --build
```

This starts:

- `backend-1`, `backend-2`, `backend-3` sharing the upload and vectorstore volumes
- `ingest-worker` consuming Redis jobs and rebuilding FAISS outside the API request path
- `redis` queue for durable ingestion dispatch
- `backend` gateway on `http://localhost:8000`
- `frontend` on `http://localhost:8080`
- `prometheus` on `http://localhost:9090`
- `grafana` on `http://localhost:3000`

Default Grafana login:

- username: `admin`
- password: `admin`

If port `8000` is already busy on your machine, use the included alternate-port override:

```bash
docker compose -f docker-compose.yml -f docker-compose.ports.override.yml up --build
```

This maps:

- backend to `http://localhost:8010`
- frontend to `http://localhost:8081`

You can also override telemetry ports with `PROMETHEUS_HOST_PORT` and `GRAFANA_HOST_PORT`.

## Kubernetes

The Kubernetes manifests deploy separate API, ingestion worker, Redis, frontend,
Prometheus, and Grafana services. For AWS/EKS, back the `ReadWriteMany` PVCs with
EFS or another RWX storage class so API and worker pods can share uploaded PDFs
and the live vectorstore safely.

Base manifests:

```bash
kubectl apply -k k8s
```

Local cluster workflow:

```bash
docker build -f docker/backend.Dockerfile -t medical-chatbot-backend:local .
docker build -f docker/frontend.Dockerfile -t medical-chatbot-frontend:local .
kubectl apply -k k8s/overlays/local
```

Helpful port-forwards:

```bash
kubectl -n medical-chatbot port-forward svc/frontend 8080:80
kubectl -n medical-chatbot port-forward svc/backend 8000:8000
kubectl -n medical-chatbot port-forward svc/prometheus 9090:9090
kubectl -n medical-chatbot port-forward svc/grafana 3000:3000
```

Optional Prometheus Operator resources remain available at `k8s/overlays/operator-monitoring`.

## GitLab CI/CD

This repository includes a GitLab-first pipeline in `.gitlab-ci.yml`.

What the pipeline does:

1. Installs backend dependencies and runs `python -m compileall backend`.
2. Installs frontend dependencies and runs `npm run build`.
3. Builds backend and frontend images from `docker/backend.Dockerfile` and `docker/frontend.Dockerfile`.
4. Pushes both images to the GitLab Container Registry.
5. Offers a manual deploy job for the default branch that applies `k8s/` to EKS and rolls the deployments forward.

Required GitLab CI/CD variables:

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_REGION`
- `EKS_CLUSTER_NAME`
- `GROQ_API_KEYS`

Notes:

- `CI_REGISTRY`, `CI_REGISTRY_USER`, `CI_REGISTRY_PASSWORD`, and `CI_REGISTRY_IMAGE` are built-in GitLab variables.
- The deploy job creates or updates the Kubernetes secrets `gitlab-registry` and `medical-chatbot-secrets`.
- The deploy job applies the full Kustomize bundle with `kubectl apply -k k8s`.

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

1. Push this project to your connected Git provider repository.
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
- `GET /metrics`
- `GET /api/auth/config`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/google`
- `GET /api/auth/me`
- `GET /api/chat-history`
- `PUT /api/chat-history`
- `POST /api/upload`
- `GET /api/upload/status/{job_id}`
- `POST /api/upload/cancel/{job_id}`
- `DELETE /api/upload/{job_id}`
- `POST /api/ask`
- `POST /api/ask/stream`
- `GET /api/source/{doc_id}`

## Authentication

Email/password authentication works locally without extra providers. In the full stack, users and chat history are stored in Postgres through `AUTH_DATABASE_URL`. If that variable is unset, the backend falls back to local SQLite at `backend/data/medibot_auth.sqlite3`.

Recommended production variables:

- `AUTH_SECRET`: required for stable, secure token signing
- `AUTH_DATABASE_URL`: Postgres connection string for accounts and chat history
- `GOOGLE_CLIENT_ID`: enables Google Sign-In in the frontend and backend verifier

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

## Production Guide

For the full CI/CD, Kubernetes, SLA, monitoring, autoscaling, and security setup, see [ops/production-guide.md](ops/production-guide.md).
