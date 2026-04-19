from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from paperbrain.cli import app, build_runtime
from paperbrain.config import AppConfig, ConfigStore
from paperbrain.models import SummaryStats
from paperbrain.services.init import run_init
from paperbrain.services.setup import run_setup
from inspect import signature


def test_run_setup_default_config_path_is_home() -> None:
    sig = signature(run_setup)
    param = sig.parameters["config_path"]
    default = param.default
    expected = Path.home() / ".config" / "paperbrain" / "paperbrain.conf"
    assert default == expected


def test_run_setup_writes_project_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config" / "paperbrain.conf"
    message = run_setup(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="sk-test",
        gemini_api_key="gm-test",
        summary_model="openai:gpt-4.1-mini",
        embedding_model="text-embedding-3-small",
        config_path=config_path,
        test_connections=False,
    )

    loaded = ConfigStore(config_path).load()
    assert loaded.database_url == "postgresql://localhost:5432/paperbrain"
    assert loaded.openai_api_key == "sk-test"
    assert loaded.gemini_api_key == "gm-test"
    assert loaded.summary_model == "openai:gpt-4.1-mini"
    assert loaded.embedding_model == "text-embedding-3-small"
    assert loaded.embeddings_enabled is False
    assert loaded.ocr_enabled is False
    assert loaded.pdf_parser == "markitdown"
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
        summary_model="openai:gpt-4.1-mini",
        embedding_model="text-embedding-3-small",
        embeddings_enabled=True,
        config_path=tmp_path / "paperbrain.conf",
        test_connections=True,
    )

    assert calls["db"] == [("postgresql://localhost:5432/paperbrain", False)]
    assert calls["api_key"] == "sk-test"
    assert calls["embed"] == [(["paperbrain connectivity check"], "text-embedding-3-small")]
    assert calls["summarize"] == [("paperbrain connectivity check", "gpt-4.1-mini")]


def test_run_setup_uses_gemini_summary_validation_for_gemini_models(
    monkeypatch: Any, tmp_path: Path
) -> None:
    calls: dict[str, Any] = {"db": [], "openai_embed": [], "gemini_summary": []}

    @contextmanager
    def fake_connect(database_url: str, *, autocommit: bool = False) -> Iterator[object]:
        calls["db"].append((database_url, autocommit))
        yield object()

    class FakeOpenAIClient:
        def __init__(self, api_key: str) -> None:
            calls["openai_api_key"] = api_key

        def embed(self, chunks: list[str], model: str) -> list[list[float]]:
            calls["openai_embed"].append((chunks, model))
            return [[0.1]]

        def summarize(self, text: str, model: str) -> str:
            raise AssertionError("OpenAI summarize must not be used for Gemini summary models")

    class FakeGeminiClient:
        def __init__(self, api_key: str) -> None:
            calls["gemini_api_key"] = api_key

        def summarize(self, text: str, model: str) -> str:
            calls["gemini_summary"].append((text, model))
            return "ok"

    monkeypatch.setattr("paperbrain.services.setup.connect", fake_connect)
    monkeypatch.setattr("paperbrain.services.setup.OpenAIClient", FakeOpenAIClient)
    monkeypatch.setattr("paperbrain.services.setup.GeminiClient", FakeGeminiClient, raising=False)

    run_setup(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="sk-test",
        gemini_api_key="gm-test",
        summary_model="gemini:gemini-2.5-flash",
        embedding_model="text-embedding-3-small",
        embeddings_enabled=True,
        config_path=tmp_path / "paperbrain.conf",
        test_connections=True,
    )

    assert calls["db"] == [("postgresql://localhost:5432/paperbrain", False)]
    assert calls["openai_api_key"] == "sk-test"
    assert calls["openai_embed"] == [(["paperbrain connectivity check"], "text-embedding-3-small")]
    assert calls["gemini_api_key"] == "gm-test"
    assert calls["gemini_summary"] == [("paperbrain connectivity check", "gemini-2.5-flash")]


def test_run_setup_skips_openai_embedding_validation_when_embeddings_disabled(
    monkeypatch: Any, tmp_path: Path
) -> None:
    calls: dict[str, Any] = {"db": [], "gemini_summary": []}

    @contextmanager
    def fake_connect(database_url: str, *, autocommit: bool = False) -> Iterator[object]:
        calls["db"].append((database_url, autocommit))
        yield object()

    class FailingOpenAIClient:
        def __init__(self, api_key: str) -> None:
            raise AssertionError("OpenAI client should not be constructed when embeddings are disabled")

    class FakeGeminiClient:
        def __init__(self, api_key: str) -> None:
            calls["gemini_api_key"] = api_key

        def summarize(self, text: str, model: str) -> str:
            calls["gemini_summary"].append((text, model))
            return "ok"

    monkeypatch.setattr("paperbrain.services.setup.connect", fake_connect)
    monkeypatch.setattr("paperbrain.services.setup.OpenAIClient", FailingOpenAIClient)
    monkeypatch.setattr("paperbrain.services.setup.GeminiClient", FakeGeminiClient, raising=False)

    run_setup(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="",
        gemini_api_key="gm-test",
        summary_model="gemini:gemini-2.5-flash",
        embedding_model="text-embedding-3-small",
        embeddings_enabled=False,
        config_path=tmp_path / "paperbrain.conf",
        test_connections=True,
    )

    assert calls["db"] == [("postgresql://localhost:5432/paperbrain", False)]
    assert calls["gemini_api_key"] == "gm-test"
    assert calls["gemini_summary"] == [("paperbrain connectivity check", "gemini-2.5-flash")]


def test_run_setup_uses_ollama_summary_validation_for_ollama_models(
    monkeypatch: Any, tmp_path: Path
) -> None:
    calls: dict[str, Any] = {"db": [], "openai_embed": [], "ollama_summary": []}

    @contextmanager
    def fake_connect(database_url: str, *, autocommit: bool = False) -> Iterator[object]:
        calls["db"].append((database_url, autocommit))
        yield object()

    class FakeOpenAIClient:
        def __init__(self, api_key: str) -> None:
            calls["openai_api_key"] = api_key

        def embed(self, chunks: list[str], model: str) -> list[list[float]]:
            calls["openai_embed"].append((chunks, model))
            return [[0.1]]

        def summarize(self, text: str, model: str) -> str:
            raise AssertionError("OpenAI summarize must not be used for Ollama summary models")

    class FakeOllamaCloudClient:
        def __init__(self, api_key: str, base_url: str) -> None:
            calls["ollama_client_args"] = (api_key, base_url)

        def summarize(self, text: str, model: str) -> str:
            calls["ollama_summary"].append((text, model))
            return "ok"

    monkeypatch.setattr("paperbrain.services.setup.connect", fake_connect)
    monkeypatch.setattr("paperbrain.services.setup.OpenAIClient", FakeOpenAIClient)
    monkeypatch.setattr(
        "paperbrain.services.setup.OllamaCloudClient",
        FakeOllamaCloudClient,
        raising=False,
    )

    run_setup(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="sk-test",
        ollama_api_key="ol-test",
        ollama_base_url="https://ollama.example",
        summary_model="ollama:llama3.2",
        embedding_model="text-embedding-3-small",
        embeddings_enabled=True,
        config_path=tmp_path / "paperbrain.conf",
        test_connections=True,
    )

    assert calls["db"] == [("postgresql://localhost:5432/paperbrain", False)]
    assert calls["openai_api_key"] == "sk-test"
    assert calls["openai_embed"] == [(["paperbrain connectivity check"], "text-embedding-3-small")]
    assert calls["ollama_client_args"] == ("ol-test", "https://ollama.example")
    assert calls["ollama_summary"] == [("paperbrain connectivity check", "llama3.2")]


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
            "--summary-model", "openai:gpt-4.1-mini",
            "--embedding-model",
            "text-embedding-3-small",
        ],
    )

    assert result.exit_code == 0
    assert "ok" in result.output
    assert calls["database_url"] == "postgresql://localhost:5432/paperbrain"
    assert calls["openai_api_key"] == "sk-test"
    assert calls["summary_model"] == "openai:gpt-4.1-mini"
    assert calls["embedding_model"] == "text-embedding-3-small"
    assert calls["embeddings_enabled"] is False
    assert calls["config_path"] == Path.home() / ".config" / "paperbrain" / "paperbrain.conf"
    assert calls["test_connections"] is True


def test_cli_setup_accepts_gemini_api_key(monkeypatch: Any) -> None:
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
            "--gemini-api-key",
            "gm-test",
            "--summary-model", "gemini:gemini-2.5-flash",
            "--embedding-model",
            "text-embedding-3-small",
        ],
    )

    assert result.exit_code == 0
    assert calls["gemini_api_key"] == "gm-test"


def test_cli_setup_accepts_ollama_options(monkeypatch: Any) -> None:
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
            "--ollama-api-key",
            "ol-test",
            "--ollama-base-url",
            "https://ollama.example",
            "--summary-model",
            "ollama:llama3.2",
            "--embedding-model",
            "text-embedding-3-small",
        ],
    )

    assert result.exit_code == 0
    assert calls["ollama_api_key"] == "ol-test"
    assert calls["ollama_base_url"] == "https://ollama.example"


def test_cli_setup_accepts_embeddings_enabled_flag(monkeypatch: Any) -> None:
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
            "openai:gpt-4.1-mini",
            "--embeddings-enabled",
        ],
    )

    assert result.exit_code == 0
    assert calls["embeddings_enabled"] is True


def test_cli_setup_accepts_ocr_enabled_flag(monkeypatch: Any) -> None:
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
            "openai:gpt-4.1-mini",
            "--ocr-enabled",
        ],
    )

    assert result.exit_code == 0
    assert calls["ocr_enabled"] is True


def test_cli_setup_accepts_pdf_parser_flag(monkeypatch: Any) -> None:
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
            "openai:gpt-4.1-mini",
            "--pdf-parser",
            "docling",
        ],
    )

    assert result.exit_code == 0
    assert calls["pdf_parser"] == "docling"


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


def test_cli_setup_does_not_prompt_when_openai_not_required(monkeypatch: Any) -> None:
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
        [
            "setup",
            "--url",
            "postgresql://localhost:5432/paperbrain",
            "--summary-model",
            "gemini:gemini-2.5-flash",
            "--gemini-api-key",
            "gm-test",
            "--no-embeddings-enabled",
        ],
        env={},
    )

    assert result.exit_code == 0
    assert prompt_calls == []
    assert calls["openai_api_key"] == ""


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
            return [[0.1]]

        def summarize(self, text: str, model: str) -> str:
            _ = text, model
            raise RuntimeError("invalid openai key")

    monkeypatch.setattr("paperbrain.services.setup.connect", fake_connect)
    monkeypatch.setattr("paperbrain.services.setup.OpenAIClient", FailingOpenAIClient)

    with pytest.raises(RuntimeError, match=r"Setup failed during OpenAI validation: invalid openai key"):
        run_setup(
            database_url="postgresql://localhost:5432/paperbrain",
            openai_api_key="sk-test",
            config_path=tmp_path / "paperbrain.conf",
            test_connections=True,
        )


def test_run_setup_gemini_validation_failure_has_context(monkeypatch: Any, tmp_path: Path) -> None:
    @contextmanager
    def fake_connect(database_url: str, *, autocommit: bool = False) -> Iterator[object]:
        _ = database_url, autocommit
        yield object()

    class FakeOpenAIClient:
        def __init__(self, api_key: str) -> None:
            _ = api_key

        def embed(self, chunks: list[str], model: str) -> list[list[float]]:
            _ = chunks, model
            return [[0.1]]

        def summarize(self, text: str, model: str) -> str:
            _ = text, model
            return "ok"

    class FailingGeminiClient:
        def __init__(self, api_key: str) -> None:
            if not api_key.strip():
                raise ValueError("Gemini API key is required when testing connections")

        def summarize(self, text: str, model: str) -> str:
            _ = text, model
            raise AssertionError("Gemini summarize must not be reached when the API key is missing")

    monkeypatch.setattr("paperbrain.services.setup.connect", fake_connect)
    monkeypatch.setattr("paperbrain.services.setup.OpenAIClient", FakeOpenAIClient)
    monkeypatch.setattr("paperbrain.services.setup.GeminiClient", FailingGeminiClient, raising=False)

    with pytest.raises(RuntimeError, match=r"Setup failed during Gemini validation: Gemini API key is required when testing connections"):
        run_setup(
            database_url="postgresql://localhost:5432/paperbrain",
            openai_api_key="sk-test",
            summary_model="gemini:gemini-2.5-flash",
            config_path=tmp_path / "paperbrain.conf",
            test_connections=True,
        )


def test_run_setup_ollama_validation_failure_has_context(monkeypatch: Any, tmp_path: Path) -> None:
    @contextmanager
    def fake_connect(database_url: str, *, autocommit: bool = False) -> Iterator[object]:
        _ = database_url, autocommit
        yield object()

    class FakeOpenAIClient:
        def __init__(self, api_key: str) -> None:
            _ = api_key

        def embed(self, chunks: list[str], model: str) -> list[list[float]]:
            _ = chunks, model
            return [[0.1]]

        def summarize(self, text: str, model: str) -> str:
            _ = text, model
            raise AssertionError("OpenAI summarize must not be used for Ollama summary models")

    class FailingOllamaCloudClient:
        def __init__(self, api_key: str, base_url: str) -> None:
            _ = base_url
            if not api_key.strip():
                raise ValueError("Ollama API key is required when testing connections")

        def summarize(self, text: str, model: str) -> str:
            _ = text, model
            raise AssertionError("Ollama summarize must not be reached when the API key is missing")

    monkeypatch.setattr("paperbrain.services.setup.connect", fake_connect)
    monkeypatch.setattr("paperbrain.services.setup.OpenAIClient", FakeOpenAIClient)
    monkeypatch.setattr(
        "paperbrain.services.setup.OllamaCloudClient",
        FailingOllamaCloudClient,
        raising=False,
    )

    with pytest.raises(RuntimeError, match=r"Setup failed during Ollama validation: Ollama API key is required when testing connections"):
        run_setup(
            database_url="postgresql://localhost:5432/paperbrain",
            openai_api_key="sk-test",
            summary_model="ollama:llama3.2",
            config_path=tmp_path / "paperbrain.conf",
            test_connections=True,
        )


def test_run_setup_rejects_embedding_models_incompatible_with_schema(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="text-embedding-3-small"):
        run_setup(
            database_url="postgresql://localhost:5432/paperbrain",
            openai_api_key="sk-test",
            embedding_model="text-embedding-3-large",
            embeddings_enabled=True,
            config_path=tmp_path / "paperbrain.conf",
            test_connections=False,
        )


def test_run_setup_rejects_unprefixed_summary_model_even_when_not_testing_connections(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Summary model must be prefixed with one of: openai:, gemini:, ollama:"):
        run_setup(
            database_url="postgresql://localhost:5432/paperbrain",
            openai_api_key="sk-test",
            summary_model="gpt-4.1-mini",
            embedding_model="text-embedding-3-small",
            config_path=tmp_path / "paperbrain.conf",
            test_connections=False,
        )


def test_build_runtime_rejects_unprefixed_summary_model(monkeypatch: Any, tmp_path: Path) -> None:
    config = AppConfig(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="sk-runtime",
        summary_model="gpt-4.1-mini",
        embedding_model="text-embedding-3-small",
    )
    config_path = tmp_path / "config" / "paperbrain.conf"

    class FakeConfigStore:
        def __init__(self, path: Path) -> None:
            assert path == config_path

        def load(self) -> AppConfig:
            return config

    monkeypatch.setattr("paperbrain.cli.ConfigStore", FakeConfigStore)
    monkeypatch.setattr("paperbrain.summary_provider.ConfigStore", FakeConfigStore)

    with pytest.raises(ValueError, match="Summary model must be prefixed with one of: openai:, gemini:, ollama:"):
        build_runtime(config_path)


def test_build_runtime_rejects_unknown_summary_provider_prefix(monkeypatch: Any, tmp_path: Path) -> None:
    config = AppConfig(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="sk-runtime",
        summary_model="anthropic:claude-3-7-sonnet",
        embedding_model="text-embedding-3-small",
    )
    config_path = tmp_path / "config" / "paperbrain.conf"

    class FakeConfigStore:
        def __init__(self, path: Path) -> None:
            assert path == config_path

        def load(self) -> AppConfig:
            return config

    monkeypatch.setattr("paperbrain.cli.ConfigStore", FakeConfigStore)
    monkeypatch.setattr("paperbrain.summary_provider.ConfigStore", FakeConfigStore)

    with pytest.raises(ValueError, match="Unknown summary provider prefix"):
        build_runtime(config_path)


def test_build_runtime_requires_gemini_key_for_gemini_summary_model(
    monkeypatch: Any, tmp_path: Path
) -> None:
    config = AppConfig(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="sk-runtime",
        gemini_api_key="",
        summary_model="gemini:gemini-2.5-flash",
        embedding_model="text-embedding-3-small",
    )
    config_path = tmp_path / "config" / "paperbrain.conf"

    class FakeConfigStore:
        def __init__(self, path: Path) -> None:
            assert path == config_path

        def load(self) -> AppConfig:
            return config

    monkeypatch.setattr("paperbrain.cli.ConfigStore", FakeConfigStore)
    monkeypatch.setattr("paperbrain.summary_provider.ConfigStore", FakeConfigStore)

    with pytest.raises(ValueError, match="Gemini API key is required for Gemini summary models"):
        build_runtime(config_path)


def test_build_runtime_allows_missing_openai_key_for_gemini_summary_model_when_embeddings_disabled(
    monkeypatch: Any, tmp_path: Path
) -> None:
    config = AppConfig(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="",
        gemini_api_key="gm-runtime",
        summary_model="gemini:gemini-2.5-flash",
        embedding_model="text-embedding-3-small",
    )
    config_path = tmp_path / "config" / "paperbrain.conf"

    class FakeConfigStore:
        def __init__(self, path: Path) -> None:
            assert path == config_path

        def load(self) -> AppConfig:
            return config

    class FakeGeminiClient:
        def __init__(self, api_key: str) -> None:
            _ = api_key

    monkeypatch.setattr("paperbrain.cli.ConfigStore", FakeConfigStore)
    monkeypatch.setattr("paperbrain.summary_provider.ConfigStore", FakeConfigStore)
    monkeypatch.setattr("paperbrain.summary_provider.GeminiClient", FakeGeminiClient, raising=False)

    runtime = build_runtime(config_path)
    assert runtime.llm is not None
    assert runtime.embeddings is None


def test_build_runtime_requires_openai_key_for_gemini_summary_model_when_embeddings_enabled(
    monkeypatch: Any, tmp_path: Path
) -> None:
    config = AppConfig(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="",
        gemini_api_key="gm-runtime",
        summary_model="gemini:gemini-2.5-flash",
        embedding_model="text-embedding-3-small",
        embeddings_enabled=True,
    )
    config_path = tmp_path / "config" / "paperbrain.conf"

    class FakeConfigStore:
        def __init__(self, path: Path) -> None:
            assert path == config_path

        def load(self) -> AppConfig:
            return config

    monkeypatch.setattr("paperbrain.cli.ConfigStore", FakeConfigStore)
    monkeypatch.setattr("paperbrain.summary_provider.ConfigStore", FakeConfigStore)

    with pytest.raises(ValueError, match="OpenAI API key is required for embeddings"):
        build_runtime(config_path)


def test_build_runtime_requires_openai_key_for_openai_summary_model(
    monkeypatch: Any, tmp_path: Path
) -> None:
    config = AppConfig(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="",
        summary_model="openai:gpt-4.1-mini",
        embedding_model="text-embedding-3-small",
    )
    config_path = tmp_path / "config" / "paperbrain.conf"

    class FakeConfigStore:
        def __init__(self, path: Path) -> None:
            assert path == config_path

        def load(self) -> AppConfig:
            return config

    monkeypatch.setattr("paperbrain.cli.ConfigStore", FakeConfigStore)
    monkeypatch.setattr("paperbrain.summary_provider.ConfigStore", FakeConfigStore)

    with pytest.raises(ValueError, match="OpenAI API key is required for OpenAI summary models"):
        build_runtime(config_path)


def test_build_runtime_requires_ollama_key_for_ollama_summary_model(
    monkeypatch: Any, tmp_path: Path
) -> None:
    config = AppConfig(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="sk-runtime",
        ollama_api_key="",
        summary_model="ollama:llama3.1:8b",
        embedding_model="text-embedding-3-small",
    )
    config_path = tmp_path / "config" / "paperbrain.conf"

    class FakeConfigStore:
        def __init__(self, path: Path) -> None:
            assert path == config_path

        def load(self) -> AppConfig:
            return config

    monkeypatch.setattr("paperbrain.cli.ConfigStore", FakeConfigStore)
    monkeypatch.setattr("paperbrain.summary_provider.ConfigStore", FakeConfigStore)

    with pytest.raises(ValueError, match="Ollama API key is required for Ollama summary models"):
        build_runtime(config_path)


def test_build_runtime_requires_ollama_base_url_for_ollama_summary_model(
    monkeypatch: Any, tmp_path: Path
) -> None:
    config = AppConfig(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="sk-runtime",
        ollama_api_key="ol-runtime",
        ollama_base_url=" \t ",
        summary_model="ollama:llama3.1:8b",
        embedding_model="text-embedding-3-small",
    )
    config_path = tmp_path / "config" / "paperbrain.conf"

    class FakeConfigStore:
        def __init__(self, path: Path) -> None:
            assert path == config_path

        def load(self) -> AppConfig:
            return config

    class FakeOpenAIClient:
        def __init__(self, api_key: str) -> None:
            _ = api_key

    class FakeOllamaCloudClient:
        def __init__(self, api_key: str, base_url: str) -> None:
            _ = api_key, base_url

    monkeypatch.setattr("paperbrain.cli.ConfigStore", FakeConfigStore)
    monkeypatch.setattr("paperbrain.summary_provider.ConfigStore", FakeConfigStore)
    monkeypatch.setattr("paperbrain.summary_provider.OpenAIClient", FakeOpenAIClient)
    monkeypatch.setattr("paperbrain.summary_provider.OllamaCloudClient", FakeOllamaCloudClient, raising=False)

    with pytest.raises(ValueError, match="Ollama base URL is required for Ollama summary models"):
        build_runtime(config_path)


def test_build_runtime_rejects_empty_ollama_summary_model_suffix(
    monkeypatch: Any, tmp_path: Path
) -> None:
    config = AppConfig(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="sk-runtime",
        ollama_api_key="ol-runtime",
        summary_model="ollama:",
        embedding_model="text-embedding-3-small",
    )
    config_path = tmp_path / "config" / "paperbrain.conf"

    class FakeConfigStore:
        def __init__(self, path: Path) -> None:
            assert path == config_path

        def load(self) -> AppConfig:
            return config

    class FakeOpenAIClient:
        def __init__(self, api_key: str) -> None:
            _ = api_key

    class FakeOllamaCloudClient:
        def __init__(self, api_key: str, base_url: str) -> None:
            _ = api_key
            _ = base_url

    monkeypatch.setattr("paperbrain.cli.ConfigStore", FakeConfigStore)
    monkeypatch.setattr("paperbrain.summary_provider.ConfigStore", FakeConfigStore)
    monkeypatch.setattr("paperbrain.summary_provider.OpenAIClient", FakeOpenAIClient)
    monkeypatch.setattr("paperbrain.summary_provider.OllamaCloudClient", FakeOllamaCloudClient, raising=False)

    with pytest.raises(
        ValueError, match="Ollama summary model must include a model name after 'ollama:'"
    ):
        build_runtime(config_path)


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


def test_run_init_surfaces_extension_permission_hint(monkeypatch: Any) -> None:
    statements = ["CREATE EXTENSION IF NOT EXISTS vector;"]

    class FakeCursor:
        def __enter__(self) -> "FakeCursor":
            return self

        def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            return None

        def execute(self, sql: str) -> None:
            _ = sql
            raise RuntimeError('permission denied to create extension "vector"')

    class FakeTransaction:
        def __enter__(self) -> "FakeTransaction":
            return self

        def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
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

    with pytest.raises(
        RuntimeError,
        match=r"Schema apply failed: permission denied to create extension \"vector\".*CREATE EXTENSION privileges.*preinstalled",
    ):
        run_init("postgresql://localhost:5432/paperbrain", force=False)


def test_run_init_surfaces_pg_trgm_permission_hint(monkeypatch: Any) -> None:
    statements = ["CREATE EXTENSION IF NOT EXISTS pg_trgm;"]

    class FakeCursor:
        def __enter__(self) -> "FakeCursor":
            return self

        def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            return None

        def execute(self, sql: str) -> None:
            _ = sql
            raise RuntimeError('permission denied to create extension "pg_trgm"')

    class FakeTransaction:
        def __enter__(self) -> "FakeTransaction":
            return self

        def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
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

    with pytest.raises(
        RuntimeError,
        match=r"Schema apply failed: permission denied to create extension \"pg_trgm\".*CREATE EXTENSION privileges.*preinstalled extensions \(vector/pg_trgm\)",
    ):
        run_init("postgresql://localhost:5432/paperbrain", force=False)


def test_cli_ingest_uses_runtime_config_and_real_wiring(monkeypatch: Any, tmp_path: Path) -> None:
    calls: dict[str, Any] = {}
    config = AppConfig(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="sk-runtime",
        summary_model="openai:gpt-4.1-mini",
        embedding_model="text-embedding-3-small",
        embeddings_enabled=True,
    )
    config_path = tmp_path / "config" / "paperbrain.conf"
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_text("fake", encoding="utf-8")

    class FakeConfigStore:
        def __init__(self, path: Path) -> None:
            calls["config_path"] = path

        def load(self) -> AppConfig:
            return config

    class FakeOpenAIClient:
        def __init__(self, api_key: str) -> None:
            calls["api_key"] = api_key

    class FakeEmbeddingAdapter:
        def __init__(self, *, client: Any, model: str) -> None:
            calls["embedding_model"] = model
            calls["embedding_client_seen"] = isinstance(client, FakeOpenAIClient)

    class FakeParser:
        def __init__(self, *, ocr_enabled: bool = False) -> None:
            _ = ocr_enabled

    class FakeParserParseWorker:
        def __init__(self, *, parser_name: str, ocr_enabled: bool = False) -> None:
            calls["worker_args"] = (parser_name, ocr_enabled)

    class FakeIngestService:
        def __init__(
            self,
            *,
            repo: Any,
            parser: Any,
            embeddings: Any,
            parse_worker_factory: Any = None,
        ) -> None:
            calls["repo"] = repo
            calls["parser_seen"] = isinstance(parser, FakeParser)
            calls["embeddings_seen"] = isinstance(embeddings, FakeEmbeddingAdapter)
            calls["parse_worker_factory"] = parse_worker_factory

        def ingest_paths(
            self,
            paths: list[str],
            force_all: bool,
            recursive: bool = False,
            *,
            start_offset: int = 0,
            max_files: int | None = None,
            parse_worker_recycle_every: int = 25,
        ) -> int:
            calls["ingest_args"] = (
                paths,
                force_all,
                recursive,
                start_offset,
                max_files,
                parse_worker_recycle_every,
            )
            return 2

    @contextmanager
    def fake_connect(database_url: str, *, autocommit: bool = False) -> Iterator[str]:
        calls["connect"] = (database_url, autocommit)
        yield "fake-connection"

    fake_repo = object()

    monkeypatch.setattr("paperbrain.cli.ConfigStore", FakeConfigStore)
    monkeypatch.setattr("paperbrain.summary_provider.ConfigStore", FakeConfigStore)
    monkeypatch.setattr("paperbrain.summary_provider.OpenAIClient", FakeOpenAIClient)
    monkeypatch.setattr("paperbrain.summary_provider.OpenAIEmbeddingAdapter", FakeEmbeddingAdapter)
    monkeypatch.setattr(
        "paperbrain.summary_provider.build_pdf_parser",
        lambda pdf_parser, *, ocr_enabled: FakeParser(),
    )
    monkeypatch.setattr("paperbrain.cli.ParserParseWorker", FakeParserParseWorker)
    monkeypatch.setattr("paperbrain.cli.IngestService", FakeIngestService)
    monkeypatch.setattr("paperbrain.cli.connect", fake_connect)
    monkeypatch.setattr("paperbrain.cli.PostgresRepo", lambda connection: fake_repo if connection == "fake-connection" else None)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "ingest",
            str(pdf_path),
            "--recursive",
            "--start-offset",
            "3",
            "--max-files",
            "10",
            "--parse-worker-recycle-every",
            "7",
            "--config-path",
            str(config_path),
        ],
    )

    assert result.exit_code == 0
    assert "Ingested 2 paper(s)." in result.output
    assert calls["config_path"] == config_path
    assert calls["api_key"] == "sk-runtime"
    assert calls["embedding_model"] == "text-embedding-3-small"
    assert calls["embedding_client_seen"] is True
    assert calls["connect"] == ("postgresql://localhost:5432/paperbrain", False)
    assert calls["repo"] is fake_repo
    assert calls["parser_seen"] is True
    assert calls["embeddings_seen"] is True
    assert calls["parse_worker_factory"] is not None
    calls["parse_worker_factory"]()
    assert calls["worker_args"] == ("marker", False)
    assert calls["ingest_args"] == ([str(pdf_path)], False, True, 3, 10, 7)


def test_cli_ingest_uses_docling_parse_worker_for_docling_parser(monkeypatch: Any, tmp_path: Path) -> None:
    calls: dict[str, Any] = {}
    config = AppConfig(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="sk-runtime",
        summary_model="openai:gpt-4.1-mini",
        embedding_model="text-embedding-3-small",
        embeddings_enabled=True,
        ocr_enabled=True,
        pdf_parser="docling",
    )
    config_path = tmp_path / "config" / "paperbrain.conf"
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_text("fake", encoding="utf-8")

    class FakeConfigStore:
        def __init__(self, path: Path) -> None:
            calls["config_path"] = path

        def load(self) -> AppConfig:
            return config

    class FakeOpenAIClient:
        def __init__(self, api_key: str) -> None:
            _ = api_key

    class FakeEmbeddingAdapter:
        def __init__(self, *, client: Any, model: str) -> None:
            _ = (client, model)

    class FakeDoclingParser:
        def __init__(self, *, ocr_enabled: bool = False) -> None:
            _ = ocr_enabled

    class FakeParserParseWorker:
        def __init__(self, *, parser_name: str, ocr_enabled: bool = False) -> None:
            calls["worker_args"] = (parser_name, ocr_enabled)

    class FakeIngestService:
        def __init__(
            self,
            *,
            repo: Any,
            parser: Any,
            embeddings: Any,
            parse_worker_factory: Any = None,
        ) -> None:
            _ = (repo, parser, embeddings)
            calls["parse_worker_factory"] = parse_worker_factory

        def ingest_paths(
            self,
            paths: list[str],
            force_all: bool,
            recursive: bool = False,
            *,
            start_offset: int = 0,
            max_files: int | None = None,
            parse_worker_recycle_every: int = 25,
        ) -> int:
            _ = (paths, force_all, recursive, start_offset, max_files)
            calls["parse_worker_recycle_every"] = parse_worker_recycle_every
            return 1

    @contextmanager
    def fake_connect(database_url: str, *, autocommit: bool = False) -> Iterator[str]:
        _ = (database_url, autocommit)
        yield "fake-connection"

    monkeypatch.setattr("paperbrain.cli.ConfigStore", FakeConfigStore)
    monkeypatch.setattr("paperbrain.summary_provider.ConfigStore", FakeConfigStore)
    monkeypatch.setattr("paperbrain.summary_provider.OpenAIClient", FakeOpenAIClient)
    monkeypatch.setattr("paperbrain.summary_provider.OpenAIEmbeddingAdapter", FakeEmbeddingAdapter)
    monkeypatch.setattr(
        "paperbrain.summary_provider.build_pdf_parser",
        lambda pdf_parser, *, ocr_enabled: FakeDoclingParser(ocr_enabled=ocr_enabled),
    )
    monkeypatch.setattr("paperbrain.cli.ParserParseWorker", FakeParserParseWorker)
    monkeypatch.setattr("paperbrain.cli.IngestService", FakeIngestService)
    monkeypatch.setattr("paperbrain.cli.connect", fake_connect)
    monkeypatch.setattr("paperbrain.cli.PostgresRepo", lambda connection: connection)

    runner = CliRunner()
    result = runner.invoke(app, ["ingest", str(pdf_path), "--config-path", str(config_path)])

    assert result.exit_code == 0
    assert calls["parse_worker_factory"] is not None
    worker = calls["parse_worker_factory"]()
    assert isinstance(worker, FakeParserParseWorker)
    assert calls["worker_args"] == ("docling", True)
    assert calls["parse_worker_recycle_every"] == 5


def test_cli_search_uses_runtime_config_and_outputs_results(monkeypatch: Any, tmp_path: Path) -> None:
    calls: dict[str, Any] = {}
    config_path = tmp_path / "config" / "paperbrain.conf"
    config = AppConfig(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="sk-runtime",
        summary_model="openai:gpt-4.1-mini",
        embedding_model="text-embedding-3-small",
        embeddings_enabled=True,
    )

    class FakeConfigStore:
        def __init__(self, path: Path) -> None:
            calls["config_path"] = path

        def load(self) -> AppConfig:
            return config

    class FakeOpenAIClient:
        def __init__(self, api_key: str) -> None:
            calls["api_key"] = api_key

    class FakeEmbeddingAdapter:
        def __init__(self, *, client: Any, model: str) -> None:
            calls["embedding_model"] = model
            calls["embedding_client_seen"] = isinstance(client, FakeOpenAIClient)

    class FakeSearchService:
        def __init__(self, *, repo: Any, embedder: Any | None = None) -> None:
            calls["repo"] = repo
            calls["embedder_seen"] = isinstance(embedder, FakeEmbeddingAdapter)

        def search(self, query: str, top_k: int = 10, include_cards: bool = False) -> list[dict]:
            calls["search_args"] = (query, top_k, include_cards)
            return [{"paper_slug": "papers/a", "score": 0.56}]

    @contextmanager
    def fake_connect(database_url: str, *, autocommit: bool = False) -> Iterator[str]:
        calls["connect"] = (database_url, autocommit)
        yield "fake-connection"

    fake_repo = object()

    monkeypatch.setattr("paperbrain.cli.ConfigStore", FakeConfigStore)
    monkeypatch.setattr("paperbrain.summary_provider.ConfigStore", FakeConfigStore)
    monkeypatch.setattr("paperbrain.summary_provider.OpenAIClient", FakeOpenAIClient)
    monkeypatch.setattr("paperbrain.summary_provider.OpenAIEmbeddingAdapter", FakeEmbeddingAdapter)
    monkeypatch.setattr("paperbrain.cli.SearchService", FakeSearchService)
    monkeypatch.setattr("paperbrain.cli.connect", fake_connect)
    monkeypatch.setattr("paperbrain.cli.PostgresRepo", lambda connection: fake_repo if connection == "fake-connection" else None)

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["search", "p53", "--top-k", "3", "--include-cards", "--config-path", str(config_path)],
    )

    assert result.exit_code == 0
    assert '"paper_slug": "papers/a"' in result.output
    assert '"score": 0.56' in result.output
    assert calls["config_path"] == config_path
    assert calls["api_key"] == "sk-runtime"
    assert calls["embedding_model"] == "text-embedding-3-small"
    assert calls["embedding_client_seen"] is True
    assert calls["connect"] == ("postgresql://localhost:5432/paperbrain", False)
    assert calls["repo"] is fake_repo
    assert calls["embedder_seen"] is True
    assert calls["search_args"] == ("p53", 3, True)


def test_cli_summarize_uses_runtime_config_and_reports_counts(monkeypatch: Any, tmp_path: Path) -> None:
    calls: dict[str, Any] = {}
    config_path = tmp_path / "config" / "paperbrain.conf"
    config = AppConfig(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="sk-runtime",
        summary_model="openai:gpt-4.1-mini",
        embedding_model="text-embedding-3-small",
    )

    class FakeConfigStore:
        def __init__(self, path: Path) -> None:
            calls["config_path"] = path

        def load(self) -> AppConfig:
            return config

    class FakeOpenAIClient:
        def __init__(self, api_key: str) -> None:
            calls["api_key"] = api_key

    class FakeSummaryAdapter:
        def __init__(self, *, client: Any, model: str) -> None:
            calls["summary_model"] = model
            calls["summary_client_seen"] = isinstance(client, FakeOpenAIClient)

    class FakeSummarizeService:
        def __init__(self, *, repo: Any, llm: Any) -> None:
            calls["repo"] = repo
            calls["llm_seen"] = isinstance(llm, FakeSummaryAdapter)

        def run(self, *, card_scope: str | None) -> SummaryStats:
            calls["run_card_scope"] = card_scope
            return SummaryStats(paper_cards=3, person_cards=2, topic_cards=1)

    @contextmanager
    def fake_connect(database_url: str, *, autocommit: bool = False) -> Iterator[str]:
        calls["connect"] = (database_url, autocommit)
        yield "fake-connection"

    fake_repo = object()

    monkeypatch.setattr("paperbrain.cli.ConfigStore", FakeConfigStore)
    monkeypatch.setattr("paperbrain.summary_provider.ConfigStore", FakeConfigStore)
    monkeypatch.setattr("paperbrain.summary_provider.OpenAIClient", FakeOpenAIClient)
    monkeypatch.setattr("paperbrain.summary_provider.OpenAISummaryAdapter", FakeSummaryAdapter)
    monkeypatch.setattr("paperbrain.cli.SummarizeService", FakeSummarizeService)
    monkeypatch.setattr("paperbrain.cli.connect", fake_connect)
    monkeypatch.setattr("paperbrain.cli.PostgresRepo", lambda connection: fake_repo if connection == "fake-connection" else None)

    runner = CliRunner()
    result = runner.invoke(app, ["summarize", "--config-path", str(config_path)])

    assert result.exit_code == 0
    assert "Summarized cards: papers=3 people=2 topics=1" in result.output
    assert calls["config_path"] == config_path
    assert calls["api_key"] == "sk-runtime"
    assert calls["summary_model"] == "gpt-4.1-mini"
    assert calls["summary_client_seen"] is True
    assert calls["connect"] == ("postgresql://localhost:5432/paperbrain", False)
    assert calls["repo"] is fake_repo
    assert calls["llm_seen"] is True
    assert calls["run_card_scope"] is None


def test_cli_summarize_rejects_invalid_card_scope() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["summarize", "--card-scope", "invalid"])

    assert result.exit_code == 2
    assert isinstance(result.exception, SystemExit)
    assert result.exception.code == 2
    assert "Invalid value for '--card-scope'" in result.output
    assert "Allowed values: all, paper, person, topic" in result.output


def test_cli_summarize_rejects_legacy_force_all_flag() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["summarize", "--force-all"])

    assert result.exit_code != 0
    assert "No such option: --force-all" in result.output


def test_cli_summarize_routes_gemini_models_through_gemini_summary_adapter(
    monkeypatch: Any, tmp_path: Path
) -> None:
    calls: dict[str, Any] = {}
    config_path = tmp_path / "config" / "paperbrain.conf"
    config = AppConfig(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="sk-runtime",
        gemini_api_key="gm-runtime",
        summary_model="gemini:gemini-2.5-flash",
        embedding_model="text-embedding-3-small",
        embeddings_enabled=True,
    )

    class FakeConfigStore:
        def __init__(self, path: Path) -> None:
            calls["config_path"] = path

        def load(self) -> AppConfig:
            return config

    class FakeOpenAIClient:
        def __init__(self, api_key: str) -> None:
            calls["openai_api_key"] = api_key

    class FakeEmbeddingAdapter:
        def __init__(self, *, client: Any, model: str) -> None:
            calls["embedding_model"] = model
            calls["embedding_client_seen"] = isinstance(client, FakeOpenAIClient)

    class FakeGeminiClient:
        def __init__(self, api_key: str) -> None:
            calls["gemini_api_key"] = api_key

    class FakeGeminiSummaryAdapter:
        def __init__(self, *, client: Any, model: str) -> None:
            calls["summary_model"] = model
            calls["summary_client_seen"] = isinstance(client, FakeGeminiClient)

    class FakeSummarizeService:
        def __init__(self, *, repo: Any, llm: Any) -> None:
            calls["repo"] = repo
            calls["llm_seen"] = isinstance(llm, FakeGeminiSummaryAdapter)

        def run(self, *, card_scope: str | None) -> SummaryStats:
            calls["run_card_scope"] = card_scope
            return SummaryStats(paper_cards=3, person_cards=2, topic_cards=1)

    @contextmanager
    def fake_connect(database_url: str, *, autocommit: bool = False) -> Iterator[str]:
        calls["connect"] = (database_url, autocommit)
        yield "fake-connection"

    fake_repo = object()

    def fail_openai_summary_adapter(**kwargs: Any) -> None:
        _ = kwargs
        pytest.fail("OpenAI summary adapter must not be used for Gemini models")

    monkeypatch.setattr("paperbrain.cli.ConfigStore", FakeConfigStore)
    monkeypatch.setattr("paperbrain.summary_provider.ConfigStore", FakeConfigStore)
    monkeypatch.setattr("paperbrain.summary_provider.OpenAIClient", FakeOpenAIClient)
    monkeypatch.setattr("paperbrain.summary_provider.OpenAIEmbeddingAdapter", FakeEmbeddingAdapter)
    monkeypatch.setattr("paperbrain.summary_provider.GeminiClient", FakeGeminiClient, raising=False)
    monkeypatch.setattr("paperbrain.summary_provider.GeminiSummaryAdapter", FakeGeminiSummaryAdapter, raising=False)
    monkeypatch.setattr("paperbrain.summary_provider.OpenAISummaryAdapter", fail_openai_summary_adapter)
    monkeypatch.setattr("paperbrain.cli.SummarizeService", FakeSummarizeService)
    monkeypatch.setattr("paperbrain.cli.connect", fake_connect)
    monkeypatch.setattr("paperbrain.cli.PostgresRepo", lambda connection: fake_repo if connection == "fake-connection" else None)

    runner = CliRunner()
    result = runner.invoke(app, ["summarize", "--card-scope", "all", "--config-path", str(config_path)])

    assert result.exit_code == 0
    assert "Summarized cards: papers=3 people=2 topics=1" in result.output
    assert calls["config_path"] == config_path
    assert calls["openai_api_key"] == "sk-runtime"
    assert calls["embedding_model"] == "text-embedding-3-small"
    assert calls["embedding_client_seen"] is True
    assert calls["gemini_api_key"] == "gm-runtime"
    assert calls["summary_model"] == "gemini-2.5-flash"
    assert calls["summary_client_seen"] is True
    assert calls["connect"] == ("postgresql://localhost:5432/paperbrain", False)
    assert calls["repo"] is fake_repo
    assert calls["llm_seen"] is True
    assert calls["run_card_scope"] == "all"


def test_cli_summarize_routes_ollama_models_through_ollama_summary_adapter(
    monkeypatch: Any, tmp_path: Path
) -> None:
    calls: dict[str, Any] = {}
    config_path = tmp_path / "config" / "paperbrain.conf"
    config = AppConfig(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="sk-runtime",
        ollama_api_key="ol-runtime",
        ollama_base_url="https://ollama.example",
        summary_model="ollama:llama3.1:8b",
        embedding_model="text-embedding-3-small",
        embeddings_enabled=True,
    )

    class FakeConfigStore:
        def __init__(self, path: Path) -> None:
            calls["config_path"] = path

        def load(self) -> AppConfig:
            return config

    class FakeOpenAIClient:
        def __init__(self, api_key: str) -> None:
            calls["openai_api_key"] = api_key

    class FakeEmbeddingAdapter:
        def __init__(self, *, client: Any, model: str) -> None:
            calls["embedding_model"] = model
            calls["embedding_client_seen"] = isinstance(client, FakeOpenAIClient)

    class FakeOllamaCloudClient:
        def __init__(self, api_key: str, base_url: str) -> None:
            calls["ollama_client_args"] = (api_key, base_url)

    class FakeOllamaSummaryAdapter:
        def __init__(self, *, client: Any, model: str) -> None:
            calls["summary_model"] = model
            calls["summary_client_seen"] = isinstance(client, FakeOllamaCloudClient)

    class FakeSummarizeService:
        def __init__(self, *, repo: Any, llm: Any) -> None:
            calls["repo"] = repo
            calls["llm_seen"] = isinstance(llm, FakeOllamaSummaryAdapter)

        def run(self, *, card_scope: str | None) -> SummaryStats:
            calls["run_card_scope"] = card_scope
            return SummaryStats(paper_cards=3, person_cards=2, topic_cards=1)

    @contextmanager
    def fake_connect(database_url: str, *, autocommit: bool = False) -> Iterator[str]:
        calls["connect"] = (database_url, autocommit)
        yield "fake-connection"

    fake_repo = object()

    def fail_openai_summary_adapter(**kwargs: Any) -> None:
        _ = kwargs
        pytest.fail("OpenAI summary adapter must not be used for Ollama models")

    monkeypatch.setattr("paperbrain.cli.ConfigStore", FakeConfigStore)
    monkeypatch.setattr("paperbrain.summary_provider.ConfigStore", FakeConfigStore)
    monkeypatch.setattr("paperbrain.summary_provider.OpenAIClient", FakeOpenAIClient)
    monkeypatch.setattr("paperbrain.summary_provider.OpenAIEmbeddingAdapter", FakeEmbeddingAdapter)
    monkeypatch.setattr("paperbrain.summary_provider.OllamaCloudClient", FakeOllamaCloudClient, raising=False)
    monkeypatch.setattr("paperbrain.summary_provider.OllamaSummaryAdapter", FakeOllamaSummaryAdapter, raising=False)
    monkeypatch.setattr("paperbrain.summary_provider.OpenAISummaryAdapter", fail_openai_summary_adapter)
    monkeypatch.setattr("paperbrain.cli.SummarizeService", FakeSummarizeService)
    monkeypatch.setattr("paperbrain.cli.connect", fake_connect)
    monkeypatch.setattr("paperbrain.cli.PostgresRepo", lambda connection: fake_repo if connection == "fake-connection" else None)

    runner = CliRunner()
    result = runner.invoke(app, ["summarize", "--card-scope", "all", "--config-path", str(config_path)])

    assert result.exit_code == 0
    assert "Summarized cards: papers=3 people=2 topics=1" in result.output
    assert calls["config_path"] == config_path
    assert calls["openai_api_key"] == "sk-runtime"
    assert calls["embedding_model"] == "text-embedding-3-small"
    assert calls["embedding_client_seen"] is True
    assert calls["ollama_client_args"] == ("ol-runtime", "https://ollama.example")
    assert calls["summary_model"] == "llama3.1:8b"
    assert calls["summary_client_seen"] is True
    assert calls["connect"] == ("postgresql://localhost:5432/paperbrain", False)
    assert calls["repo"] is fake_repo
    assert calls["llm_seen"] is True
    assert calls["run_card_scope"] == "all"

def test_runtime_prefixed_provider_positive_paths(monkeypatch: Any, tmp_path: Path) -> None:
    # openai positive path
    config_openai = AppConfig(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="sk-runtime",
        summary_model="openai:gpt-4.1-mini",
        embedding_model="text-embedding-3-small",
        embeddings_enabled=True,
    )
    config_path_openai = tmp_path / "config" / "paperbrain_openai.conf"

    class FakeConfigStoreOpenAI:
        def __init__(self, path: Path) -> None:
            assert path == config_path_openai

        def load(self) -> AppConfig:
            return config_openai

    class FakeOpenAIClient:
        def __init__(self, api_key: str) -> None:
            _ = api_key

        def embed(self, chunks: list[str], model: str) -> list[list[float]]:
            return [[0.1]]

        def summarize(self, text: str, model: str) -> str:
            return "ok"

    class FakeOpenAIEmbeddingAdapter:
        def __init__(self, client, model):
            _ = client, model

    monkeypatch.setattr("paperbrain.summary_provider.ConfigStore", FakeConfigStoreOpenAI)
    monkeypatch.setattr("paperbrain.summary_provider.OpenAIClient", FakeOpenAIClient)
    monkeypatch.setattr("paperbrain.summary_provider.OpenAIEmbeddingAdapter", FakeOpenAIEmbeddingAdapter)

    rt = build_runtime(config_path_openai)
    assert rt.llm is not None
    assert rt.embeddings is not None

    # gemini positive path
    config_gemini = AppConfig(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="sk-runtime",
        gemini_api_key="gm-runtime",
        summary_model="gemini:gemini-2.5-flash",
        embedding_model="text-embedding-3-small",
        embeddings_enabled=True,
    )
    config_path_gemini = tmp_path / "config" / "paperbrain_gemini.conf"

    class FakeConfigStoreGemini:
        def __init__(self, path: Path) -> None:
            assert path == config_path_gemini

        def load(self) -> AppConfig:
            return config_gemini

    class FakeGeminiClient:
        def __init__(self, api_key: str) -> None:
            _ = api_key

        def summarize(self, text: str, model: str) -> str:
            return "ok"

    monkeypatch.setattr("paperbrain.summary_provider.ConfigStore", FakeConfigStoreGemini)
    monkeypatch.setattr("paperbrain.summary_provider.GeminiClient", FakeGeminiClient)
    monkeypatch.setattr("paperbrain.summary_provider.OpenAIClient", FakeOpenAIClient)
    monkeypatch.setattr("paperbrain.summary_provider.OpenAIEmbeddingAdapter", FakeOpenAIEmbeddingAdapter)

    rt = build_runtime(config_path_gemini)
    assert rt.llm is not None

    # ollama positive path
    config_ollama = AppConfig(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="sk-runtime",
        ollama_api_key="ol-runtime",
        ollama_base_url="https://ollama.example",
        summary_model="ollama:llama3.2",
        embedding_model="text-embedding-3-small",
        embeddings_enabled=True,
    )
    config_path_ollama = tmp_path / "config" / "paperbrain_ollama.conf"

    class FakeConfigStoreOllama:
        def __init__(self, path: Path) -> None:
            assert path == config_path_ollama

        def load(self) -> AppConfig:
            return config_ollama

    class FakeOllamaCloudClient:
        def __init__(self, api_key: str, base_url: str) -> None:
            _ = api_key, base_url

        def summarize(self, text: str, model: str) -> str:
            return "ok"

    monkeypatch.setattr("paperbrain.summary_provider.ConfigStore", FakeConfigStoreOllama)
    monkeypatch.setattr("paperbrain.summary_provider.OllamaCloudClient", FakeOllamaCloudClient)
    monkeypatch.setattr("paperbrain.summary_provider.OpenAIClient", FakeOpenAIClient)
    monkeypatch.setattr("paperbrain.summary_provider.OpenAIEmbeddingAdapter", FakeOpenAIEmbeddingAdapter)

    rt = build_runtime(config_path_ollama)
    assert rt.llm is not None
