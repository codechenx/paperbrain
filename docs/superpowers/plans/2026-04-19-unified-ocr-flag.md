# Unified OCR Flag for Marker + Docling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace parser-specific OCR config with one required `ocr_enabled` flag shared by Marker and Docling, defaulting to disabled.

**Architecture:** Rename the OCR config/CLI/setup contract from `docling_ocr_enabled` to `ocr_enabled`, then thread that single boolean through runtime parser construction. Keep parser selection unchanged (`pdf_parser`), but update factory and parser adapters so both backends consume the same OCR setting. Enforce strict config validation (missing `ocr_enabled` invalid) and update docs/tests to match.

**Tech Stack:** Python 3.12, Typer CLI, pytest, marker-pdf, docling.

---

## File Structure

- **Modify:** `paperbrain/config.py` — unified OCR config constant/field/save/load validation.
- **Modify:** `paperbrain/services/setup.py` — run_setup signature/plumbing for `ocr_enabled`.
- **Modify:** `paperbrain/cli.py` — setup flag rename to `--ocr-enabled`.
- **Modify:** `paperbrain/summary_provider.py` — factory call now uses `config.ocr_enabled`.
- **Modify:** `paperbrain/adapters/parser_factory.py` — signature rename to `ocr_enabled`, pass to both parsers.
- **Modify:** `paperbrain/adapters/marker.py` — accept OCR flag and map to Marker converter config (`force_ocr`).
- **Modify:** `tests/test_config.py` — strict required `ocr_enabled` contract.
- **Modify:** `tests/test_setup_command.py` — setup flag rename and runtime wiring assertions.
- **Modify:** `tests/test_summary_provider.py` — parser factory call assertions with `ocr_enabled`.
- **Modify:** `tests/test_parser_factory.py` — signature and behavior checks.
- **Modify:** `tests/test_marker_parser.py` — Marker OCR config mapping tests.
- **Modify:** `README.md` — user-facing config/CLI docs for unified OCR flag.

---

### Task 1: Replace config contract with required `ocr_enabled`

**Files:**
- Modify: `tests/test_config.py`
- Modify: `paperbrain/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing config tests for unified OCR key**

```python
def test_save_and_load_config_round_trip(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"
    store = ConfigStore(config_path)
    store.save(database_url="postgresql://localhost:5432/paperbrain")
    loaded = store.load()
    assert loaded.ocr_enabled is False


def test_load_rejects_missing_ocr_enabled_key(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"
    config_path.write_text(
        (
            "[paperbrain]\n"
            'database_url = "postgresql://localhost:5432/paperbrain"\n'
            "embeddings_enabled = false\n"
            'pdf_parser = "marker"\n'
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="ocr_enabled"):
        ConfigStore(config_path).load()


def test_load_rejects_legacy_docling_ocr_enabled_without_ocr_enabled(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"
    config_path.write_text(
        (
            "[paperbrain]\n"
            'database_url = "postgresql://localhost:5432/paperbrain"\n'
            "embeddings_enabled = false\n"
            "docling_ocr_enabled = true\n"
            'pdf_parser = "docling"\n'
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="ocr_enabled"):
        ConfigStore(config_path).load()
```

- [ ] **Step 2: Run config tests to verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_config.py`  
Expected: FAIL due to missing `ocr_enabled` implementation.

- [ ] **Step 3: Implement unified OCR config contract**

```python
# paperbrain/config.py
DEFAULT_OCR_ENABLED = False

@dataclass(slots=True)
class AppConfig:
    ...
    embeddings_enabled: bool = DEFAULT_EMBEDDINGS_ENABLED
    ocr_enabled: bool = DEFAULT_OCR_ENABLED
    pdf_parser: str = DEFAULT_PDF_PARSER
```

```python
# ConfigStore.save signature + rendered config body
def save(..., embeddings_enabled: bool = DEFAULT_EMBEDDINGS_ENABLED, ocr_enabled: bool = DEFAULT_OCR_ENABLED, pdf_parser: str = DEFAULT_PDF_PARSER) -> None:
    body = (
        ...
        "embeddings_enabled = {embeddings_enabled}\n"
        "ocr_enabled = {ocr_enabled}\n"
        'pdf_parser = "{pdf_parser}"\n'
    ).format(..., ocr_enabled=str(ocr_enabled).lower(), ...)
```

```python
# ConfigStore.load validation path
if "ocr_enabled" not in section:
    raise ValueError("Missing ocr_enabled in configuration file")
ocr_enabled = section["ocr_enabled"]
if not isinstance(ocr_enabled, bool):
    raise ValueError("Invalid ocr_enabled in configuration file")

return AppConfig(..., embeddings_enabled=embeddings_enabled, ocr_enabled=ocr_enabled, pdf_parser=normalized_pdf_parser, ...)
```

- [ ] **Step 4: Re-run config tests to verify GREEN**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_config.py`  
Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add paperbrain/config.py tests/test_config.py
git commit -m "feat: require unified ocr_enabled config flag"
```

---

### Task 2: Rename setup/CLI OCR flag and pass-through

**Files:**
- Modify: `tests/test_setup_command.py`
- Modify: `paperbrain/services/setup.py`
- Modify: `paperbrain/cli.py`
- Test: `tests/test_setup_command.py`

- [ ] **Step 1: Add failing setup/CLI tests for `--ocr-enabled`**

```python
def test_cli_setup_accepts_ocr_enabled_flag(monkeypatch: Any) -> None:
    calls: dict[str, Any] = {}

    def fake_run_setup(**kwargs: Any) -> str:
        calls.update(kwargs)
        return "ok"

    monkeypatch.setattr("paperbrain.cli.run_setup", fake_run_setup)
    result = CliRunner().invoke(
        app,
        [
            "setup",
            "--url", "postgresql://localhost:5432/paperbrain",
            "--openai-api-key", "sk-test",
            "--summary-model", "openai:gpt-4.1-mini",
            "--ocr-enabled",
        ],
    )
    assert result.exit_code == 0
    assert calls["ocr_enabled"] is True
```

```python
def test_run_setup_writes_project_config(tmp_path: Path) -> None:
    ...
    loaded = ConfigStore(config_path).load()
    assert loaded.ocr_enabled is False
```

- [ ] **Step 2: Run setup tests to verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_setup_command.py`  
Expected: FAIL for missing `ocr_enabled` plumbing and missing `--ocr-enabled` flag.

- [ ] **Step 3: Implement setup and CLI rename**

```python
# paperbrain/services/setup.py
def run_setup(
    ...,
    embeddings_enabled: bool = DEFAULT_EMBEDDINGS_ENABLED,
    ocr_enabled: bool = False,
    pdf_parser: str = DEFAULT_PDF_PARSER,
    ...
) -> str:
    ...
    store.save(
        ...,
        embeddings_enabled=embeddings_enabled,
        ocr_enabled=ocr_enabled,
        pdf_parser=normalized_pdf_parser,
    )
```

```python
# paperbrain/cli.py setup()
ocr_enabled: bool = typer.Option(
    False,
    "--ocr-enabled/--no-ocr-enabled",
),

message = run_setup(
    ...,
    embeddings_enabled=embeddings_enabled,
    ocr_enabled=ocr_enabled,
    pdf_parser=pdf_parser,
    ...
)
```

- [ ] **Step 4: Re-run setup tests to verify GREEN**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_setup_command.py`  
Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```bash
git add paperbrain/services/setup.py paperbrain/cli.py tests/test_setup_command.py
git commit -m "feat: rename setup OCR flag to parser-agnostic ocr_enabled"
```

---

### Task 3: Unify runtime parser wiring with `ocr_enabled`

**Files:**
- Modify: `tests/test_summary_provider.py`
- Modify: `tests/test_parser_factory.py`
- Modify: `paperbrain/summary_provider.py`
- Modify: `paperbrain/adapters/parser_factory.py`
- Test: `tests/test_summary_provider.py`, `tests/test_parser_factory.py`

- [ ] **Step 1: Add failing parser factory + provider wiring tests**

```python
# tests/test_parser_factory.py
def test_build_pdf_parser_returns_docling_with_ocr() -> None:
    parser = build_pdf_parser("docling", ocr_enabled=True)
    assert isinstance(parser, DoclingParser)
    assert parser.ocr_enabled is True


def test_build_pdf_parser_returns_marker_with_ocr_flag() -> None:
    parser = build_pdf_parser("marker", ocr_enabled=True)
    assert isinstance(parser, MarkerParser)
    assert parser.ocr_enabled is True
```

```python
# tests/test_summary_provider.py
monkeypatch.setattr(
    "paperbrain.summary_provider.build_pdf_parser",
    lambda pdf_parser, *, ocr_enabled: captured.update({"pdf_parser": pdf_parser, "ocr_enabled": ocr_enabled}) or object(),
)
...
assert captured["ocr_enabled"] is True
```

- [ ] **Step 2: Run runtime wiring tests to verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_summary_provider.py tests/test_parser_factory.py`  
Expected: FAIL due to `docling_ocr_enabled` signature mismatch.

- [ ] **Step 3: Implement unified runtime wiring**

```python
# paperbrain/adapters/parser_factory.py
def build_pdf_parser(pdf_parser: str, *, ocr_enabled: bool) -> Parser:
    normalized = normalize_pdf_parser(pdf_parser)
    if normalized == "marker":
        return MarkerParser(ocr_enabled=ocr_enabled)
    if normalized == "docling":
        return DoclingParser(ocr_enabled=ocr_enabled)
    raise ValueError("Invalid pdf_parser in configuration file. Allowed values: docling, marker")
```

```python
# paperbrain/summary_provider.py
self.parser = build_pdf_parser(
    self.config.pdf_parser,
    ocr_enabled=self.config.ocr_enabled,
)
```

- [ ] **Step 4: Re-run runtime wiring tests to verify GREEN**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_summary_provider.py tests/test_parser_factory.py`  
Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```bash
git add paperbrain/adapters/parser_factory.py paperbrain/summary_provider.py tests/test_summary_provider.py tests/test_parser_factory.py
git commit -m "feat: route unified ocr_enabled through parser factory"
```

---

### Task 4: Add Marker OCR mapping (`force_ocr`) and tests

**Files:**
- Modify: `tests/test_marker_parser.py`
- Modify: `paperbrain/adapters/marker.py`
- Test: `tests/test_marker_parser.py`

- [ ] **Step 1: Add failing Marker OCR mapping tests**

```python
def test_marker_parser_passes_force_ocr_true_when_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("fake", encoding="utf-8")
    captured: dict[str, object] = {}

    class FakePdfConverter:
        def __init__(self, artifact_dict: dict[str, str], config: dict[str, object] | None = None) -> None:
            captured["config"] = config
        def __call__(self, file_path: str) -> dict[str, str]:
            return {"path": file_path}
    ...
    MarkerParser(ocr_enabled=True).parse_pdf(pdf_path)
    assert captured["config"] == {"force_ocr": True}
```

```python
def test_marker_parser_passes_no_force_ocr_when_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ...
    MarkerParser(ocr_enabled=False).parse_pdf(pdf_path)
    assert captured["config"] in (None, {})
```

- [ ] **Step 2: Run Marker parser tests to verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_marker_parser.py`  
Expected: FAIL because `MarkerParser` has no OCR flag mapping.

- [ ] **Step 3: Implement Marker OCR mapping**

```python
# paperbrain/adapters/marker.py
class MarkerParser:
    def __init__(self, *, ocr_enabled: bool = False) -> None:
        self.ocr_enabled = ocr_enabled
        self._docling_parser = DoclingParser()

    def create_converter(self) -> object:
        ...
        converter_kwargs: dict[str, object] = {"artifact_dict": create_model_dict()}
        if self.ocr_enabled:
            converter_kwargs["config"] = {"force_ocr": True}
        converter = PdfConverter(**converter_kwargs)
        return _MarkerConverterAdapter(converter=converter, text_from_rendered=text_from_rendered)
```

- [ ] **Step 4: Re-run Marker parser tests to verify GREEN**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_marker_parser.py`  
Expected: PASS.

- [ ] **Step 5: Commit Task 4**

```bash
git add paperbrain/adapters/marker.py tests/test_marker_parser.py
git commit -m "feat: support unified OCR toggle in marker parser"
```

---

### Task 5: Update docs and run regression/full verification

**Files:**
- Modify: `README.md`
- Modify: `tests/test_setup_command.py` (any remaining runtime monkeypatch callsites)
- Modify: `tests/test_config.py` (any remaining legacy key references)
- Test: targeted regression + full suite

- [ ] **Step 1: Update README to unified OCR naming**

```markdown
# setup flag
paperbrain setup ... --pdf-parser docling --ocr-enabled

# config shape
ocr_enabled = false
pdf_parser = "marker"

# behavior
- `ocr_enabled` is required and shared across marker/docling parsers.
- Default is `ocr_enabled = false`.
```

- [ ] **Step 2: Run targeted regression suite**

Run:  
`PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_config.py tests/test_setup_command.py tests/test_summary_provider.py tests/test_parser_factory.py tests/test_marker_parser.py tests/test_ingest_service.py tests/test_docling_worker.py`

Expected: PASS.

- [ ] **Step 3: Run full suite**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q`  
Expected: PASS (with existing optional skip only).

- [ ] **Step 4: Commit docs + final cleanups**

```bash
git add README.md tests/test_config.py tests/test_setup_command.py tests/test_summary_provider.py tests/test_parser_factory.py tests/test_marker_parser.py
git commit -m "docs: document unified ocr_enabled behavior"
```

