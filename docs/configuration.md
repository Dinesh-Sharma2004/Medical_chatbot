# Configuration

```env

## Authentication

Medibot supports email/password authentication locally and optionally Google Sign-In.

## Local Development

If `AUTH_DATABASE_URL` is not configured, the backend falls back to:

```text
backend/data/medibot_auth.sqlite3
```

## Production

Configure PostgreSQL:

```env
AUTH_DATABASE_URL=postgresql://...
```

Recommended:

```env
AUTH_SECRET=<strong-random-secret>
AUTH_DATABASE_URL=<postgresql-connection-string>
GOOGLE_CLIENT_ID=<google-client-id>
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
