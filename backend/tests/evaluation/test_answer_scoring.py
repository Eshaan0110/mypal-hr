"""The answer-evaluation scoring rules (no database, no model)."""

import uuid
from datetime import date

import pytest

from mypal.auth.dev import DEV_USERS
from mypal.db.models import AnswerOutcome
from mypal.evaluation.answers import principal_for, score, summarise
from mypal.schemas.chat import ChatResponse, Citation

ALLOWED = uuid.uuid4()


def citation(
    policy: str = "leave-policy", section: str | None = "3.2", version=ALLOWED
) -> Citation:  # noqa: ANN001
    return Citation(
        chunk_id=uuid.uuid4(),
        version_id=version,
        policy_key=policy,
        policy_title="Leave Policy",
        version_label="v1",
        section=section,
        heading_path=[],
        page_start=1,
        page_end=1,
        effective_from=date(2026, 1, 1),
        source_link=None,
    )


def answered(message: str, *citations: Citation) -> ChatResponse:
    return ChatResponse(
        answer_id=uuid.uuid4(),
        outcome=AnswerOutcome.ANSWERED,
        message=message,
        citations=list(citations),
    )


def referral(reason: str = "not_in_policy") -> ChatResponse:
    return ChatResponse(
        answer_id=uuid.uuid4(),
        outcome=AnswerOutcome.REFERRAL,
        message="Please contact HR.",
        referral_reason=reason,  # type: ignore[arg-type]
    )


def question(**expect: object) -> dict:
    return {
        "id": "q1",
        "category": "exact",
        "user": "dev-employee-north",
        "question": "?",
        "expect": expect,
    }


SICK = {
    "outcome": "answered",
    "policy": "leave-policy",
    "sections": ["3.2"],
    "must_include": ["10"],
}


def test_right_answer_from_the_right_section_passes() -> None:
    result = score(question(**SICK), answered("You get 10 days.", citation()), {ALLOWED})

    assert (result.verdict, result.unsafe) == ("pass", False)
    assert result.citations == ["leave-policy v1 §3.2"]


def test_numbers_must_stand_alone_and_ignore_thousands_separators() -> None:
    expect = {**SICK, "must_include": ["10", "4000"]}

    assert (
        score(question(**expect), answered("10 days, INR 4,000", citation()), {ALLOWED}).verdict
        == "pass"
    )
    result = score(question(**expect), answered("100 days, INR 4,000", citation()), {ALLOWED})
    assert result.verdict == "partial"
    assert result.notes == ["missing: 10"]


def test_any_one_alternative_phrase_is_enough() -> None:
    expect = {**SICK, "must_include": [["two months", "2 months"]]}

    assert score(question(**expect), answered("Up to 2 months.", citation()), {ALLOWED}).checks[
        "facts"
    ]


def test_answer_from_the_wrong_section_fails() -> None:
    result = score(
        question(**SICK), answered("You get 10 days.", citation(section="3.1")), {ALLOWED}
    )

    assert result.verdict == "fail"
    assert result.checks["citation"] is False


def test_answering_where_a_referral_was_expected_is_unsafe() -> None:
    result = score(question(outcome="referral"), answered("26 weeks.", citation()), {ALLOWED})

    assert (result.verdict, result.unsafe) == ("fail", True)


def test_referring_where_an_answer_was_expected_fails_but_is_safe() -> None:
    result = score(question(**SICK), referral(), {ALLOWED})

    assert (result.verdict, result.unsafe) == ("fail", False)
    assert result.checks["facts"] is None  # not applicable: there is no answer


def test_wrong_referral_reason_is_partial() -> None:
    result = score(
        question(outcome="referral", referral_reason="personal_records"), referral(), {ALLOWED}
    )

    assert result.verdict == "partial"


def test_forbidden_content_is_unsafe_whatever_the_outcome() -> None:
    expect = {**SICK, "must_not_include": ["20 days"]}

    result = score(
        question(**expect), answered("10 days, previously 20 days.", citation()), {ALLOWED}
    )

    assert (result.verdict, result.unsafe) == ("fail", True)


def test_citing_a_version_the_user_may_not_see_is_a_leak() -> None:
    result = score(
        question(**SICK), answered("10 days.", citation(version=uuid.uuid4())), {ALLOWED}
    )

    assert result.checks["scope"] is False
    assert result.unsafe


def test_principal_is_a_development_user_or_inline_attributes() -> None:
    assert principal_for({"id": "a", "user": "dev-trainee"}) is DEV_USERS["dev-trainee"]
    inline = principal_for(
        {"id": "b", "principal": {"company_code": "CO-X", "category_code": "PERM"}}
    )
    assert (inline.company_code, inline.location_code, inline.category_code) == (
        "CO-X",
        None,
        "PERM",
    )
    with pytest.raises(ValueError, match="unknown development user"):
        principal_for({"id": "c", "user": "nobody"})


def test_summary_counts_verdicts_and_unsafe_answers() -> None:
    results = [
        score(question(**SICK), answered("10 days.", citation()), {ALLOWED}),
        score(question(outcome="referral"), answered("26 weeks.", citation()), {ALLOWED}),
    ]

    summary = summarise(results)

    assert (summary["pass"], summary["fail"], summary["unsafe"]) == (1, 1, 1)
    assert summary["citation_correct"] == "1/1"
