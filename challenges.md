# Challenges Faced While Building and Verifying the Medical Chatbot

This document captures the main problems we ran into while building, running, and verifying the Medical Chatbot stack across local development, Docker, and Kubernetes-oriented deployment files.

The goal is not just to list failures, but to record what actually helped us move forward.

## Summary

The project is structurally sound and the core stack does run, but verification exposed a mix of:

- local machine issues,
- environment and dependency mismatches,
- container configuration gaps, and
- deployment-manifest follow-ups.

## Challenge Log

| Area | Problem faced | What happened | Resolution / mitigation used | Status |
| --- | --- | --- | --- | --- |
| Python environment on Windows | The default `python` / `uvicorn` path pointed to the Windows Store shim instead of the intended project environment. | Direct local startup failed or behaved inconsistently because the shell was not using the right interpreter. | We switched to the project virtual environment directly and used `.venv313\Scripts\python.exe` for all backend verification. | Resolved for local verification |
| Backend startup configuration | The backend requires `GROQ_API_KEYS` at import time. | Importing `backend.main` failed immediately when the process was started without loading `backend/.env`. | We started the API with `--env-file backend/.env` so the backend saw the same variables it expects in normal deployment. In hosted environments, the same values must come from platform secrets. | Resolved |
| Local port conflict | Port `8000` was already occupied on the machine by Docker Desktop / WSL-related processes. | The backend could start, but binding to `127.0.0.1:8000` failed with `WinError 10013`. Docker Compose also failed because host port `8000` was already allocated. | We verified the app on alternate ports such as `8010`, `8012`, and `8081`. The project still keeps `8000` as the default application port for deployment. | Resolved with local workaround |
| Frontend local build | `npm run build` failed in the current shell because Node child-process spawning was blocked with `spawn EPERM`. | Vite could not launch `esbuild`, even though the binary itself was present. | We validated the frontend using the already built `frontend/dist` output and then verified that the frontend builds successfully inside Docker, where the toolchain runs normally. | Mitigated |
| Local telemetry dependency | The backend treats Prometheus metrics as optional, and `.venv313` did not contain `prometheus_client`. | Local `/metrics` returned `200` but with an empty body, so telemetry looked present but was not actually populated. | We confirmed that the Docker image installs `prometheus-client` from `backend/requirements.txt`, and telemetry worked correctly there. The local virtual environment should be synced with the same dependency set. | Mitigated locally, resolved in container build |
| Live Groq requests during local verification | Outbound network calls from the local verification environment were blocked. | Health checks reported `llm_ready=true`, but actual `POST /api/ask` and streaming generation hit `httpx.ConnectError` / `WinError 10013` when trying to reach Groq. | We separated stack verification into two parts: local app health/readiness verification and container/runtime verification. Full answer-generation testing should be done in an environment that allows outbound HTTPS to Groq. | Mitigated |
| Docker vector store path | `DB_FAISS_BASE` in `backend/.env` is stored as `\"vectorstore\"` with quotes. | Inside the backend container, the app looked for `\"vectorstore\"/db_faiss` instead of the mounted `/app/vectorstore`, so container health showed `vector_ready=false` and RAG was not ready. | During diagnosis, we confirmed that deployment targets work best with unquoted, explicit paths such as `/app/vectorstore`, `/tmp/vectorstore`, or `/data/vectorstore`. The root cause is now known and should be normalized in environment configuration. | Root cause identified, repo follow-up pending |
| SPA route ordering | The diagnostic endpoint `/_frontend_info` is defined after the catch-all SPA route in `backend/main.py`. | Requests to `/_frontend_info` returned `404` because the catch-all route handled them first. | We confirmed the issue during runtime verification. The fix is to place `/_frontend_info` before `/{full_path:path}`. | Follow-up pending |
| Docker Compose host mapping | The Compose file maps backend to `8000:8000`, which clashed with the machine's existing listener on port `8000`. | `docker compose up --build` built both images successfully but could not finish starting the backend container. | We finished container verification by running the built images manually on alternate ports. On machines where `8000` is free, the existing Compose file should work as written. | Resolved with local workaround |
| Container image verification | We needed to verify whether the project was only locally runnable or actually image-ready. | Because of the local toolchain restrictions, frontend and backend verification had to move to container builds. | We built both images successfully from `docker/backend.Dockerfile` and `docker/frontend.Dockerfile`, then ran them directly to confirm the frontend served correctly and backend health responded. | Resolved |
| GitLab CI file paths | `.gitlab-ci.yml` points to `backend/Dockerfile` and `frontend/Dockerfile`, but the active Dockerfiles live under `docker/`. | If GitLab CI is used as-is, image builds will fail because those referenced Dockerfiles do not exist in the current project structure. | The correct fix is to update the GitLab pipeline to use `docker/backend.Dockerfile` and `docker/frontend.Dockerfile`. | Follow-up pending |
| GitHub Actions deployment completeness | The GitHub Actions workflow applies `prometheus-rules.yaml` but does not apply `servicemonitor.yaml`. | Monitoring rules may be created while the scrape target itself is never registered with Prometheus Operator. | The deployment step should also apply `k8s/monitoring/servicemonitor.yaml`, or switch fully to `kubectl apply -k k8s` so the monitored bundle stays in sync. | Follow-up pending |
| Kubernetes validation without a live cluster | Some Kubernetes validation steps depend on CRDs and an active API server. | `kubectl apply --dry-run=client` still failed in this environment because there was no local cluster and the manifests include Prometheus Operator resources. | We rendered the full stack successfully with `kubectl kustomize k8s`, which verified manifest composition. Full validation still needs a real cluster with the required CRDs installed. | Mitigated |

## What Worked Well

- The backend starts correctly in `.venv313` when launched with the proper env file.
- The frontend static build is already wired into FastAPI serving.
- The Docker backend and frontend images both build successfully.
- The backend health endpoint is correctly exposed as `/api/health`.
- Prometheus instrumentation is implemented in the backend and works when the dependency is present.
- The Kubernetes manifest set renders cleanly through `kubectl kustomize`.

## Recommended Next Fixes

1. Normalize `DB_FAISS_BASE` so container and local runs use the same unquoted path convention.
2. Reorder `/_frontend_info` ahead of the SPA catch-all route.
3. Sync `.venv313` with `backend/requirements.txt` so local telemetry behaves like the container image.
4. Update `.gitlab-ci.yml` to point at `docker/backend.Dockerfile` and `docker/frontend.Dockerfile`.
5. Update the GitHub Actions deploy job to include the `ServiceMonitor`, or deploy the whole `k8s/` bundle through Kustomize.

## Final Note

Even with the issues above, the project is close to deployment-ready. Most of the friction came from environment alignment and deployment consistency rather than from the core application architecture itself.
