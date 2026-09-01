# RAG Pipeline

## 01 — Upload

The user uploads a medical PDF through the React frontend.

```text
User
 │
 ▼
React
 │
 ▼
FastAPI
```

The API creates an ingestion job instead of performing the complete indexing operation synchronously.

---

## 02 — Queue

The ingestion job is dispatched through Redis/RQ.

```text
FastAPI
   │
   ▼
Redis Queue
   │
   ▼
Ingestion Worker
```

This keeps document processing separate from normal chat traffic.

---

## 03 — Extract

The worker extracts text from the uploaded document.

```text
PDF
 │
 ▼
Text Extraction
 │
 ▼
Document Chunks
```

---

## 04 — Embed

Each chunk is transformed into an embedding using FastEmbed.

Default model:

```text
BAAI/bge-small-en-v1.5
```

```text
Document Chunk
      │
      ▼
   FastEmbed
      │
      ▼
Embedding Vector
```

---

## 05 — Index

Embeddings are stored in a FAISS vector index.

```text
Embedding Vectors
       │
       ▼
      FAISS
       │
       ▼
Searchable Knowledge Base
```

---

## 06 — Retrieve

When a user asks a question, the query is embedded and compared against the vector index.

```text
User Question
      │
      ▼
Query Embedding
      │
      ▼
FAISS Similarity Search
      │
      ▼
Relevant Chunks
      │
      ▼
Hybrid Reranking (BM25 and Dense Retrieval)
      │
      ▼
Top 6 documents
```

---

## 07 — Generate

The retrieved context is provided to the Groq-powered LLM.

```text
                  ┌──────────────────┐
                  │   User Question  │
                  └────────┬─────────┘
                           │
                           +
                           │
                  ┌────────▼─────────┐
                  │ Retrieved Context│
                  └────────┬─────────┘
                           │
                           ▼
                     ┌───────────┐
                     │  Groq LLM │
                     └─────┬─────┘
                           │
                           ▼
                    Grounded Answer
```

---

## 08 — Respond

The response is streamed back to the frontend.

```text
┌──────────────────────────────────┐
│          AI RESPONSE             │
│                                  │
│  Generated using retrieved       │
│  medical document context.       │
│                                  │
│  Sources                          │
│  ──────────────────────────────  │
│  📄 Document — Page X            │
│  📄 Document — Page Y            │
└──────────────────────────────────┘
```

---
