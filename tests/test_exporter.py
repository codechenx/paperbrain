from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from paperbrain.cli import app
from paperbrain.exporter import render_paper_markdown
from paperbrain.exporter import render_person_markdown
from paperbrain.exporter import render_topic_markdown
from paperbrain.services.export import ExportService, ExportStats


class FakeExportRepo:
    def list_paper_cards(self) -> list[dict]:
        return [
            {
                "slug": "papers/chen-p53-nature-2024-abc123",
                "title": "P53 Mutations and Cancer Progression",
                "authors": ["Stephen Chen"],
                "corresponding_authors": ["people/alice-university-org"],
                "journal": "Nature",
                "year": 2024,
                "summary": "Key question solved: How do specific P53 mutations drive cancer progression?",
                "related_topics": ["topics/cancer-genetics"],
            }
        ]

    def list_person_cards(self) -> list[dict]:
        return [
            {
                "slug": "people/alice-university-org",
                "name": "Alice Research",
                "related_papers": ["papers/chen-p53-nature-2024-abc123"],
            }
        ]

    def list_topic_cards(self) -> list[dict]:
        return [
            {
                "slug": "topics/cancer-genetics",
                "topic": "Cancer Genetics",
                "related_papers": ["papers/chen-p53-nature-2024-abc123"],
                "related_people": ["people/alice-university-org"],
            }
        ]


def test_render_paper_markdown_writes_bidirectional_links() -> None:
    md = render_paper_markdown(
        slug="papers/chen-p53-nature-2024-abc123",
        title="P53 Mutations and Cancer Progression",
        authors=["Stephen Chen"],
        corresponding_authors=["people/alice-university-org"],
        journal="Nature",
        year=2024,
        summary_block="Key question solved: How do specific P53 mutations drive cancer progression?",
        related_topics=["topics/cancer-genetics"],
    )
    assert "[[people/alice-university-org]]" in md
    assert "[[topics/cancer-genetics]]" in md


def test_export_service_writes_cross_linked_markdown(tmp_path: Path) -> None:
    stats = ExportService(repo=FakeExportRepo()).export(tmp_path)

    assert stats.papers == 1
    assert stats.people == 1
    assert stats.topics == 1
    assert stats.files_written == 3

    paper_md = (tmp_path / "papers/chen-p53-nature-2024-abc123.md").read_text(encoding="utf-8")
    person_md = (tmp_path / "people/alice-university-org.md").read_text(encoding="utf-8")
    topic_md = (tmp_path / "topics/cancer-genetics.md").read_text(encoding="utf-8")

    assert "[[people/alice-university-org]]" in paper_md
    assert "[[topics/cancer-genetics]]" in paper_md
    assert "[[papers/chen-p53-nature-2024-abc123]]" in person_md
    assert "[[topics/cancer-genetics]]" in person_md
    assert "[[papers/chen-p53-nature-2024-abc123]]" in topic_md
    assert "[[people/alice-university-org]]" in topic_md


def test_cli_export_invokes_run_export(monkeypatch: Any, tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def fake_run_export(database_url: str, output_dir: Path) -> ExportStats:
        captured["database_url"] = database_url
        captured["output_dir"] = output_dir
        return ExportStats(papers=1, people=2, topics=3, files_written=6)

    class FakeConfig:
        database_url = "postgresql://localhost:5432/paperbrain"

    class FakeStore:
        def __init__(self, path: Any) -> None:
            captured["config_path"] = path

        def load(self) -> FakeConfig:
            return FakeConfig()

    output_dir = tmp_path / "vault"
    monkeypatch.setattr("paperbrain.cli.ConfigStore", FakeStore)
    monkeypatch.setattr("paperbrain.cli.run_export", fake_run_export, raising=False)

    result = CliRunner().invoke(app, ["export", "--output-dir", str(output_dir)])

    assert result.exit_code == 0
    assert "Exported 6 files" in result.output
    assert "papers=1 people=2 topics=3" in result.output
    assert captured["database_url"] == "postgresql://localhost:5432/paperbrain"
    assert captured["output_dir"] == output_dir


def test_render_markdown_frontmatter_escapes_quoted_values() -> None:
    paper_md = render_paper_markdown(
        slug="papers/example",
        title="A \"quoted\" title",
        authors=["Author"],
        corresponding_authors=[],
        journal="Journal",
        year=2024,
        summary_block="Summary",
        related_topics=[],
    )
    person_md = render_person_markdown(
        slug="people/example",
        name="Dr. \"Q\"",
        related_papers=[],
        related_topics=[],
    )
    topic_md = render_topic_markdown(
        slug="topics/example",
        topic="Cell \"signaling\"",
        related_papers=[],
        related_people=[],
    )

    assert "title: \"A \\\"quoted\\\" title\"" in paper_md
    assert "name: \"Dr. \\\"Q\\\"\"" in person_md
    assert "topic: \"Cell \\\"signaling\\\"\"" in topic_md
