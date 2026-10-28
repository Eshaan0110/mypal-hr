"""Checks applied to the model's answer BEFORE it reaches the employee.

A model can produce fluent text that the evidence does not support. These checks catch the
mechanical failures; they do not prove the answer is right (that is what the HR-reviewed
evaluation set in Phase 8 measures):

1. An answer must cite at least one passage, and only passages we actually supplied.
2. Every number in the answer (days, amounts, dates, instalments) must appear in the cited
   passages - the concept note forbids inventing amounts, limits, dates or instalments.
3. A clarification must actually contain a question.

Any failure turns the response into a referral to HR.
"""

import re
from dataclasses import dataclass, field

from mypal.answering.prompts import ModelAnswer

# "P2", "[P2]", " p2 " -> "P2"
_LABEL = re.compile(r"^\[?\s*(P\d+)\s*\]?$", re.IGNORECASE)
# Only bracketed markers such as "[P1]", "[P1, P2]" or "(P2)": a bare "P1" may be real text
# (form P1). Left in place, the digits of a marker would also count as unsupported numbers.
_INLINE_LABEL = re.compile(
    r"\s*(?:\[\s*P\d+(?:\s*,\s*P\d+)*\s*\]|\(\s*P\d+(?:\s*,\s*P\d+)*\s*\))", re.IGNORECASE
)
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
# "1. ", "2) ", "(3) " at the start of a line: the model's own list numbering, not a policy value.
_LIST_MARKER = re.compile(r"^\s*\(?\d{1,2}[.)]\s+", re.MULTILINE)


@dataclass
class ValidationResult:
    cited_labels: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def normalise_label(label: str) -> str | None:
    match = _LABEL.match(label.strip())
    return match.group(1).upper() if match else None


def strip_inline_labels(text: str) -> str:
    """Remove "[P1]" markers the model may put in the prose; citations are shown separately."""
    return re.sub(r"\s{2,}", " ", _INLINE_LABEL.sub("", text)).strip()


def numbers_in(text: str) -> set[str]:
    return {n.replace(",", "").rstrip(".") for n in _NUMBER.findall(text)}


def validate_answer(answer: ModelAnswer, passages: dict[str, str]) -> ValidationResult:
    """passages maps label -> the passage text (including its headings) given to the model."""
    result = ValidationResult()

    if answer.outcome == "needs_clarification":
        if "?" not in answer.clarification_question:
            result.problems.append("clarification requested without a question")
        return result
    if answer.outcome != "answered":
        return result

    labels = []
    for raw in answer.citations:
        label = normalise_label(raw)
        if label is None or label not in passages:
            result.problems.append(f"cites unknown passage {raw!r}")
        elif label not in labels:
            labels.append(label)
    result.cited_labels = labels

    text = strip_inline_labels(answer.answer)
    if not text:
        result.problems.append("empty answer")
    if not labels:
        result.problems.append("answer has no citations")
        return result

    supported = set().union(*(numbers_in(passages[label]) for label in labels))
    unsupported = sorted(numbers_in(_LIST_MARKER.sub("", text)) - supported)
    if unsupported:
        result.problems.append(f"numbers not found in the cited passages: {', '.join(unsupported)}")
    return result
