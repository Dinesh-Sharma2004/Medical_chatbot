# Troubleshooting

<details>
<summary><strong>❌ Render deployment fails because of large local files</strong></summary>

Ensure generated runtime directories are not committed:

```text
backend/data/
vectorstore/
```

Also ensure `.env` files are excluded from the Docker build context.

</details>

<details>
<summary><strong>❌ /app/health returns Not Found</strong></summary>

Use:

```text
/api/health
```

instead.

</details>

<details>
<summary><strong>❌ RAG not ready</strong></summary>

Check that:

1. At least one PDF has been uploaded.
2. Ingestion has completed.
3. The vectorstore exists.
4. `DB_FAISS_BASE` points to the correct location.

</details>

<details>
<summary><strong>❌ Frontend loads but is blank</strong></summary>

Check that static assets are being served from:

```text
/assets/
```

Then perform a hard refresh.

</details>

<details>
<summary><strong>❌ Railway runs out of memory during ingestion</strong></summary>

Reduce:

```env
EMBED_BATCH_SIZE=4
```

and:

```env
RAG_MAX_PDF_PAGES=80
```

Start with smaller PDFs on memory-constrained instances.

</details>

---
