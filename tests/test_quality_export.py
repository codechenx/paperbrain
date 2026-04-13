from paperbrain.exporter import render_paper_markdown
from paperbrain.quality import normalize_whitespace


def test_trim_whitespace_fix() -> None:
    assert normalize_whitespace("a  b\n\n") == "a b\n"


def test_export_writes_bidirectional_links() -> None:
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
            "Why this question is important: Important.\n"
            "How the paper solves this question: Method.\n"
            "Key findings and flow: Result.\n"
            "Limitations of the paper: Limits."
        ),
        related_topics=["topics/cancer-genetics"],
    )
    assert "[[people/alice-university-org]]" in md
    assert "[[topics/cancer-genetics]]" in md
