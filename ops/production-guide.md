# Production Setup Guide

This repository is organized for a production-style medical chatbot deployment with a split frontend/backend architecture.

## 1) Project Architecture

```text
browser
  -> Ingress / Load Balancer
    -> frontend service (React static app)
    -> backend service (FastAPI + RAG + metrics, multi-replica)
      -> persistent volume for uploaded PDFs
      -> persistent volume for FAISS vector store
      -> Prometheus / Grafana
```

### Suggested folder structure

```text
backend/
  main.py
  ingest.py
  rag_chain.py
  requirements.txt
frontend/
  src/
  nginx/
docker/
  backend.Dockerfile
  frontend.Dockerfile
k8s/
  namespace.yaml
  configmap.yaml
  pvc.yaml
  backend-*.yaml
  frontend-*.yaml
  ingress.yaml
  monitoring/
.gitlab-ci.yml
ops/
  production-guide.md
```

## 2) Docker

The repository now ships with:

- `docker/backend.Dockerfile` for the API and RAG pipeline.
- `docker/frontend.Dockerfile` for a small NGINX-based React runtime.
- `docker-compose.yml` for local backend/frontend orchestration.

### Local run

```bash
docker compose up --build
```

Open:

- Frontend: `http://localhost:8080`
- Backend health: `http://localhost:8000/api/health`
- Metrics: `http://localhost:8000/metrics`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000`

## 3) CI/CD

The GitLab pipeline does four things:

1. Installs backend and frontend dependencies.
2. Compiles the backend and builds the frontend.
3. Builds and pushes Docker images to the GitLab Container Registry.
4. Applies the Kubernetes manifests and updates image tags in-place.

### Required GitLab CI/CD variables

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_REGION`
- `EKS_CLUSTER_NAME`
- `GROQ_API_KEYS`

Built-in GitLab registry variables used by the pipeline:

- `CI_REGISTRY`
- `CI_REGISTRY_USER`
- `CI_REGISTRY_PASSWORD`
- `CI_REGISTRY_IMAGE`

The deploy job creates or updates:

- `gitlab-registry` as the image pull secret in Kubernetes
- `medical-chatbot-secrets` for `GROQ_API_KEYS`

## 4) Kubernetes

Use the manifests under `k8s/` as the base deployment.

### Apply everything

```bash
kubectl apply -k k8s
```

### What is included

- `Deployment` for backend and frontend.
- `Service` objects for internal routing.
- `Ingress` for public traffic.
- `HPA` for autoscaling.
- `PodDisruptionBudget` for rolling maintenance safety.
- `PVC` for the PDF uploads and FAISS index.
- Plain Kubernetes `Prometheus` and `Grafana` resources for local and portable monitoring.
- Optional operator-specific `ServiceMonitor` and `PrometheusRule` overlay when Prometheus Operator is installed.

### Local cluster overlay

Build local images:

```bash
docker build -f docker/backend.Dockerfile -t medical-chatbot-backend:local .
docker build -f docker/frontend.Dockerfile -t medical-chatbot-frontend:local .
```

Apply:

```bash
kubectl apply -k k8s/overlays/local
```

## 5) Deployment Flow

```text
git push
  -> GitLab CI/CD
    -> tests + build
    -> docker build
    -> push to GitLab Container Registry
    -> kubectl apply -k k8s
    -> rollout update
    -> ingress routes live traffic
```

## 6) Monitoring and Scaling

### Monitoring stack

- Prometheus scrapes `/metrics` from the backend.
- Grafana reads Prometheus for dashboards.
- Alertmanager pages or notifies on latency and error thresholds.
- OpenTelemetry can be added next for traces across API, retrieval, and model calls.

### Scaling strategy

- Frontend scales with pod replicas because it is static and cheap.
- Backend scales on CPU and request load.
- Document ingestion is the heaviest part, so it should stay on persistent storage and run with limited concurrency.
- For very large ingest jobs, move ingestion to a worker queue or batch job.

## 7) SLA, SLO, and SLI

### Realistic SLA targets

- Availability: `99.9%`
- Non-AI API latency: `< 300ms p95`
- RAG answer latency: `< 2-3s p95`
- Error rate: `< 1%`
- Throughput target: size it for expected peak chatbot traffic, then keep 30% headroom

### Internal SLOs

- Availability: `99.95%`
- Non-AI API latency: `< 200ms p95`
- RAG answer latency: `< 2s p95`
- Error rate: `< 0.5%`

### SLIs to measure

- Request latency
- Request success rate
- Pod uptime
- Ingestion completion success
- Retrieval latency

### Enforcement

- Kubernetes liveness and readiness probes.
- HPA for traffic bursts.
- PodDisruptionBudget for maintenance safety.
- Prometheus alerting rules for SLO burn or sustained degradation.
- Ingress/body-size limits to prevent runaway uploads.
- Rate limiting at the ingress or API gateway layer.

## 8) Security

- Store secrets in Kubernetes Secrets or AWS Secrets Manager.
- Do not commit `.env` files.
- Run containers as non-root.
- Set resource requests and limits.
- Restrict inbound traffic to Ingress only.
- Add RBAC for admins, reviewers, and users when auth is introduced.

## 9) Best path to production

1. Run locally with `docker compose`.
2. Deploy to a staging EKS cluster.
3. Verify `/api/health` and `/metrics`.
4. Load test upload + retrieval.
5. Turn on alerts.
6. Promote to production with blue-green or rolling deploys.
