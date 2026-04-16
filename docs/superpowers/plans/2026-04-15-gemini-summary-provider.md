# Gemini Summary Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Gemini as a summary-generation provider (selected by summary model prefix) while keeping OpenAI as the only embedding provider.

**Architecture:** Add a dedicated Gemini summary client and route summary adapter construction in CLI runtime based on `summary_model.startswith("gemini-")`. Extend config/setup to carry `gemini_api_key` and perform provider-aware summary validation, while preserving OpenAI embedding validation and all current non-summary flows.

**Tech Stack:** Python 3.12, Typer, OpenAI SDK, Google GenAI SDK, pytest

---

## File structure map

- **Create:** `paperbrain/adapters/gemini_client.py`
  - Gemini summarize API wrapper (`summarize(text, model)`).
- **Modify:** `paperbrain/config.py`
  - Add `gemini_api_key` to `AppConfig`, save/load behavior.
- **Modify:** `paperbrain/services/setup.py`
  - Add provider-aware summary validation branch.
- **Modify:** `paperbrain/cli.py`
  - Accept `--gemini-api-key` in setup command.
  - Build Gemini summary adapter when summary model prefix is `gemini-`.
- **Modify:** `paperbrain/adapters/llm.py`
  - Allow summary adapter constructor to accept either OpenAI or Gemini summary client type.
- **Create:** `tests/test_gemini_client.py`
  - Unit tests for Gemini summarize client behavior.
- **Modify:** `tests/test_config.py`
  - Add `gemini_api_key` coverage and legacy compatibility.
- **Modify:** `tests/test_setup_command.py`
  - Add setup/provider-routing tests and CLI option tests.
- **Modify:** `README.md`
  - Add `gemini_api_key`, setup usage, and provider-selection rule.

### Task 1: Red tests for config + setup provider-aware behavior

**Files:**
- Modify: `tests/test_config.py`
- Modify: `tests/test_setup_command.py`
- Test: `tests/test_config.py`
- Test: `tests/test_setup_command.py`

- [ ] **Step 1: Add failing config tests for new key**

```python
def test_config_stores_openai_and_gemini_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"
    store = ConfigStore(config_path)
    store.save(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="sk-openai",
        gemini_api_key="gm-test",
        summary_model="gpt-4.1-mini",
        embedding_model="text-embedding-3-small",
    )

    loaded = store.load()
    assert loaded.openai_api_key == "sk-openai"
    assert loaded.gemini_api_key == "gm-test"
```

- [ ] **Step 2: Add failing setup tests for provider-aware summary validation**

```python
def test_run_setup_uses_gemini_summary_validation_for_gemini_models(monkeypatch: Any, tmp_path: Path) -> None:
    calls: dict[str, Any] = {"openai_embed": [], "gemini_summary": []}

    @contextmanager
    def fake_connect(database_url: str, *, autocommit: bool = False) -> Iterator[object]:
        _ = database_url, autocommit
        yield object()

    class FakeOpenAIClient:
        def __init__(self, api_key: str) -> None:
            calls["openai_key"] = api_key

        def embed(self, chunks: list[str], model: str) -> list[list[float]]:
            calls["openai_embed"].append((chunks, model))
            return [[0.1]]

        def summarize(self, text: str, model: str) -> str:
            raise AssertionError("OpenAI summarize must not be used for gemini summary models")

    class FakeGeminiClient:
        def __init__(self, api_key: str) -> None:
            calls["gemini_key"] = api_key

        def summarize(self, text: str, model: str) -> str:
            calls["gemini_summary"].append((text, model))
            return "ok"

    monkeypatch.setattr("paperbrain.services.setup.connect", fake_connect)
    monkeypatch.setattr("paperbrain.services.setup.OpenAIClient", FakeOpenAIClient)
    monkeypatch.setattr("paperbrain.services.setup.GeminiClient", FakeGeminiClient)

    run_setup(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="sk-openai",
        gemini_api_key="gm-test",
        summary_model="gemini-2.5-flash",
        embedding_model="text-embedding-3-small",
        config_path=tmp_path / "paperbrain.conf",
        test_connections=True,
    )

    assert calls["openai_embed"] == [(["paperbrain connectivity check"], "text-embedding-3-small")]
    assert calls["gemini_summary"] == [("paperbrain connectivity check", "gemini-2.5-flash")]
```

- [ ] **Step 3: Add failing CLI setup option test**

```python
def test_cli_setup_accepts_gemini_api_key(monkeypatch: Any) -> None:
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
            "--openai-api-key",
            "sk-test",
            "--gemini-api-key",
            "gm-test",
        ],
    )
    assert result.exit_code == 0
    assert calls["gemini_api_key"] == "gm-test"
```

- [ ] **Step 4: Run focused tests and confirm fail**

Run:
```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_config.py tests/test_setup_command.py -q
```

Expected:
- FAIL due missing `gemini_api_key` support and setup branching.

- [ ] **Step 5: Commit red tests**

```bash
git add tests/test_config.py tests/test_setup_command.py
git commit -m "test: add failing gemini config and setup coverage" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 2: Implement config + setup provider-aware validation

**Files:**
- Modify: `paperbrain/config.py`
- Modify: `paperbrain/services/setup.py`
- Modify: `paperbrain/cli.py`
- Test: `tests/test_config.py`
- Test: `tests/test_setup_command.py`

- [ ] **Step 1: Extend config dataclass and save/load API**

```python
@dataclass(slots=True)
class AppConfig:
    database_url: str
    openai_api_key: str
    gemini_api_key: str
    summary_model: str
    embedding_model: str
```

```python
def save(
    self,
    database_url: str,
    openai_api_key: str = "",
    gemini_api_key: str = "",
    summary_model: str = DEFAULT_SUMMARY_MODEL,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
) -> None:
    body = (
        "[paperbrain]\n"
        'database_url = "{database_url}"\n'
        'openai_api_key = "{openai_api_key}"\n'
        'gemini_api_key = "{gemini_api_key}"\n'
        'summary_model = "{summary_model}"\n'
        'embedding_model = "{embedding_model}"\n'
    ).format(...)
```

- [ ] **Step 2: Add provider-aware setup validation logic**

```python
def _is_gemini_summary_model(summary_model: str) -> bool:
    return summary_model.strip().lower().startswith("gemini-")
```

```python
def _validate_summary_connection(*, summary_model: str, openai_api_key: str, gemini_api_key: str) -> None:
    probe = "paperbrain connectivity check"
    if _is_gemini_summary_model(summary_model):
        if not gemini_api_key.strip():
            raise ValueError("Gemini API key is required for Gemini summary models")
        GeminiClient(api_key=gemini_api_key).summarize(probe, model=summary_model)
        return
    if not openai_api_key.strip():
        raise ValueError("OpenAI API key is required for OpenAI summary models")
    OpenAIClient(api_key=openai_api_key).summarize(probe, model=summary_model)
```

```python
def _validate_embedding_connection(*, openai_api_key: str, embedding_model: str) -> None:
    if not openai_api_key.strip():
        raise ValueError("OpenAI API key is required when testing embedding connection")
    OpenAIClient(api_key=openai_api_key).embed(["paperbrain connectivity check"], model=embedding_model)
```

- [ ] **Step 3: Wire new setup option through CLI and service**

```python
@app.command()
def setup(
    url: str = typer.Option(..., "--url"),
    openai_api_key: str | None = typer.Option(None, "--openai-api-key"),
    gemini_api_key: str | None = typer.Option(None, "--gemini-api-key"),
    ...
) -> None:
    resolved_gemini_api_key = (gemini_api_key or os.getenv("GEMINI_API_KEY", "")).strip()
    ...
    message = run_setup(
        database_url=url,
        openai_api_key=resolved_openai_api_key,
        gemini_api_key=resolved_gemini_api_key,
        ...
    )
```

- [ ] **Step 4: Run focused tests and confirm pass**

Run:
```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_config.py tests/test_setup_command.py -q
```

Expected:
- PASS.

- [ ] **Step 5: Commit implementation**

```bash
git add paperbrain/config.py paperbrain/services/setup.py paperbrain/cli.py tests/test_config.py tests/test_setup_command.py
git commit -m "feat: add gemini key and provider-aware setup validation" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 3: Red tests for runtime summary-provider routing + Gemini client

**Files:**
- Create: `tests/test_gemini_client.py`
- Modify: `tests/test_setup_command.py`
- Test: `tests/test_gemini_client.py`
- Test: `tests/test_setup_command.py`

- [ ] **Step 1: Add failing Gemini client API test**

```python
def test_gemini_client_calls_models_generate_content() -> None:
    class FakeModels:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def generate_content(self, *, model: str, contents: str):
            self.calls.append({"model": model, "contents": contents})
            return type("Resp", (), {"text": "  gm output\n"})()

    fake_sdk = type("SDK", (), {"models": FakeModels()})()
    client = GeminiClient(api_key="gm-test", sdk_client=fake_sdk)
    summary = client.summarize("paper text", model="gemini-2.5-flash")
    assert summary == "gm output"
    assert fake_sdk.models.calls == [{"model": "gemini-2.5-flash", "contents": "paper text"}]
```

- [ ] **Step 2: Add failing runtime routing test in CLI summarize flow**

```python
def test_cli_summarize_uses_gemini_summary_adapter_when_summary_model_is_gemini(monkeypatch: Any, tmp_path: Path) -> None:
    calls: dict[str, Any] = {}
    config = AppConfig(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="sk-runtime",
        gemini_api_key="gm-runtime",
        summary_model="gemini-2.5-flash",
        embedding_model="text-embedding-3-small",
    )
    ...
    class FakeGeminiClient:
        def __init__(self, api_key: str) -> None:
            calls["gemini_key"] = api_key
    class FakeGeminiSummaryAdapter:
        def __init__(self, *, client: Any, model: str) -> None:
            calls["summary_model"] = model
            calls["gemini_client_seen"] = isinstance(client, FakeGeminiClient)
    ...
    assert calls["summary_model"] == "gemini-2.5-flash"
    assert calls["gemini_client_seen"] is True
```

- [ ] **Step 3: Run focused tests and confirm fail**

Run:
```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_gemini_client.py tests/test_setup_command.py -q
```

Expected:
- FAIL before Gemini client and runtime routing implementation.

- [ ] **Step 4: Commit red tests**

```bash
git add tests/test_gemini_client.py tests/test_setup_command.py
git commit -m "test: add failing gemini summary routing and client coverage" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 4: Implement Gemini summary client + runtime routing

**Files:**
- Create: `paperbrain/adapters/gemini_client.py`
- Modify: `paperbrain/adapters/llm.py`
- Modify: `paperbrain/cli.py`
- Test: `tests/test_gemini_client.py`
- Test: `tests/test_setup_command.py`

- [ ] **Step 1: Implement Gemini client**

```python
from typing import Any


class GeminiClient:
    def __init__(self, api_key: str, sdk_client: Any | None = None) -> None:
        if sdk_client is None:
            from google import genai
            sdk_client = genai.Client(api_key=api_key)
        self.sdk_client = sdk_client

    def summarize(self, text: str, model: str) -> str:
        response = self.sdk_client.models.generate_content(model=model, contents=text)
        return (response.text or "").strip()
```

- [ ] **Step 2: Add Gemini summary adapter class and shared client protocol**

```python
class SummaryClient(Protocol):
    def summarize(self, text: str, model: str) -> str: ...
```

```python
class OpenAISummaryAdapter:
    def __init__(self, *, client: SummaryClient, model: str) -> None:
        self.client = client
        self.model = model
```

```python
class GeminiSummaryAdapter(OpenAISummaryAdapter):
    pass
```

- [ ] **Step 3: Route summary provider in `build_runtime`**

```python
def _is_gemini_summary_model(summary_model: str) -> bool:
    return summary_model.strip().lower().startswith("gemini-")
```

```python
def build_runtime(config_path: Path) -> RuntimeAdapters:
    config = ConfigStore(config_path).load()
    openai_client = OpenAIClient(api_key=config.openai_api_key)
    embeddings = OpenAIEmbeddingAdapter(client=openai_client, model=config.embedding_model)
    if _is_gemini_summary_model(config.summary_model):
        gemini_client = GeminiClient(api_key=config.gemini_api_key)
        llm = GeminiSummaryAdapter(client=gemini_client, model=config.summary_model)
    else:
        llm = OpenAISummaryAdapter(client=openai_client, model=config.summary_model)
    return RuntimeAdapters(config=config, parser=DoclingParser(), embeddings=embeddings, llm=llm)
```

- [ ] **Step 4: Run focused tests and confirm pass**

Run:
```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_gemini_client.py tests/test_setup_command.py tests/test_openai_adapter.py -q
```

Expected:
- PASS.

- [ ] **Step 5: Commit implementation**

```bash
git add paperbrain/adapters/gemini_client.py paperbrain/adapters/llm.py paperbrain/cli.py tests/test_gemini_client.py tests/test_setup_command.py
git commit -m "feat: add gemini summary provider runtime routing" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 5: Documentation and full verification

**Files:**
- Modify: `README.md`
- Test: full suite

- [ ] **Step 1: Update README provider configuration docs**

```toml
[paperbrain]
database_url = "postgresql://<user>:<pass>@localhost:5432/paperbrain"
openai_api_key = "sk-..."
gemini_api_key = "gm-..."
summary_model = "gemini-2.5-flash"
embedding_model = "text-embedding-3-small"
```

```bash
paperbrain setup \
  --url postgresql://<user>:<pass>@localhost:5432/paperbrain \
  --openai-api-key $OPENAI_API_KEY \
  --gemini-api-key $GEMINI_API_KEY \
  --summary-model gemini-2.5-flash
```

- [ ] **Step 2: Run full suite**

Run:
```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q
```

Expected:
- PASS (with existing skipped tests allowed).

- [ ] **Step 3: Commit docs/verification adjustments if needed**

```bash
git add README.md
git commit -m "docs: add gemini summary provider setup guidance" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

## Plan self-review (completed)

1. **Spec coverage:** All in-scope requirements from `2026-04-15-gemini-summary-provider-design.md` map to explicit tasks.
2. **Placeholder scan:** No TODO/TBD placeholders remain.
3. **Type consistency:** Uses consistent names (`gemini_api_key`, `GeminiClient`, `GeminiSummaryAdapter`, provider selection by `summary_model.startswith("gemini-")`) across tasks.
