from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from paperbrain.cli import app
from paperbrain.config import ConfigStore
from paperbrain.services.init import run_init
from paperbrain.services.setup import run_setup


def test_run_setup_writes_project_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config" / "paperbrain.conf"
    message = run_setup(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="sk-test",
        summary_model="gpt-4.1-mini",
        embedding_model="text-embedding-3-small",
        config_path=config_path,
        test_connections=False,
    )

    loaded = ConfigStore(config_path).load()
    assert loaded.database_url == "postgresql://localhost:5432/paperbrain"
    assert loaded.openai_api_key == "sk-test"
    assert loaded.summary_model == "gpt-4.1-mini"
    assert loaded.embedding_model == "text-embedding-3-small"
    assert message == f"Saved configuration to {config_path}"


def test_run_setup_validates_database_and_openai(monkeypatch: Any, tmp_path: Path) -> None:
    calls: dict[str, Any] = {"db": [], "embed": [], "summarize": []}

    @contextmanager
    def fake_connect(database_url: str, *, autocommit: bool = False) -> Iterator[object]:
        calls["db"].append((database_url, autocommit))
        yield object()

    class FakeOpenAIClient:
        def __init__(self, api_key: str) -> None:
            calls["api_key"] = api_key

        def embed(self, chunks: list[str], model: str) -> list[list[float]]:
            calls["embed"].append((chunks, model))
            return [[0.1]]

        def summarize(self, text: str, model: str) -> str:
            calls["summarize"].append((text, model))
            return "ok"

    monkeypatch.setattr("paperbrain.services.setup.connect", fake_connect)
    monkeypatch.setattr("paperbrain.services.setup.OpenAIClient", FakeOpenAIClient)

    run_setup(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="sk-test",
        summary_model="gpt-4.1-mini",
        embedding_model="text-embedding-3-small",
        config_path=tmp_path / "paperbrain.conf",
        test_connections=True,
    )

    assert calls["db"] == [("postgresql://localhost:5432/paperbrain", False)]
    assert calls["api_key"] == "sk-test"
    assert calls["embed"] == [(["paperbrain connectivity check"], "text-embedding-3-small")]
    assert calls["summarize"] == [("paperbrain connectivity check", "gpt-4.1-mini")]


def test_cli_setup_accepts_openai_options(monkeypatch: Any) -> None:
    calls: dict[str, Any] = {}

    def fake_run_setup(**kwargs: Any) -> str:
        calls.update(kwargs)
        return "ok"

    monkeypatch.setattr("paperbrain.cli.run_setup", fake_run_setup)
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "setup",
            "--url",
            "postgresql://localhost:5432/paperbrain",
            "--openai-api-key",
            "sk-test",
            "--summary-model",
            "gpt-4.1-mini",
            "--embedding-model",
            "text-embedding-3-small",
        ],
    )

    assert result.exit_code == 0
    assert "ok" in result.output
    assert calls["database_url"] == "postgresql://localhost:5432/paperbrain"
    assert calls["openai_api_key"] == "sk-test"
    assert calls["summary_model"] == "gpt-4.1-mini"
    assert calls["embedding_model"] == "text-embedding-3-small"
    assert calls["config_path"] == Path("config/paperbrain.conf")
    assert calls["test_connections"] is True


def test_run_init_applies_schema_to_database(monkeypatch: Any) -> None:
    statements = ["SELECT 1;", "SELECT 2;"]
    executed: list[str] = []

    class FakeCursor:
        def __enter__(self) -> "FakeCursor":
            return self

        def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            return None

        def execute(self, sql: str) -> None:
            executed.append(sql)

    class FakeConnection:
        def cursor(self) -> FakeCursor:
            return FakeCursor()

    @contextmanager
    def fake_connect(database_url: str, *, autocommit: bool = False) -> Iterator[FakeConnection]:
        assert database_url == "postgresql://localhost:5432/paperbrain"
        assert autocommit is True
        yield FakeConnection()

    monkeypatch.setattr("paperbrain.services.init.schema_statements", lambda force: statements)
    monkeypatch.setattr("paperbrain.services.init.connect", fake_connect)

    count = run_init("postgresql://localhost:5432/paperbrain", force=True)

    assert count == 2
    assert executed == statements
