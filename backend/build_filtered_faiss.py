"""
Build a FAISS index from local data folders, using only PDFs below a size limit.

Default behavior:
- scans ../data and backend/data,
- includes PDFs smaller than 50 MB,
- de-duplicates identical files by SHA-256,
- writes the index to DB_FAISS_BASE from backend/.env.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = REPO_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_pdfs(data_dirs: List[Path], max_mb: float) -> List[Path]:
    max_bytes = max_mb * 1024 * 1024
    candidates: List[Path] = []
    seen_hashes: Dict[str, Path] = {}

    for data_dir in data_dirs:
        if not data_dir.exists():
            print(f"Skipping missing data folder: {data_dir}")
            continue

        for path in sorted(data_dir.rglob("*.pdf")):
            if not path.is_file():
                continue
            if path.stat().st_size >= max_bytes:
                print(f"Skipping >= {max_mb:g} MB: {path.name}")
                continue
            if path.stat().st_size < 1024:
                print(f"Skipping tiny/invalid-looking PDF: {path.name}")
                continue

            digest = file_sha256(path)
            if digest in seen_hashes:
                print(f"Skipping duplicate: {path.name} == {seen_hashes[digest].name}")
                continue

            seen_hashes[digest] = path
            candidates.append(path)

    return candidates


def main() -> None:
    parser = argparse.ArgumentParser(description="Build filtered FAISS index from PDFs under a size limit.")
    parser.add_argument("--max-mb", type=float, default=50.0)
    parser.add_argument(
        "--data-dir",
        action="append",
        default=None,
        help="Data folder to scan. Can be passed multiple times.",
    )
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / "backend" / ".env")
    os.environ.setdefault("RAG_WARMUP_ON_INGEST", "false")
    if os.name == "nt" and os.getenv("HF_HOME", "").startswith("/"):
        cache_dir = REPO_ROOT / ".cache" / "huggingface"
        os.environ["HF_HOME"] = str(cache_dir)
        os.environ["HF_HUB_CACHE"] = str(cache_dir)

    from backend.ingest import create_vector_store

    data_dirs = (
        [Path(p).resolve() for p in args.data_dir]
        if args.data_dir
        else [WORKSPACE_ROOT / "data", REPO_ROOT / "backend" / "data"]
    )

    pdfs = find_pdfs(data_dirs, args.max_mb)
    if not pdfs:
        raise SystemExit("No PDFs matched the filter.")

    print("\nIndexing these PDFs:")
    for path in pdfs:
        size_mb = path.stat().st_size / 1024 / 1024
        print(f"- {path} ({size_mb:.2f} MB)")

    def progress(percent: int, detail: str) -> None:
        print(f"[{percent:3d}%] {detail}", flush=True)

    ok = create_vector_store([str(path) for path in pdfs], progress)
    if not ok:
        raise SystemExit("FAISS build failed.")

    db_base = os.getenv("DB_FAISS_BASE", "vectorstore").strip('"').strip("'")
    print(f"\nFAISS build complete: {db_base}")


if __name__ == "__main__":
    main()
