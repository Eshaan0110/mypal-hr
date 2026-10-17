"""Retrieval evaluation: does search put the right policy section near the top?

    uv run mypal-eval-retrieval                       dense vs BM25 vs hybrid
    uv run mypal-eval-retrieval --rerank-model Xenova/ms-marco-MiniLM-L-6-v2

The documents listed in the question file are parsed and chunked with the real ingestion
pipeline, indexed with the real embedding models into a temporary Qdrant collection (deleted
afterwards), and every question is run through each search configuration. Postgres is not used,
so the result does not depend on what happens to be published in the development database.

Metrics, over the questions that have an answer:
- hit@k  - share of questions where a correct section is among the first k results
- MRR    - mean reciprocal rank: 1 if the correct section is 1st, 1/2 if 2nd, 1/3 if 3rd ...
And for the confidence gate (cosine threshold MYPAL_RETRIEVAL_MIN_SCORE):
- referred correctly - unanswerable questions whose best similarity is below the threshold
- wrongly referred    - answerable questions below the threshold (would get "contact HR")
"""

import argparse
import json
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from mypal.config import Settings
from mypal.ingestion.service import parse_file
from mypal.retrieval.embeddings import create_embedder, create_sparse_embedder, passage_text
from mypal.retrieval.index import create_index
from mypal.retrieval.rerank import FastEmbedReranker
from mypal.retrieval.retriever import Retriever

BACKEND_DIR = Path(__file__).resolve().parents[3]
QUESTIONS = BACKEND_DIR / "eval" / "retrieval_questions.json"
SAMPLES = BACKEND_DIR.parent / "sample_data" / "policies"
RESULTS = BACKEND_DIR / "eval" / "results"
TOP_K = 5
MRR_DEPTH = 10


@dataclass
class QuestionResult:
    id: str
    type: str
    question: str
    expected: list[str]
    retrieved: list[str]  # "policy#section" of each result, in rank order
    first_correct_rank: int | None
    best_dense_score: float | None
    top_score: float | None  # final ranking score of the first result (reranker score if used)


@dataclass
class ConfigReport:
    name: str
    hit_at_1: float
    hit_at_3: float
    hit_at_5: float
    mrr: float
    by_type: dict[str, dict[str, float]]
    unanswerable_referred: str
    answerable_wrongly_referred: str
    avg_ms: float
    questions: list[QuestionResult] = field(default_factory=list)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        prog="mypal-eval-retrieval", description=__doc__.splitlines()[0]
    )
    parser.add_argument("--rerank-model", help="also evaluate hybrid + this fastembed reranker")
    parser.add_argument("--questions", type=Path, default=QUESTIONS)
    args = parser.parse_args(argv)

    settings = Settings()
    spec = json.loads(args.questions.read_text(encoding="utf-8"))
    dense, sparse = create_embedder(settings), create_sparse_embedder(settings)
    index = create_index(settings, collection=f"eval_{uuid.uuid4().hex[:12]}")

    try:
        labels, texts, version_ids = _index_documents(
            spec["documents"], Retriever(dense, sparse, index)
        )
        configs = [
            ("dense", Retriever(dense, sparse, index, mode="dense")),
            ("bm25", Retriever(dense, sparse, index, mode="sparse")),
            ("hybrid (RRF)", Retriever(dense, sparse, index, mode="hybrid", rrf_k=settings.rrf_k)),
        ]
        if args.rerank_model:
            reranker = FastEmbedReranker(args.rerank_model, settings.embedding_cache_dir)
            short = args.rerank_model.split("/")[-1]
            configs += [
                (
                    f"dense + {short}",
                    Retriever(dense, sparse, index, mode="dense", reranker=reranker),
                ),
                (
                    f"hybrid + {short}",
                    Retriever(dense, sparse, index, mode="hybrid", reranker=reranker),
                ),
            ]
        reports = [
            _evaluate(name, retriever, spec["questions"], labels, texts, version_ids, settings)
            for name, retriever in configs
        ]
    finally:
        index.drop()

    _print(reports, settings.retrieval_min_score)
    path = _save(reports, settings)
    print(f"\nFull per-question results: {path.relative_to(BACKEND_DIR)}")
    return 0


def _index_documents(
    documents: list[dict], retriever: Retriever
) -> tuple[dict[uuid.UUID, str], dict[uuid.UUID, str], list[uuid.UUID]]:
    """Parse and index each document. Returns chunk -> "policy#section", chunk -> text, and the
    version ids (all treated as allowed)."""
    labels: dict[uuid.UUID, str] = {}
    texts: dict[uuid.UUID, str] = {}
    version_ids: list[uuid.UUID] = []
    for document in documents:
        path = SAMPLES / document["file"]
        result = parse_file(path.read_bytes(), path.name)
        version_id = uuid.uuid4()
        chunk_ids = [uuid.uuid4() for _ in result.chunks]
        chunk_texts = [passage_text(c.heading_path, c.text) for c in result.chunks]
        retriever.index_version(version_id, chunk_ids, chunk_texts)
        for chunk_id, chunk, text in zip(chunk_ids, result.chunks, chunk_texts, strict=True):
            labels[chunk_id] = f"{document['policy_key']}#{chunk.section_ref or '-'}"
            texts[chunk_id] = text
        version_ids.append(version_id)
    return labels, texts, version_ids


def _evaluate(
    name: str,
    retriever: Retriever,
    questions: list[dict],
    labels: dict[uuid.UUID, str],
    texts: dict[uuid.UUID, str],
    version_ids: list[uuid.UUID],
    settings: Settings,
) -> ConfigReport:
    results: list[QuestionResult] = []
    started = time.perf_counter()
    for q in questions:
        retrieved = retriever.retrieve(
            q["question"],
            version_ids,
            top_k=MRR_DEPTH,
            load_texts=lambda ids: {i: texts[i] for i in ids},
        )
        ranked = [labels[c.chunk_id] for c in retrieved.chunks]
        first = next((i for i, label in enumerate(ranked, 1) if label in q["expected"]), None)
        results.append(
            QuestionResult(
                q["id"],
                q["type"],
                q["question"],
                q["expected"],
                ranked,
                first,
                retrieved.best_dense_score,
                retrieved.chunks[0].score if retrieved.chunks else None,
            )
        )
    elapsed_ms = (time.perf_counter() - started) * 1000 / max(len(questions), 1)

    answerable = [r for r in results if r.expected]
    unanswerable = [r for r in results if not r.expected]
    threshold = settings.retrieval_min_score

    def below(r: QuestionResult) -> bool:
        return r.best_dense_score is None or r.best_dense_score < threshold

    by_type: dict[str, dict[str, float]] = {}
    for kind in sorted({r.type for r in answerable}):
        group = [r for r in answerable if r.type == kind]
        by_type[kind] = {"n": len(group), "hit@1": _hit(group, 1), "hit@5": _hit(group, 5)}

    return ConfigReport(
        name=name,
        hit_at_1=_hit(answerable, 1),
        hit_at_3=_hit(answerable, 3),
        hit_at_5=_hit(answerable, 5),
        mrr=sum(1 / r.first_correct_rank for r in answerable if r.first_correct_rank)
        / max(len(answerable), 1),
        by_type=by_type,
        unanswerable_referred=f"{sum(below(r) for r in unanswerable)}/{len(unanswerable)}",
        answerable_wrongly_referred=f"{sum(below(r) for r in answerable)}/{len(answerable)}",
        avg_ms=round(elapsed_ms, 1),
        questions=results,
    )


def _hit(results: list[QuestionResult], k: int) -> float:
    if not results:
        return 0.0
    return sum(1 for r in results if r.first_correct_rank and r.first_correct_rank <= k) / len(
        results
    )


def _print(reports: list[ConfigReport], threshold: float) -> None:
    n = sum(1 for q in reports[0].questions if q.expected)
    print(f"\nRetrieval evaluation - {n} answerable questions, top-{TOP_K}\n")
    print(f"{'configuration':<34}{'hit@1':>7}{'hit@3':>7}{'hit@5':>7}{'MRR':>7}{'ms/q':>8}")
    for r in reports:
        print(
            f"{r.name:<34}{r.hit_at_1:>7.0%}{r.hit_at_3:>7.0%}{r.hit_at_5:>7.0%}"
            f"{r.mrr:>7.2f}{r.avg_ms:>8.0f}"
        )
    types = list(reports[0].by_type)
    print("\nhit@1 by question type")
    print(f"{'configuration':<34}" + "".join(f"{t[:11]:>12}" for t in types))
    for r in reports:
        print(f"{r.name:<34}" + "".join(f"{r.by_type[t]['hit@1']:>12.0%}" for t in types))
    print(f"\nConfidence gate (best cosine similarity < {threshold}):")
    for r in reports:
        if r.name == "bm25":
            continue  # keyword-only search has no cosine score
        print(
            f"  {r.name:<32} unanswerable referred {r.unanswerable_referred:>5}   "
            f"answerable wrongly referred {r.answerable_wrongly_referred:>5}"
        )
    misses = {}
    for r in reports:
        for q in r.questions:
            if q.expected and (not q.first_correct_rank or q.first_correct_rank > 1):
                misses.setdefault(q.id, []).append(f"{r.name}: rank {q.first_correct_rank or '-'}")
    if misses:
        print("\nQuestions not ranked first by every configuration:")
        for qid, notes in misses.items():
            print(f"  {qid:<16} " + "; ".join(notes))


def _save(reports: list[ConfigReport], settings: Settings) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    path = RESULTS / f"retrieval-{stamp}.json"
    payload = {
        "created_at": stamp,
        "embedding_model": settings.embedding_model,
        "sparse_model": "Qdrant/bm25",
        "rrf_k": settings.rrf_k,
        "confidence_threshold": settings.retrieval_min_score,
        "configurations": [asdict(r) for r in reports],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


if __name__ == "__main__":
    raise SystemExit(main())
