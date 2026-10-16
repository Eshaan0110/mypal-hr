"""Development command-line tool for the policy lifecycle (the HR admin portal replaces it in
Phase 7). The same lifecycle rules apply as in the portal: four-eyes approval, audit records.

    uv run mypal-policy submit  VERSION_ID --actor hr-uploader@example.test
    uv run mypal-policy approve VERSION_ID --actor hr-reviewer@example.test
    uv run mypal-policy publish VERSION_ID --actor hr-reviewer@example.test
    uv run mypal-policy reindex                   rebuild the search index from Postgres

`--actor` is self-declared in this development tool; the portal takes it from the login.
"""

import argparse
import sys
import uuid
from datetime import date

from sqlalchemy import select

from mypal.config import Settings
from mypal.db.models import Chunk, PolicyVersion, PolicyVersionStatus
from mypal.db.session import create_db_engine, create_session_factory
from mypal.errors import AppError
from mypal.policies import lifecycle
from mypal.retrieval.embeddings import create_embedder, passage_text
from mypal.retrieval.index import create_index


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mypal-policy", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(required=True)
    for name, help_text in (
        ("submit", "draft -> in_review"),
        ("approve", "in_review -> approved (approver must differ from uploader)"),
        ("publish", "approved -> active; index chunks; supersede the previous version"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("version_id", type=uuid.UUID)
        command.add_argument("--actor", required=True, help="who performs the action")
        command.set_defaults(command=name)
    reindex = commands.add_parser("reindex", help="rebuild the search index for active versions")
    reindex.set_defaults(command="reindex")
    args = parser.parse_args(argv)

    settings = Settings()
    session = create_session_factory(create_db_engine(settings))()
    try:
        with session:
            if args.command == "reindex":
                return _reindex(session, settings)
            if args.command == "submit":
                version = lifecycle.submit_for_review(session, args.version_id, args.actor)
            elif args.command == "approve":
                version = lifecycle.approve(session, args.version_id, args.actor)
            else:
                version = lifecycle.publish(
                    session,
                    args.version_id,
                    args.actor,
                    create_embedder(settings),
                    create_index(settings),
                    date.today(),
                )
            session.commit()
            print(f"{version.version_label} is now {version.status.value}.")
            return 0
    except AppError as exc:
        print(f"error ({exc.code}): {exc.message}", file=sys.stderr)
        return 2


def _reindex(session, settings: Settings) -> int:  # noqa: ANN001
    """Rebuild every active version's points from Postgres (e.g. after changing the embedding
    model). Postgres is the source of truth, so this is always safe."""
    embedder, index = create_embedder(settings), create_index(settings)
    index.ensure_collection(embedder.dimension)
    versions = session.scalars(
        select(PolicyVersion).where(PolicyVersion.status == PolicyVersionStatus.ACTIVE)
    ).all()
    for version in versions:
        chunks = session.scalars(
            select(Chunk).where(Chunk.version_id == version.id).order_by(Chunk.ordinal)
        ).all()
        vectors = embedder.embed_passages([passage_text(c.heading_path, c.text) for c in chunks])
        index.upsert_version(version.id, [c.id for c in chunks], vectors)
        print(f"indexed {version.id} ({len(chunks)} chunks)")
    print(f"{len(versions)} active version(s) indexed; {index.count()} points in the index.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
