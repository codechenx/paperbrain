import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from paperbrain.cli import app
from paperbrain.config import DEFAULT_EMBEDDING_MODEL, DEFAULT_SUMMARY_MODEL

pytestmark = pytest.mark.skipif(
    os.getenv("PAPERBRAIN_LIVE_TEST") != "1",
    reason="Set PAPERBRAIN_LIVE_TEST=1 to run live OpenAI + Postgres integration tests.",
)


def _ensure_local_pdf_fixture(pdf_dir: Path) -> Path:
    pdf_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(pdf_dir.glob("*.pdf"))
    if existing:
        return existing[0]

    sample_pdf = pdf_dir / "live-sample.pdf"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length 85 >>\nstream\nBT\n/F1 18 Tf\n72 720 Td\n(PaperBrain live integration sample document.) Tj\nET\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    parts = [b"%PDF-1.4\n"]
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(sum(len(part) for part in parts))
        parts.append(f"{index} 0 obj\n".encode())
        parts.append(obj)
        parts.append(b"\nendobj\n")

    xref_start = sum(len(part) for part in parts)
    parts.append(f"xref\n0 {len(objects) + 1}\n".encode())
    parts.append(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        parts.append(f"{offset:010d} 00000 n \n".encode())
    parts.append(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode())
    parts.append(f"startxref\n{xref_start}\n%%EOF\n".encode())
    sample_pdf.write_bytes(b"".join(parts))
    return sample_pdf


def test_live_openai_postgres_pipeline(tmp_path: Path) -> None:
    if os.getenv("PAPERBRAIN_ALLOW_DB_RESET", "").strip() != "1":
        pytest.skip("PAPERBRAIN_ALLOW_DB_RESET=1 is required before running destructive init --force.")

    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not openai_api_key:
        pytest.skip("OPENAI_API_KEY is required for live integration test.")

    database_url = os.getenv("PAPERBRAIN_TEST_DATABASE_URL", "").strip()
    if not database_url:
        pytest.skip("PAPERBRAIN_TEST_DATABASE_URL is required for live integration test.")

    pdf_dir = Path(__file__).parent / "pdf"
    pdf_fixture = _ensure_local_pdf_fixture(pdf_dir)

    config_path = tmp_path / "config" / "paperbrain.conf"
    runner = CliRunner()
    env = {"OPENAI_API_KEY": openai_api_key}

    setup_result = runner.invoke(
        app,
        [
            "setup",
            "--url",
            database_url,
            "--summary-model",
            DEFAULT_SUMMARY_MODEL,
            "--embedding-model",
            DEFAULT_EMBEDDING_MODEL,
            "--config-path",
            str(config_path),
        ],
        env=env,
        catch_exceptions=False,
    )
    assert setup_result.exit_code == 0, setup_result.output
    assert "Saved configuration" in setup_result.output

    init_result = runner.invoke(
        app,
        ["init", "--url", database_url, "--force"],
        catch_exceptions=False,
    )
    assert init_result.exit_code == 0, init_result.output
    assert "Applied" in init_result.output

    ingest_result = runner.invoke(
        app,
        ["ingest", str(pdf_fixture), "--config-path", str(config_path)],
        catch_exceptions=False,
    )
    assert ingest_result.exit_code == 0, ingest_result.output
    assert "Ingested " in ingest_result.output

    summarize_result = runner.invoke(
        app,
        ["summarize", "--force-all", "--config-path", str(config_path)],
        catch_exceptions=False,
    )
    assert summarize_result.exit_code == 0, summarize_result.output
    assert "Summarized cards: papers=" in summarize_result.output

    search_result = runner.invoke(
        app,
        ["search", pdf_fixture.stem, "--config-path", str(config_path)],
        env=env,
        catch_exceptions=False,
    )
    assert search_result.exit_code == 0, search_result.output
    assert '"keyword_rank":' in search_result.output
    assert '"vector_rank":' in search_result.output
    assert '"score":' in search_result.output
