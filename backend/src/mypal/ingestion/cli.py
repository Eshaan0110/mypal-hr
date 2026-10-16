"""Development command-line tool for ingestion (the HR admin portal replaces it in Phase 7).

uv run mypal-ingest parse FILE                 preview: parse and chunk, store nothing
uv run mypal-ingest seed-demo                  add the FICTIONAL demo scope codes
uv run mypal-ingest ingest FILE --policy-key ... --scope DEMO-HEALTH ...
uv run mypal-ingest list                       list stored policy versions
uv run mypal-ingest show VERSION_ID            inspect a stored draft and its chunks
"""

import argparse
import sys
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from mypal.config import Settings
from mypal.db.models import Chunk, Policy, PolicyVersion
from mypal.db.session import create_db_engine, create_session_factory
from mypal.errors import AppError
from mypal.ingestion.chunker import ChunkDraft
from mypal.ingestion.demo_reference import seed_demo_reference_data
from mypal.ingestion.schemas import DraftMetadata, ScopeInput
from mypal.ingestion.service import parse_file, store_draft


def main(argv: list[str] | None = None) -> int:
    # Policy text can contain characters the Windows console code page cannot print.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = _parser().parse_args(argv)
    try:
        return args.handler(args)
    except AppError as exc:
        print(f"error ({exc.code}): {exc.message}", file=sys.stderr)
        return 2
    except ValidationError as exc:
        print("error (validation_error):", file=sys.stderr)
        for err in exc.errors():
            field = ".".join(str(part) for part in err["loc"])
            print(f"  {field}: {err['msg']}", file=sys.stderr)
        return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mypal-ingest", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(required=True)

    parse = commands.add_parser("parse", help="preview parsing and chunking; stores nothing")
    parse.add_argument("file", type=Path)
    parse.add_argument("--full", action="store_true", help="print full chunk text")
    parse.set_defaults(handler=_cmd_parse)

    seed = commands.add_parser("seed-demo", help="add the fictional demo scope codes")
    seed.set_defaults(handler=_cmd_seed)

    ingest = commands.add_parser("ingest", help="parse a file and store it as a DRAFT version")
    ingest.add_argument("file", type=Path)
    ingest.add_argument("--policy-key", required=True, help="e.g. leave-policy")
    ingest.add_argument("--title", required=True)
    ingest.add_argument("--owner", required=True, help="HR content owner")
    ingest.add_argument("--version", required=True, dest="version_label", help="e.g. v1")
    ingest.add_argument("--uploaded-by", required=True, help="uploader's identity")
    ingest.add_argument("--effective-from", type=date.fromisoformat, help="YYYY-MM-DD")
    ingest.add_argument("--source-link", help="intranet URL employees can open")
    ingest.add_argument(
        "--scope",
        action="append",
        required=True,
        help="COMPANY[:LOCATION[:CATEGORY]], '*' = all; repeat for several",
    )
    ingest.set_defaults(handler=_cmd_ingest)

    listing = commands.add_parser("list", help="list stored policy versions")
    listing.set_defaults(handler=_cmd_list)

    show = commands.add_parser("show", help="inspect a stored version and its chunks")
    show.add_argument("version_id", type=uuid.UUID)
    show.add_argument("--full", action="store_true", help="print full chunk text")
    show.set_defaults(handler=_cmd_show)
    return parser


def _session() -> Session:
    return create_session_factory(create_db_engine(Settings()))()


# --- Commands ---------------------------------------------------------------------------------


def _cmd_parse(args: argparse.Namespace) -> int:
    result = parse_file(args.file.read_bytes(), args.file.name)
    _print_report(result.report)
    _print_chunks(result.chunks, full=args.full)
    return 1 if result.report["blocking"] else 0


def _cmd_seed(_: argparse.Namespace) -> int:
    with _session() as session:
        added = seed_demo_reference_data(session)
        session.commit()
    print(f"Added {added} fictional demo reference code(s).")
    return 0


def _cmd_ingest(args: argparse.Namespace) -> int:
    metadata = DraftMetadata(
        policy_key=args.policy_key,
        title=args.title,
        owner=args.owner,
        version_label=args.version_label,
        uploaded_by=args.uploaded_by,
        effective_from=args.effective_from,
        source_link=args.source_link,
        scopes=[ScopeInput.parse(value) for value in args.scope],
    )
    with _session() as session:
        version, result = store_draft(session, metadata, args.file.name, args.file.read_bytes())
        session.commit()
    print(f"Stored DRAFT version {version.id}")
    print("It is not visible to employees until it is reviewed, approved and published.")
    _print_report(result.report)
    return 0


def _cmd_list(_: argparse.Namespace) -> int:
    with _session() as session:
        rows = session.execute(
            select(Policy.policy_key, PolicyVersion)
            .join(PolicyVersion, PolicyVersion.policy_id == Policy.id)
            .order_by(Policy.policy_key, PolicyVersion.created_at)
        ).all()
        if not rows:
            print("No policy versions stored.")
        for key, version in rows:
            review = (
                "needs review" if (version.parse_report or {}).get("needs_manual_review") else ""
            )
            print(
                f"{version.id}  {key:<32} {version.version_label:<6} {version.status:<11} {review}"
            )
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    with _session() as session:
        version = session.get(PolicyVersion, args.version_id)
        if version is None:
            print(f"No policy version {args.version_id}", file=sys.stderr)
            return 1
        print(f"Policy:    {version.policy.policy_key} - {version.policy.title}")
        print(f"Version:   {version.version_label}  status={version.status}")
        print(f"File:      {version.source_filename}  sha256={version.source_sha256[:12]}...")
        print(f"Uploaded:  {version.created_by} at {version.created_at:%Y-%m-%d %H:%M}")
        print(f"Effective: {version.effective_from or 'not set'}")
        scopes = [
            f"{s.company_code}:{s.location_code or '*'}:{s.category_code or '*'}"
            for s in version.scopes
        ]
        print(f"Scopes:    {', '.join(scopes)}")
        _print_report(version.parse_report or {})
        stored = session.scalars(
            select(Chunk).where(Chunk.version_id == version.id).order_by(Chunk.ordinal)
        ).all()
        _print_chunks(stored, full=args.full)
    return 0


# --- Output -----------------------------------------------------------------------------------


def _print_report(report: dict[str, Any]) -> None:
    pages = report.get("page_count")
    print(
        f"\nFormat: {report.get('format')}  pages: {pages if pages is not None else 'n/a'}  "
        f"chunks: {report.get('chunk_count')} ({report.get('table_chunk_count')} table)"
    )
    verdict = (
        "BLOCKED - cannot be ingested"
        if report.get("blocking")
        else "NEEDS MANUAL REVIEW"
        if report.get("needs_manual_review")
        else "no problems detected"
    )
    print(f"Quality: {verdict}")
    for issue in report.get("issues", []):
        where = f" (page {issue['page']})" if issue.get("page") else ""
        print(f"  [{issue['severity']}] {issue['code']}{where}: {issue['message']}")


def _print_chunks(chunks: list[ChunkDraft] | list[Chunk], full: bool) -> None:
    print()
    for chunk in chunks:
        pages = (
            f"p{chunk.page_start}"
            + (f"-{chunk.page_end}" if chunk.page_end != chunk.page_start else "")
            if chunk.page_start
            else "p-"
        )
        path = " > ".join(chunk.heading_path) or "(before first heading)"
        kind = getattr(chunk.kind, "value", chunk.kind)
        print(f"#{chunk.ordinal:<3} {kind:<5} {pages:<6} §{chunk.section_ref or '-':<5} {path}")
        text = chunk.text if full else _preview(chunk.text)
        print("     " + text.replace("\n", "\n     "))


def _preview(text: str, limit: int = 160) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 3] + "..."


if __name__ == "__main__":
    raise SystemExit(main())
