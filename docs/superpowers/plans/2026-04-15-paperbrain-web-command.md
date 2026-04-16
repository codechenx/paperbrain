# PaperBrain Web Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first-class `paperbrain web` CLI command that runs the FastAPI web app with configurable host/port/reload/config-path defaults.

**Architecture:** Extend the Typer CLI with a new `web` command that builds an app-factory closure bound to `config_path` and launches uvicorn via `uvicorn.run(..., factory=True)`. Keep behavior minimal: print startup URL, forward options, and surface existing config/runtime errors without fallback wrappers. Validate wiring through CLI tests that monkeypatch `uvicorn.run` rather than starting a real server.

**Tech Stack:** Python 3.12, Typer, FastAPI, Uvicorn, pytest

---

## File structure map

- **Modify:** `paperbrain/cli.py`
  - Add `web` command and uvicorn import.
  - Build app-factory closure and forward host/port/reload/config-path.
- **Modify:** `tests/test_cli_commands.py`
  - Ensure `web` appears in top-level help output.
- **Create:** `tests/test_cli_web_command.py`
  - Add focused CLI wiring tests for default and explicit option forwarding.

### Task 1: Add failing CLI tests for `web` command (red phase)

**Files:**
- Modify: `tests/test_cli_commands.py:6-22`
- Create: `tests/test_cli_web_command.py`
- Test: `tests/test_cli_commands.py`
- Test: `tests/test_cli_web_command.py`

- [ ] **Step 1: Update help-command test to expect `web`**

```python
def test_cli_exposes_core_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    output = result.output
    for name in [
        "setup",
        "init",
        "ingest",
        "browse",
        "search",
        "summarize",
        "lint",
        "stats",
        "export",
        "web",
    ]:
        assert name in output
```

- [ ] **Step 2: Add failing tests for uvicorn wiring**

```python
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from paperbrain.cli import app


def test_web_command_uses_default_runtime_options(monkeypatch) -> None:
    runner = CliRunner()
    captured: dict[str, Any] = {}

    def fake_run(application, **kwargs):  # noqa: ANN001, ANN003
        captured["application"] = application
        captured.update(kwargs)

    monkeypatch.setattr("paperbrain.cli.uvicorn.run", fake_run)

    result = runner.invoke(app, ["web"])

    assert result.exit_code == 0
    assert "http://127.0.0.1:8000" in result.output
    assert callable(captured["application"])
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8000
    assert captured["reload"] is False
    assert captured["factory"] is True


def test_web_command_forwards_explicit_options(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    captured: dict[str, Any] = {}
    config_path = tmp_path / "custom.conf"
    config_path.write_text("fake=1", encoding="utf-8")

    def fake_run(application, **kwargs):  # noqa: ANN001, ANN003
        captured["application"] = application
        captured.update(kwargs)

    monkeypatch.setattr("paperbrain.cli.uvicorn.run", fake_run)

    result = runner.invoke(
        app,
        [
            "web",
            "--host",
            "0.0.0.0",
            "--port",
            "9000",
            "--reload",
            "--config-path",
            str(config_path),
        ],
    )

    assert result.exit_code == 0
    assert "http://0.0.0.0:9000" in result.output
    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 9000
    assert captured["reload"] is True
    assert captured["factory"] is True
```

- [ ] **Step 3: Run focused tests to verify fail**

Run:
```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_cli_commands.py tests/test_cli_web_command.py -q
```

Expected:
- FAIL because `web` command is not implemented yet.

- [ ] **Step 4: Commit red tests**

```bash
git add tests/test_cli_commands.py tests/test_cli_web_command.py
git commit -m "test: add failing coverage for paperbrain web command" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 2: Implement `paperbrain web` command in CLI

**Files:**
- Modify: `paperbrain/cli.py:1-220`
- Test: `tests/test_cli_web_command.py`

- [ ] **Step 1: Add uvicorn import and `web` command implementation**

```python
import uvicorn
```

```python
@app.command()
def web(
    host: str = typer.Option("127.0.0.1", "--host", help="Host interface for the web server"),
    port: int = typer.Option(8000, "--port", help="Port for the web server"),
    reload: bool = typer.Option(False, "--reload/--no-reload", help="Enable auto-reload for development"),
    config_path: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config-path"),
) -> None:
    from paperbrain.web.app import create_app

    def app_factory():  # noqa: ANN202
        return create_app(config_path=config_path)

    typer.echo(f"Starting web server at http://{host}:{port}")
    uvicorn.run(app_factory, host=host, port=port, reload=reload, factory=True)
```

- [ ] **Step 2: Extend explicit-options test to verify config-path wiring**

```python
app_factory = captured["application"]
app_instance = app_factory()
assert app_instance.title == "PaperBrain Browser"
```

Note: monkeypatch `paperbrain.web.app.ConfigStore` in this test before calling `app_factory()` so no real DB/config lookup is required.

- [ ] **Step 3: Run focused tests**

Run:
```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_cli_commands.py tests/test_cli_web_command.py -q
```

Expected:
- PASS.

- [ ] **Step 4: Commit implementation**

```bash
git add paperbrain/cli.py tests/test_cli_commands.py tests/test_cli_web_command.py
git commit -m "feat: add paperbrain web command" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 3: Run full verification and finalize

**Files:**
- Modify: none unless minor test-fix adjustments are required
- Test: full suite

- [ ] **Step 1: Run full test suite**

Run:
```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q
```

Expected:
- PASS (allow existing skipped tests).

- [ ] **Step 2: Commit verification-only adjustments (if any)**

```bash
git add paperbrain/cli.py tests/test_cli_commands.py tests/test_cli_web_command.py
git commit -m "test: finalize web command coverage" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

## Plan self-review (completed)

1. **Spec coverage:** Includes command interface, defaults, app-factory config-path wiring, and tests.
2. **Placeholder scan:** No TBD/TODO placeholders remain.
3. **Type consistency:** Uses consistent command name (`web`) and option names (`host`, `port`, `reload`, `config_path`) across all tasks.
