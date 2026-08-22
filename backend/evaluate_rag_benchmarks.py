"""
Benchmark the applied RAG stack on open BEIR-style retrieval datasets.

Recommended datasets for this medical/scientific app:
  - scifact: scientific claim verification, small enough for quick iteration.
  - nfcorpus: biomedical information retrieval.
  - trec-covid: biomedical literature retrieval, larger and slower.

The harness reports retrieval quality at @100, retrieval/index/LLM latency,
BLEU, ROUGE-1/2/L, and optional transformer perplexity for generated answers.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import ssl
import shutil
import statistics
import tempfile
import time
import urllib.request
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import httpx
from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS

try:
    from .http_clients import request_kwargs
    from . import rag_chain as rc
except ImportError:
    from http_clients import request_kwargs
    import rag_chain as rc


REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = REPO_ROOT / "testing" / "reports" / "rag_benchmarks"
DATA_DIR = REPO_ROOT / "testing" / "benchmarks" / "beir"
INDEX_DIR = REPO_ROOT / "testing" / "benchmarks" / "indexes"

BEIR_URLS = {
    "scifact": "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/scifact.zip",
    "nfcorpus": "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/nfcorpus.zip",
    "trec-covid": "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/trec-covid.zip",
}


def read_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def ensure_dataset(dataset: str, data_dir: Path, allow_download: bool, insecure_download: bool) -> Path:
    dataset_dir = data_dir / dataset
    if (dataset_dir / "corpus.jsonl").exists():
        return dataset_dir
    if not allow_download:
        raise FileNotFoundError(
            f"{dataset_dir} is missing. Re-run with --download or place BEIR files there."
        )

    data_dir.mkdir(parents=True, exist_ok=True)
    url = BEIR_URLS[dataset]
    zip_path = data_dir / f"{dataset}.zip"
    print(f"Downloading {dataset} from {url}")
    if insecure_download:
        context = ssl._create_unverified_context()
        with urllib.request.urlopen(url, context=context) as response, zip_path.open("wb") as out:
            out.write(response.read())
    else:
        urllib.request.urlretrieve(url, zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        with tempfile.TemporaryDirectory() as td:
            zf.extractall(td)
            extracted = next(Path(td).iterdir())
            if dataset_dir.exists():
                raise FileExistsError(f"Refusing to overwrite existing {dataset_dir}")
            shutil.move(str(extracted), str(dataset_dir))
    return dataset_dir


def load_beir(dataset_dir: Path, split: str) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str], Dict[str, Dict[str, int]]]:
    corpus = {str(row["_id"]): row for row in read_jsonl(dataset_dir / "corpus.jsonl")}
    queries = {str(row["_id"]): str(row["text"]) for row in read_jsonl(dataset_dir / "queries.jsonl")}
    qrels_path = dataset_dir / "qrels" / f"{split}.tsv"
    if not qrels_path.exists():
        available = sorted(p.stem for p in (dataset_dir / "qrels").glob("*.tsv"))
        raise FileNotFoundError(f"Missing {qrels_path}. Available qrel splits: {available}")

    qrels: Dict[str, Dict[str, int]] = defaultdict(dict)
    with qrels_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            qid = str(row.get("query-id") or row.get("query_id"))
            docid = str(row.get("corpus-id") or row.get("corpus_id"))
            score = int(float(row.get("score", 0)))
            if score > 0:
                qrels[qid][docid] = score
    return corpus, queries, dict(qrels)


def corpus_documents(corpus: Dict[str, Dict[str, Any]]) -> List[Document]:
    docs = []
    for doc_id, row in corpus.items():
        title = (row.get("title") or "").strip()
        text = (row.get("text") or "").strip()
        content = f"{title}\n\n{text}".strip()
        docs.append(
            Document(
                page_content=content,
                metadata={
                    "doc_id": doc_id,
                    "page_key": doc_id,
                    "filename": doc_id,
                    "source": "beir",
                    "page": 0,
                    "title": title,
                },
            )
        )
    return docs


def build_or_load_index(dataset: str, docs: List[Document], rebuild: bool) -> FAISS:
    index_path = INDEX_DIR / f"{dataset}_{rc.EMBED_MODEL.replace('/', '__')}"
    embeddings = rc.Resources.embeddings()
    if index_path.exists() and not rebuild:
        return FAISS.load_local(str(index_path), embeddings, allow_dangerous_deserialization=True)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    vectorstore = FAISS.from_documents(docs, embeddings)
    vectorstore.save_local(str(index_path))
    print(f"Built FAISS index for {len(docs)} docs in {time.perf_counter() - started:.2f}s")
    return vectorstore


def source_record(doc: Document, score: float, question: str, rank: int) -> Dict[str, Any]:
    record = rc.source_from_doc_score(doc, score, question=question, rank=rank)
    record["_doc"] = doc
    record["_score"] = score
    return record


def retrieve_benchmark(
    vectorstore: FAISS,
    question: str,
    *,
    k: int,
    fetch_k: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    started = time.perf_counter()
    optimization = rc.optimize_prompt_embeddings(question)
    retrieval_query = optimization["query"]
    vector_started = time.perf_counter()
    query_vec = rc.optimize_prompt_embedding_vector(question, retrieval_query)
    if query_vec is None:
        query_vec = rc.Resources.embeddings().embed_query(retrieval_query)
    vector_latency = time.perf_counter() - vector_started

    search_started = time.perf_counter()
    docs_scores = vectorstore.similarity_search_with_score_by_vector(query_vec, fetch_k)
    docs_scores.sort(key=lambda item: item[1])
    search_latency = time.perf_counter() - search_started

    records = [
        source_record(doc, score, question=retrieval_query, rank=rank)
        for rank, (doc, score) in enumerate(docs_scores, start=1)
    ]
    records = rc.rerank_hybrid_records(records, retrieval_query)
    selected = records[:k]
    for rank, record in enumerate(selected, start=1):
        record["rank"] = rank
        record["optimized_query"] = retrieval_query
        record["optimization_terms"] = optimization["added_terms"]
        record["optimization_loss"] = optimization["loss"]

    return selected, {
        "retrieval_latency_sec": time.perf_counter() - started,
        "embedding_latency_sec": vector_latency,
        "vector_search_latency_sec": search_latency,
        "optimization_terms": optimization["added_terms"],
        "optimization_loss": optimization["loss"],
    }


def dcg(relevances: Sequence[int]) -> float:
    return sum((2**rel - 1) / math.log2(idx + 2) for idx, rel in enumerate(relevances))


def retrieval_metrics(
    ranked_doc_ids: List[str],
    relevant: Dict[str, int],
    k: int = 100,
    prefix: str = "",
) -> Dict[str, float]:
    top = ranked_doc_ids[:k]
    relevant_ids = set(relevant)
    hits = [1 if doc_id in relevant_ids else 0 for doc_id in top]
    rels = [relevant.get(doc_id, 0) for doc_id in top]
    ideal = sorted(relevant.values(), reverse=True)[:k]
    first_hit = next((idx + 1 for idx, hit in enumerate(hits) if hit), None)
    label = f"{prefix}@" if prefix else ""
    return {
        f"{label}recall@{k}": sum(hits) / max(1, len(relevant_ids)),
        f"{label}precision@{k}": sum(hits) / max(1, k),
        f"{label}hit_rate@{k}": 1.0 if sum(hits) > 0 else 0.0,
        f"{label}mrr@{k}": 1.0 / first_hit if first_hit else 0.0,
        f"{label}ndcg@{k}": dcg(rels) / max(1e-9, dcg(ideal)),
    }


def first_relevant_rank(ranked_doc_ids: List[str], relevant: Dict[str, int]) -> Optional[int]:
    relevant_ids = set(relevant)
    for idx, doc_id in enumerate(ranked_doc_ids, start=1):
        if doc_id in relevant_ids:
            return idx
    return None


def context_quality_metrics(
    context_doc_ids: List[str],
    relevant: Dict[str, int],
    answer: str = "",
    reference: str = "",
    context: str = "",
) -> Dict[str, Optional[float]]:
    relevant_ids = set(relevant)
    hits = sum(1 for doc_id in context_doc_ids if doc_id in relevant_ids)
    context_size = max(1, len(context_doc_ids))
    answer_terms = set(tokenize(answer))
    reference_terms = set(tokenize(reference))
    context_terms = set(tokenize(context))
    answer_reference_overlap = (
        len(answer_terms & reference_terms) / max(1, len(answer_terms))
        if answer_terms and reference_terms
        else None
    )
    abstained = 1.0 if "don't know" in answer.lower() or "not enough information" in answer.lower() else 0.0
    return {
        "context_precision": hits / context_size,
        "context_recall": hits / max(1, len(relevant_ids)),
        "context_utilization": (
            len(answer_terms & context_terms) / max(1, len(answer_terms))
            if answer_terms and context_terms
            else None
        ),
        "faithfulness_proxy": answer_reference_overlap,
        "answer_relevancy_proxy": answer_reference_overlap,
        "abstention_rate": abstained,
    }


def ngrams(tokens: List[str], n: int) -> Counter:
    return Counter(tuple(tokens[i : i + n]) for i in range(max(0, len(tokens) - n + 1)))


def tokenize(text: str) -> List[str]:
    return rc._question_terms(text)


def bleu(candidate: str, reference: str, max_n: int = 4) -> float:
    cand = tokenize(candidate)
    ref = tokenize(reference)
    if not cand or not ref:
        return 0.0
    precisions = []
    for n in range(1, max_n + 1):
        cand_ngrams = ngrams(cand, n)
        ref_ngrams = ngrams(ref, n)
        overlap = sum((cand_ngrams & ref_ngrams).values())
        total = sum(cand_ngrams.values())
        precisions.append((overlap + 1) / (total + 1))
    brevity = 1.0 if len(cand) > len(ref) else math.exp(1 - len(ref) / max(1, len(cand)))
    return brevity * math.exp(sum(math.log(p) for p in precisions) / max_n)


def rouge_n(candidate: str, reference: str, n: int) -> float:
    cand_ngrams = ngrams(tokenize(candidate), n)
    ref_ngrams = ngrams(tokenize(reference), n)
    if not ref_ngrams:
        return 0.0
    return sum((cand_ngrams & ref_ngrams).values()) / sum(ref_ngrams.values())


def lcs_len(a: List[str], b: List[str]) -> int:
    prev = [0] * (len(b) + 1)
    for token_a in a:
        cur = [0]
        for idx_b, token_b in enumerate(b, start=1):
            cur.append(prev[idx_b - 1] + 1 if token_a == token_b else max(prev[idx_b], cur[-1]))
        prev = cur
    return prev[-1]


def rouge_l(candidate: str, reference: str) -> float:
    cand = tokenize(candidate)
    ref = tokenize(reference)
    if not ref:
        return 0.0
    return lcs_len(cand, ref) / len(ref)


def unigram_perplexity(candidate: str, reference: str) -> Optional[float]:
    cand = tokenize(candidate)
    ref = tokenize(reference)
    if not cand or not ref:
        return None
    vocab = set(ref) | set(cand)
    counts = Counter(ref)
    denom = len(ref) + len(vocab)
    nll = 0.0
    for token in cand:
        prob = (counts.get(token, 0) + 1) / denom
        nll -= math.log(prob)
    return math.exp(nll / len(cand))


class PerplexityScorer:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.available = False
        self.error = ""
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            self.torch = torch
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModelForCausalLM.from_pretrained(model_name)
            self.model.eval()
            self.available = True
        except Exception as exc:
            self.error = str(exc)[:500]

    def score(self, text: str) -> Optional[float]:
        if not self.available or not text.strip():
            return None
        with self.torch.no_grad():
            inputs = self.tokenizer(text, return_tensors="pt", truncation=True, max_length=1024)
            outputs = self.model(**inputs, labels=inputs["input_ids"])
            return float(self.torch.exp(outputs.loss).item())


def groq_keys() -> List[str]:
    keys = [k.strip() for k in os.getenv("GROQ_API_KEYS", "").split(",") if k.strip()]
    if not keys:
        single = os.getenv("GROQ_API_KEY", "").strip()
        if single:
            keys.append(single)
    return keys


def build_benchmark_prompt(dataset: str, question: str, context: str) -> str:
    if dataset == "scifact":
        return f"""You are evaluating a scientific claim using only the provided evidence.
Decide whether the evidence SUPPORTS, REFUTES, or gives NOT ENOUGH INFORMATION for the claim.
Use arithmetic when it is directly implied by the evidence.
Cite evidence labels such as [Evidence 2]. Do not use outside knowledge.

Evidence:
{context}

Claim:
{question}

Answer with:
Label: SUPPORTS / REFUTES / NOT ENOUGH INFORMATION
Rationale: one concise evidence-grounded explanation with citations.
"""
    return rc.build_prompt_from_context(context, question, "optimized")


def groq_answer(dataset: str, question: str, context: str, *, timeout: float, max_tokens: int) -> Tuple[str, Dict[str, Any]]:
    prompt = build_benchmark_prompt(dataset, question, context)
    payload = rc._groq_payload(prompt, stream=False)
    payload["max_tokens"] = max_tokens
    started = time.perf_counter()
    response = httpx.post(
        rc.GROQ_ENDPOINT,
        headers={"Authorization": f"Bearer {groq_keys()[0]}", "Content-Type": "application/json"},
        json=payload,
        **request_kwargs(timeout=timeout),
    )
    latency = time.perf_counter() - started
    response.raise_for_status()
    data = response.json()
    text = data["choices"][0]["message"].get("content", "")
    usage = data.get("usage") or {}
    return text, {"llm_latency_sec": latency, "usage": usage}


def summarize(values: List[float]) -> Dict[str, Optional[float]]:
    if not values:
        return {"mean": None, "p50": None, "p95": None}
    ordered = sorted(values)
    p95_idx = min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1)
    return {
        "mean": round(statistics.mean(values), 6),
        "p50": round(statistics.median(values), 6),
        "p95": round(ordered[p95_idx], 6),
    }


def average_metric(rows: List[Dict[str, Any]], key: str) -> Optional[float]:
    values = [row[key] for row in rows if isinstance(row.get(key), (int, float))]
    return round(statistics.mean(values), 6) if values else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate this RAG framework on BEIR benchmarks.")
    parser.add_argument("--dataset", choices=sorted(BEIR_URLS), default="scifact")
    parser.add_argument("--split", default="test")
    parser.add_argument("--download", action="store_true")
    parser.add_argument(
        "--insecure-download",
        action="store_true",
        help="Disable TLS certificate verification for known benchmark mirrors if local CA validation fails.",
    )
    parser.add_argument("--rebuild-index", action="store_true")
    parser.add_argument("--max-queries", type=int, default=25)
    parser.add_argument("--k", type=int, default=100)
    parser.add_argument("--fetch-k", type=int, default=100)
    parser.add_argument("--context-k", type=int, default=8, help="Number of reranked records sent to generation.")
    parser.add_argument("--generate", action="store_true", help="Call Groq and compute BLEU/ROUGE/latency.")
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--perplexity-model", default=os.getenv("EVAL_PERPLEXITY_MODEL", "distilgpt2"))
    parser.add_argument(
        "--perplexity-mode",
        choices=["transformer", "unigram", "none"],
        default="unigram",
        help="Use transformer LM perplexity, reference-unigram perplexity, or skip.",
    )
    parser.add_argument("--skip-perplexity", action="store_true")
    parser.add_argument("--out-dir", default=str(REPORT_DIR))
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / "backend" / ".env")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    dataset_dir = ensure_dataset(args.dataset, DATA_DIR, args.download, args.insecure_download)
    corpus, queries, qrels = load_beir(dataset_dir, args.split)
    query_ids = [qid for qid in queries if qid in qrels][: args.max_queries]
    docs = corpus_documents(corpus)
    print(f"Dataset: {args.dataset}/{args.split}; docs={len(docs)}; eval_queries={len(query_ids)}")

    index_started = time.perf_counter()
    vectorstore = build_or_load_index(args.dataset, docs, args.rebuild_index)
    index_latency = time.perf_counter() - index_started

    perplexity = (
        PerplexityScorer(args.perplexity_model)
        if args.generate and not args.skip_perplexity and args.perplexity_mode == "transformer"
        else None
    )
    if args.generate and not groq_keys():
        print("No GROQ_API_KEYS/GROQ_API_KEY found; generation metrics will be skipped.")
        args.generate = False
    if perplexity and not perplexity.available:
        print(f"Perplexity disabled: could not load {args.perplexity_model}: {perplexity.error}")

    rows: List[Dict[str, Any]] = []
    for idx, qid in enumerate(query_ids, start=1):
        question = queries[qid]
        records, timing = retrieve_benchmark(vectorstore, question, k=args.k, fetch_k=args.fetch_k)
        ranked_ids = [str(record.get("doc_id")) for record in records]
        metrics = retrieval_metrics(ranked_ids, qrels[qid], k=args.k)
        context_records = records[: min(args.context_k, len(records))]
        context_doc_ids = [str(record.get("doc_id")) for record in context_records]
        metrics.update(retrieval_metrics(context_doc_ids, qrels[qid], k=len(context_doc_ids) or 1, prefix="context"))
        row: Dict[str, Any] = {
            "query_index": idx,
            "query_id": qid,
            "question": question,
            "retrieved_doc_ids": ranked_ids,
            "context_doc_ids": context_doc_ids,
            "first_relevant_rank": first_relevant_rank(ranked_ids, qrels[qid]),
            **metrics,
            **timing,
        }

        context = rc.build_context_from_docs(
            [record["_doc"] for record in context_records],
            question,
            mode="optimized",
            sources=context_records,
        )
        reference = "\n\n".join(
            f"{corpus[doc_id].get('title', '')}\n{corpus[doc_id].get('text', '')}"
            for doc_id in qrels[qid]
            if doc_id in corpus
        )
        row.update(context_quality_metrics(context_doc_ids, qrels[qid], context=context))

        if args.generate:
            try:
                answer, llm_timing = groq_answer(args.dataset, question, context, timeout=args.timeout, max_tokens=args.max_tokens)
                row.update(llm_timing)
                row["answer"] = answer
                row["bleu"] = bleu(answer, reference)
                row["rouge1"] = rouge_n(answer, reference, 1)
                row["rouge2"] = rouge_n(answer, reference, 2)
                row["rougeL"] = rouge_l(answer, reference)
                if args.skip_perplexity or args.perplexity_mode == "none":
                    row["perplexity"] = None
                elif args.perplexity_mode == "transformer":
                    row["perplexity"] = perplexity.score(answer) if perplexity and perplexity.available else None
                else:
                    row["perplexity"] = unigram_perplexity(answer, reference)
                row.update(context_quality_metrics(context_doc_ids, qrels[qid], answer, reference, context))
            except Exception as exc:
                row["generation_error"] = str(exc)[:1000]
        rows.append({k: v for k, v in row.items() if not k.startswith("_")})
        print(
            f"[{idx}/{len(query_ids)}] recall@{args.k}={row[f'recall@{args.k}']:.3f} "
            f"context_recall={row['context_recall']:.3f} "
            f"ndcg@{args.k}={row[f'ndcg@{args.k}']:.3f} retrieval={timing['retrieval_latency_sec']:.3f}s"
        )

    summary = {
        "dataset": args.dataset,
        "split": args.split,
        "documents": len(docs),
        "queries": len(query_ids),
        "k": args.k,
        "fetch_k": args.fetch_k,
        "context_k": args.context_k,
        "index_load_or_build_latency_sec": round(index_latency, 6),
        "metrics": {
            key: average_metric(rows, key)
            for key in [
                f"recall@{args.k}",
                f"precision@{args.k}",
                f"hit_rate@{args.k}",
                f"mrr@{args.k}",
                f"ndcg@{args.k}",
                f"context@recall@{args.context_k}",
                f"context@precision@{args.context_k}",
                f"context@hit_rate@{args.context_k}",
                f"context@mrr@{args.context_k}",
                f"context@ndcg@{args.context_k}",
                "context_precision",
                "context_recall",
                "context_utilization",
                "faithfulness_proxy",
                "answer_relevancy_proxy",
                "abstention_rate",
                "bleu",
                "rouge1",
                "rouge2",
                "rougeL",
                "perplexity",
            ]
        },
        "latency": {
            "retrieval_latency_sec": summarize([r["retrieval_latency_sec"] for r in rows]),
            "embedding_latency_sec": summarize([r["embedding_latency_sec"] for r in rows]),
            "vector_search_latency_sec": summarize([r["vector_search_latency_sec"] for r in rows]),
            "llm_latency_sec": summarize([r["llm_latency_sec"] for r in rows if "llm_latency_sec" in r]),
        },
        "notes": {
            "retrieval_metrics": "Computed against BEIR qrels at @100.",
            "context_metrics": "Computed over the reranked records actually sent to the LLM.",
            "generation_metrics": "BLEU/ROUGE compare generated answers to concatenated relevant evidence text; faithfulness/relevancy are lexical proxies unless an external judge is added.",
            "perplexity": (
                f"Mode={args.perplexity_mode}. Transformer model={args.perplexity_model}; "
                "unigram mode uses Laplace-smoothed relevant-evidence token probabilities."
            ),
        },
    }

    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{args.dataset}_{stamp}.json"
    csv_path = out_dir / f"{args.dataset}_{stamp}.csv"
    json_path.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        fieldnames = sorted({key for row in rows for key in row})
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print("\nSummary")
    print(json.dumps(summary, indent=2))
    print(f"Wrote {json_path}")
    print(f"Wrote {csv_path}")


if __name__ == "__main__":
    main()
