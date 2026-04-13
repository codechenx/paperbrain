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
                "email": "alice@university.org",
                "affiliation": "University Lab",
                "focus_area": ["Cancer Genetics"],
                "big_questions": [
                    {
                        "question": "How do P53 mutations drive progression?",
                        "why_important": "Enables targeted treatment.",
                        "related_papers": ["papers/chen-p53-nature-2024-abc123"],
                    }
                ],
                "related_papers": ["papers/chen-p53-nature-2024-abc123"],
            }
        ]

    def list_topic_cards(self) -> list[dict]:
        return [
            {
                "slug": "topics/cancer-genetics",
                "topic": "Cancer Genetics",
                "related_big_questions": [
                    {
                        "question": "How do P53 mutations drive progression?",
                        "why_important": "Enables targeted treatment.",
                        "related_papers": ["papers/chen-p53-nature-2024-abc123"],
                        "related_people": ["people/alice-university-org"],
                    }
                ],
                "related_papers": ["papers/chen-p53-nature-2024-abc123"],
                "related_people": ["people/alice-university-org"],
            }
        ]


def test_render_paper_markdown_writes_bidirectional_links() -> None:
    md = render_paper_markdown(
        slug="papers/chen-p53-nature-2024-abc123",
        paper_type="article",
        title="P53 Mutations and Cancer Progression",
        authors=["Stephen Chen"],
        corresponding_authors=["people/alice-university-org"],
        journal="Nature",
        year=2024,
        summary_block=(
            "Key question solved: How do specific P53 mutations drive cancer progression?\n"
            "Why this question is important: Impact.\n"
            "How the paper solves this question: Method.\n"
            "Key findings and flow: Results.\n"
            "Limitations of the paper: Limit."
        ),
        related_topics=["topics/cancer-genetics"],
    )
    assert "[[people/alice-university-org]]" in md
    assert "[[topics/cancer-genetics]]" in md
    assert "<!-- paperbrain_paper_summary:start -->" not in md
    assert "<!-- paperbrain_paper_summary:end -->" not in md
    assert "## Key question solved" in md
    assert "## Why this question is important" in md
    assert "## How the paper solves this question" in md
    assert "## Key findings and flow" in md
    assert "## Limitations of the paper" in md


def test_render_paper_markdown_preserves_multiline_findings_with_figure_bullets() -> None:
    md = render_paper_markdown(
        slug="papers/example-flow",
        paper_type="article",
        title="Flow Test",
        authors=["Author One"],
        corresponding_authors=["people/author-one"],
        journal="Science",
        year=2026,
        summary_block=(
            "Key question solved: Q\n"
            "Why this question is important: W\n"
            "How the paper solves this question: H\n"
            "Key findings and flow: Logical flow of sections and experiments:\n"
            "- Figure 1: Discovery cohort identifies baseline pattern.\n"
            "- Figure 2: Perturbation experiment validates causality.\n"
            "- Figure 3: Ablation experiment confirms mechanism.\n"
            "Limitations of the paper: L"
        ),
        related_topics=["topics/example"],
    )

    assert "## Key findings and flow" in md
    assert "Logical flow of sections and experiments:" in md
    assert "- Figure 1: Discovery cohort identifies baseline pattern." in md
    assert "- Figure 2: Perturbation experiment validates causality." in md
    assert "- Figure 3: Ablation experiment confirms mechanism." in md


def test_export_service_writes_cross_linked_markdown(tmp_path: Path) -> None:
    stats = ExportService(repo=FakeExportRepo()).export(tmp_path)

    assert stats.papers == 1
    assert stats.people == 1
    assert stats.topics == 1
    assert stats.files_written == 4

    paper_md = (tmp_path / "papers/chen-p53-nature-2024-abc123.md").read_text(encoding="utf-8")
    person_md = (tmp_path / "people/alice-university-org.md").read_text(encoding="utf-8")
    topic_md = (tmp_path / "topics/cancer-genetics.md").read_text(encoding="utf-8")
    index_md = (tmp_path / "index.md").read_text(encoding="utf-8")

    assert "[[people/alice-university-org]]" in paper_md
    assert "[[topics/cancer-genetics]]" in paper_md
    assert "[[papers/chen-p53-nature-2024-abc123]]" in person_md
    assert "[[topics/cancer-genetics]]" in person_md
    assert "[[papers/chen-p53-nature-2024-abc123]]" in topic_md
    assert "[[people/alice-university-org]]" in topic_md
    assert "email: \"alice@university.org\"" in person_md
    assert "affiliation: \"University Lab\"" in person_md
    assert "Question: How do P53 mutations drive progression?" in person_md
    assert "Question: How do P53 mutations drive progression?" in topic_md
    assert "## Focus area" in person_md
    assert "## Big questions" in person_md
    assert "## Related big questions" in topic_md
    assert "## Papers" in index_md
    assert "## People" in index_md
    assert "## Topics" in index_md


def test_export_service_backfills_topic_big_questions_from_related_people(tmp_path: Path) -> None:
    class MissingTopicQuestionsRepo(FakeExportRepo):
        def list_topic_cards(self) -> list[dict]:
            return [
                {
                    "slug": "topics/cancer-genetics",
                    "topic": "Cancer Genetics",
                    "related_papers": ["papers/chen-p53-nature-2024-abc123"],
                    "related_people": ["people/alice-university-org"],
                }
            ]

    _ = ExportService(repo=MissingTopicQuestionsRepo()).export(tmp_path)
    topic_md = (tmp_path / "topics/cancer-genetics.md").read_text(encoding="utf-8")

    assert "## Related big questions" in topic_md
    assert "- (none)" not in topic_md
    assert "Question: How do P53 mutations drive progression?" in topic_md


def test_export_backfill_merges_duplicate_topic_questions(tmp_path: Path) -> None:
    class DuplicatePeopleRepo:
        def list_paper_cards(self) -> list[dict]:
            return [
                {
                    "slug": "papers/example-a",
                    "title": "A",
                    "authors": ["Author A"],
                    "corresponding_authors": ["people/alice-university-org"],
                    "journal": "Nature",
                    "year": 2024,
                    "summary": "Key question solved: Q",
                    "related_topics": ["topics/gut-microbiome-and-lung-cancer-treatment"],
                },
                {
                    "slug": "papers/example-b",
                    "title": "B",
                    "authors": ["Author B"],
                    "corresponding_authors": ["people/bob-university-org"],
                    "journal": "Nature",
                    "year": 2024,
                    "summary": "Key question solved: Q",
                    "related_topics": ["topics/gut-microbiome-and-lung-cancer-treatment"],
                },
            ]

        def list_person_cards(self) -> list[dict]:
            shared = {
                "question": "How can gut microbiome signals improve lung cancer treatment response?",
                "why_important": "Could personalize treatment and improve outcomes.",
            }
            return [
                {
                    "slug": "people/alice-university-org",
                    "name": "Alice",
                    "email": "alice@u.org",
                    "affiliation": "u.org",
                    "focus_area": ["gut microbiome and lung cancer treatment"],
                    "big_questions": [{**shared, "related_papers": ["papers/example-a"]}],
                    "related_papers": ["papers/example-a"],
                },
                {
                    "slug": "people/bob-university-org",
                    "name": "Bob",
                    "email": "bob@u.org",
                    "affiliation": "u.org",
                    "focus_area": ["gut microbiome and lung cancer treatment"],
                    "big_questions": [{**shared, "related_papers": ["papers/example-b"]}],
                    "related_papers": ["papers/example-b"],
                },
            ]

        def list_topic_cards(self) -> list[dict]:
            return [
                {
                    "slug": "topics/gut-microbiome-and-lung-cancer-treatment",
                    "topic": "gut microbiome and lung cancer treatment",
                    "related_papers": ["papers/example-a", "papers/example-b"],
                    "related_people": ["people/alice-university-org", "people/bob-university-org"],
                }
            ]

    _ = ExportService(repo=DuplicatePeopleRepo()).export(tmp_path)
    topic_md = (tmp_path / "topics/gut-microbiome-and-lung-cancer-treatment.md").read_text(encoding="utf-8")
    assert topic_md.count("Question: How can gut microbiome signals improve lung cancer treatment response?") == 1


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
        paper_type="article",
        title="A \"quoted\" title",
        authors=["Author"],
        corresponding_authors=[],
        journal="Journal",
        year=2024,
        summary_block="Key findings and flow: Summary",
        related_topics=[],
    )
    person_md = render_person_markdown(
        slug="people/example",
        name="Dr. \"Q\"",
        email="q@example.org",
        affiliation="Lab \"X\"",
        focus_areas=[],
        big_questions=[],
        related_papers=[],
        related_topics=[],
    )
    topic_md = render_topic_markdown(
        slug="topics/example",
        topic="Cell \"signaling\"",
        related_big_questions=[],
        related_papers=[],
        related_people=[],
    )

    assert "title: \"A \\\"quoted\\\" title\"" in paper_md
    assert "name: \"Dr. \\\"Q\\\"\"" in person_md
    assert "affiliation: \"Lab \\\"X\\\"\"" in person_md
    assert "topic: \"Cell \\\"signaling\\\"\"" in topic_md
