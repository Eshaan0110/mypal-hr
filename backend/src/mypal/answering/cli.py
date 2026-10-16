"""Ask My Pal a question from the command line, as one of the development test users.

    uv run mypal-ask "How many sick leave days do I get?" --as dev-employee-north

Runs exactly the same pipeline as POST /api/chat.
"""

import argparse
import json
import sys
from datetime import date

from mypal.answering.llm import create_llm
from mypal.answering.service import AnswerDependencies, answer_question
from mypal.auth.dev import DEV_USERS
from mypal.config import Settings
from mypal.db.session import create_db_engine, create_session_factory
from mypal.retrieval.embeddings import create_embedder
from mypal.retrieval.index import create_index


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="mypal-ask", description=__doc__.splitlines()[0])
    parser.add_argument("question")
    parser.add_argument(
        "--as", dest="user", default="dev-employee-north", choices=sorted(DEV_USERS)
    )
    parser.add_argument("--json", action="store_true", help="print the raw API response")
    args = parser.parse_args(argv)

    settings = Settings()
    deps = AnswerDependencies(
        settings=settings,
        embedder=create_embedder(settings),
        index=create_index(settings),
        llm=create_llm(settings),
    )
    with create_session_factory(create_db_engine(settings))() as session:
        response = answer_question(session, deps, DEV_USERS[args.user], args.question, date.today())

    if args.json:
        print(json.dumps(response.model_dump(mode="json"), indent=2))
        return 0
    print(
        f"[{response.outcome.value}]"
        + (f" ({response.referral_reason})" if response.referral_reason else "")
    )
    print(response.message)
    for i, c in enumerate(response.citations, start=1):
        pages = f", page {c.page_start}" if c.page_start else ""
        section = f", section {c.section}" if c.section else ""
        effective = f", effective {c.effective_from}" if c.effective_from else ""
        print(f"  [{i}] {c.policy_title} {c.version_label}{section}{pages}{effective}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
