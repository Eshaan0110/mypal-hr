"""Checks applied to the question BEFORE any retrieval or model call.

Two kinds of question are routed straight to HR, as the concept note requires:
- requests for personal records (balances, payslips) - out of scope, the system has no such data;
- sensitive matters (harassment, grievances, disciplinary issues) - shown the confidential route.

These keyword lists are a deliberately simple starting point for HR to review and extend. They
will miss paraphrases; the model's own "not_in_policy" outcome and the validator are further
safety nets, and Phase 8 tests these cases systematically.
"""

import re
from dataclasses import dataclass
from typing import Literal

GuardReason = Literal["personal_records", "sensitive_topic"]

_PERSONAL_RECORDS = re.compile(
    r"\b(pay\s?slip|salary\s+slip|leave\s+balance|my\s+balance|balance\s+leave|"
    r"leaves?\s+(do\s+i\s+have\s+)?left|my\s+(salary|pf|tax|ctc|appraisal\s+rating))\b",
    re.IGNORECASE,
)
_SENSITIVE = re.compile(
    r"\b(harass\w*|grievance\w*|disciplinary|misconduct|discriminat\w*|bully\w*|abuse\w*|"
    r"whistle\s?blow\w*|posh|complaint\s+against)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GuardResult:
    reason: GuardReason


def check_question(question: str) -> GuardResult | None:
    if _SENSITIVE.search(question):
        return GuardResult("sensitive_topic")
    if _PERSONAL_RECORDS.search(question):
        return GuardResult("personal_records")
    return None
