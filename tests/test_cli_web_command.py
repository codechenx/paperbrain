from pathlib import Path
from types import SimpleNamespace
from typing import Any

from typer.testing import CliRunner

from paperbrain.cli import app


def _make_fake_uvicorn(calls: list[dict[str, Any]]) -> SimpleNamespace:
    def fake_run(app_factory: Any, **kwargs: Any) -> None:
        calls.append({"app_factory": app_factory, **kwargs})
        if callable(app_factory):
            app_factory()

    return SimpleNamespace(run=fake_run)


def test_cli_web_uses_default_host_port_reload_and_prints_url(monkeypatch: Any) -> None:
    calls: list[dict[str, Any]] = []
    fake_create_app_calls: list[Path] = []

    def fake_create_app(*, config_path: Path) -> object:
        fake_create_app_calls.append(config_path)
        return object()

    monkeypatch.setattr("paperbrain.cli.uvicorn", _make_fake_uvicorn(calls), raising=False)
    monkeypatch.setattr("paperbrain.cli.create_app", fake_create_app, raising=False)

    result = CliRunner().invoke(app, ["web"])

    assert result.exit_code == 0
    assert calls == [
        {
            "app_factory": calls[0]["app_factory"],
            "host": "127.0.0.1",
            "port": 8000,
            "reload": False,
            "factory": True,
        }
    ]
    assert fake_create_app_calls == [Path("config/paperbrain.conf")]
    assert "http://127.0.0.1:8000" in result.output


def test_cli_web_forwards_explicit_options_and_prints_url(monkeypatch: Any, tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []
    fake_create_app_calls: list[Path] = []
    config_path = tmp_path / "paperbrain.conf"

    def fake_create_app(*, config_path: Path) -> object:
        fake_create_app_calls.append(config_path)
        return object()

    monkeypatch.setattr("paperbrain.cli.uvicorn", _make_fake_uvicorn(calls), raising=False)
    monkeypatch.setattr("paperbrain.cli.create_app", fake_create_app, raising=False)

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
    assert calls == [
        {
            "app_factory": calls[0]["app_factory"],
            "host": "0.0.0.0",
            "port": 9001,
            "reload": True,
            "factory": True,
        }
    ]
    assert fake_create_app_calls == [config_path]
    assert "http://0.0.0.0:9001" in result.output
