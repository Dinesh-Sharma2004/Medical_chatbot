# API Reference

## Health & Observability

| Method | Endpoint      | Description        |
| ------ | ------------- | ------------------ |
| `GET`  | `/api/health` | Application health |
| `GET`  | `/metrics`    | Prometheus metrics |

## Authentication

| Method | Endpoint             | Description                  |
| ------ | -------------------- | ---------------------------- |
| `GET`  | `/api/auth/config`   | Authentication configuration |
| `POST` | `/api/auth/register` | Register                     |
| `POST` | `/api/auth/login`    | Login                        |
| `POST` | `/api/auth/google`   | Google Sign-In               |
| `GET`  | `/api/auth/me`       | Current user                 |

## Chat

| Method | Endpoint            | Description           |
| ------ | ------------------- | --------------------- |
| `GET`  | `/api/chat-history` | Retrieve chat history |
| `PUT`  | `/api/chat-history` | Update chat history   |
| `POST` | `/api/ask`          | Ask a question        |
| `POST` | `/api/ask/stream`   | Stream an answer      |

## Documents

| Method   | Endpoint                      | Description              |
| -------- | ----------------------------- | ------------------------ |
| `POST`   | `/api/upload`                 | Upload PDF               |
| `GET`    | `/api/upload/status/{job_id}` | Check ingestion status   |
| `POST`   | `/api/upload/cancel/{job_id}` | Cancel ingestion         |
| `DELETE` | `/api/upload/{job_id}`        | Delete uploaded document |
| `GET`    | `/api/source/{doc_id}`        | Retrieve source document |

---
