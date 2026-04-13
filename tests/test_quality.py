from typing import Any

from typer.testing import CliRunner

from paperbrain.cli import app
from paperbrain.quality import normalize_whitespace
from paperbrain.services.lint import LintStats
from paperbrain.services.lint import lint_markdown


def test_normalize_whitespace_preserves_paragraph_breaks() -> None:
    source = "Line  one\n\nLine   two\n"
    assert normalize_whitespace(source) == "Line one\n\nLine two\n"


def test_lint_markdown_removes_dead_links() -> None:
    source = "See [[papers/a]] and [[papers/missing]]"
    assert lint_markdown(source, {"papers/a"}) == "See [[papers/a]] and papers/missing\n"


def test_cli_lint_invokes_run_lint(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    def fake_run_lint(database_url: str) -> LintStats:
        captured["database_url"] = database_url
        return LintStats(checked=4, fixed=1)

    class FakeConfig:
        database_url = "postgresql://localhost:5432/paperbrain"

    class FakeStore:
        def __init__(self, path: Any) -> None:
            captured["config_path"] = path

        def load(self) -> FakeConfig:
            return FakeConfig()

    monkeypatch.setattr("paperbrain.cli.ConfigStore", FakeStore)
    monkeypatch.setattr("paperbrain.cli.run_lint", fake_run_lint, raising=False)

    result = CliRunner().invoke(app, ["lint"])

    assert result.exit_code == 0
    assert "Linted 4 cards, fixed 1." in result.output
    assert captured["database_url"] == "postgresql://localhost:5432/paperbrain"
