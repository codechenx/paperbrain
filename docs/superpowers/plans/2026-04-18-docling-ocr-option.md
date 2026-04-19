# Docling OCR Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent Docling OCR configuration toggle (default disabled), require both OCR and embeddings booleans in config loading, and wire OCR behavior into parser construction.

**Architecture:** Extend the config contract first (tests + strict loading), then wire setup/CLI persistence, and finally pass the config flag into `SummaryProvider` and `DoclingParser` converter creation. Keep ingest behavior unchanged (no per-run OCR override) and validate behavior with focused unit/CLI tests before running the full suite.

**Tech Stack:** Python 3, Typer CLI, pytest, Docling adapter integration.

---

## File Structure

- **Modify:** `paperbrain/config.py`
  - Add `docling_ocr_enabled` config field and strict load-time validation for both `embeddings_enabled` and `docling_ocr_enabled`.
- **Modify:** `paperbrain/services/setup.py`
  - Accept/persist the OCR toggle through setup service.
- **Modify:** `paperbrain/cli.py`
  - Add `--docling-ocr-enabled/--no-docling-ocr-enabled` setup option and pass through to `run_setup`.
- **Modify:** `paperbrain/summary_provider.py`
  - Construct parser with configured OCR setting.
- **Modify:** `paperbrain/adapters/docling.py`
  - Store parser OCR state and apply it while constructing the Docling converter.
- **Modify/Test:** `tests/test_config.py`
  - Cover strict required booleans and OCR config round-trips.
- **Modify/Test:** `tests/test_setup_command.py`
  - Cover setup CLI/service wiring for OCR flag.
- **Modify/Test:** `tests/test_ingest_service.py`
  - Cover converter-construction OCR wiring.
- **Modify/Test:** `tests/test_summary_provider.py`
  - Cover parser construction with OCR toggle.
- **Modify:** `README.md`
  - Document new setup option and config key.

---

### Task 1: Lock down config contract (required booleans + OCR field)

**Files:**
- Modify: `tests/test_config.py`
- Modify: `paperbrain/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing config tests for required booleans and OCR round-trip**

```python
def test_save_and_load_config_round_trip(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"
    store = ConfigStore(config_path)
    store.save(database_url="postgresql://localhost:5432/paperbrain")
    loaded = store.load()
    assert loaded.embeddings_enabled is False
    assert loaded.docling_ocr_enabled is False


@pytest.mark.parametrize("missing_key", ["embeddings_enabled", "docling_ocr_enabled"])
def test_load_rejects_missing_required_boolean_flags(tmp_path: Path, missing_key: str) -> None:
    config_path = tmp_path / "paperbrain.conf"
    lines = [
        "[paperbrain]",
        'database_url = "postgresql://localhost:5432/paperbrain"',
        "embeddings_enabled = false",
        "docling_ocr_enabled = false",
    ]
    lines = [line for line in lines if not line.startswith(f"{missing_key} =")]
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=missing_key):
        ConfigStore(config_path).load()
```

- [ ] **Step 2: Run the focused config tests (expect FAIL)**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_config.py`

Expected: FAIL with missing `docling_ocr_enabled` attribute/validation behavior.

- [ ] **Step 3: Implement strict config behavior in `paperbrain/config.py`**

```python
DEFAULT_DOCLING_OCR_ENABLED = False


@dataclass(slots=True)
class AppConfig:
    database_url: str
    openai_api_key: str
    summary_model: str
    embedding_model: str
    embeddings_enabled: bool
    docling_ocr_enabled: bool = DEFAULT_DOCLING_OCR_ENABLED
```

```python
# ConfigStore.save() new body line
'docling_ocr_enabled = {docling_ocr_enabled}\n'
```

```python
# ConfigStore.load() strict required fields
if "embeddings_enabled" not in section:
    raise ValueError("Missing embeddings_enabled in configuration file")
embeddings_enabled = section["embeddings_enabled"]
if not isinstance(embeddings_enabled, bool):
    raise ValueError("Invalid embeddings_enabled in configuration file")

if "docling_ocr_enabled" not in section:
    raise ValueError("Missing docling_ocr_enabled in configuration file")
docling_ocr_enabled = section["docling_ocr_enabled"]
if not isinstance(docling_ocr_enabled, bool):
    raise ValueError("Invalid docling_ocr_enabled in configuration file")
```

- [ ] **Step 4: Re-run config tests (expect PASS)**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_config.py`

Expected: PASS.

- [ ] **Step 5: Commit Task 1 changes**

```bash
git add tests/test_config.py paperbrain/config.py
git commit -m "feat: require boolean config flags for embeddings and docling OCR"
```

---

### Task 2: Wire OCR toggle through setup service and CLI

**Files:**
- Modify: `tests/test_setup_command.py`
- Modify: `paperbrain/services/setup.py`
- Modify: `paperbrain/cli.py`
- Test: `tests/test_setup_command.py`

- [ ] **Step 1: Add failing setup/CLI wiring tests**

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
    assert loaded.docling_ocr_enabled is False


def test_cli_setup_accepts_docling_ocr_enabled_flag(monkeypatch: Any) -> None:
    calls: dict[str, Any] = {}
    def fake_run_setup(**kwargs: Any) -> str:
        calls.update(kwargs)
        return "ok"
    monkeypatch.setattr("paperbrain.cli.run_setup", fake_run_setup)
    result = CliRunner().invoke(
        app,
        ["setup", "--url", "postgresql://localhost:5432/paperbrain", "--docling-ocr-enabled"],
    )
    assert result.exit_code == 0
    assert calls["docling_ocr_enabled"] is True
```

- [ ] **Step 2: Run setup tests (expect FAIL)**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_setup_command.py`

Expected: FAIL because `run_setup`/CLI do not yet accept `docling_ocr_enabled`.

- [ ] **Step 3: Implement setup + CLI plumbing**

```python
# paperbrain/services/setup.py
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
    config_path: Path = Path.home() / ".config" / "paperbrain" / "paperbrain.conf",
    test_connections: bool = True,
) -> str:
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
    )
```

```python
# paperbrain/cli.py setup command args
docling_ocr_enabled: bool = typer.Option(
    False,
    "--docling-ocr-enabled/--no-docling-ocr-enabled",
),
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
    config_path=config_path,
    test_connections=test_connections,
)
```

- [ ] **Step 4: Re-run setup tests (expect PASS)**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_setup_command.py`

Expected: PASS.

- [ ] **Step 5: Commit Task 2 changes**

```bash
git add tests/test_setup_command.py paperbrain/services/setup.py paperbrain/cli.py
git commit -m "feat: add setup wiring for docling OCR toggle"
```

---

### Task 3: Apply OCR setting in parser construction and converter wiring

**Files:**
- Modify: `tests/test_summary_provider.py`
- Modify: `tests/test_ingest_service.py`
- Modify: `paperbrain/summary_provider.py`
- Modify: `paperbrain/adapters/docling.py`
- Test: `tests/test_summary_provider.py`, `tests/test_ingest_service.py`

- [ ] **Step 1: Add failing tests for parser wiring**

```python
def test_summary_provider_passes_docling_ocr_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyConfig:
        summary_model = "openai:gpt-4.1-mini"
        openai_api_key = "sk-test"
        embedding_model = "text-embedding-3-small"
        embeddings_enabled = True
        docling_ocr_enabled = True
        gemini_api_key = ""
        ollama_api_key = ""
        ollama_base_url = ""

    captured: dict[str, bool] = {}
    class FakeDoclingParser:
        def __init__(self, *, ocr_enabled: bool = False) -> None:
            captured["ocr_enabled"] = ocr_enabled
```

```python
def test_docling_parser_create_converter_respects_ocr_toggle(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    class FakePipelineOptions:
        def __init__(self) -> None:
            self.do_ocr = True
    class FakePdfFormatOption:
        def __init__(self, *, pipeline_options: object) -> None:
            captured["do_ocr"] = getattr(pipeline_options, "do_ocr", None)
    class FakeConverter:
        def __init__(self, *, format_options: object) -> None:
            captured["format_options"] = format_options

    # monkeypatch docling imports used in create_converter()
    parser = DoclingParser(ocr_enabled=False)
    parser.create_converter()
    assert captured["do_ocr"] is False
```

- [ ] **Step 2: Run parser/provider tests (expect FAIL)**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_summary_provider.py tests/test_ingest_service.py`

Expected: FAIL because `DoclingParser` does not yet accept/store OCR toggle.

- [ ] **Step 3: Implement parser + provider OCR wiring**

```python
# paperbrain/adapters/docling.py
class DoclingParser:
    def __init__(self, *, ocr_enabled: bool = False) -> None:
        self.ocr_enabled = ocr_enabled

    def create_converter(self) -> object:
        from docling.document_converter import DocumentConverter
        from docling.document_converter import PdfFormatOption
        from docling.datamodel.pipeline_options import PdfPipelineOptions

        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = self.ocr_enabled
        pdf_option = PdfFormatOption(pipeline_options=pipeline_options)
        return DocumentConverter(format_options={"pdf": pdf_option})
```

```python
# paperbrain/summary_provider.py
self.parser = DoclingParser(ocr_enabled=self.config.docling_ocr_enabled)
```

- [ ] **Step 4: Re-run parser/provider tests (expect PASS)**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_summary_provider.py tests/test_ingest_service.py`

Expected: PASS.

- [ ] **Step 5: Commit Task 3 changes**

```bash
git add tests/test_summary_provider.py tests/test_ingest_service.py paperbrain/summary_provider.py paperbrain/adapters/docling.py
git commit -m "feat: apply configured docling OCR setting in parser"
```

---

### Task 4: Update docs and run regression verification

**Files:**
- Modify: `README.md`
- Test: full suite

- [ ] **Step 1: Update README setup/config documentation**

```markdown
# setup option list
--docling-ocr-enabled/--no-docling-ocr-enabled

# config example
embeddings_enabled = false
docling_ocr_enabled = false
```

- [ ] **Step 2: Run targeted regression for touched areas**

Run:  
`PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_config.py tests/test_setup_command.py tests/test_summary_provider.py tests/test_ingest_service.py`

Expected: PASS.

- [ ] **Step 3: Run full suite**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q`

Expected: PASS (all tests green, with existing optional skips only).

- [ ] **Step 4: Commit docs/final adjustments**

```bash
git add README.md
git commit -m "docs: document docling OCR setup and config option"
```
