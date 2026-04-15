# Ollama Cloud Summary Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Ollama Cloud as a summary provider selected by `summary_model=ollama:<model>`, while keeping OpenAI as the only embedding provider.

**Architecture:** Introduce a dedicated Ollama client and summary adapter, then extend existing provider-routing logic in setup and runtime paths. Persist `ollama_api_key` and `ollama_base_url` in config, route validation by summary-model prefix, and keep OpenAI embedding checks mandatory. Follow existing Gemini integration patterns to minimize risk and keep behavior explicit.

**Tech Stack:** Python 3.12, Typer CLI, pytest, official `ollama` Python SDK, existing OpenAI/Gemini adapters.

---

## File structure and responsibilities

- `paperbrain/adapters/ollama_client.py` (create): Ollama Cloud SDK wrapper with `summarize(text, model)` contract matching `SummaryClient`.
- `paperbrain/adapters/llm.py` (modify): add `OllamaSummaryAdapter` extending existing summary adapter behavior.
- `paperbrain/config.py` (modify): add `ollama_api_key` and `ollama_base_url` to persisted app config defaults/save/load.
- `paperbrain/services/setup.py` (modify): add Ollama summary-model detection + provider-aware setup validation for Ollama.
- `paperbrain/cli.py` (modify): add setup options for Ollama key/base URL and runtime summary provider routing for `ollama:`.
- `tests/test_ollama_client.py` (create): unit tests for Ollama client request/response mapping.
- `tests/test_config.py` (modify): persistence/backward-compat tests for new config fields.
- `tests/test_setup_command.py` (modify): setup option acceptance, provider-specific validation, runtime routing/fail-fast tests.
- `README.md` (modify): config/setup examples and provider-selection documentation for Ollama.
- `pyproject.toml` (modify): add `ollama` dependency.

---

### Task 1: Add Ollama SDK dependency and client wrapper

**Files:**
- Modify: `pyproject.toml`
- Create: `paperbrain/adapters/ollama_client.py`
- Test: `tests/test_ollama_client.py`

- [ ] **Step 1: Write failing Ollama client tests**

```python
# tests/test_ollama_client.py
from typing import Any


def test_ollama_client_summarize_uses_chat_and_strips_response() -> None:
    from paperbrain.adapters.ollama_client import OllamaCloudClient

    class FakeSDKClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def chat(self, *, model: str, messages: list[dict[str, str]]) -> dict[str, Any]:
            self.calls.append({"model": model, "messages": messages})
            return {"message": {"content": "  ollama summary  \n"}}

    sdk_client = FakeSDKClient()
    client = OllamaCloudClient(api_key="ol-test", base_url="https://ollama.com", sdk_client=sdk_client)

    summary = client.summarize("paper text", model="llama3.1:8b")

    assert summary == "ollama summary"
    assert sdk_client.calls == [
        {
            "model": "llama3.1:8b",
            "messages": [{"role": "user", "content": "paper text"}],
        }
    ]


def test_ollama_client_summarize_handles_missing_content() -> None:
    from paperbrain.adapters.ollama_client import OllamaCloudClient

    class FakeSDKClient:
        def chat(self, *, model: str, messages: list[dict[str, str]]) -> dict[str, Any]:
            _ = model, messages
            return {"message": {}}

    client = OllamaCloudClient(api_key="ol-test", base_url="https://ollama.com", sdk_client=FakeSDKClient())
    assert client.summarize("paper text", model="llama3.1:8b") == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_ollama_client.py -v`  
Expected: FAIL with `ModuleNotFoundError` for `paperbrain.adapters.ollama_client`.

- [ ] **Step 3: Add dependency and minimal implementation**

```toml
# pyproject.toml (dependencies excerpt)
dependencies = [
  "typer>=0.12.0",
  "psycopg[binary]>=3.2.0",
  "openai>=1.51.0",
  "google-genai>=0.3.0",
  "ollama>=0.4.7",
  "docling>=2.9.0",
  "fastapi>=0.115.0",
  "jinja2>=3.1.4",
  "uvicorn>=0.30.0",
]
```

```python
# paperbrain/adapters/ollama_client.py
from typing import Any


class OllamaCloudClient:
    def __init__(self, api_key: str, base_url: str, sdk_client: Any | None = None) -> None:
        if sdk_client is None:
            from ollama import Client

            headers = {"Authorization": f"Bearer {api_key.strip()}"} if api_key.strip() else None
            sdk_client = Client(host=base_url, headers=headers)
        self.sdk_client = sdk_client

    def summarize(self, text: str, model: str) -> str:
        response = self.sdk_client.chat(
            model=model,
            messages=[{"role": "user", "content": text}],
        )
        content = response.get("message", {}).get("content", "")
        return str(content).strip() if content is not None else ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_ollama_client.py -v`  
Expected: PASS (all tests in file).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml paperbrain/adapters/ollama_client.py tests/test_ollama_client.py
git commit -m "feat: add Ollama Cloud summary client"
```

---

### Task 2: Add Ollama fields to persisted configuration

**Files:**
- Modify: `paperbrain/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing config tests for new fields**

```python
def test_config_stores_ollama_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"
    store = ConfigStore(config_path)
    store.save(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="sk-test",
        gemini_api_key="gm-test",
        ollama_api_key="ol-test",
        ollama_base_url="https://ollama.com",
        summary_model="ollama:llama3.1:8b",
        embedding_model="text-embedding-3-small",
    )
    loaded = store.load()
    assert loaded.ollama_api_key == "ol-test"
    assert loaded.ollama_base_url == "https://ollama.com"


def test_load_legacy_config_defaults_ollama_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"
    config_path.write_text(
        '[paperbrain]\ndatabase_url = "postgresql://localhost:5432/paperbrain"\n',
        encoding="utf-8",
    )
    loaded = ConfigStore(config_path).load()
    assert loaded.ollama_api_key == ""
    assert loaded.ollama_base_url == "https://ollama.com"
```

- [ ] **Step 2: Run targeted config tests to verify failure**

Run: `python3 -m pytest tests/test_config.py -q`  
Expected: FAIL with unexpected keyword/attribute errors for `ollama_*`.

- [ ] **Step 3: Implement config model/save/load updates**

```python
# paperbrain/config.py (AppConfig excerpt)
@dataclass(slots=True)
class AppConfig:
    database_url: str
    openai_api_key: str
    summary_model: str
    embedding_model: str
    gemini_api_key: str = ""
    ollama_api_key: str = ""
    ollama_base_url: str = "https://ollama.com"
```

```python
# paperbrain/config.py (save signature excerpt)
def save(
    self,
    database_url: str,
    openai_api_key: str = "",
    gemini_api_key: str = "",
    ollama_api_key: str = "",
    ollama_base_url: str = "https://ollama.com",
    summary_model: str = DEFAULT_SUMMARY_MODEL,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
) -> None:
```

```python
# paperbrain/config.py (TOML body + load excerpt)
'ollama_api_key = "{ollama_api_key}"\n'
'ollama_base_url = "{ollama_base_url}"\n'
...
ollama_api_key = section.get("ollama_api_key", "")
if not isinstance(ollama_api_key, str):
    raise ValueError("Invalid ollama_api_key in configuration file")
ollama_base_url = section.get("ollama_base_url", "https://ollama.com")
if not isinstance(ollama_base_url, str):
    raise ValueError("Invalid ollama_base_url in configuration file")
...
return AppConfig(
    ...,
    gemini_api_key=gemini_api_key,
    ollama_api_key=ollama_api_key,
    ollama_base_url=ollama_base_url,
)
```

- [ ] **Step 4: Run config tests to verify pass**

Run: `python3 -m pytest tests/test_config.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperbrain/config.py tests/test_config.py
git commit -m "feat: persist Ollama credentials and base URL"
```

---

### Task 3: Add Ollama provider validation to setup service

**Files:**
- Modify: `paperbrain/services/setup.py`
- Test: `tests/test_setup_command.py` (setup validation sections)

- [ ] **Step 1: Write failing setup validation tests**

```python
def test_run_setup_uses_ollama_summary_validation_for_ollama_models(
    monkeypatch: Any, tmp_path: Path
) -> None:
    calls: dict[str, Any] = {"openai_embed": [], "ollama_summary": []}

    @contextmanager
    def fake_connect(database_url: str, *, autocommit: bool = False) -> Iterator[object]:
        _ = database_url, autocommit
        yield object()

    class FakeOpenAIClient:
        def __init__(self, api_key: str) -> None:
            _ = api_key

        def embed(self, chunks: list[str], model: str) -> list[list[float]]:
            calls["openai_embed"].append((chunks, model))
            return [[0.1]]

        def summarize(self, text: str, model: str) -> str:
            raise AssertionError("OpenAI summary must not run for ollama: models")

    class FakeOllamaClient:
        def __init__(self, api_key: str, base_url: str) -> None:
            calls["ollama_init"] = (api_key, base_url)

        def summarize(self, text: str, model: str) -> str:
            calls["ollama_summary"].append((text, model))
            return "ok"

    monkeypatch.setattr("paperbrain.services.setup.connect", fake_connect)
    monkeypatch.setattr("paperbrain.services.setup.OpenAIClient", FakeOpenAIClient)
    monkeypatch.setattr("paperbrain.services.setup.OllamaCloudClient", FakeOllamaClient, raising=False)

    run_setup(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="sk-test",
        ollama_api_key="ol-test",
        ollama_base_url="https://ollama.com",
        summary_model="ollama:llama3.1:8b",
        embedding_model="text-embedding-3-small",
        config_path=tmp_path / "paperbrain.conf",
        test_connections=True,
    )

    assert calls["ollama_init"] == ("ol-test", "https://ollama.com")
    assert calls["ollama_summary"] == [("paperbrain connectivity check", "llama3.1:8b")]
```

```python
def test_run_setup_ollama_validation_failure_has_context(monkeypatch: Any, tmp_path: Path) -> None:
    ...
    with pytest.raises(RuntimeError, match=r"Setup failed during Ollama validation: Ollama API key is required when testing connections"):
        run_setup(
            database_url="postgresql://localhost:5432/paperbrain",
            openai_api_key="sk-test",
            summary_model="ollama:llama3.1:8b",
            config_path=tmp_path / "paperbrain.conf",
            test_connections=True,
        )
```

- [ ] **Step 2: Run targeted setup tests to verify failure**

Run: `python3 -m pytest tests/test_setup_command.py -k "ollama and setup" -v`  
Expected: FAIL because `run_setup` has no Ollama validation path yet.

- [ ] **Step 3: Implement provider-aware Ollama validation**

```python
# paperbrain/services/setup.py (imports)
from paperbrain.adapters.ollama_client import OllamaCloudClient
```

```python
def _is_ollama_summary_model(summary_model: str) -> bool:
    return summary_model.strip().lower().startswith("ollama:")


def _strip_ollama_prefix(summary_model: str) -> str:
    return summary_model.strip()[len("ollama:") :].strip()


def _validate_ollama_summary_connection(
    ollama_api_key: str,
    ollama_base_url: str,
    summary_model: str,
) -> None:
    if not ollama_api_key.strip():
        raise ValueError("Ollama API key is required when testing connections")
    model = _strip_ollama_prefix(summary_model)
    if not model:
        raise ValueError("Ollama summary model must be non-empty after 'ollama:' prefix")
    client = OllamaCloudClient(api_key=ollama_api_key, base_url=ollama_base_url)
    client.summarize("paperbrain connectivity check", model=model)
```

```python
# run_setup signature + save call excerpt
def run_setup(
    ...,
    gemini_api_key: str = "",
    ollama_api_key: str = "",
    ollama_base_url: str = "https://ollama.com",
    summary_model: str = DEFAULT_SUMMARY_MODEL,
    ...
) -> str:
```

```python
# run_setup validation routing excerpt
summary_uses_gemini = _is_gemini_summary_model(summary_model)
summary_uses_ollama = _is_ollama_summary_model(summary_model)
...
if not summary_uses_gemini and not summary_uses_ollama:
    _validate_openai_summary_connection(openai_client, summary_model)
if summary_uses_gemini:
    ...
if summary_uses_ollama:
    try:
        _validate_ollama_summary_connection(
            ollama_api_key=ollama_api_key,
            ollama_base_url=ollama_base_url,
            summary_model=summary_model,
        )
    except Exception as exc:
        raise RuntimeError(f"Setup failed during Ollama validation: {exc}") from exc
```

- [ ] **Step 4: Run setup tests to verify pass**

Run: `python3 -m pytest tests/test_setup_command.py -k "setup and (gemini or ollama)" -v`  
Expected: PASS for setup validation coverage.

- [ ] **Step 5: Commit**

```bash
git add paperbrain/services/setup.py tests/test_setup_command.py
git commit -m "feat: validate Ollama summary provider during setup"
```

---

### Task 4: Add CLI runtime routing and setup options for Ollama

**Files:**
- Modify: `paperbrain/cli.py`
- Modify: `paperbrain/adapters/llm.py`
- Test: `tests/test_setup_command.py` (CLI setup/runtime routing sections)

- [ ] **Step 1: Write failing CLI/runtime tests**

```python
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
            "--url", "postgresql://localhost:5432/paperbrain",
            "--openai-api-key", "sk-test",
            "--ollama-api-key", "ol-test",
            "--ollama-base-url", "https://ollama.com",
            "--summary-model", "ollama:llama3.1:8b",
        ],
    )
    assert result.exit_code == 0
    assert calls["ollama_api_key"] == "ol-test"
    assert calls["ollama_base_url"] == "https://ollama.com"
```

```python
def test_build_runtime_requires_ollama_key_for_ollama_summary_model(
    monkeypatch: Any, tmp_path: Path
) -> None:
    ...
    with pytest.raises(ValueError, match="Ollama API key is required for Ollama summary models"):
        build_runtime(config_path)
```

```python
def test_cli_summarize_routes_ollama_models_through_ollama_summary_adapter(
    monkeypatch: Any, tmp_path: Path
) -> None:
    ...
    assert calls["summary_model"] == "llama3.1:8b"  # prefix stripped
    assert calls["summary_client_seen"] is True
```

- [ ] **Step 2: Run targeted CLI/runtime tests to verify failure**

Run: `python3 -m pytest tests/test_setup_command.py -k "ollama and (build_runtime or cli_setup or summarize_routes)" -v`  
Expected: FAIL because CLI has no Ollama options/routing.

- [ ] **Step 3: Implement CLI routing and adapter exposure**

```python
# paperbrain/adapters/llm.py
class OllamaSummaryAdapter(OpenAISummaryAdapter):
    pass
```

```python
# paperbrain/cli.py imports excerpt
from paperbrain.adapters.llm import (
    GeminiSummaryAdapter,
    LLMAdapter,
    OllamaSummaryAdapter,
    OpenAISummaryAdapter,
)
from paperbrain.adapters.ollama_client import OllamaCloudClient
```

```python
# paperbrain/cli.py helpers excerpt
def _is_ollama_summary_model(summary_model: str) -> bool:
    return summary_model.strip().lower().startswith("ollama:")


def _strip_ollama_prefix(summary_model: str) -> str:
    return summary_model.strip()[len("ollama:") :].strip()
```

```python
# build_runtime excerpt
summary_uses_gemini = _is_gemini_summary_model(summary_model)
summary_uses_ollama = _is_ollama_summary_model(summary_model)
if not config.openai_api_key.strip():
    raise ValueError("OpenAI API key is required for embeddings")
if summary_uses_gemini and not config.gemini_api_key.strip():
    raise ValueError("Gemini API key is required for Gemini summary models")
if summary_uses_ollama and not config.ollama_api_key.strip():
    raise ValueError("Ollama API key is required for Ollama summary models")

openai_client = OpenAIClient(api_key=config.openai_api_key)
if summary_uses_gemini:
    summary_client = GeminiClient(api_key=config.gemini_api_key)
    llm: LLMAdapter = GeminiSummaryAdapter(client=summary_client, model=summary_model)
elif summary_uses_ollama:
    ollama_model = _strip_ollama_prefix(summary_model)
    if not ollama_model:
        raise ValueError("Ollama summary model must be non-empty after 'ollama:' prefix")
    summary_client = OllamaCloudClient(api_key=config.ollama_api_key, base_url=config.ollama_base_url)
    llm = OllamaSummaryAdapter(client=summary_client, model=ollama_model)
else:
    llm = OpenAISummaryAdapter(client=openai_client, model=summary_model)
```

```python
# setup command options excerpt
ollama_api_key: str | None = typer.Option(None, "--ollama-api-key", help="Ollama Cloud API key"),
ollama_base_url: str = typer.Option("https://ollama.com", "--ollama-base-url"),
...
if ollama_api_key is not None:
    resolved_ollama_api_key = ollama_api_key.strip()
else:
    resolved_ollama_api_key = os.getenv("OLLAMA_API_KEY", "").strip()
...
message = run_setup(
    ...,
    ollama_api_key=resolved_ollama_api_key,
    ollama_base_url=ollama_base_url,
    ...
)
```

- [ ] **Step 4: Run targeted CLI/runtime tests to verify pass**

Run: `python3 -m pytest tests/test_setup_command.py -k "ollama and (build_runtime or summarize_routes or setup_accepts)" -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperbrain/cli.py paperbrain/adapters/llm.py tests/test_setup_command.py
git commit -m "feat: route ollama summary models in CLI runtime"
```

---

### Task 5: Update docs and run regression suite

**Files:**
- Modify: `README.md`
- Validate: `tests/test_config.py`, `tests/test_setup_command.py`, `tests/test_ollama_client.py`, full suite

- [ ] **Step 1: Update README config and setup examples**

```markdown
paperbrain setup \
  --url postgresql://<user>:<pass>@localhost:5432/paperbrain \
  --openai-api-key $OPENAI_API_KEY \
  --ollama-api-key $OLLAMA_API_KEY \
  --ollama-base-url https://ollama.com \
  --summary-model ollama:llama3.1:8b
```

```toml
[paperbrain]
database_url = "postgresql://<user>:<pass>@localhost:5432/paperbrain"
openai_api_key = "sk-..."
gemini_api_key = "AIza..."
ollama_api_key = "ol_..."
ollama_base_url = "https://ollama.com"
summary_model = "ollama:llama3.1:8b"
embedding_model = "text-embedding-3-small"
```

```markdown
Summary provider is selected from the summary model prefix:
- `gemini-*` -> Gemini summaries
- `ollama:*` -> Ollama summaries
- otherwise -> OpenAI summaries
```

- [ ] **Step 2: Run focused regression tests**

Run: `python3 -m pytest tests/test_config.py tests/test_setup_command.py tests/test_ollama_client.py -q`  
Expected: PASS.

- [ ] **Step 3: Run full test suite**

Run: `python3 -m pytest -q`  
Expected: PASS (all tests green, with existing skip count unchanged unless intentionally updated).

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document Ollama Cloud summary configuration"
```

```bash
git add -A
git commit -m "test: finalize Ollama summary provider regression coverage"
```

---

## Self-review checklist (completed)

1. **Spec coverage:** all spec requirements map to tasks:
   - Ollama summary provider + prefix routing: Tasks 1, 3, 4
   - OpenAI embeddings unchanged: Tasks 3, 4 tests/assertions
   - Config/setup additions: Tasks 2, 3, 4
   - Tests/docs updates: Tasks 1, 2, 4, 5
2. **Placeholder scan:** no TBD/TODO placeholders remain.
3. **Type/contract consistency:** `summary_model` prefix contract (`ollama:`) and stripped model handling are consistent across setup, runtime, tests, and docs.
