# Explicit Provider Prefix Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce explicit summary-model prefixes for all providers (`openai:`, `gemini:`, `ollama:`) and remove implicit OpenAI fallback behavior.

**Architecture:** Introduce a small shared parser for `summary_model` that returns provider + stripped model and raises clear errors for invalid selectors. Use that parser in both runtime wiring (`cli.py`) and setup validation (`services/setup.py`) so provider selection rules are identical in both paths. Update tests and README to use prefixed selectors only.

**Tech Stack:** Python 3.12, Typer, pytest.

---

## File structure and responsibilities

- Create: `paperbrain/summary_provider.py` — shared summary selector parsing (`provider`, `model`) and validation.
- Modify: `paperbrain/cli.py` — runtime adapter routing and key checks based on parsed provider.
- Modify: `paperbrain/services/setup.py` — setup connection validation routing based on parsed provider.
- Modify: `tests/test_setup_command.py` — update selector-format expectations and add invalid-selector coverage.
- Modify: `README.md` — document explicit prefix-only selector format and examples.

---

### Task 1: Add shared summary provider parser

**Files:**
- Create: `paperbrain/summary_provider.py`
- Modify/Test: `tests/test_setup_command.py` (add parser-behavior tests or runtime/setup invalid selector tests)

- [ ] **Step 1: Write failing tests for selector parsing behavior**

```python
def test_build_runtime_rejects_unprefixed_summary_model(monkeypatch: Any, tmp_path: Path) -> None:
    config = AppConfig(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="sk-runtime",
        summary_model="gpt-4.1-mini",
        embedding_model="text-embedding-3-small",
    )
    config_path = tmp_path / "config" / "paperbrain.conf"

    class FakeConfigStore:
        def __init__(self, path: Path) -> None:
            assert path == config_path

        def load(self) -> AppConfig:
            return config

    monkeypatch.setattr("paperbrain.cli.ConfigStore", FakeConfigStore)

    with pytest.raises(ValueError, match="Summary model must be prefixed with one of: openai:, gemini:, ollama:"):
        build_runtime(config_path)
```

```python
def test_build_runtime_rejects_unknown_summary_provider_prefix(monkeypatch: Any, tmp_path: Path) -> None:
    config = AppConfig(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="sk-runtime",
        summary_model="anthropic:claude-3-7-sonnet",
        embedding_model="text-embedding-3-small",
    )
    config_path = tmp_path / "config" / "paperbrain.conf"

    class FakeConfigStore:
        def __init__(self, path: Path) -> None:
            assert path == config_path

        def load(self) -> AppConfig:
            return config

    monkeypatch.setattr("paperbrain.cli.ConfigStore", FakeConfigStore)

    with pytest.raises(ValueError, match="Unknown summary provider prefix"):
        build_runtime(config_path)
```

- [ ] **Step 2: Run targeted tests to verify fail**

Run: `python3 -m pytest tests/test_setup_command.py -k "unprefixed_summary_model or unknown_summary_provider_prefix" -q`  
Expected: FAIL before parser implementation.

- [ ] **Step 3: Implement shared parser module**

```python
# paperbrain/summary_provider.py
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ParsedSummaryModel:
    provider: str
    model: str


def parse_summary_model(summary_model: str) -> ParsedSummaryModel:
    raw = summary_model.strip()
    if ":" not in raw:
        raise ValueError("Summary model must be prefixed with one of: openai:, gemini:, ollama:")
    provider, model = raw.split(":", 1)
    provider = provider.strip().lower()
    model = model.strip()
    if provider not in {"openai", "gemini", "ollama"}:
        raise ValueError(f"Unknown summary provider prefix: {provider}")
    if not model:
        raise ValueError(f"{provider.capitalize()} summary model must include a model name after '{provider}:'")
    return ParsedSummaryModel(provider=provider, model=model)
```

- [ ] **Step 4: Run targeted tests to verify pass**

Run: `python3 -m pytest tests/test_setup_command.py -k "unprefixed_summary_model or unknown_summary_provider_prefix" -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperbrain/summary_provider.py tests/test_setup_command.py
git commit -m "feat: add explicit summary provider parser"
```

---

### Task 2: Wire runtime and setup to explicit prefixes

**Files:**
- Modify: `paperbrain/cli.py`
- Modify: `paperbrain/services/setup.py`
- Modify/Test: `tests/test_setup_command.py`

- [ ] **Step 1: Write failing routing/key-check tests using prefixed selectors**

```python
# examples to update existing tests
summary_model="openai:gpt-4.1-mini"
summary_model="gemini:gemini-2.5-flash"
summary_model="ollama:llama3.1:8b"
```

```python
with pytest.raises(ValueError, match="Gemini API key is required for Gemini summary models"):
    build_runtime(config_path)  # when summary_model is gemini:...
```

- [ ] **Step 2: Run targeted setup/runtime tests to verify fail**

Run: `python3 -m pytest tests/test_setup_command.py -k "build_runtime or run_setup_uses" -q`  
Expected: FAIL while old `gemini-` detection and fallback logic still exist.

- [ ] **Step 3: Implement runtime and setup routing with parser**

```python
# paperbrain/cli.py (imports)
from paperbrain.summary_provider import parse_summary_model
```

```python
# paperbrain/cli.py (build_runtime excerpt)
parsed = parse_summary_model(config.summary_model)
if not config.openai_api_key.strip():
    raise ValueError("OpenAI API key is required for embeddings")

openai_client = OpenAIClient(api_key=config.openai_api_key)
if parsed.provider == "gemini":
    if not config.gemini_api_key.strip():
        raise ValueError("Gemini API key is required for Gemini summary models")
    summary_client = GeminiClient(api_key=config.gemini_api_key)
    llm: LLMAdapter = GeminiSummaryAdapter(client=summary_client, model=parsed.model)
elif parsed.provider == "ollama":
    if not config.ollama_api_key.strip():
        raise ValueError("Ollama API key is required for Ollama summary models")
    ollama_base_url = config.ollama_base_url.strip()
    if not ollama_base_url:
        raise ValueError("Ollama base URL is required for Ollama summary models")
    summary_client = OllamaCloudClient(api_key=config.ollama_api_key, base_url=ollama_base_url)
    llm = OllamaSummaryAdapter(client=summary_client, model=parsed.model)
else:
    llm = OpenAISummaryAdapter(client=openai_client, model=parsed.model)
```

```python
# paperbrain/services/setup.py (imports)
from paperbrain.summary_provider import parse_summary_model
```

```python
# paperbrain/services/setup.py (run_setup validation excerpt)
parsed = parse_summary_model(summary_model)
...
if parsed.provider == "openai":
    _validate_openai_summary_connection(openai_client, parsed.model)
elif parsed.provider == "gemini":
    _validate_gemini_summary_connection(gemini_api_key=gemini_api_key, summary_model=parsed.model)
else:
    _validate_ollama_summary_connection(
        ollama_api_key=ollama_api_key,
        ollama_base_url=ollama_base_url,
        summary_model=f"ollama:{parsed.model}",
    )
```

- [ ] **Step 4: Update tests to explicit prefixes and run**

Run: `python3 -m pytest tests/test_setup_command.py -q`  
Expected: PASS with prefixed selectors only.

- [ ] **Step 5: Commit**

```bash
git add paperbrain/cli.py paperbrain/services/setup.py tests/test_setup_command.py
git commit -m "feat: require explicit provider prefixes for summary models"
```

---

### Task 3: Update README and run regressions

**Files:**
- Modify: `README.md`
- Validate: full test suite

- [ ] **Step 1: Update README selector examples and rules**

```markdown
paperbrain setup \
  --url postgresql://<user>:<pass>@localhost:5432/paperbrain \
  --openai-api-key $OPENAI_API_KEY \
  --summary-model openai:gpt-4.1-mini
```

```markdown
paperbrain setup \
  --url postgresql://<user>:<pass>@localhost:5432/paperbrain \
  --openai-api-key $OPENAI_API_KEY \
  --gemini-api-key $GEMINI_API_KEY \
  --summary-model gemini:gemini-2.5-flash
```

```markdown
Summary provider is selected from the summary model prefix (required):
- `openai:*` models use OpenAI for summaries
- `gemini:*` models use Gemini for summaries
- `ollama:*` models use Ollama for summaries
```

- [ ] **Step 2: Run focused and full regression tests**

Run: `python3 -m pytest tests/test_setup_command.py tests/test_gemini_client.py tests/test_ollama_client.py -q`  
Expected: PASS.

Run: `python3 -m pytest -q`  
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: switch summary model selection to explicit prefixes"
```

---

## Self-review checklist (completed)

1. **Spec coverage:** tasks include strict explicit prefixes, no fallback, runtime/setup parser routing, tests, and docs.
2. **Placeholder scan:** no placeholder TODO/TBD language remains in tasks.
3. **Type consistency:** provider tokens and model formats are consistent (`openai:`, `gemini:`, `ollama:`) across runtime, setup, tests, and docs.
