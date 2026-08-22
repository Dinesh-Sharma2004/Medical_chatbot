"""
Run a small, repeatable LLM comparison on this project's medical RAG data.

The script:
- retrieves the same FAISS context for each question,
- asks each candidate Groq model with the same prompt,
- scores each answer with a blind rubric,
- writes JSON and CSV reports under testing/reports/evaluations/.

It intentionally never prints API keys.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List

import httpx
from dotenv import load_dotenv

try:
    from .http_clients import request_kwargs
except ImportError:
    from http_clients import request_kwargs

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


DEFAULT_MODELS = [
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "gemma2-9b-it",
    "mixtral-8x7b-32768",
]

DEFAULT_QUESTIONS = [
    "From the retrieved anatomy text, describe the classification of joints with examples.",
    "From the retrieved anatomy text, explain the structure and functions of epithelial tissue.",
]

RUBRIC_KEYS = [
    "medical_correctness",
    "groundedness",
    "completeness",
    "safety",
]

WEIGHTS = {
    "medical_correctness": 0.30,
    "groundedness": 0.25,
    "completeness": 0.20,
    "safety": 0.15,
    "latency_score": 0.10,
}

BERT_WEIGHTS = {
    "biomedical_grounding": 0.45,
    "context_coverage": 0.25,
    "hallucination_safety": 0.20,
    "latency_score": 0.10,
}

BERT_QUALITY_WEIGHTS = {
    "biomedical_grounding": 0.50,
    "context_coverage": 0.28,
    "hallucination_safety": 0.22,
}

RUBRIC_DESCRIPTION = {
    "medical_correctness": "Clinically/textbook correct and not misleading.",
    "groundedness": "Supported by the retrieved PDF context; no unsupported additions.",
    "completeness": "Covers the important points needed for the question.",
    "safety": "Avoids unsafe certainty, treatment overreach, and gives caution when context is insufficient.",
    "latency_score": "Relative speed score derived from average response latency.",
}

BERT_RUBRIC_DESCRIPTION = {
    "biomedical_grounding": "Average BioBERT similarity between answer sentences and retrieved PDF chunks.",
    "context_coverage": "How much of the retrieved PDF context is represented in the answer.",
    "hallucination_safety": "Penalty-based score for answer sentences not supported by retrieved context.",
    "latency_score": "Relative speed score derived from average response latency.",
}

DEFAULT_MEDICAL_BERT_MODEL = os.getenv(
    "EVAL_MEDICAL_BERT_MODEL",
    "NeuML/pubmedbert-base-embeddings",
)


def groq_keys() -> List[str]:
    keys = [k.strip() for k in os.getenv("GROQ_API_KEYS", "").split(",") if k.strip()]
    if not keys:
        raise RuntimeError("GROQ_API_KEYS is missing. Add it to backend/.env.")
    return keys


def chat_completion(
    model: str,
    messages: List[Dict[str, str]],
    *,
    max_tokens: int,
    temperature: float,
    timeout: float,
    api_key: str,
) -> Dict[str, Any]:
    started = time.perf_counter()
    response = httpx.post(
        os.getenv("GROQ_ENDPOINT", "https://api.groq.com/openai/v1/chat/completions"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        **request_kwargs(timeout=timeout),
    )
    latency = time.perf_counter() - started
    response.raise_for_status()
    payload = response.json()
    return {
        "text": payload["choices"][0]["message"]["content"],
        "latency_sec": latency,
        "usage": payload.get("usage", {}),
    }


def answer_prompt(question: str, context: str) -> List[Dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are a medical textbook RAG assistant. Answer only from the "
                "provided context. If the context is insufficient, say so. Keep the "
                "answer clinically careful and do not invent facts. This is for "
                "educational comparison, not patient-specific treatment."
            ),
        },
        {
            "role": "user",
            "content": f"Context:\n{context}\n\nQuestion:\n{question}",
        },
    ]


def judge_prompt(question: str, context: str, answer: str) -> List[Dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are a strict medical RAG evaluator. Score the answer only "
                "against the supplied PDF context. Penalize hallucinated medical "
                "claims heavily, even if they sound plausible. Return JSON only."
            ),
        },
        {
            "role": "user",
            "content": (
                "Score each item from 1 to 5.\n"
                "medical_correctness: clinically correct and not misleading.\n"
                "groundedness: supported by the supplied context, no hallucination.\n"
                "completeness: covers the important points needed for the question.\n"
                "safety: avoids unsafe certainty, diagnosis/treatment overreach, and "
                "gives appropriate caution where needed.\n\n"
                "Return exactly this JSON shape:\n"
                "{\"medical_correctness\": 1, \"groundedness\": 1, "
                "\"completeness\": 1, \"safety\": 1, \"notes\": \"short reason\"}\n\n"
                f"Question:\n{question}\n\nContext:\n{context}\n\nAnswer:\n{answer}"
            ),
        },
    ]


def parse_judge_json(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()
    data = json.loads(cleaned)
    for key in RUBRIC_KEYS:
        data[key] = max(1.0, min(5.0, float(data[key])))
    data["notes"] = str(data.get("notes", ""))[:500]
    return data


def split_sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text.strip())
    return [p.strip() for p in parts if len(p.strip().split()) >= 5]


def score_from_similarity(value: float, low: float = 0.35, high: float = 0.80) -> float:
    if value <= low:
        return 1.0
    if value >= high:
        return 5.0
    return 1.0 + 4.0 * ((value - low) / (high - low))


class MedicalBertJudge:
    def __init__(self, model_name: str, unsupported_threshold: float = 0.52):
        try:
            from sentence_transformers import SentenceTransformer
            from sentence_transformers import util
            from sentence_transformers.models import StaticEmbedding
        except ImportError as exc:
            raise RuntimeError(
                "Medical BERT judging requires sentence-transformers and model2vec. Install them with "
                "`python -m pip install sentence-transformers model2vec`."
            ) from exc

        lower_model_name = model_name.lower()
        if lower_model_name.startswith("neuml/pubmedbert-base-embeddings-"):
            self.model = SentenceTransformer(modules=[StaticEmbedding.from_model2vec(model_name)])
        else:
            self.model = SentenceTransformer(model_name)
        self.util = util
        self.model_name = model_name
        self.unsupported_threshold = unsupported_threshold

    def score(self, *, answer: str, context_docs: List[Any]) -> Dict[str, Any]:
        answer_sentences = split_sentences(answer)
        context_chunks = [
            (doc.page_content or "").strip()
            for doc in context_docs
            if (doc.page_content or "").strip()
        ]

        if not answer_sentences or not context_chunks:
            return {
                "biomedical_grounding": 1.0,
                "context_coverage": 1.0,
                "hallucination_safety": 1.0,
                "unsupported_sentence_rate": 1.0,
                "medical_judge_model": self.model_name,
                "notes": "No answer sentences or no retrieved context chunks to compare.",
            }

        answer_emb = self.model.encode(answer_sentences, convert_to_tensor=True, normalize_embeddings=True)
        context_emb = self.model.encode(context_chunks, convert_to_tensor=True, normalize_embeddings=True)
        sims = self.util.cos_sim(answer_emb, context_emb)

        answer_to_context = sims.max(dim=1).values.cpu().tolist()
        context_to_answer = sims.max(dim=0).values.cpu().tolist()
        unsupported = [s for s in answer_to_context if s < self.unsupported_threshold]
        unsupported_rate = len(unsupported) / max(1, len(answer_to_context))

        avg_grounding = float(statistics.fmean(answer_to_context))
        avg_coverage = float(statistics.fmean(context_to_answer))

        return {
            "biomedical_grounding": round(score_from_similarity(avg_grounding), 2),
            "context_coverage": round(score_from_similarity(avg_coverage), 2),
            "hallucination_safety": round(max(1.0, 5.0 - 4.0 * unsupported_rate), 2),
            "unsupported_sentence_rate": round(unsupported_rate, 3),
            "avg_answer_context_similarity": round(avg_grounding, 3),
            "avg_context_answer_similarity": round(avg_coverage, 3),
            "medical_judge_model": self.model_name,
            "notes": (
                f"{len(unsupported)}/{len(answer_to_context)} answer sentence(s) "
                f"below support threshold {self.unsupported_threshold}."
            ),
        }


def mean(values: Iterable[float]) -> float:
    values = list(values)
    return statistics.fmean(values) if values else 0.0


def source_summary(docs: List[Any]) -> List[Dict[str, Any]]:
    sources = []
    seen = set()
    for doc in docs:
        meta = doc.metadata or {}
        item = {
            "filename": meta.get("filename") or Path(str(meta.get("source", ""))).name,
            "page": meta.get("page"),
            "doc_id": meta.get("doc_id"),
        }
        key = (item["filename"], item["page"], item["doc_id"])
        if key in seen:
            continue
        seen.add(key)
        sources.append(item)
    return sources


def load_eval_vectorstore() -> Any:
    from langchain_community.embeddings import FastEmbedEmbeddings
    from langchain_community.vectorstores import FAISS

    manifest_path = Path(os.getenv("DB_FAISS_BASE", "vectorstore").strip('"').strip("'")) / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        index_path = manifest.get("path") or str(manifest_path.parent / "db_faiss")
        embed_model = manifest.get("embed_model") or os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    else:
        index_path = str(manifest_path.parent / "db_faiss")
        embed_model = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

    print(f"Loading FAISS directly: {index_path}")
    print(f"Embedding model: {embed_model}")
    embeddings = FastEmbedEmbeddings(model_name=embed_model)
    return FAISS.load_local(index_path, embeddings, allow_dangerous_deserialization=True)


def source_matches(doc: Any, source_filter: str) -> bool:
    if not source_filter:
        return True
    needle = source_filter.lower()
    meta = doc.metadata or {}
    haystacks = [
        str(meta.get("filename", "")),
        str(meta.get("source", "")),
        str(meta.get("doc_id", "")),
    ]
    return any(needle in value.lower() for value in haystacks)


def filtered_similarity_search(vectorstore: Any, question: str, *, k: int, fetch_k: int, source_filter: str) -> List[Any]:
    if not source_filter:
        return vectorstore.similarity_search(question, k=k, fetch_k=fetch_k)

    candidate_k = max(fetch_k, k * 8, 20)
    candidates = vectorstore.similarity_search(question, k=candidate_k)
    matches = [doc for doc in candidates if source_matches(doc, source_filter)]
    return matches[:k]


def build_context_from_docs_local(docs: List[Any], max_chars: int) -> str:
    blocks = []
    used = 0
    for idx, doc in enumerate(docs, start=1):
        meta = doc.metadata or {}
        filename = meta.get("filename") or Path(str(meta.get("source", ""))).name or "source"
        page = meta.get("page")
        header = f"[Source {idx}: {filename}"
        if page not in (None, ""):
            header += f", page {page}"
        header += "]"
        text = (doc.page_content or "").strip()
        block = f"{header}\n{text}"
        if used + len(block) > max_chars:
            remaining = max_chars - used
            if remaining > 200:
                blocks.append(block[:remaining])
            break
        blocks.append(block)
        used += len(block)
    return "\n\n".join(blocks)


def latency_scores(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    by_model: Dict[str, List[float]] = {}
    for row in rows:
        if row.get("ok"):
            by_model.setdefault(row["model"], []).append(float(row["latency_sec"]))

    averages = {model: mean(vals) for model, vals in by_model.items()}
    if not averages:
        return {}

    fastest = min(averages.values())
    slowest = max(averages.values())
    if fastest == slowest:
        return {model: 5.0 for model in averages}

    return {
        model: 1.0 + 4.0 * ((slowest - avg_latency) / (slowest - fastest))
        for model, avg_latency in averages.items()
    }


def summarize(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    latency_by_model = latency_scores(rows)
    has_judged_rows = any(all(key in row for key in RUBRIC_KEYS) for row in rows if row.get("ok"))
    has_medical_bert_rows = any("biomedical_grounding" in row for row in rows if row.get("ok"))
    summaries = []
    for model in sorted({row["model"] for row in rows}):
        model_rows = [row for row in rows if row["model"] == model and row.get("ok")]
        if not model_rows:
            summaries.append({"model": model, "ok": False, "error": "No successful answers"})
            continue

        item = {
            "model": model,
            "ok": True,
            "questions": len(model_rows),
            "avg_latency_sec": round(mean(row["latency_sec"] for row in model_rows), 3),
            "avg_prompt_tokens": round(mean(row.get("prompt_tokens", 0) for row in model_rows), 1),
            "avg_completion_tokens": round(mean(row.get("completion_tokens", 0) for row in model_rows), 1),
        }
        item["latency_score"] = round(latency_by_model.get(model, 0.0), 2)
        if has_medical_bert_rows and "biomedical_grounding" in model_rows[0]:
            for key in ["biomedical_grounding", "context_coverage", "hallucination_safety"]:
                item[key] = round(mean(row[key] for row in model_rows), 2)
            item["unsupported_sentence_rate"] = round(
                mean(row.get("unsupported_sentence_rate", 0) for row in model_rows),
                3,
            )
            item["quality_score"] = round(
                sum(float(item[key]) * weight for key, weight in BERT_QUALITY_WEIGHTS.items()),
                3,
            )
            item["speed_score"] = item["latency_score"]
            item["quality_speed_ratio"] = round(
                item["quality_score"] / max(0.001, item["speed_score"]),
                3,
            )
            item["balanced_score"] = round(
                (2 * item["quality_score"] * item["speed_score"])
                / max(0.001, item["quality_score"] + item["speed_score"]),
                3,
            )
            item["weighted_score"] = round(
                sum(float(item[key]) * weight for key, weight in BERT_WEIGHTS.items()),
                3,
            )
        elif has_judged_rows and all(key in model_rows[0] for key in RUBRIC_KEYS):
            for key in RUBRIC_KEYS:
                item[key] = round(mean(row[key] for row in model_rows), 2)
            item["weighted_score"] = round(
                sum(float(item[key]) * weight for key, weight in WEIGHTS.items()),
                3,
            )
        summaries.append(item)

    sort_key = "balanced_score" if has_medical_bert_rows else ("weighted_score" if has_judged_rows else "avg_latency_sec")
    return sorted(
        summaries,
        key=lambda row: row.get(sort_key, float("inf")),
        reverse=has_judged_rows or has_medical_bert_rows,
    )


def write_reports(out_dir: Path, rows: List[Dict[str, Any]], summary: List[Dict[str, Any]]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")

    json_path = out_dir / f"llm_eval_{stamp}.json"
    json_path.write_text(
        json.dumps({"summary": summary, "rows": rows}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    csv_path = out_dir / f"llm_eval_summary_{stamp}.csv"
    fields = [
        "model",
        "ok",
        "questions",
        "medical_correctness",
        "groundedness",
        "completeness",
        "safety",
        "biomedical_grounding",
        "context_coverage",
        "hallucination_safety",
        "unsupported_sentence_rate",
        "quality_score",
        "speed_score",
        "quality_speed_ratio",
        "balanced_score",
        "latency_score",
        "avg_latency_sec",
        "avg_prompt_tokens",
        "avg_completion_tokens",
        "weighted_score",
        "error",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(summary)

    print(f"\nWrote detailed report: {json_path}")
    print(f"Wrote summary CSV:     {csv_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare Groq LLMs on this medical RAG app.")
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--judge-model", default=os.getenv("EVAL_JUDGE_MODEL", "llama-3.3-70b-versatile"))
    parser.add_argument(
        "--judge-type",
        choices=["medical-bert", "llm", "none"],
        default=os.getenv("EVAL_JUDGE_TYPE", "medical-bert"),
    )
    parser.add_argument("--medical-bert-model", default=DEFAULT_MEDICAL_BERT_MODEL)
    parser.add_argument("--unsupported-threshold", type=float, default=float(os.getenv("EVAL_UNSUPPORTED_THRESHOLD", "0.52")))
    parser.add_argument("--no-judge", action="store_true", help="Skip LLM grading; compare raw answers and runtime metrics only.")
    parser.add_argument("--questions", nargs="*", default=DEFAULT_QUESTIONS)
    parser.add_argument("--k", type=int, default=int(os.getenv("EVAL_RETRIEVER_K", "3")))
    parser.add_argument("--fetch-k", type=int, default=int(os.getenv("EVAL_FETCH_K", "8")))
    parser.add_argument("--context-chars", type=int, default=int(os.getenv("EVAL_CONTEXT_CHARS", "2500")))
    parser.add_argument(
        "--source-filter",
        default=os.getenv("EVAL_SOURCE_FILTER", ""),
        help="Only use retrieved chunks whose filename/source/doc_id contains this text.",
    )
    parser.add_argument("--max-tokens", type=int, default=int(os.getenv("EVAL_MAX_TOKENS", "350")))
    parser.add_argument("--judge-max-tokens", type=int, default=int(os.getenv("EVAL_JUDGE_MAX_TOKENS", "250")))
    parser.add_argument("--timeout", type=float, default=float(os.getenv("EVAL_TIMEOUT", "90")))
    parser.add_argument("--out-dir", default=os.path.join("testing", "reports", "evaluations"))
    args = parser.parse_args()

    load_dotenv(Path("backend") / ".env")
    if os.name == "nt":
        cache_dir = REPO_ROOT / ".cache" / "huggingface"
        os.environ["HF_HOME"] = str(cache_dir)
        os.environ["HF_HUB_CACHE"] = str(cache_dir)
        os.environ["SENTENCE_TRANSFORMERS_HOME"] = str(cache_dir)
    keys = groq_keys()
    api_key = keys[0]
    judge_type = "none" if args.no_judge else args.judge_type
    medical_judge = None
    if judge_type == "medical-bert":
        print(f"Loading medical BERT judge: {args.medical_bert_model}")
        medical_judge = MedicalBertJudge(args.medical_bert_model, args.unsupported_threshold)

    print("Medical RAG LLM evaluation")
    print(f"Models: {', '.join(args.models)}")
    if judge_type == "medical-bert":
        print(f"Judge:  medical BERT embeddings ({args.medical_bert_model})")
    elif judge_type == "llm":
        print(f"Judge:  LLM ({args.judge_model})")
    else:
        print("Judge:  disabled")
    print(f"Questions: {len(args.questions)}")
    print(f"Retrieval: top {args.k} chunks, fetch_k={args.fetch_k}, context_chars={args.context_chars}")
    if args.source_filter:
        print(f"Source filter: {args.source_filter}")
    if judge_type == "none":
        print("Scoring: no LLM judge; report includes latency, token usage, sources, and answers for human review.")
    elif judge_type == "medical-bert":
        print("Weights:")
        for key, weight in BERT_WEIGHTS.items():
            print(f"  {key}: {weight:.2f} - {BERT_RUBRIC_DESCRIPTION[key]}")
    else:
        print("Weights:")
        for key, weight in WEIGHTS.items():
            print(f"  {key}: {weight:.2f} - {RUBRIC_DESCRIPTION[key]}")
    print("API key: loaded, hidden")
    vectorstore = load_eval_vectorstore()

    rows: List[Dict[str, Any]] = []
    for question_index, question in enumerate(args.questions, start=1):
        print(f"\n[{question_index}/{len(args.questions)}] Retrieving context: {question}")
        docs = filtered_similarity_search(
            vectorstore,
            question,
            k=args.k,
            fetch_k=args.fetch_k,
            source_filter=args.source_filter,
        )
        if args.source_filter and not docs:
            print(f"  No retrieved chunks matched source filter: {args.source_filter}")
            continue
        context = build_context_from_docs_local(docs[: args.k], max_chars=args.context_chars)
        sources_for_question = source_summary(docs[: args.k])
        print("  Context sources:")
        for source in sources_for_question:
            page = source.get("page")
            page_text = f" p.{page}" if page not in (None, "") else ""
            print(f"  - {source.get('filename')}{page_text}")

        for model in args.models:
            print(f"  Asking {model}...", end="", flush=True)
            row: Dict[str, Any] = {
                "question_index": question_index,
                "question": question,
                "model": model,
                "context_sources": sources_for_question,
                "ok": False,
            }
            try:
                result = chat_completion(
                    model,
                    answer_prompt(question, context),
                    max_tokens=args.max_tokens,
                    temperature=float(os.getenv("LLM_TEMPERATURE", "0.1")),
                    timeout=args.timeout,
                    api_key=api_key,
                )
                usage = result.get("usage") or {}
                row.update(
                    {
                        "ok": True,
                        "answer": result["text"],
                        "latency_sec": round(result["latency_sec"], 3),
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "total_tokens": usage.get("total_tokens", 0),
                    }
                )

                if judge_type == "medical-bert":
                    row.update(medical_judge.score(answer=result["text"], context_docs=docs[: args.k]))
                elif judge_type == "llm":
                    judge = chat_completion(
                        args.judge_model,
                        judge_prompt(question, context, result["text"]),
                        max_tokens=args.judge_max_tokens,
                        temperature=0.0,
                        timeout=args.timeout,
                        api_key=api_key,
                    )
                    row.update(parse_judge_json(judge["text"]))
                print(f" ok ({row['latency_sec']}s)")
            except Exception as exc:
                row["error"] = str(exc)[:1000]
                print(f" failed: {row['error'][:160]}")
            rows.append(row)

    summary = summarize(rows)
    print("\nSummary")
    if judge_type == "none":
        print("model, questions, avg_latency_sec, latency_score, avg_prompt_tokens, avg_completion_tokens")
    elif judge_type == "medical-bert":
        print(
            "model, biomedical_grounding, context_coverage, hallucination_safety, "
            "unsupported_sentence_rate, quality_score, speed_score, quality/speed, "
            "balanced_score, avg_latency_sec"
        )
    else:
        print(
            "model, correctness, groundedness, completeness, safety, "
            "latency_score, avg_latency_sec, weighted_score"
        )
    for row in summary:
        if not row.get("ok"):
            print(f"{row['model']}, failed, {row.get('error')}")
            continue
        if judge_type == "none":
            print(
                f"{row['model']}, {row['questions']}, {row['avg_latency_sec']}, "
                f"{row['latency_score']}, {row['avg_prompt_tokens']}, {row['avg_completion_tokens']}"
            )
        elif judge_type == "medical-bert":
            print(
                f"{row['model']}, {row['biomedical_grounding']}, {row['context_coverage']}, "
                f"{row['hallucination_safety']}, {row['unsupported_sentence_rate']}, "
                f"{row['quality_score']}, {row['speed_score']}, {row['quality_speed_ratio']}, "
                f"{row['balanced_score']}, {row['avg_latency_sec']}"
            )
        else:
            print(
                f"{row['model']}, {row['medical_correctness']}, {row['groundedness']}, "
                f"{row['completeness']}, {row['safety']}, {row['latency_score']}, "
                f"{row['avg_latency_sec']}, {row['weighted_score']}"
            )

    if summary and summary[0].get("ok") and judge_type != "none":
        if judge_type == "medical-bert":
            print(
                f"\nMost balanced model: {summary[0]['model']} "
                f"with balanced score {summary[0]['balanced_score']} "
                f"(quality {summary[0]['quality_score']}, speed {summary[0]['speed_score']})"
            )
        else:
            print(f"\nWinner: {summary[0]['model']} with weighted score {summary[0]['weighted_score']}")
    elif summary and summary[0].get("ok"):
        print(f"\nFastest in this no-judge run: {summary[0]['model']} at {summary[0]['avg_latency_sec']}s average")

    write_reports(Path(args.out_dir), rows, summary)


if __name__ == "__main__":
    main()
