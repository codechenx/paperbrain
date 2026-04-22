from contextlib import contextmanager
from typing import Any

from typer.testing import CliRunner

from paperbrain.cli import app
from paperbrain.services.stats import CorpusStats, StatsService, run_stats


class FakeStatsRepo:
    def count_papers(self) -> int:
        return 2

    def count_paper_cards(self) -> int:
        return 3

    def count_person_cards(self) -> int:
        return 4

    def count_topic_cards(self) -> int:
        return 5


def test_stats_service_collect_returns_counts() -> None:
    stats = StatsService(repo=FakeStatsRepo()).collect()
    assert stats == CorpusStats(papers=2, paper_cards=3, person_cards=4, topic_cards=5)


def test_run_stats_uses_database_connection(monkeypatch: Any) -> None:
    executed: list[str] = []

    class FakeCursor:
        def __enter__(self) -> "FakeCursor":
            return self

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            return None

        def execute(self, sql: str, params: Any = None) -> None:
            _ = params
            executed.append(sql)

        def fetchone(self) -> tuple[int]:
            return (1,)

        def fetchall(self) -> list[tuple[str]]:
            return [("1",)]

    class FakeConnection:
        def cursor(self) -> FakeCursor:
            return FakeCursor()

    @contextmanager
    def fake_connect(database_url: str, *, autocommit: bool = False) -> Any:
        assert database_url == "postgresql://localhost:5432/paperbrain"
        assert autocommit is False
        yield FakeConnection()

    monkeypatch.setattr("paperbrain.services.stats.connect", fake_connect)

    stats = run_stats("postgresql://localhost:5432/paperbrain")

    assert stats == CorpusStats(papers=1, paper_cards=1, person_cards=1, topic_cards=1)
    assert executed == [
        "SELECT COUNT(*) FROM papers;",
        "SELECT COUNT(*) FROM paper_cards;",
        "SELECT COUNT(*) FROM person_cards;",
        "SELECT COUNT(*) FROM topic_cards;",
    ]


def test_cli_stats_invokes_run_stats(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    def fake_run_stats(database_url: str) -> CorpusStats:
        captured["database_url"] = database_url
        return CorpusStats(papers=5, paper_cards=7, person_cards=11, topic_cards=13)

    class FakeConfig:
        database_url = "postgresql://localhost:5432/paperbrain"

    class FakeStore:
        def __init__(self, path: Any) -> None:
            captured["config_path"] = path

        def load(self) -> FakeConfig:
            return FakeConfig()

    monkeypatch.setattr("paperbrain.cli.ConfigStore", FakeStore)
    monkeypatch.setattr("paperbrain.cli.run_stats", fake_run_stats, raising=False)

    result = CliRunner().invoke(app, ["stats"])

    assert result.exit_code == 0
    assert "papers=5" in result.output
    assert "paper_cards=7" in result.output
    assert "person_cards=11" in result.output
    assert "topic_cards=13" in result.output
    assert "authors=" not in result.output
    assert "topics=" not in result.output
    assert captured["database_url"] == "postgresql://localhost:5432/paperbrain"
