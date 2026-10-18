"""The question-answering pipeline.

    question -> guard -> scope -> retrieve -> confidence gate -> model -> validate -> cite

At every point where the evidence is missing, weak or unverifiable, the pipeline stops and
refers the employee to HR. A referral is always preferred to a guess.
"""

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from mypal.answering.guard import check_question
from mypal.answering.llm import GenerationUnavailable, LanguageModel
from mypal.answering.prompts import (
    ANSWER_SCHEMA,
    ANSWER_SCHEMA_NAME,
    SYSTEM_PROMPT,
    ModelAnswer,
    PromptPassage,
    build_user_prompt,
)
from mypal.answering.validator import strip_inline_labels, validate_answer
from mypal.auth.principal import Principal
from mypal.config import Settings
from mypal.db.models import AnswerOutcome, Chunk, HrContact, Policy, PolicyVersion, QueryMetric
from mypal.retrieval.embeddings import passage_text
from mypal.retrieval.retriever import RankedChunk, Retriever
from mypal.retrieval.scope import allowed_version_ids
from mypal.schemas.chat import ChatResponse, Citation, ReferralReason
from mypal.schemas.chat import HrContact as HrContactOut

logger = logging.getLogger(__name__)

REFERRAL_MESSAGE = (
    "I cannot confirm this from the approved policy information available. "
    "Please contact {contact}."
)
PERSONAL_RECORDS_MESSAGE = (
    "I can only explain HR policies. I cannot see personal records such as leave balances, "
    "payslips or salary details. Please contact {contact}."
)
SENSITIVE_MESSAGE = (
    "This may be a sensitive matter, so please raise it through the confidential HR route: "
    "{contact}. Please do not share personal details in this chat."
)
GENERIC_CONTACT = "your designated HR contact"


@dataclass
class AnswerDependencies:
    settings: Settings
    retriever: Retriever
    llm: LanguageModel


@dataclass
class _Timings:
    started: float
    retrieval_ms: int | None = None
    generation_ms: int | None = None


def answer_question(
    session: Session,
    deps: AnswerDependencies,
    principal: Principal,
    question: str,
    today: date,
    request_id: str | None = None,
) -> ChatResponse:
    timings = _Timings(started=time.perf_counter())
    response, reply_model, tokens, top_score = _answer(
        session, deps, principal, question, today, timings
    )
    _record_metrics(session, response, timings, reply_model, tokens, top_score, request_id)
    return response


def _answer(
    session: Session,
    deps: AnswerDependencies,
    principal: Principal,
    question: str,
    today: date,
    timings: _Timings,
) -> tuple[ChatResponse, str | None, tuple[int | None, int | None], float | None]:
    no_model = (None, (None, None))
    question = question.strip()

    # 1. Guard: personal records and sensitive topics go straight to HR.
    guard = check_question(question)
    if guard is not None:
        return (_referral(session, principal, guard.reason), *no_model, None)

    # 2. Scope: which published, in-effect versions apply to this employee?
    allowed = allowed_version_ids(session, principal, today)
    if not allowed:
        return (_referral(session, principal, "no_applicable_policy"), *no_model, None)

    # 3. Retrieve (hybrid: meaning + keywords, fused), only inside the allowed versions.
    retrieval_started = time.perf_counter()
    result = deps.retriever.retrieve(
        question,
        allowed,
        deps.settings.retrieval_top_k,
        load_texts=lambda ids: _passage_texts(session, ids, allowed),
    )
    timings.retrieval_ms = _elapsed_ms(retrieval_started)
    top_score = result.best_dense_score

    # 4. Confidence gate: if nothing the employee may see is close in meaning, refer to HR
    #    without spending a model call. Uses cosine similarity, which (unlike BM25 or RRF
    #    scores) is comparable from one question to the next.
    if top_score is None or top_score < deps.settings.retrieval_min_score:
        return (_referral(session, principal, "insufficient_evidence"), *no_model, top_score)

    chunks = _load_chunks(session, result.chunks, allowed)
    if not chunks:  # index and database disagree; never answer from unverified text
        logger.warning("retrieved chunks not found among allowed versions")
        return (_referral(session, principal, "insufficient_evidence"), *no_model, top_score)

    # 5. Ask the model, with passages labelled P1..Pn.
    labelled = {f"P{i}": row for i, row in enumerate(chunks, start=1)}
    passages = [
        PromptPassage(label, _source_label(policy, version, chunk), chunk.text)
        for label, (chunk, version, policy) in labelled.items()
    ]
    generation_started = time.perf_counter()
    try:
        reply = deps.llm.complete_json(
            SYSTEM_PROMPT,
            build_user_prompt(question, passages),
            ANSWER_SCHEMA_NAME,
            ANSWER_SCHEMA,
        )
    except GenerationUnavailable as exc:
        logger.warning("language model unavailable: %s", exc)
        return (_referral(session, principal, "generation_unavailable"), *no_model, top_score)
    finally:
        timings.generation_ms = _elapsed_ms(generation_started)
    tokens = (reply.prompt_tokens, reply.completion_tokens)

    try:
        model_answer = ModelAnswer.model_validate_json(reply.content)
    except ValueError:
        logger.warning("model returned output that does not match the answer schema")
        return (_referral(session, principal, "validation_failed"), reply.model, tokens, top_score)

    # 6. Validate before anything reaches the employee.
    check = validate_answer(
        model_answer,
        {p.label: f"{p.source}\n{p.text}" for p in passages},
    )
    if not check.ok:
        logger.warning("answer failed validation: %s", "; ".join(check.problems))
        return (_referral(session, principal, "validation_failed"), reply.model, tokens, top_score)

    if model_answer.outcome == "not_in_policy":
        return (_referral(session, principal, "not_in_policy"), reply.model, tokens, top_score)
    if model_answer.outcome == "needs_clarification":
        response = ChatResponse(
            answer_id=uuid.uuid4(),
            outcome=AnswerOutcome.CLARIFICATION,
            message=model_answer.clarification_question.strip(),
        )
        return response, reply.model, tokens, top_score

    # 7. Answered: citations come from the database, for exactly the passages the model cited.
    citations = [_citation(*labelled[label]) for label in check.cited_labels]
    response = ChatResponse(
        answer_id=uuid.uuid4(),
        outcome=AnswerOutcome.ANSWERED,
        message=strip_inline_labels(model_answer.answer),
        citations=citations,
    )
    return response, reply.model, tokens, top_score


def _passage_texts(
    session: Session, chunk_ids: list[uuid.UUID], allowed: list[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """Texts for the reranker - loaded from Postgres, and again only from allowed versions."""
    rows = session.execute(
        select(Chunk.id, Chunk.heading_path, Chunk.text).where(
            Chunk.id.in_(chunk_ids), Chunk.version_id.in_(allowed)
        )
    ).all()
    return {row.id: passage_text(row.heading_path, row.text) for row in rows}


def _load_chunks(
    session: Session, hits: list[RankedChunk], allowed: list[uuid.UUID]
) -> list[tuple[Chunk, PolicyVersion, Policy]]:
    """Re-check every hit against Postgres: the chunk must belong to an allowed version.
    Defence in depth - even a stale or tampered index entry cannot leak other content."""
    rows = session.execute(
        select(Chunk, PolicyVersion, Policy)
        .join(PolicyVersion, PolicyVersion.id == Chunk.version_id)
        .join(Policy, Policy.id == PolicyVersion.policy_id)
        .where(Chunk.id.in_([h.chunk_id for h in hits]), PolicyVersion.id.in_(allowed))
    ).all()
    by_id = {chunk.id: (chunk, version, policy) for chunk, version, policy in rows}
    return [by_id[h.chunk_id] for h in hits if h.chunk_id in by_id]  # keep ranking order


def _source_label(policy: Policy, version: PolicyVersion, chunk: Chunk) -> str:
    section = f", section {chunk.section_ref}" if chunk.section_ref else ""
    return (
        f"{policy.title} {version.version_label}{section}: "
        + passage_text(chunk.heading_path, "").strip()
    )


def _citation(chunk: Chunk, version: PolicyVersion, policy: Policy) -> Citation:
    return Citation(
        chunk_id=chunk.id,
        version_id=version.id,
        policy_key=policy.policy_key,
        policy_title=policy.title,
        version_label=version.version_label,
        section=chunk.section_ref,
        heading_path=list(chunk.heading_path),
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        effective_from=version.effective_from,
        source_link=version.source_link,
    )


def _referral(session: Session, principal: Principal, reason: ReferralReason) -> ChatResponse:
    confidential = reason == "sensitive_topic"
    contact = _find_hr_contact(session, principal, confidential)
    contact_text = f"{contact.label} ({contact.route})" if contact else GENERIC_CONTACT
    template = {
        "personal_records": PERSONAL_RECORDS_MESSAGE,
        "sensitive_topic": SENSITIVE_MESSAGE,
    }.get(reason, REFERRAL_MESSAGE)
    return ChatResponse(
        answer_id=uuid.uuid4(),
        outcome=AnswerOutcome.REFERRAL,
        message=template.format(contact=contact_text),
        referral_reason=reason,
        hr_contact=contact,
    )


def _find_hr_contact(
    session: Session, principal: Principal, confidential: bool
) -> HrContactOut | None:
    """The most specific active contact configured by HR for this employee. If HR has not
    configured one, None - the message then names no contact rather than inventing one."""
    candidates = session.scalars(
        select(HrContact).where(
            HrContact.is_active.is_(True),
            HrContact.company_code == principal.company_code,
            or_(
                HrContact.location_code.is_(None),
                HrContact.location_code == principal.location_code,
            ),
        )
    ).all()
    if confidential:
        candidates = [c for c in candidates if c.is_confidential] or list(candidates)
    else:
        candidates = [c for c in candidates if not c.is_confidential]
    if not candidates:
        return None
    best = sorted(candidates, key=lambda c: (c.location_code is None, c.topic is not None))[0]
    return HrContactOut(label=best.label, route=best.route, is_confidential=best.is_confidential)


def _record_metrics(
    session: Session,
    response: ChatResponse,
    timings: _Timings,
    model: str | None,
    tokens: tuple[int | None, int | None],
    top_score: float | None,
    request_id: str | None,
) -> None:
    """Performance, cost and what was cited - no question text, no answer text, no user
    identity. The answer id lets feedback refer to this answer (see feedback/service.py)."""
    session.add(
        QueryMetric(
            request_id=request_id or "none",
            answer_id=response.answer_id,
            cited_version_ids=sorted({c.version_id for c in response.citations}, key=str),
            outcome=response.outcome,
            total_ms=_elapsed_ms(timings.started),
            retrieval_ms=timings.retrieval_ms,
            generation_ms=timings.generation_ms,
            model=model,
            prompt_tokens=tokens[0],
            completion_tokens=tokens[1],
            estimated_cost=None,  # local model: no per-token charge
            top_retrieval_score=top_score,
        )
    )
    session.commit()


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
