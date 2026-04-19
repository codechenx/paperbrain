# Marker Memory Optimization with Generic Parse Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce RAM growth during large Marker/Docling ingest runs by using a generic parser worker process with a lower default recycle cadence.

**Architecture:** Introduce a parser-agnostic worker that constructs parser instances from config (`pdf_parser`, `ocr_enabled`) and keeps converter state inside the worker lifecycle. Wire CLI ingest to always use this worker path for supported parsers, and lower default `--parse-worker-recycle-every` from 25 to 5. Preserve streaming ingest semantics and fail-fast parse error behavior.

**Tech Stack:** Python 3.12, Typer, multiprocessing (spawn), pytest, marker-pdf, docling.

---

## File Structure

- **Create:** `paperbrain/adapters/parser_worker.py` — generic parse worker process protocol and lifecycle.
- **Modify:** `paperbrain/adapters/marker.py` — add converter-reuse entrypoint used by worker.
- **Modify:** `paperbrain/cli.py` — switch ingest to generic worker and change default recycle to 5.
- **Modify:** `tests/test_setup_command.py` — ingest wiring tests for Marker + Docling worker usage and recycle default.
- **Create:** `tests/test_parser_worker.py` — worker tests for parser selection, OCR plumbing, parse command, and error forwarding.
- **Modify:** `README.md` — update default recycle examples to 5 and note applies to Marker + Docling.

---

### Task 1: Add generic parser worker module

**Files:**
- Create: `tests/test_parser_worker.py`
- Create: `paperbrain/adapters/parser_worker.py`
- Test: `tests/test_parser_worker.py`

- [ ] **Step 1: Write failing worker tests first**

```python
from typing import Any
from pathlib import Path

import pytest

import paperbrain.adapters.parser_worker as parser_worker


def test_worker_main_builds_parser_with_selected_backend_and_ocr(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeConnection:
        def __init__(self) -> None:
            self._commands = [("shutdown", None)]
            self.sent: list[tuple[str, Any]] = []
            self.closed = False

        def recv(self) -> tuple[str, Any]:
            return self._commands.pop(0)

        def send(self, payload: tuple[str, Any]) -> None:
            self.sent.append(payload)

        def close(self) -> None:
            self.closed = True

    class FakeParser:
        def create_converter(self) -> object:
            captured["create_converter"] = True
            return object()

        def parse_pdf_with_converter(self, path: Path, converter: object):  # noqa: ANN001, ANN201
            _ = (path, converter)
            raise AssertionError("parse should not run in this test")

    def fake_build_pdf_parser(pdf_parser: str, *, ocr_enabled: bool) -> object:
        captured["pdf_parser"] = pdf_parser
        captured["ocr_enabled"] = ocr_enabled
        return FakeParser()

    monkeypatch.setattr(parser_worker, "build_pdf_parser", fake_build_pdf_parser)
    connection = FakeConnection()

    parser_worker._worker_main(connection, parser_name="marker", ocr_enabled=True)

    assert captured["pdf_parser"] == "marker"
    assert captured["ocr_enabled"] is True
    assert captured["create_converter"] is True
    assert connection.sent == [("ok", None)]
    assert connection.closed is True


def test_worker_main_parses_and_returns_payload(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_text("fake", encoding="utf-8")

    class FakeConnection:
        def __init__(self) -> None:
            self._commands = [("parse", str(pdf_path)), ("shutdown", None)]
            self.sent: list[tuple[str, Any]] = []

        def recv(self) -> tuple[str, Any]:
            return self._commands.pop(0)

        def send(self, payload: tuple[str, Any]) -> None:
            self.sent.append(payload)

        def close(self) -> None:
            return None

    class FakeParsed:
        def __init__(self) -> None:
            self.title = "t"
            self.journal = "j"
            self.year = 2024
            self.authors = []
            self.corresponding_authors = []
            self.full_text = "x"
            self.source_path = str(pdf_path)

    class FakeParser:
        def create_converter(self) -> object:
            return object()

        def parse_pdf_with_converter(self, path: Path, converter: object) -> FakeParsed:
            _ = converter
            assert path == pdf_path
            return FakeParsed()

    monkeypatch.setattr(parser_worker, "build_pdf_parser", lambda *_args, **_kwargs: FakeParser())
    connection = FakeConnection()

    parser_worker._worker_main(connection, parser_name="docling", ocr_enabled=False)

    assert connection.sent[0][0] == "ok"
    payload = connection.sent[0][1]
    assert isinstance(payload, dict)
    assert payload["source_path"] == str(pdf_path)


def test_worker_main_surfaces_parse_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_text("fake", encoding="utf-8")

    class FakeConnection:
        def __init__(self) -> None:
            self._commands = [("parse", str(pdf_path)), ("shutdown", None)]
            self.sent: list[tuple[str, Any]] = []

        def recv(self) -> tuple[str, Any]:
            return self._commands.pop(0)

        def send(self, payload: tuple[str, Any]) -> None:
            self.sent.append(payload)

        def close(self) -> None:
            return None

    class BrokenParser:
        def create_converter(self) -> object:
            return object()

        def parse_pdf_with_converter(self, path: Path, converter: object):  # noqa: ANN001, ANN201
            _ = (path, converter)
            raise RuntimeError("boom")

    monkeypatch.setattr(parser_worker, "build_pdf_parser", lambda *_args, **_kwargs: BrokenParser())
    connection = FakeConnection()

    parser_worker._worker_main(connection, parser_name="marker", ocr_enabled=False)

    assert connection.sent[0][0] == "error"
    assert "RuntimeError: boom" in connection.sent[0][1]
```

- [ ] **Step 2: Run test to verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_parser_worker.py`  
Expected: FAIL because `paperbrain.adapters.parser_worker` does not exist.

- [ ] **Step 3: Implement minimal generic worker**

```python
# paperbrain/adapters/parser_worker.py
from __future__ import annotations

from dataclasses import asdict
from multiprocessing import get_context
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any

from paperbrain.adapters.parser_factory import build_pdf_parser
from paperbrain.models import ParsedPaper


def _worker_main(connection: Connection, parser_name: str, ocr_enabled: bool) -> None:
    parser = build_pdf_parser(parser_name, ocr_enabled=ocr_enabled)
    converter = parser.create_converter() if hasattr(parser, "create_converter") else None
    try:
        while True:
            command, payload = connection.recv()
            if command == "shutdown":
                connection.send(("ok", None))
                return
            if command != "parse":
                connection.send(("error", f"Unknown command: {command}"))
                continue
            try:
                file_path = Path(str(payload))
                if converter is not None and hasattr(parser, "parse_pdf_with_converter"):
                    parsed = parser.parse_pdf_with_converter(file_path, converter)
                else:
                    parsed = parser.parse_pdf(file_path)
            except Exception as exc:
                connection.send(("error", f"{type(exc).__name__}: {exc}"))
                continue
            connection.send(("ok", asdict(parsed)))
    finally:
        connection.close()


class ParserParseWorker:
    def __init__(self, *, parser_name: str, ocr_enabled: bool = False) -> None:
        context = get_context("spawn")
        parent_connection, child_connection = context.Pipe()
        self._connection = parent_connection
        self._process = context.Process(target=_worker_main, args=(child_connection, parser_name, ocr_enabled))
        self._process.start()
        child_connection.close()

    def parse(self, path: Path) -> ParsedPaper:
        if not self._process.is_alive():
            raise RuntimeError("Parser worker process is not running")
        self._connection.send(("parse", str(path)))
        status, payload = self._connection.recv()
        if status != "ok":
            raise RuntimeError(str(payload))
        if not isinstance(payload, dict):
            raise RuntimeError("Parser worker returned an invalid payload")
        return ParsedPaper(**payload)

    def close(self) -> None:
        if self._process.is_alive():
            try:
                self._connection.send(("shutdown", None))
                self._connection.recv()
            except Exception:
                pass
            self._process.join(timeout=2)
        if self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=2)
        self._connection.close()
```

- [ ] **Step 4: Run test to verify GREEN**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_parser_worker.py`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperbrain/adapters/parser_worker.py tests/test_parser_worker.py
git commit -m "feat: add generic parser worker for ingest" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 2: Enable converter reuse for Marker in worker lifecycle

**Files:**
- Modify: `tests/test_marker_parser.py`
- Modify: `paperbrain/adapters/marker.py`
- Test: `tests/test_marker_parser.py`

- [ ] **Step 1: Add failing test for `parse_pdf_with_converter`**

```python
def test_marker_parser_parse_pdf_with_converter_reuses_converter(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("fake", encoding="utf-8")

    class FakeConverter:
        def convert(self, file_path: str):  # noqa: ANN201
            class Result:
                document = None
                markdown = "Nature Medicine\\nPublished 2024\\nAlice Example Bob Example\\nCorresponding author: alice@example.com"
                metadata = {}

            assert file_path == str(pdf_path)
            return Result()

    parser = MarkerParser(ocr_enabled=False)
    parsed = parser.parse_pdf_with_converter(pdf_path, FakeConverter())
    assert parsed.title == "paper"
    assert parsed.year == 2024
```

- [ ] **Step 2: Run test to verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_marker_parser.py`  
Expected: FAIL because `MarkerParser.parse_pdf_with_converter` is missing.

- [ ] **Step 3: Implement minimal converter-reuse entrypoint**

```python
# paperbrain/adapters/marker.py
class MarkerParser:
    def __init__(self, *, ocr_enabled: bool = False) -> None:
        self.ocr_enabled = ocr_enabled
        self._docling_parser = DoclingParser()

    def parse_pdf(self, path: Path) -> ParsedPaper:
        converter = self.create_converter()
        return self.parse_pdf_with_converter(path, converter)

    def parse_pdf_with_converter(self, path: Path, converter: object) -> ParsedPaper:
        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {path}")
        return self._docling_parser.parse_pdf_with_converter(path, converter)
```

- [ ] **Step 4: Run test to verify GREEN**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_marker_parser.py`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperbrain/adapters/marker.py tests/test_marker_parser.py
git commit -m "feat: support marker converter reuse in worker path" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 3: Wire CLI ingest to generic worker and set default recycle to 5

**Files:**
- Modify: `tests/test_setup_command.py`
- Modify: `paperbrain/cli.py`
- Test: `tests/test_setup_command.py`

- [ ] **Step 1: Write failing CLI ingest wiring tests**

```python
def test_cli_ingest_uses_worker_for_marker_parser(monkeypatch: Any, tmp_path: Path) -> None:
    calls: dict[str, Any] = {}
    config_path = tmp_path / "config" / "paperbrain.conf"
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_text("fake", encoding="utf-8")

    class FakeRuntime:
        def __init__(self) -> None:
            self.config = AppConfig(
                database_url="postgresql://localhost:5432/paperbrain",
                openai_api_key="",
                summary_model="gemini:gemini-2.5-flash",
                embedding_model="text-embedding-3-small",
                embeddings_enabled=False,
                ocr_enabled=False,
                pdf_parser="marker",
            )
            self.parser = object()
            self.embeddings = None
            self.llm = object()

    class FakeParserParseWorker:
        def __init__(self, *, parser_name: str, ocr_enabled: bool = False) -> None:
            calls["worker_args"] = (parser_name, ocr_enabled)

    class FakeIngestService:
        def __init__(self, *, repo: Any, parser: Any, embeddings: Any, parse_worker_factory: Any = None) -> None:
            _ = (repo, parser, embeddings)
            calls["parse_worker_factory"] = parse_worker_factory

        def ingest_paths(self, paths: list[str], force_all: bool, recursive: bool = False, **kwargs: Any) -> int:
            calls["kwargs"] = kwargs
            return 1

    monkeypatch.setattr("paperbrain.cli.build_runtime", lambda _path: FakeRuntime())
    monkeypatch.setattr("paperbrain.cli.ParserParseWorker", FakeParserParseWorker)
    monkeypatch.setattr("paperbrain.cli.IngestService", FakeIngestService)
    monkeypatch.setattr("paperbrain.cli.repo_from_url", contextmanager(lambda *_args, **_kwargs: iter([object()])))

    result = CliRunner().invoke(app, ["ingest", str(pdf_path), "--config-path", str(config_path)])
    assert result.exit_code == 0
    calls["parse_worker_factory"]()
    assert calls["worker_args"] == ("marker", False)
    assert calls["kwargs"]["parse_worker_recycle_every"] == 5
```

- [ ] **Step 2: Run test to verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_setup_command.py`  
Expected: FAIL because CLI still uses Docling-only worker branch and default recycle is 25.

- [ ] **Step 3: Implement CLI wiring + new default**

```python
# paperbrain/cli.py
from paperbrain.adapters.parser_worker import ParserParseWorker

def ingest(
    path: Path = typer.Argument(..., exists=True),
    force_all: bool = typer.Option(False, "--force-all"),
    recursive: bool = typer.Option(False, "--recursive"),
    start_offset: int = typer.Option(0, "--start-offset", min=0),
    max_files: int | None = typer.Option(None, "--max-files", min=0),
    parse_worker_recycle_every: int = typer.Option(5, "--parse-worker-recycle-every", min=1),
    config_path: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config-path"),
) -> None:
    runtime = build_runtime(config_path)
    parse_worker_factory = lambda: ParserParseWorker(
        parser_name=runtime.config.pdf_parser,
        ocr_enabled=runtime.config.ocr_enabled,
    )
    with repo_from_url(runtime.config.database_url) as repo:
        inserted = IngestService(
            repo=repo,
            parser=runtime.parser,
            embeddings=runtime.embeddings,
            parse_worker_factory=parse_worker_factory,
        ).ingest_paths(
            [str(path)],
            force_all=force_all,
            recursive=recursive,
            start_offset=start_offset,
            max_files=max_files,
            parse_worker_recycle_every=parse_worker_recycle_every,
        )
```

- [ ] **Step 4: Run test to verify GREEN**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_setup_command.py`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperbrain/cli.py tests/test_setup_command.py
git commit -m "feat: use generic parse worker and lower recycle default" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 4: Update README and run regressions

**Files:**
- Modify: `README.md`
- Test: targeted + full suite

- [ ] **Step 1: Update ingest docs for recycle default 5**

```markdown
paperbrain ingest /path/to/pdfs --recursive --start-offset 0 --max-files 200 --parse-worker-recycle-every 5
paperbrain ingest /path/to/pdfs --recursive --start-offset 200 --max-files 200 --parse-worker-recycle-every 5
```

```markdown
- `--parse-worker-recycle-every` defaults to 5 for both Marker and Docling parsers.
```

- [ ] **Step 2: Run targeted regression**

Run:  
`PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_parser_worker.py tests/test_marker_parser.py tests/test_setup_command.py tests/test_ingest_service.py`

Expected: PASS.

- [ ] **Step 3: Run full suite**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q`  
Expected: PASS (existing skip only).

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document parse worker recycle default for marker and docling" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```
