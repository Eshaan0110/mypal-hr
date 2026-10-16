"""End-to-end parsing of the committed FICTIONAL sample policies."""

from pathlib import Path

import pytest

from mypal.ingestion.cli import main
from mypal.ingestion.service import parse_file

SAMPLES = Path(__file__).resolve().parents[3] / "sample_data" / "policies"
SAMPLE_FILES = sorted(SAMPLES.glob("*.*"))


def test_sample_policies_exist() -> None:
    assert len(SAMPLE_FILES) >= 4


@pytest.mark.parametrize("path", SAMPLE_FILES, ids=lambda p: p.name)
def test_sample_policy_parses_cleanly_and_is_labelled_fictional(path: Path) -> None:
    result = parse_file(path.read_bytes(), path.name)

    assert result.report["needs_manual_review"] is False, result.report["issues"]
    # Guard: sample documents must always announce that they are not real policies.
    assert result.chunks[0].text.startswith("FICTIONAL SAMPLE")
    numbered = [c for c in result.chunks if c.section_ref]
    assert len(numbered) >= 4
    if path.suffix == ".pdf":
        assert all(c.page_start for c in result.chunks)


def test_leave_policy_sections_are_traceable() -> None:
    path = SAMPLES / "leave-policy-v1.pdf"
    chunks = parse_file(path.read_bytes(), path.name).chunks

    sick = next(c for c in chunks if c.section_ref == "3.2")
    assert sick.heading_path == ["3. Types of leave", "3.2 Sick leave"]
    assert "10 days of sick leave" in sick.text
    assert sick.page_start == 1


def test_travel_policy_table_is_its_own_chunk() -> None:
    path = SAMPLES / "travel-reimbursement-policy-v1.docx"
    chunks = parse_file(path.read_bytes(), path.name).chunks

    table = next(c for c in chunks if c.kind == "table")
    assert table.section_ref == "2"
    assert "Grade B | INR 3,000 | INR 2,200" in table.text


def test_cli_preview_prints_report_and_chunks(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["parse", str(SAMPLES / "leave-policy-v1.pdf")])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "no problems detected" in output
    assert "3. Types of leave > 3.2 Sick leave" in output


def test_cli_reports_rejected_files(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bogus = tmp_path / "notes.pdf"
    bogus.write_text("not a pdf")

    assert main(["parse", str(bogus)]) == 2
    assert "unsupported_format" in capsys.readouterr().err
