# Testing

This folder keeps automated tests and their generated reports separate from
application code.

## Layout

- `tests/` - Python test modules.
- `reports/evaluations/` - LLM evaluation JSON and CSV reports.
- `reports/verification/` - local verification logs.
- `reports/runtime/` - ad-hoc local run logs.

## Commands

Run the backend smoke tests:

```powershell
.\.venv313\Scripts\python.exe -m unittest testing.tests.test_api
```

Run the LLM evaluator:

```powershell
.\.venv313\Scripts\python.exe -m backend.evaluate_llms --out-dir testing\reports\evaluations
```
