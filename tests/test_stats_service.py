from contextlib import contextmanager
from typing import Any

from typer.testing import CliRunner

from paperbrain.cli import app
from paperbrain.services.stats import CorpusStats, StatsService, run_stats


class FakeStatsRepo:
    def count_papers(self) -> int:
        return 2

    def count_authors(self) -> int:
        return 3

    def count_topics(self) -> int:
        return 4


def test_stats_service_collect_returns_counts() -> None:
    stats = StatsService(repo=FakeStatsRepo()).collect()
    assert stats == CorpusStats(papers=2, authors=3, topics=4)


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
            return [('["Alice", "Bob"]',), ('["Bob"]',)]

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

    assert stats == CorpusStats(papers=1, authors=2, topics=1)
    assert len(executed) == 3


def test_cli_stats_invokes_run_stats(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    def fake_run_stats(database_url: str) -> CorpusStats:
        captured["database_url"] = database_url
        return CorpusStats(papers=5, authors=7, topics=9)

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
    assert "authors=7" in result.output
    assert "topics=9" in result.output
    assert captured["database_url"] == "postgresql://localhost:5432/paperbrain"
