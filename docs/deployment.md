# Deployment

## Kubernetes

The Kubernetes deployment separates the major components:

```text
Frontend
Backend API
Ingestion Workers
Redis
Prometheus
Grafana
Ingress
Autoscaling
```

Deploy:

```bash
kubectl apply -k k8s
```

---

## Local Kubernetes

Build the backend:

```bash
docker build \
  -f docker/backend.Dockerfile \
  -t medical-chatbot-backend:local .
```

Build the frontend:

```bash
docker build \
  -f docker/frontend.Dockerfile \
  -t medical-chatbot-frontend:local .
```

Deploy:

```bash
kubectl apply -k k8s/overlays/local
```

### Port forwarding

```bash
kubectl -n medical-chatbot \
  port-forward svc/frontend 8080:80
```

```bash
kubectl -n medical-chatbot \
  port-forward svc/backend 8000:8000
```

```bash
kubectl -n medical-chatbot \
  port-forward svc/prometheus 9090:9090
```

```bash
kubectl -n medical-chatbot \
  port-forward svc/grafana 3000:3000
```

---

## AWS EKS

The production Kubernetes architecture is designed to support AWS EKS.

For shared uploaded PDFs and FAISS indexes, `ReadWriteMany` PVCs should use **EFS or another appropriate RWX-compatible storage class**.

```text
                       AWS EKS
                          │
          ┌───────────────┼───────────────┐
          │               │               │
          ▼               ▼               ▼
      Frontend         Backend          Workers
                          │               │
                          ▼               ▼
                        Redis       Shared Storage
                                          │
                                          ▼
                                        FAISS
```

Optional Prometheus Operator resources are available at:

```text
k8s/overlays/operator-monitoring
```

---

## GitLab CI/CD

The repository includes a GitLab-first CI/CD pipeline.

```text
Git Push
   │
   ▼
Test / Compile
   │
   ▼
Frontend Build
   │
   ▼
Docker Build
   │
   ▼
GitLab Container Registry
   │
   ▼
Manual Deployment
   │
   ▼
AWS EKS
```

### Pipeline

1. Install backend dependencies
2. Run `python -m compileall backend`
3. Install frontend dependencies
4. Run `npm run build`
5. Build backend image
6. Build frontend image
7. Push both images
8. Optionally deploy to EKS

### Required GitLab variables

```text
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
AWS_REGION
EKS_CLUSTER_NAME
GROQ_API_KEYS
```

GitLab provides:

```text
CI_REGISTRY
CI_REGISTRY_USER
CI_REGISTRY_PASSWORD
CI_REGISTRY_IMAGE
```

The deployment job creates or updates:

```text
gitlab-registry
medical-chatbot-secrets
```

and applies:

```bash
kubectl apply -k k8s
```

---

## Hugging Face Spaces

Medibot is configured to run as a Docker Space.

## Setup

1. Create a new Hugging Face Space.
2. Select **Docker**.
3. Upload or connect this repository.
4. Add the secret:

```text
GROQ_API_KEYS
```

5. Push the repository.
6. Wait for the Space to build.

The application is exposed on port:

```text
8000
```

### ⚠️ Free-tier storage

The free CPU environment uses ephemeral storage.

Uploaded PDFs, embedding caches, and FAISS indexes may be lost after restarts or rebuilds.

Hugging Face Spaces is therefore best suited for:

```text
Demos · Prototypes · Experiments · Evaluation
```

rather than persistent production document storage.

---

## Render

The repository includes:

```text
render.yaml
```

and can be deployed as a Docker web service.

## Setup

1. Push the repository to your connected Git provider.
2. Create a Render Blueprint.
3. Point it to the repository.
4. Configure:

```text
GROQ_API_KEYS
```

5. Deploy.

Recommended values:

```env
DB_FAISS_BASE=/tmp/vectorstore
EMBED_MODEL=BAAI/bge-small-en-v1.5
EMBED_BATCH_SIZE=4
RAG_MAX_PDF_PAGES=80
GROQ_MODEL=llama-3.1-8b-instant
```

Health endpoint:

```text
/api/health
```

### Storage

Free Render instances may spin down when idle and use ephemeral storage.

For persistent storage on a paid instance:

```env
DB_FAISS_BASE=/data/vectorstore
```

---

## Railway

Login:

```bash
npx @railway/cli login
```

Initialize:

```bash
npx @railway/cli init --name Medical_chatbot
```

Link the service:

```bash
npx @railway/cli service link backend
```

Deploy:

```bash
npx @railway/cli up --service backend
```

Configure:

```text
GROQ_API_KEYS
GROQ_MODEL
DB_FAISS_BASE
EMBED_MODEL
EMBED_BATCH_SIZE
RAG_MAX_PDF_PAGES
```

Recommended:

```env
GROQ_MODEL=llama-3.1-8b-instant
DB_FAISS_BASE=/data/vectorstore
EMBED_MODEL=BAAI/bge-small-en-v1.5
EMBED_BATCH_SIZE=4
RAG_MAX_PDF_PAGES=80
```

Add persistent storage:

```bash
npx @railway/cli volume add
```

Mount:

```text
/data
```

Set:

```bash
npx @railway/cli variable set \
  --service backend \
  --environment production \
  DB_FAISS_BASE=/data/vectorstore
```

Redeploy:

```bash
npx @railway/cli up --service backend
```

---

## Deployment Options

| Platform          | Best For            | Persistent Storage | Complexity |
| ----------------- | ------------------- | -----------------: | ---------: |
| 🐳 Docker         | Development         |                  ✅ |        Low |
| 🐳 Docker Compose | Full local stack    |                  ✅ |        Low |
| 🤗 Hugging Face   | Demo / prototype    |        ❌ Free tier |        Low |
| 🚀 Render         | Simple deployment   |  ⚠️ Plan dependent |        Low |
| 🚂 Railway        | Small production    |      ✅ With volume |        Low |
| ☸️ Kubernetes     | Production          |                  ✅ |       High |
| ☁️ AWS EKS        | Scalable production |                  ✅ |       High |

---
