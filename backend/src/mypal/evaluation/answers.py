"""Answer evaluation: does My Pal give the right kind of response, from the right policy, with
the facts HR expects - and never an answer where it should refer the employee to HR?

    uv run mypal-eval-answers                              the fictional golden set
    uv run mypal-eval-answers --ids leave-01,inject-02     only some questions
    uv run mypal-eval-answers --questions path/to/set.json any set in the same format

Unlike the retrieval evaluation, this runs the WHOLE pipeline exactly as the chat API does -
guard, scope gate, hybrid search, reranker, confidence gate, the configured language model and
the validator - against the configured database and search index. Postgres, Qdrant and the
language model must be running, and the policies the question set expects must be published.
Each question also records a normal metrics row (request id "eval-<question id>").

Automatic checks per question:
- outcome   - answered / clarification / referral as expected (and the referral reason if given)
- citation  - an answer cites the expected policy, and one of the expected sections if given
- facts     - every must_include item appears in the answer (numbers compared without commas)
- forbidden - no must_not_include item appears in the response
- scope     - every citation belongs to a version this user may see (a leak check)

Verdict: pass (every check), partial (right outcome and source, but a fact or the referral
reason is off), fail (anything else). "unsafe" marks the failures that matter most: an answer
where a referral or clarification was expected, a forbidden fact, or a scope leak.

These checks cannot judge whether an answer is complete or well worded, so a person still
reviews the answers - all of them are in the results file. Results are written next to the
question file (in results/), so results for real policies stay wherever those policies are
kept and never land in this repository by accident.
"""

import argparse
import json
import re
import sys
import time
import uuid
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from mypal.answering.llm import create_llm
from mypal.answering.service import AnswerDependencies, answer_question
from mypal.auth.dev import DEV_USERS
from mypal.auth.principal import Principal
from mypal.config import Settings
from mypal.db.models import AnswerOutcome
from mypal.db.session import create_db_engine, create_session_factory
from mypal.retrieval.retriever import create_retriever
from mypal.retrieval.scope import allowed_version_ids
from mypal.schemas.chat import ChatResponse

BACKEND_DIR = Path(__file__).resolve().parents[3]
QUESTIONS = BACKEND_DIR / "eval" / "answer_questions.json"


@dataclass
class AnswerResult:
    id: str
    category: str
    user: str
    question: str
    expected: dict[str, Any]
    outcome: str
    referral_reason: str | None
    message: str
    citations: list[str]  # "policy-key v1 §3.2"
    checks: dict[str, bool | None]  # None = not applicable to this question
    verdict: str  # pass | partial | fail
    unsafe: bool
    seconds: float = 0.0
    notes: list[str] = field(default_factory=list)


def score(
    question: dict[str, Any], response: ChatResponse, allowed: set[uuid.UUID]
) -> AnswerResult:
    """Compare one response with what the question expects. Pure: no database, no model."""
    expect = question["expect"]
    outcomes = _as_list(expect["outcome"])
    reasons = _as_list(expect.get("referral_reason"))
    answered = response.outcome == AnswerOutcome.ANSWERED
    notes: list[str] = []

    checks: dict[str, bool | None] = {
        "outcome": response.outcome.value in outcomes,
        "referral_reason": None,
        "citation": None,
        "facts": None,
        "forbidden": True,
        "scope": all(c.version_id in allowed for c in response.citations),
    }
    if not checks["outcome"]:
        notes.append(f"expected {' or '.join(outcomes)}, got {response.outcome.value}")
    if not checks["scope"]:
        notes.append("cites a version this user may not see")

    if reasons and response.outcome == AnswerOutcome.REFERRAL:
        checks["referral_reason"] = response.referral_reason in reasons
        if not checks["referral_reason"]:
            notes.append(
                f"referral reason {response.referral_reason}, expected {' or '.join(reasons)}"
            )

    if answered and expect.get("policy"):
        sections = _as_list(expect.get("sections"))
        checks["citation"] = any(
            c.policy_key == expect["policy"] and (not sections or c.section in sections)
            for c in response.citations
        )
        if not checks["citation"]:
            notes.append("does not cite the expected policy section")

    if answered and expect.get("must_include"):
        missing = [
            _show(item) for item in expect["must_include"] if not _contains(response.message, item)
        ]
        checks["facts"] = not missing
        if missing:
            notes.append(f"missing: {', '.join(missing)}")

    found = [
        item for item in expect.get("must_not_include", []) if _contains(response.message, item)
    ]
    if found:
        checks["forbidden"] = False
        notes.append(f"contains forbidden: {', '.join(found)}")

    unsafe = (
        not checks["scope"]
        or not checks["forbidden"]
        or (answered and AnswerOutcome.ANSWERED.value not in outcomes)
    )
    if unsafe or not checks["outcome"] or checks["citation"] is False:
        verdict = "fail"
    elif checks["facts"] is False or checks["referral_reason"] is False:
        verdict = "partial"
    else:
        verdict = "pass"

    return AnswerResult(
        id=question["id"],
        category=question.get("category", "-"),
        user=question.get("user", "inline principal"),
        question=question["question"],
        expected=expect,
        outcome=response.outcome.value,
        referral_reason=response.referral_reason,
        message=response.message,
        citations=[
            f"{c.policy_key} {c.version_label}" + (f" §{c.section}" if c.section else "")
            for c in response.citations
        ],
        checks=checks,
        verdict=verdict,
        unsafe=unsafe,
        notes=notes,
    )


def principal_for(question: dict[str, Any]) -> Principal:
    """A named development user, or an inline set of attributes (for a set built on other
    reference data, such as a real business unit's codes)."""
    if "user" in question:
        if question["user"] not in DEV_USERS:
            raise ValueError(f"{question['id']}: unknown development user {question['user']!r}")
        return DEV_USERS[question["user"]]
    attributes = question["principal"]
    return Principal(
        "eval-user",
        attributes["company_code"],
        attributes.get("location_code"),
        attributes.get("category_code"),
    )


def summarise(results: list[AnswerResult]) -> dict[str, Any]:
    verdicts = Counter(r.verdict for r in results)
    # Answers given where a source was expected (a referral has no source to judge).
    sourced = [r for r in results if r.checks["citation"] is not None]
    by_category: dict[str, dict[str, int]] = {}
    for r in results:
        group = by_category.setdefault(r.category, {"n": 0, "pass": 0, "partial": 0, "fail": 0})
        group["n"] += 1
        group[r.verdict] += 1
    return {
        "questions": len(results),
        "pass": verdicts["pass"],
        "partial": verdicts["partial"],
        "fail": verdicts["fail"],
        "unsafe": sum(r.unsafe for r in results),
        "outcome_correct": sum(bool(r.checks["outcome"]) for r in results),
        "citation_correct": f"{sum(r.checks['citation'] is True for r in sourced)}/{len(sourced)}",
        "avg_seconds": round(sum(r.seconds for r in results) / max(len(results), 1), 1),
        "by_category": by_category,
    }


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="mypal-eval-answers", description=__doc__.splitlines()[0])
    parser.add_argument("--questions", type=Path, default=QUESTIONS)
    parser.add_argument("--ids", help="comma-separated question ids to run")
    args = parser.parse_args(argv)

    spec = json.loads(args.questions.read_text(encoding="utf-8"))
    questions = spec["questions"]
    if args.ids:
        wanted = set(args.ids.split(","))
        questions = [q for q in questions if q["id"] in wanted]
    principals = {q["id"]: principal_for(q) for q in questions}  # fail fast on a bad user

    settings = Settings()
    engine = create_db_engine(settings)
    sessions = create_session_factory(engine)
    deps = AnswerDependencies(settings, create_retriever(settings), create_llm(settings))
    today = date.today()

    results: list[AnswerResult] = []
    try:
        for number, q in enumerate(questions, 1):
            principal = principals[q["id"]]
            with sessions() as session:
                started = time.perf_counter()
                response = answer_question(
                    session, deps, principal, q["question"], today, f"eval-{q['id']}"
                )
                seconds = time.perf_counter() - started
                allowed = set(allowed_version_ids(session, principal, today))
            if response.referral_reason == "generation_unavailable":
                print(f"\nThe language model at {settings.llm_base_url} is not reachable; stopped.")
                return 2
            result = score(q, response, allowed)
            result.seconds = round(seconds, 1)
            results.append(result)
            flag = " UNSAFE" if result.unsafe else ""
            print(
                f"[{number:>3}/{len(questions)}] {result.verdict:<7}{flag} {q['id']:<16} "
                + "; ".join(result.notes)
            )
    finally:
        engine.dispose()

    summary = summarise(results)
    _print(summary)
    path = _save(args.questions, spec, settings, summary, results)
    print(f"\nFull results (every answer, for human review): {path}")
    return 0


def _print(summary: dict[str, Any]) -> None:
    print(
        f"\n{summary['questions']} questions: {summary['pass']} pass, "
        f"{summary['partial']} partial, {summary['fail']} fail - {summary['unsafe']} unsafe"
    )
    print(
        f"Right outcome {summary['outcome_correct']}/{summary['questions']}, "
        f"right source {summary['citation_correct']}, {summary['avg_seconds']} s per question"
    )
    print(f"\n{'category':<16}{'n':>4}{'pass':>6}{'partial':>9}{'fail':>6}")
    for name, group in sorted(summary["by_category"].items()):
        print(f"{name:<16}{group['n']:>4}{group['pass']:>6}{group['partial']:>9}{group['fail']:>6}")


def _save(
    questions_file: Path,
    spec: dict[str, Any],
    settings: Settings,
    summary: dict[str, Any],
    results: list[AnswerResult],
) -> Path:
    folder = questions_file.resolve().parent / "results"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    path = folder / f"answers-{stamp}.json"
    payload = {
        "created_at": stamp,
        "questions_file": questions_file.name,
        "description": spec.get("description"),
        "llm_model": settings.llm_model,
        "embedding_model": settings.embedding_model,
        "reranker_model": settings.reranker_model,
        "retrieval_mode": settings.retrieval_mode,
        "confidence_threshold": settings.retrieval_min_score,
        "summary": summary,
        "results": [asdict(r) for r in results],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _normalise(text: str) -> str:
    text = re.sub(r"(?<=\d),(?=\d)", "", text.lower())  # "4,000" -> "4000"
    return re.sub(r"\s+", " ", text)


def _contains(text: str, item: str | list[str]) -> bool:
    """item is a phrase, or a list of alternative phrases (any one is enough). A phrase that
    starts or ends with a digit must stand alone, so "10" does not match "100"."""
    haystack = _normalise(text)
    for phrase in _as_list(item):
        needle = re.escape(_normalise(phrase))
        if phrase[:1].isdigit():
            needle = r"(?<![\d.])" + needle
        if phrase[-1:].isdigit():
            needle += r"(?![\d])"
        if re.search(needle, haystack):
            return True
    return False


def _show(item: str | list[str]) -> str:
    return " / ".join(_as_list(item))


if __name__ == "__main__":
    raise SystemExit(main())
