from pathlib import Path
from types import SimpleNamespace
from typing import Any

from typer.testing import CliRunner

from paperbrain import cli
from paperbrain.cli import app


def _make_fake_uvicorn_run(calls: list[dict[str, Any]]) -> Any:
    def fake_run(app_factory: Any, **kwargs: Any) -> None:
        calls.append({"app_factory": app_factory, **kwargs})

    return fake_run


def test_cli_web_uses_default_host_port_reload_and_prints_url(monkeypatch: Any) -> None:
    calls: list[dict[str, Any]] = []

    monkeypatch.setattr(cli, "uvicorn", SimpleNamespace(run=_make_fake_uvicorn_run(calls)), raising=False)

    result = CliRunner().invoke(app, ["web"])

    assert result.exit_code == 0
    assert len(calls) == 1
    call = calls[0]
    assert call["host"] == "127.0.0.1"
    assert call["port"] == 8000
    assert call["reload"] is False
    assert call["factory"] is True
    assert call["app_factory"] is not None
    assert "http://127.0.0.1:8000" in result.output


def test_cli_web_forwards_explicit_options_and_prints_url(monkeypatch: Any, tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []
    config_path = tmp_path / "paperbrain.conf"

    monkeypatch.setattr(cli, "uvicorn", SimpleNamespace(run=_make_fake_uvicorn_run(calls)), raising=False)

    result = CliRunner().invoke(
        app,
        [
            "web",
            "--host",
            "0.0.0.0",
            "--port",
            "9001",
            "--reload",
            "--config-path",
            str(config_path),
        ],
    )

    assert result.exit_code == 0
    assert len(calls) == 1
    call = calls[0]
    assert call["host"] == "0.0.0.0"
    assert call["port"] == 9001
    assert call["reload"] is True
    assert call["factory"] is True
    assert call["app_factory"] is not None
    assert "http://0.0.0.0:9001" in result.output
