from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
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


def test_cli_setup_reads_openai_key_from_env(monkeypatch: Any) -> None:
    calls: dict[str, Any] = {}

    def fake_run_setup(**kwargs: Any) -> str:
        calls.update(kwargs)
        return "ok"

    monkeypatch.setattr("paperbrain.cli.run_setup", fake_run_setup)
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["setup", "--url", "postgresql://localhost:5432/paperbrain"],
        env={"OPENAI_API_KEY": "sk-env"},
    )

    assert result.exit_code == 0
    assert calls["openai_api_key"] == "sk-env"


def test_cli_setup_prompts_securely_when_openai_key_missing(monkeypatch: Any) -> None:
    calls: dict[str, Any] = {}
    prompt_calls: list[tuple[str, bool]] = []

    def fake_run_setup(**kwargs: Any) -> str:
        calls.update(kwargs)
        return "ok"

    def fake_prompt(text: str, *, hide_input: bool = False) -> str:
        prompt_calls.append((text, hide_input))
        return "sk-prompted"

    monkeypatch.setattr("paperbrain.cli.run_setup", fake_run_setup)
    monkeypatch.setattr("paperbrain.cli.typer.prompt", fake_prompt)

    runner = CliRunner()
    result = runner.invoke(app, ["setup", "--url", "postgresql://localhost:5432/paperbrain"], env={})

    assert result.exit_code == 0
    assert prompt_calls == [("OpenAI API key", True)]
    assert calls["openai_api_key"] == "sk-prompted"


def test_cli_setup_does_not_prompt_when_connection_tests_disabled(monkeypatch: Any) -> None:
    calls: dict[str, Any] = {}
    prompt_calls: list[tuple[str, bool]] = []

    def fake_run_setup(**kwargs: Any) -> str:
        calls.update(kwargs)
        return "ok"

    def fake_prompt(text: str, *, hide_input: bool = False) -> str:
        prompt_calls.append((text, hide_input))
        return "sk-prompted"

    monkeypatch.setattr("paperbrain.cli.run_setup", fake_run_setup)
    monkeypatch.setattr("paperbrain.cli.typer.prompt", fake_prompt)

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["setup", "--url", "postgresql://localhost:5432/paperbrain", "--no-test-connections"],
        env={},
    )

    assert result.exit_code == 0
    assert prompt_calls == []
    assert calls["openai_api_key"] == ""
    assert calls["test_connections"] is False


def test_run_setup_database_validation_failure_has_context(monkeypatch: Any, tmp_path: Path) -> None:
    def failing_connect(database_url: str, *, autocommit: bool = False) -> Iterator[object]:
        _ = database_url, autocommit
        raise RuntimeError("database unreachable")
        yield object()

    monkeypatch.setattr("paperbrain.services.setup.connect", contextmanager(failing_connect))

    with pytest.raises(RuntimeError, match=r"Setup failed during database validation: database unreachable"):
        run_setup(
            database_url="postgresql://localhost:5432/paperbrain",
            openai_api_key="sk-test",
            config_path=tmp_path / "paperbrain.conf",
            test_connections=True,
        )


def test_run_setup_openai_validation_failure_has_context(monkeypatch: Any, tmp_path: Path) -> None:
    @contextmanager
    def fake_connect(database_url: str, *, autocommit: bool = False) -> Iterator[object]:
        _ = database_url, autocommit
        yield object()

    class FailingOpenAIClient:
        def __init__(self, api_key: str) -> None:
            _ = api_key

        def embed(self, chunks: list[str], model: str) -> list[list[float]]:
            _ = chunks, model
            raise RuntimeError("invalid openai key")

        def summarize(self, text: str, model: str) -> str:
            _ = text, model
            return "unused"

    monkeypatch.setattr("paperbrain.services.setup.connect", fake_connect)
    monkeypatch.setattr("paperbrain.services.setup.OpenAIClient", FailingOpenAIClient)

    with pytest.raises(RuntimeError, match=r"Setup failed during OpenAI validation: invalid openai key"):
        run_setup(
            database_url="postgresql://localhost:5432/paperbrain",
            openai_api_key="sk-test",
            config_path=tmp_path / "paperbrain.conf",
            test_connections=True,
        )


def test_run_init_applies_schema_to_database(monkeypatch: Any) -> None:
    statements = ["SELECT 1;", "SELECT 2;"]
    executed: list[str] = []
    committed: list[bool] = []

    class FakeCursor:
        def __enter__(self) -> "FakeCursor":
            return self

        def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            return None

        def execute(self, sql: str) -> None:
            executed.append(sql)

    class FakeTransaction:
        def __enter__(self) -> "FakeTransaction":
            return self

        def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            if exc_type is None:
                committed.append(True)
            return None

    class FakeConnection:
        def cursor(self) -> FakeCursor:
            return FakeCursor()

        def transaction(self) -> FakeTransaction:
            return FakeTransaction()

    @contextmanager
    def fake_connect(database_url: str, *, autocommit: bool = False) -> Iterator[FakeConnection]:
        assert database_url == "postgresql://localhost:5432/paperbrain"
        assert autocommit is False
        yield FakeConnection()

    monkeypatch.setattr("paperbrain.services.init.schema_statements", lambda force: statements)
    monkeypatch.setattr("paperbrain.services.init.connect", fake_connect)

    count = run_init("postgresql://localhost:5432/paperbrain", force=True)

    assert count == 2
    assert executed == statements
    assert committed == [True]


def test_run_init_rolls_back_and_raises_context_on_failure(monkeypatch: Any) -> None:
    statements = ["SELECT 1;", "SELECT broken;", "SELECT 3;"]
    executed: list[str] = []
    rollback_markers: list[str] = []

    class FakeCursor:
        def __enter__(self) -> "FakeCursor":
            return self

        def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            return None

        def execute(self, sql: str) -> None:
            executed.append(sql)
            if sql == "SELECT broken;":
                raise RuntimeError("boom")

    class FakeTransaction:
        def __enter__(self) -> "FakeTransaction":
            return self

        def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            if exc_type is not None:
                rollback_markers.append("rolled_back")
            return None

    class FakeConnection:
        def cursor(self) -> FakeCursor:
            return FakeCursor()

        def transaction(self) -> FakeTransaction:
            return FakeTransaction()

    @contextmanager
    def fake_connect(database_url: str, *, autocommit: bool = False) -> Iterator[FakeConnection]:
        assert database_url == "postgresql://localhost:5432/paperbrain"
        assert autocommit is False
        yield FakeConnection()

    monkeypatch.setattr("paperbrain.services.init.schema_statements", lambda force: statements)
    monkeypatch.setattr("paperbrain.services.init.connect", fake_connect)

    with pytest.raises(RuntimeError, match=r"Schema apply failed: boom"):
        run_init("postgresql://localhost:5432/paperbrain", force=False)

    assert executed == ["SELECT 1;", "SELECT broken;"]
    assert rollback_markers == ["rolled_back"]
