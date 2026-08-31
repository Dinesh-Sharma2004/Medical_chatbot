# Testing & Evaluation

Tests and generated reports are located under:

```text
testing/
```

Run the API test suite:

```bash
python -m unittest testing.tests.test_api
```

LLM evaluation reports are written to:

```text
testing/reports/evaluations/
```

The testing layer provides a foundation for:

* API regression testing
* ingestion verification
* RAG evaluation
* LLM response evaluation
* system verification

---
