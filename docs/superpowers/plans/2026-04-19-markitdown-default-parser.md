# MarkItDown Default Parser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Marker with MarkItDown as the default PDF parser, keep Docling as the only alternate parser, enforce fail-fast OCR behavior for MarkItDown, and update tests/docs/dependencies accordingly.

**Architecture:** Keep parser selection centralized in `config.py` + `parser_factory.py`. Add a dedicated `MarkItDownParser` adapter that reuses existing `DoclingParser.parse_pdf_with_converter()` normalization so output stays consistent. Keep the existing parser worker lifecycle and converter reuse model; only parser names and adapter wiring change.

**Tech Stack:** Python 3.12, Typer CLI, pytest, MarkItDown, Docling.

---

## File Structure Map

- **Create:** `paperbrain/adapters/markitdown.py` (native MarkItDown adapter with OCR fail-fast checks)
- **Create:** `tests/test_markitdown_parser.py` (unit tests for MarkItDown adapter behavior)
- **Modify:** `paperbrain/config.py` (default parser + allowed parser validation + migration error)
- **Modify:** `paperbrain/adapters/parser_factory.py` (construct `MarkItDownParser`/`DoclingParser` only)
- **Modify:** `paperbrain/services/setup.py` (setup writes `markitdown` as default parser)
- **Modify:** `paperbrain/cli.py` (parser option defaults/help reflect `markitdown|docling`)
- **Modify:** `paperbrain/summary_provider.py` (ensure parser construction still uses factory and parser config)
- **Modify:** `pyproject.toml` (replace Marker dependency with MarkItDown PDF dependency)
- **Modify:** `README.md` (install/config/docs update: markitdown default, OCR plugin note)
- **Modify:** `tests/test_config.py` (default/validation migration behavior)
- **Modify:** `tests/test_parser_factory.py` (factory now returns MarkItDown/Docling only)
- **Modify:** `tests/test_parser_worker.py` (worker test fixtures use `markitdown` parser name)
- **Modify:** `tests/test_setup_command.py` (CLI ingest/setup default parser assertions)
- **Modify:** `tests/test_summary_provider.py` (parser selection assertions)
- **Delete:** `paperbrain/adapters/marker.py` (remove Marker adapter)
- **Delete:** `tests/test_marker_parser.py` (replace with MarkItDown tests)

### Task 1: Migrate config contract to `markitdown|docling`

**Files:**
- Modify: `tests/test_config.py`
- Modify: `paperbrain/config.py`
- Modify: `paperbrain/services/setup.py`
- Modify: `paperbrain/cli.py`

- [ ] **Step 1: Write failing config tests for new defaults and marker rejection**

```python
def test_save_and_load_config_round_trip(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"
    store = ConfigStore(config_path)
    store.save(database_url="postgresql://localhost:5432/paperbrain")
    loaded = store.load()
    assert loaded.pdf_parser == "markitdown"


def test_load_rejects_marker_pdf_parser_with_migration_guidance(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"
    config_path.write_text(
        (
            "[paperbrain]\n"
            'database_url = "postgresql://localhost:5432/paperbrain"\n'
            "embeddings_enabled = false\n"
            "ocr_enabled = false\n"
            'pdf_parser = "marker"\n'
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match='Use "markitdown"'):
        ConfigStore(config_path).load()
```

- [ ] **Step 2: Run targeted tests to verify failure**

Run: `python3 -m pytest -q tests/test_config.py -k "pdf_parser or round_trip"`  
Expected: FAIL because current default/validation still permits `marker`.

- [ ] **Step 3: Implement config + setup defaults**

```python
# paperbrain/config.py
DEFAULT_PDF_PARSER = "markitdown"
SUPPORTED_PDF_PARSERS = {"markitdown", "docling"}

def normalize_pdf_parser(pdf_parser: str) -> str:
    normalized = pdf_parser.strip().lower()
    if normalized == "marker":
        raise ValueError(
            'Invalid pdf_parser in configuration file. Allowed values: docling, markitdown. '
            'Marker support was removed. Use "markitdown".'
        )
    if normalized not in SUPPORTED_PDF_PARSERS:
        supported = ", ".join(sorted(SUPPORTED_PDF_PARSERS))
        raise ValueError(f"Invalid pdf_parser in configuration file. Allowed values: {supported}")
    return normalized
```

```python
# paperbrain/services/setup.py (signature/default)
def run_setup(
    database_url: str,
    openai_api_key: str = "",
    gemini_api_key: str = "",
    ollama_api_key: str = "",
    ollama_base_url: str = "https://ollama.com",
    summary_model: str = DEFAULT_SUMMARY_MODEL,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    embeddings_enabled: bool = DEFAULT_EMBEDDINGS_ENABLED,
    ocr_enabled: bool = DEFAULT_OCR_ENABLED,
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
        ocr_enabled=ocr_enabled,
        pdf_parser=normalized_pdf_parser,
    )
```

```python
# paperbrain/cli.py (setup command option)
pdf_parser: str = typer.Option(DEFAULT_PDF_PARSER, "--pdf-parser")
```

- [ ] **Step 4: Run targeted tests to verify pass**

Run: `python3 -m pytest -q tests/test_config.py -k "pdf_parser or round_trip"`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_config.py paperbrain/config.py paperbrain/services/setup.py paperbrain/cli.py
git commit -m "feat: switch config parser defaults to markitdown"
```

### Task 2: Replace Marker adapter with native MarkItDown adapter

**Files:**
- Create: `paperbrain/adapters/markitdown.py`
- Delete: `paperbrain/adapters/marker.py`
- Modify: `paperbrain/adapters/parser_factory.py`
- Create: `tests/test_markitdown_parser.py`
- Delete: `tests/test_marker_parser.py`
- Modify: `tests/test_parser_factory.py`

- [ ] **Step 1: Write failing parser factory + adapter tests**

```python
# tests/test_parser_factory.py
from paperbrain.adapters.docling import DoclingParser
from paperbrain.adapters.markitdown import MarkItDownParser

def test_build_pdf_parser_returns_markitdown() -> None:
    parser = build_pdf_parser("markitdown", ocr_enabled=False)
    assert isinstance(parser, MarkItDownParser)

def test_build_pdf_parser_rejects_marker_value() -> None:
    with pytest.raises(ValueError, match='Use "markitdown"'):
        build_pdf_parser("marker", ocr_enabled=False)
```

```python
# tests/test_markitdown_parser.py
def test_markitdown_parser_raises_when_markitdown_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_import_module(name: str) -> object:
        raise ModuleNotFoundError(name=name)
    monkeypatch.setattr("paperbrain.adapters.markitdown.import_module", fake_import_module)
    with pytest.raises(RuntimeError, match="markitdown"):
        MarkItDownParser().parse_pdf(tmp_path / "paper.pdf")

def test_markitdown_parser_requires_ocr_plugin_when_ocr_enabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "paperbrain.adapters.markitdown.import_module",
        lambda name: (_ for _ in ()).throw(ModuleNotFoundError(name=name)) if name == "markitdown_ocr" else object(),
    )
    with pytest.raises(RuntimeError, match="markitdown-ocr"):
        MarkItDownParser(ocr_enabled=True).create_converter()
```

- [ ] **Step 2: Run targeted tests to verify failure**

Run: `python3 -m pytest -q tests/test_parser_factory.py tests/test_markitdown_parser.py`  
Expected: FAIL because `MarkItDownParser` and factory wiring do not exist yet.

- [ ] **Step 3: Implement MarkItDown adapter and factory wiring**

```python
# paperbrain/adapters/markitdown.py
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path

from paperbrain.adapters.docling import DoclingParser
from paperbrain.models import ParsedPaper


@dataclass(slots=True)
class _MarkItDownConversionResult:
    markdown: str
    metadata: object
    title: str | None = None


class _MarkItDownConverterAdapter:
    def __init__(self, converter: object) -> None:
        self._converter = converter

    def convert(self, file_path: str) -> _MarkItDownConversionResult:
        result = self._converter.convert(file_path)
        markdown = getattr(result, "text_content", "")
        title = getattr(result, "title", None)
        metadata = getattr(result, "metadata", None)
        return _MarkItDownConversionResult(markdown=str(markdown), metadata=metadata, title=title)


class MarkItDownParser:
    def __init__(self, *, ocr_enabled: bool = False) -> None:
        self.ocr_enabled = ocr_enabled
        self._docling_parser = DoclingParser()

    def create_converter(self) -> object:
        try:
            markitdown_module = import_module("markitdown")
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "markitdown is required for PDF parsing. Install it with `pip install 'markitdown[pdf]'`."
            ) from exc
        if self.ocr_enabled:
            try:
                import_module("markitdown_ocr")
            except ModuleNotFoundError as exc:
                raise RuntimeError(
                    "OCR for markitdown requires `markitdown-ocr`. Install it, or set ocr_enabled=false."
                ) from exc
        markitdown_type = getattr(markitdown_module, "MarkItDown", None)
        if markitdown_type is None:
            raise RuntimeError("markitdown installation is invalid: MarkItDown class is missing.")
        converter = markitdown_type(enable_plugins=self.ocr_enabled)
        return _MarkItDownConverterAdapter(converter)

    def parse_pdf(self, path: Path) -> ParsedPaper:
        converter = self.create_converter()
        return self.parse_pdf_with_converter(path, converter)

    def parse_pdf_with_converter(self, path: Path, converter: object) -> ParsedPaper:
        return self._docling_parser.parse_pdf_with_converter(path, converter)
```

```python
# paperbrain/adapters/parser_factory.py
from paperbrain.adapters.docling import DoclingParser
from paperbrain.adapters.markitdown import MarkItDownParser
from paperbrain.config import normalize_pdf_parser

def build_pdf_parser(pdf_parser: str, *, ocr_enabled: bool) -> Parser:
    normalized = normalize_pdf_parser(pdf_parser)
    if normalized == "markitdown":
        return MarkItDownParser(ocr_enabled=ocr_enabled)
    if normalized == "docling":
        return DoclingParser(ocr_enabled=ocr_enabled)
    raise ValueError(
        'Invalid pdf_parser in configuration file. Allowed values: docling, markitdown. '
        'Marker support was removed. Use "markitdown".'
    )
```

- [ ] **Step 4: Run targeted tests to verify pass**

Run: `python3 -m pytest -q tests/test_parser_factory.py tests/test_markitdown_parser.py`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperbrain/adapters/markitdown.py paperbrain/adapters/parser_factory.py \
  tests/test_markitdown_parser.py tests/test_parser_factory.py
git rm paperbrain/adapters/marker.py tests/test_marker_parser.py
git commit -m "feat: replace marker adapter with markitdown parser"
```

### Task 3: Align runtime/worker tests with MarkItDown defaults

**Files:**
- Modify: `tests/test_parser_worker.py`
- Modify: `tests/test_setup_command.py`
- Modify: `tests/test_summary_provider.py`
- Modify: `paperbrain/summary_provider.py`

- [ ] **Step 1: Write failing tests for parser-name propagation**

```python
# tests/test_parser_worker.py
parser_worker._worker_main(connection, parser_name="markitdown", ocr_enabled=True)
assert captured["pdf_parser"] == "markitdown"
```

```python
# tests/test_setup_command.py
calls["parse_worker_factory"]()
assert calls["worker_args"] == ("markitdown", False)
```

```python
# tests/test_summary_provider.py
assert captured["pdf_parser"] == "markitdown"
```

- [ ] **Step 2: Run targeted tests to verify failure**

Run: `python3 -m pytest -q tests/test_parser_worker.py tests/test_setup_command.py tests/test_summary_provider.py -k "parser or worker"`  
Expected: FAIL where tests still expect `"marker"`.

- [ ] **Step 3: Implement minimal runtime wiring adjustments**

```python
# paperbrain/summary_provider.py (constructor fragment)
self.parser = build_pdf_parser(
    self.config.pdf_parser,
    ocr_enabled=self.config.ocr_enabled,
)
```

```python
# keep ingest worker factory unchanged except parser_name now comes from updated config default
parse_worker_factory = lambda: ParserParseWorker(
    parser_name=runtime.config.pdf_parser,
    ocr_enabled=runtime.config.ocr_enabled,
)
```

- [ ] **Step 4: Run targeted tests to verify pass**

Run: `python3 -m pytest -q tests/test_parser_worker.py tests/test_setup_command.py tests/test_summary_provider.py`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_parser_worker.py tests/test_setup_command.py tests/test_summary_provider.py paperbrain/summary_provider.py
git commit -m "test: align runtime and worker parser wiring with markitdown"
```

### Task 4: Update dependencies/docs and run full verification

**Files:**
- Modify: `pyproject.toml`
- Modify: `README.md`

- [ ] **Step 1: Write failing dependency/doc assertions**

```python
# tests/test_setup_command.py
def test_setup_defaults_pdf_parser_to_markitdown(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}
    def fake_run_setup(**kwargs: Any) -> str:
        captured.update(kwargs)
        return "ok"
    monkeypatch.setattr("paperbrain.cli.run_setup", fake_run_setup)
    result = CliRunner().invoke(app, ["setup", "--url", "postgresql://localhost:5432/paperbrain"])
    assert result.exit_code == 0
    assert captured["pdf_parser"] == "markitdown"
```

- [ ] **Step 2: Run targeted tests to verify failure**

Run: `python3 -m pytest -q tests/test_setup_command.py -k "defaults_pdf_parser"`  
Expected: FAIL until docs/dependency/default wiring is updated.

- [ ] **Step 3: Update dependency and README references**

```toml
# pyproject.toml (dependencies)
dependencies = [
  "typer>=0.12.0",
  "psycopg[binary]>=3.2.0",
  "openai>=1.51.0",
  "ollama>=0.4.7",
  "google-genai>=0.3.0",
  "docling>=2.9.0",
  "markitdown[pdf]>=0.1.0",
  "fastapi>=0.115.0",
  "jinja2>=3.1.4",
  "uvicorn>=0.30.0",
]
```

```markdown
# README.md snippets
- `markitdown[pdf]` — default PDF parsing
- `docling` — alternate PDF parser
- `ocr_enabled=true` with `pdf_parser="markitdown"` requires `markitdown-ocr`
```

- [ ] **Step 4: Run full test suite**

Run: `python3 -m pytest -q`  
Expected: all tests pass (plus existing skips).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml README.md tests/test_setup_command.py
git commit -m "docs: switch default pdf parser docs and deps to markitdown"
```

## Final Validation Commands

Run these before opening PR:

```bash
python3 -m pytest -q tests/test_config.py tests/test_parser_factory.py tests/test_markitdown_parser.py
python3 -m pytest -q tests/test_parser_worker.py tests/test_setup_command.py tests/test_summary_provider.py
python3 -m pytest -q
```

Expected:
- Targeted parser/config/runtime tests: PASS
- Full suite: PASS (with any existing repo skips)
