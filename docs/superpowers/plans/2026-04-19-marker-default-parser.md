# Marker Default Parser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Marker as the default PDF ingest parser with Docling as an explicit configurable alternative, while requiring an explicit `pdf_parser` config key.

**Architecture:** Extend config/setup to persist a required parser selector (`marker|docling`), then centralize parser construction in a dedicated factory. Add a `MarkerParser` adapter that normalizes output to `ParsedPaper` using metadata heuristics aligned with current Docling behavior, and keep Docling worker recycling logic only for Docling parser instances.

**Tech Stack:** Python 3.12, Typer, pytest, marker-pdf, docling.

---

## File Structure

- **Create:** `paperbrain/adapters/marker.py` — Marker-backed `parse_pdf` adapter returning `ParsedPaper`.
- **Create:** `paperbrain/adapters/parser_factory.py` — centralized parser selection for `marker|docling`.
- **Create:** `tests/test_marker_parser.py` — Marker adapter unit tests (missing dependency + parsed output normalization).
- **Create:** `tests/test_parser_factory.py` — parser factory selection/validation tests.
- **Modify:** `paperbrain/config.py` — add required `pdf_parser` contract.
- **Modify:** `paperbrain/services/setup.py` — accept and persist `pdf_parser`.
- **Modify:** `paperbrain/cli.py` — setup flag + parser-agnostic runtime typing + ingest worker branch.
- **Modify:** `paperbrain/summary_provider.py` — use parser factory.
- **Modify:** `tests/test_config.py` — parser key required/default tests.
- **Modify:** `tests/test_setup_command.py` — setup CLI wiring + runtime parser wiring tests.
- **Modify:** `tests/test_summary_provider.py` — provider parser selection tests.
- **Modify:** `README.md` — parser install/config/setup docs.
- **Modify:** `pyproject.toml` — add `marker-pdf` dependency.

---

### Task 1: Add required `pdf_parser` config contract

**Files:**
- Modify: `tests/test_config.py`
- Modify: `paperbrain/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing config tests for parser key behavior**

```python
def test_save_and_load_config_round_trip(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"
    store = ConfigStore(config_path)
    store.save(database_url="postgresql://localhost:5432/paperbrain")
    loaded = store.load()
    assert loaded.pdf_parser == "marker"


def test_load_rejects_missing_pdf_parser_key(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"
    config_path.write_text(
        (
            "[paperbrain]\n"
            'database_url = "postgresql://localhost:5432/paperbrain"\n'
            "embeddings_enabled = false\n"
            "docling_ocr_enabled = false\n"
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="pdf_parser"):
        ConfigStore(config_path).load()


def test_load_rejects_invalid_pdf_parser_value(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"
    config_path.write_text(
        (
            "[paperbrain]\n"
            'database_url = "postgresql://localhost:5432/paperbrain"\n'
            "embeddings_enabled = false\n"
            "docling_ocr_enabled = false\n"
            'pdf_parser = "unknown"\n'
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="pdf_parser"):
        ConfigStore(config_path).load()
```

- [ ] **Step 2: Run config tests to verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_config.py`  
Expected: FAIL on missing `pdf_parser` support.

- [ ] **Step 3: Implement required parser config in `paperbrain/config.py`**

```python
DEFAULT_PDF_PARSER = "marker"
SUPPORTED_PDF_PARSERS = {"marker", "docling"}


def normalize_pdf_parser(pdf_parser: str) -> str:
    normalized = pdf_parser.strip().lower()
    if normalized not in SUPPORTED_PDF_PARSERS:
        allowed = ", ".join(sorted(SUPPORTED_PDF_PARSERS))
        raise ValueError(f"Invalid pdf_parser in configuration file. Allowed values: {allowed}")
    return normalized
```

```python
@dataclass(slots=True)
class AppConfig:
    database_url: str
    openai_api_key: str
    summary_model: str
    embedding_model: str
    embeddings_enabled: bool = DEFAULT_EMBEDDINGS_ENABLED
    docling_ocr_enabled: bool = DEFAULT_DOCLING_OCR_ENABLED
    pdf_parser: str = DEFAULT_PDF_PARSER
    gemini_api_key: str = ""
    ollama_api_key: str = ""
    ollama_base_url: str = "https://ollama.com"
```

```python
# ConfigStore.save() template body
'pdf_parser = "{pdf_parser}"\n'
```

```python
# ConfigStore.load()
if "pdf_parser" not in section:
    raise ValueError("Missing pdf_parser in configuration file")
pdf_parser = section["pdf_parser"]
if not isinstance(pdf_parser, str):
    raise ValueError("Invalid pdf_parser in configuration file")
normalized_pdf_parser = normalize_pdf_parser(pdf_parser)
```

- [ ] **Step 4: Re-run config tests to verify GREEN**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_config.py`  
Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add paperbrain/config.py tests/test_config.py
git commit -m "feat: require explicit pdf_parser in config"
```

---

### Task 2: Wire parser selection through setup and CLI

**Files:**
- Modify: `tests/test_setup_command.py`
- Modify: `paperbrain/services/setup.py`
- Modify: `paperbrain/cli.py`
- Test: `tests/test_setup_command.py`

- [ ] **Step 1: Add failing setup/CLI tests for parser option**

```python
def test_run_setup_writes_project_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config" / "paperbrain.conf"
    run_setup(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="sk-test",
        summary_model="openai:gpt-4.1-mini",
        embedding_model="text-embedding-3-small",
        config_path=config_path,
        test_connections=False,
    )
    loaded = ConfigStore(config_path).load()
    assert loaded.pdf_parser == "marker"


def test_cli_setup_accepts_pdf_parser_flag(monkeypatch: Any) -> None:
    calls: dict[str, Any] = {}

    def fake_run_setup(**kwargs: Any) -> str:
        calls.update(kwargs)
        return "ok"

    monkeypatch.setattr("paperbrain.cli.run_setup", fake_run_setup)
    result = CliRunner().invoke(
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
            "--pdf-parser",
            "docling",
        ],
    )
    assert result.exit_code == 0
    assert calls["pdf_parser"] == "docling"
```

- [ ] **Step 2: Run setup tests to verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_setup_command.py`  
Expected: FAIL on missing `pdf_parser` plumbing.

- [ ] **Step 3: Implement setup + CLI parser plumbing**

```python
# paperbrain/services/setup.py
from paperbrain.config import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_EMBEDDINGS_ENABLED,
    DEFAULT_PDF_PARSER,
    DEFAULT_SUMMARY_MODEL,
    ConfigStore,
    normalize_pdf_parser,
    validate_embedding_model_for_schema,
)

def run_setup(
    database_url: str,
    openai_api_key: str = "",
    gemini_api_key: str = "",
    ollama_api_key: str = "",
    ollama_base_url: str = "https://ollama.com",
    summary_model: str = DEFAULT_SUMMARY_MODEL,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    embeddings_enabled: bool = DEFAULT_EMBEDDINGS_ENABLED,
    docling_ocr_enabled: bool = False,
    pdf_parser: str = DEFAULT_PDF_PARSER,
    config_path: Path = Path.home() / ".config" / "paperbrain" / "paperbrain.conf",
    test_connections: bool = True,
) -> str:
    normalized_pdf_parser = normalize_pdf_parser(pdf_parser)
    store = ConfigStore(config_path)
    store.save(
        database_url=database_url,
        openai_api_key=openai_api_key,
        gemini_api_key=gemini_api_key,
        ollama_api_key=ollama_api_key,
        ollama_base_url=ollama_base_url,
        summary_model=summary_model,
        embedding_model=embedding_model,
        embeddings_enabled=embeddings_enabled,
        docling_ocr_enabled=docling_ocr_enabled,
        pdf_parser=normalized_pdf_parser,
    )
    return f"Saved configuration to {config_path}"
```

```python
# paperbrain/cli.py setup()
from paperbrain.config import DEFAULT_EMBEDDING_MODEL, DEFAULT_PDF_PARSER, DEFAULT_SUMMARY_MODEL

pdf_parser: str = typer.Option(DEFAULT_PDF_PARSER, "--pdf-parser"),

message = run_setup(
    database_url=url,
    openai_api_key=resolved_openai_api_key,
    gemini_api_key=resolved_gemini_api_key,
    ollama_api_key=resolved_ollama_api_key,
    ollama_base_url=ollama_base_url,
    summary_model=summary_model,
    embedding_model=embedding_model,
    embeddings_enabled=embeddings_enabled,
    docling_ocr_enabled=docling_ocr_enabled,
    pdf_parser=pdf_parser,
    config_path=config_path,
    test_connections=test_connections,
)
```

- [ ] **Step 4: Re-run setup tests to verify GREEN**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_setup_command.py`  
Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```bash
git add paperbrain/services/setup.py paperbrain/cli.py tests/test_setup_command.py
git commit -m "feat: add setup and CLI parser selection option"
```

---

### Task 3: Add parser factory + Marker adapter

**Files:**
- Create: `paperbrain/adapters/parser_factory.py`
- Create: `paperbrain/adapters/marker.py`
- Create: `tests/test_parser_factory.py`
- Create: `tests/test_marker_parser.py`
- Test: `tests/test_parser_factory.py`, `tests/test_marker_parser.py`

- [ ] **Step 1: Add failing parser factory and Marker adapter tests**

```python
# tests/test_parser_factory.py
import pytest

from paperbrain.adapters.docling import DoclingParser
from paperbrain.adapters.marker import MarkerParser
from paperbrain.adapters.parser_factory import build_pdf_parser


def test_build_pdf_parser_returns_marker() -> None:
    parser = build_pdf_parser("marker", docling_ocr_enabled=False)
    assert isinstance(parser, MarkerParser)


def test_build_pdf_parser_returns_docling_with_ocr() -> None:
    parser = build_pdf_parser("docling", docling_ocr_enabled=True)
    assert isinstance(parser, DoclingParser)
    assert parser.ocr_enabled is True


def test_build_pdf_parser_rejects_invalid_value() -> None:
    with pytest.raises(ValueError, match="pdf_parser"):
        build_pdf_parser("invalid", docling_ocr_enabled=False)
```

```python
# tests/test_marker_parser.py
import sys
import types
from pathlib import Path

import pytest

from paperbrain.adapters.marker import MarkerParser


def test_marker_parser_raises_when_marker_missing(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("fake", encoding="utf-8")
    parser = MarkerParser()
    with pytest.raises(RuntimeError, match="marker-pdf"):
        parser.parse_pdf(pdf_path)
```

- [ ] **Step 2: Run new tests to verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_parser_factory.py tests/test_marker_parser.py`  
Expected: FAIL because files/implementations do not exist yet.

- [ ] **Step 3: Implement parser factory and Marker adapter**

```python
# paperbrain/adapters/parser_factory.py
from paperbrain.adapters.docling import DoclingParser
from paperbrain.adapters.marker import MarkerParser
from paperbrain.services.ingest import Parser


def build_pdf_parser(pdf_parser: str, *, docling_ocr_enabled: bool) -> Parser:
    normalized = pdf_parser.strip().lower()
    if normalized == "marker":
        return MarkerParser()
    if normalized == "docling":
        return DoclingParser(ocr_enabled=docling_ocr_enabled)
    raise ValueError("Invalid pdf_parser. Allowed values: docling, marker")
```

```python
# paperbrain/adapters/marker.py
from importlib import import_module
from pathlib import Path
import re

from paperbrain.adapters.docling import DoclingParser
from paperbrain.models import ParsedPaper


class MarkerParser:
    @staticmethod
    def _infer_year(text: str) -> int | None:
        match = re.search(r"\b(19|20)\d{2}\b", text)
        return int(match.group(0)) if match else None

    def parse_pdf(self, path: Path) -> ParsedPaper:
        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {path}")
        try:
            pdf_module = import_module("marker.converters.pdf")
            models_module = import_module("marker.models")
            output_module = import_module("marker.output")
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "marker-pdf is required for Marker parsing. Install it with `pip install marker-pdf`."
            ) from exc

        PdfConverter = getattr(pdf_module, "PdfConverter")
        create_model_dict = getattr(models_module, "create_model_dict")
        text_from_rendered = getattr(output_module, "text_from_rendered")

        converter = PdfConverter(artifact_dict=create_model_dict())
        rendered = converter(str(path))
        content, _, _ = text_from_rendered(rendered)
        content = DoclingParser._strip_image_payloads(str(content))
        content = DoclingParser._trim_references_section(content)
        first_page_text = content[:4000].strip()

        return ParsedPaper(
            title=path.stem,
            journal=DoclingParser._infer_journal_from_first_page(first_page_text) or "Unknown Journal",
            year=self._infer_year(first_page_text) or 1970,
            authors=DoclingParser._infer_authors_from_first_page(first_page_text),
            corresponding_authors=DoclingParser._extract_corresponding_authors_from_first_page(first_page_text),
            full_text=content.strip(),
            source_path=str(path),
        )
```

- [ ] **Step 4: Expand Marker adapter tests for normalized output**

```python
def test_marker_parser_returns_normalized_parsed_paper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("fake", encoding="utf-8")

    class FakePdfConverter:
        def __init__(self, artifact_dict):  # noqa: ANN001
            self.artifact_dict = artifact_dict
        def __call__(self, file_path: str):  # noqa: ANN201
            return {"path": file_path}

    def fake_create_model_dict() -> dict[str, str]:
        return {"ok": "yes"}

    def fake_text_from_rendered(rendered):  # noqa: ANN001, ANN201
        _ = rendered
        text = "Nature Medicine\nCorresponding author: alice@example.com\nPublished 2024\nAlice Example Bob Example"
        return text, {}, {}

    monkeypatch.setitem(sys.modules, "marker", types.ModuleType("marker"))
    converters_pkg = types.ModuleType("marker.converters")
    pdf_module = types.ModuleType("marker.converters.pdf")
    models_module = types.ModuleType("marker.models")
    output_module = types.ModuleType("marker.output")
    pdf_module.PdfConverter = FakePdfConverter
    models_module.create_model_dict = fake_create_model_dict
    output_module.text_from_rendered = fake_text_from_rendered
    monkeypatch.setitem(sys.modules, "marker.converters", converters_pkg)
    monkeypatch.setitem(sys.modules, "marker.converters.pdf", pdf_module)
    monkeypatch.setitem(sys.modules, "marker.models", models_module)
    monkeypatch.setitem(sys.modules, "marker.output", output_module)

    parsed = MarkerParser().parse_pdf(pdf_path)
    assert parsed.title == "paper"
    assert parsed.journal == "Nature Medicine"
    assert parsed.year == 2024
    assert parsed.source_path == str(pdf_path)
```

- [ ] **Step 5: Run parser tests to verify GREEN**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_parser_factory.py tests/test_marker_parser.py`  
Expected: PASS.

- [ ] **Step 6: Commit Task 3**

```bash
git add paperbrain/adapters/parser_factory.py paperbrain/adapters/marker.py tests/test_parser_factory.py tests/test_marker_parser.py
git commit -m "feat: add marker parser adapter and parser factory"
```

---

### Task 4: Wire runtime parser selection and ingest behavior

**Files:**
- Modify: `paperbrain/summary_provider.py`
- Modify: `paperbrain/cli.py`
- Modify: `tests/test_summary_provider.py`
- Modify: `tests/test_setup_command.py`
- Test: `tests/test_summary_provider.py`, `tests/test_setup_command.py`

- [ ] **Step 1: Add failing runtime wiring tests**

```python
# tests/test_summary_provider.py
def test_summary_provider_uses_parser_factory(monkeypatch):
    captured = {}

    class DummyParser:
        def parse_pdf(self, path):  # noqa: ANN001, ANN201
            raise NotImplementedError

    def fake_build_pdf_parser(pdf_parser: str, *, docling_ocr_enabled: bool):
        captured["pdf_parser"] = pdf_parser
        captured["docling_ocr_enabled"] = docling_ocr_enabled
        return DummyParser()

    monkeypatch.setattr("paperbrain.summary_provider.build_pdf_parser", fake_build_pdf_parser)
    monkeypatch.setattr("paperbrain.summary_provider.ConfigStore", DummyConfigStore)
    provider = SummaryProvider(config_path=Path("dummy"))
    assert captured["pdf_parser"] == "marker"
    assert provider.parser is not None
```

```python
# tests/test_setup_command.py
def test_cli_ingest_marker_parser_does_not_use_docling_worker(monkeypatch: Any, tmp_path: Path) -> None:
    calls: dict[str, Any] = {}
    # monkeypatch build_runtime to return runtime.parser as non-Docling parser,
    # then assert IngestService gets parse_worker_factory=None
```

- [ ] **Step 2: Run runtime tests to verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_summary_provider.py tests/test_setup_command.py`  
Expected: FAIL on parser factory/runtime assumptions.

- [ ] **Step 3: Implement runtime parser factory usage**

```python
# paperbrain/summary_provider.py
from paperbrain.adapters.parser_factory import build_pdf_parser

self.parser = build_pdf_parser(
    self.config.pdf_parser,
    docling_ocr_enabled=self.config.docling_ocr_enabled,
)
```

```python
# paperbrain/cli.py
from paperbrain.services.ingest import Parser as IngestParser

@dataclass(slots=True)
class RuntimeAdapters:
    config: AppConfig
    parser: IngestParser
    embeddings: OpenAIEmbeddingAdapter | None
    llm: LLMAdapter
```

```python
# paperbrain/cli.py ingest()
parse_worker_factory = None
if isinstance(runtime.parser, DoclingParser):
    parse_worker_factory = lambda: DoclingParseWorker(ocr_enabled=runtime.parser.ocr_enabled)
```

- [ ] **Step 4: Replace placeholder test with concrete CLI ingest worker assertion**

```python
def test_cli_ingest_marker_parser_does_not_use_docling_worker(monkeypatch: Any, tmp_path: Path) -> None:
    calls: dict[str, Any] = {}
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_text("fake", encoding="utf-8")

    class FakeParser:
        pass

    class FakeRuntime:
        def __init__(self) -> None:
            self.config = AppConfig(
                database_url="postgresql://localhost:5432/paperbrain",
                openai_api_key="",
                summary_model="gemini:gemini-2.5-flash",
                embedding_model="text-embedding-3-small",
                embeddings_enabled=False,
                docling_ocr_enabled=False,
                pdf_parser="marker",
            )
            self.parser = FakeParser()
            self.embeddings = None
            self.llm = object()

    class FakeIngestService:
        def __init__(self, *, repo: Any, parser: Any, embeddings: Any, parse_worker_factory: Any = None) -> None:
            _ = (repo, parser, embeddings)
            calls["parse_worker_factory"] = parse_worker_factory
        def ingest_paths(self, paths: list[str], force_all: bool, recursive: bool = False, **kwargs: Any) -> int:
            _ = (paths, force_all, recursive, kwargs)
            return 1

    monkeypatch.setattr("paperbrain.cli.build_runtime", lambda _: FakeRuntime())
    monkeypatch.setattr("paperbrain.cli.IngestService", FakeIngestService)
    monkeypatch.setattr("paperbrain.cli.repo_from_url", contextmanager(lambda *_args, **_kwargs: iter([object()])))
    result = CliRunner().invoke(app, ["ingest", str(pdf_path)])
    assert result.exit_code == 0
    assert calls["parse_worker_factory"] is None
```

- [ ] **Step 5: Re-run runtime tests to verify GREEN**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_summary_provider.py tests/test_setup_command.py`  
Expected: PASS.

- [ ] **Step 6: Commit Task 4**

```bash
git add paperbrain/summary_provider.py paperbrain/cli.py tests/test_summary_provider.py tests/test_setup_command.py
git commit -m "feat: wire runtime parser selection for marker and docling"
```

---

### Task 5: Document Marker parser and run full verification

**Files:**
- Modify: `pyproject.toml`
- Modify: `README.md`
- Test: targeted + full suite

- [ ] **Step 1: Add Marker dependency**

```toml
[project]
dependencies = [
  "typer>=0.12.0",
  "psycopg[binary]>=3.2.0",
  "openai>=1.51.0",
  "ollama>=0.4.7",
  "google-genai>=0.3.0",
  "docling>=2.9.0",
  "marker-pdf>=1.8.0",
  "fastapi>=0.115.0",
  "jinja2>=3.1.4",
  "uvicorn>=0.30.0",
]
```

- [ ] **Step 2: Update README parser docs**

```markdown
# setup examples
paperbrain setup --url postgresql://<user>:<pass>@localhost:5432/paperbrain --gemini-api-key $GEMINI_API_KEY --summary-model gemini:gemini-2.5-flash --pdf-parser marker
paperbrain setup --url postgresql://<user>:<pass>@localhost:5432/paperbrain --gemini-api-key $GEMINI_API_KEY --summary-model gemini:gemini-2.5-flash --pdf-parser docling --docling-ocr-enabled

# config shape
pdf_parser = "marker"
```

```markdown
- `pdf_parser` is required in config (`marker` or `docling`).
- Marker is the default in setup-generated config.
- If Marker is selected but not installed, ingest fails with install guidance.
```

- [ ] **Step 3: Run targeted regression**

Run:  
`PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_config.py tests/test_setup_command.py tests/test_summary_provider.py tests/test_ingest_service.py tests/test_docling_worker.py tests/test_parser_factory.py tests/test_marker_parser.py`

Expected: PASS.

- [ ] **Step 4: Run full suite**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q`  
Expected: PASS (existing optional skip(s) only).

- [ ] **Step 5: Commit Task 5**

```bash
git add pyproject.toml README.md
git commit -m "docs: document marker parser configuration and dependency"
```

