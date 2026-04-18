# Optional Embeddings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make embeddings optional and disabled by default while preserving current behavior when embeddings are enabled.

**Architecture:** Add an explicit `embeddings_enabled` configuration toggle and propagate it through setup, runtime wiring, ingest, and search. Runtime should only construct embedding clients when enabled. Ingest and search paths should gracefully operate without vectors by using chunk-only ingestion and keyword-only search.

**Tech Stack:** Python 3.12, Typer CLI, PostgreSQL + pgvector, pytest

---

## File Structure

- Modify: `paperbrain/config.py` (new `embeddings_enabled` config field + conditional embedding validation)
- Modify: `paperbrain/services/setup.py` (conditional OpenAI embedding validation)
- Modify: `paperbrain/cli.py` (new setup option and conditional OpenAI key prompt behavior)
- Modify: `paperbrain/summary_provider.py` (optional embedding adapter construction)
- Modify: `paperbrain/services/ingest.py` (ingest path supporting no embedder)
- Modify: `paperbrain/repositories/postgres.py` (store chunks with/without embeddings; keyword-only query)
- Modify: `paperbrain/services/search.py` (fallback keyword-only search when embedder missing)
- Modify: `README.md` (document embedding-default-disabled behavior and setup flag)
- Test: `tests/test_config.py`
- Test: `tests/test_setup_command.py`
- Test: `tests/test_ingest_service.py`
- Test: `tests/test_search_service.py`
- Test: `tests/test_postgres_repo.py`

### Task 1: Config contract for optional embeddings

**Files:**
- Modify: `paperbrain/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing config tests for new default and conditional validation**

```python
def test_load_legacy_config_defaults_embeddings_disabled(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"
    config_path.write_text('[paperbrain]\ndatabase_url = "postgresql://localhost:5432/paperbrain"\n', encoding="utf-8")
    loaded = ConfigStore(config_path).load()
    assert loaded.embeddings_enabled is False

def test_save_allows_non_1536_embedding_model_when_embeddings_disabled(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"
    ConfigStore(config_path).save(
        database_url="postgresql://localhost:5432/paperbrain",
        embeddings_enabled=False,
        embedding_model="text-embedding-3-large",
    )
```

- [ ] **Step 2: Run targeted tests and confirm failure**

Run: `python3 -m pytest -q tests/test_config.py -k "embeddings_enabled or non_1536"`  
Expected: FAIL due to missing `embeddings_enabled` support and unconditional model validation.

- [ ] **Step 3: Implement config changes**

```python
@dataclass(slots=True)
class AppConfig:
    database_url: str
    openai_api_key: str
    summary_model: str
    embedding_model: str
    embeddings_enabled: bool = False
    gemini_api_key: str = ""
    ollama_api_key: str = ""
    ollama_base_url: str = "https://ollama.com"

def _validate_embedding_model_for_mode(embedding_model: str, embeddings_enabled: bool) -> None:
    if not embeddings_enabled:
        return
    validate_embedding_model_for_schema(embedding_model)
```

- [ ] **Step 4: Re-run targeted tests**

Run: `python3 -m pytest -q tests/test_config.py`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperbrain/config.py tests/test_config.py
git commit -m "feat: add embeddings_enabled config toggle"
```

### Task 2: Setup + runtime validation behavior

**Files:**
- Modify: `paperbrain/services/setup.py`
- Modify: `paperbrain/cli.py`
- Modify: `paperbrain/summary_provider.py`
- Test: `tests/test_setup_command.py`

- [ ] **Step 1: Add failing tests for conditional OpenAI key requirements**

```python
def test_build_runtime_allows_gemini_without_openai_when_embeddings_disabled(
    monkeypatch: Any, tmp_path: Path
) -> None:
    config = AppConfig(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="",
        gemini_api_key="gm-runtime",
        summary_model="gemini:gemini-2.5-flash",
        embedding_model="text-embedding-3-small",
        embeddings_enabled=False,
    )
    config_path = tmp_path / "paperbrain.conf"
    monkeypatch.setattr("paperbrain.summary_provider.ConfigStore", lambda _: type("S", (), {"load": lambda self: config})())
    monkeypatch.setattr("paperbrain.summary_provider.GeminiClient", lambda api_key: object(), raising=False)
    rt = build_runtime(config_path)
    assert rt.embeddings is None

def test_run_setup_skips_embedding_connectivity_when_embeddings_disabled(monkeypatch: Any, tmp_path: Path) -> None:
    calls: dict[str, int] = {"embedding_checks": 0}
    monkeypatch.setattr(
        "paperbrain.services.setup._validate_openai_embedding_connection",
        lambda **_: calls.__setitem__("embedding_checks", calls["embedding_checks"] + 1),
    )
    run_setup(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="",
        summary_model="gemini:gemini-2.5-flash",
        gemini_api_key="gm-runtime",
        embeddings_enabled=False,
        test_connections=False,
        config_path=tmp_path / "cfg.conf",
    )
    assert calls["embedding_checks"] == 0

def test_cli_setup_accepts_embeddings_enabled_flag() -> None:
    result = CliRunner().invoke(
        app,
        [
            "setup",
            "--url",
            "postgresql://localhost:5432/paperbrain",
            "--summary-model",
            "gemini:gemini-2.5-flash",
            "--no-embeddings-enabled",
            "--no-test-connections",
        ],
    )
    assert result.exit_code == 0
```

- [ ] **Step 2: Run targeted setup/runtime tests and confirm failure**

Run: `python3 -m pytest -q tests/test_setup_command.py -k "embeddings_disabled or embeddings_enabled"`  
Expected: FAIL due to unconditional OpenAI embedding wiring.

- [ ] **Step 3: Implement setup/cli/provider changes**

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
    config_path: Path = Path.home() / ".config" / "paperbrain" / "paperbrain.conf",
    test_connections: bool = True,
    embeddings_enabled: bool = False,
):
    if embeddings_enabled:
        validate_embedding_model_for_schema(embedding_model)
    if test_connections and embeddings_enabled:
        _validate_openai_embedding_connection(openai_api_key=openai_api_key, embedding_model=embedding_model)

# paperbrain/summary_provider.py
self.embeddings = (
    OpenAIEmbeddingAdapter(client=self.openai_client, model=self.config.embedding_model)
    if self.config.embeddings_enabled
    else None
)
```

- [ ] **Step 4: Re-run setup/runtime tests**

Run: `python3 -m pytest -q tests/test_setup_command.py`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperbrain/services/setup.py paperbrain/cli.py paperbrain/summary_provider.py tests/test_setup_command.py
git commit -m "feat: make setup/runtime embedding wiring optional"
```

### Task 3: Ingest without embeddings

**Files:**
- Modify: `paperbrain/services/ingest.py`
- Modify: `paperbrain/repositories/postgres.py`
- Test: `tests/test_ingest_service.py`
- Test: `tests/test_postgres_repo.py`

- [ ] **Step 1: Add failing tests for chunk-only ingest path**

```python
def test_ingest_service_ingests_without_embeddings(tmp_path: Path) -> None:
    service = IngestService(repo=repo, parser=parser, embeddings=None, chunk_size_words=3)
    inserted = service.ingest_paths([str(paper_file)], force_all=False)
    assert inserted == 1
    assert repo.replacements[0][2] == []
```

- [ ] **Step 2: Run targeted ingest/repo tests and confirm failure**

Run: `python3 -m pytest -q tests/test_ingest_service.py tests/test_postgres_repo.py -k "without_embeddings or replace_chunks"`  
Expected: FAIL because embeddings are required and repo expects vectors length to match chunks.

- [ ] **Step 3: Implement optional-embedding ingest**

```python
class IngestService:
    def __init__(
        self,
        *,
        repo: IngestRepository,
        parser: Parser,
        embeddings: Embeddings | None,
        chunk_size_words: int = 200,
    ) -> None:
        self.embeddings = embeddings

    def ingest_paths(self, paths: list[str], force_all: bool, recursive: bool = False) -> int:
        chunks = chunk_words(parsed.full_text, self.chunk_size_words)
        vectors = self.embeddings.embed(chunks) if self.embeddings is not None else []
        if self.embeddings is not None and len(chunks) != len(vectors):
            raise ValueError("Embedding count must match chunk count")
        self.repo.replace_chunks(paper_id, chunks, vectors)
```

```python
def replace_chunks(self, paper_id: str, chunks: list[str], vectors: list[list[float]]) -> None:
    if vectors and len(chunks) != len(vectors):
        raise ValueError("chunks and vectors length mismatch")
    for chunk_index, chunk_text in enumerate(chunks):
        chunk_id = f"{paper_id}-chunk-{chunk_index}"
        self.execute(
            "INSERT INTO paper_chunks (id, paper_id, chunk_index, chunk_text) VALUES (%s, %s, %s, %s);",
            (chunk_id, paper_id, chunk_index, chunk_text),
        )
        if vectors:
            vector_literal = f"[{', '.join(str(value) for value in vectors[chunk_index])}]"
            self.execute(
                "INSERT INTO paper_embeddings (chunk_id, embedding) VALUES (%s, %s::vector);",
                (chunk_id, vector_literal),
            )
```

- [ ] **Step 4: Re-run ingest/repo tests**

Run: `python3 -m pytest -q tests/test_ingest_service.py tests/test_postgres_repo.py`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperbrain/services/ingest.py paperbrain/repositories/postgres.py tests/test_ingest_service.py tests/test_postgres_repo.py
git commit -m "feat: support ingest without embeddings"
```

### Task 4: Search keyword-only fallback

**Files:**
- Modify: `paperbrain/services/search.py`
- Modify: `paperbrain/repositories/postgres.py`
- Test: `tests/test_search_service.py`

- [ ] **Step 1: Add failing tests for no-embedder search path**

```python
def test_search_without_embedder_uses_keyword_only_query() -> None:
    service = SearchService(repo=repo, embedder=None)
    rows = service.search("p53", top_k=1, include_cards=False)
    assert repo.keyword_calls == [("p53", 1)]
```

- [ ] **Step 2: Run targeted search tests and confirm failure**

Run: `python3 -m pytest -q tests/test_search_service.py -k "without_embedder or keyword_only"`  
Expected: FAIL because service currently raises RuntimeError when embedder is missing.

- [ ] **Step 3: Implement keyword-only fallback**

```python
class SearchRepository(Protocol):
    def search_keyword(self, query: str, top_k: int) -> list[dict]:
        pass

def search(self, query: str, top_k: int = 10, include_cards: bool = False) -> list[dict]:
    if self.embedder is None:
        rows = self.repo.search_keyword(query, top_k)
    else:
        query_vector = _validate_query_vector(self.embedder.embed([query])[0])
        rows = self.repo.search_hybrid(query, query_vector, top_k)
```

- [ ] **Step 4: Re-run search tests**

Run: `python3 -m pytest -q tests/test_search_service.py`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperbrain/services/search.py paperbrain/repositories/postgres.py tests/test_search_service.py
git commit -m "feat: add keyword-only search fallback when embeddings disabled"
```

### Task 5: Docs + full verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README config/setup docs**

```md
- embeddings_enabled = false (default)
- use --embeddings-enabled to turn on embedding generation/hybrid search
- OpenAI key required only for openai:* summaries or when embeddings are enabled
```

- [ ] **Step 2: Run focused regression suite**

Run: `python3 -m pytest -q tests/test_config.py tests/test_setup_command.py tests/test_ingest_service.py tests/test_search_service.py tests/test_postgres_repo.py`  
Expected: PASS.

- [ ] **Step 3: Run full project tests**

Run: `python3 -m pytest -q`  
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document optional embeddings and default-disabled mode"
```
