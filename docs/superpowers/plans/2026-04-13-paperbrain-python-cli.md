# PaperBrain Python CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python PaperBrain CLI that supports setup/init/ingest/browse/search/summarize/lint/stats/export using Postgres + pgvector and pluggable Docling/LLM adapters.

**Architecture:** Implement a modular `paperbrain` package with Typer command entrypoints mapped to service modules. Keep external integrations behind adapter interfaces (`docling`, `llm`, embedding provider) so all command flows are runnable with deterministic default adapters or mocks in tests.

**Tech Stack:** Python 3.12, Typer, psycopg (v3), pgvector, pydantic-settings, pytest

---

## Planned file structure

- `pyproject.toml` — package metadata, dependencies, scripts, pytest config
- `paperbrain/cli.py` — Typer app and command wiring
- `paperbrain/config.py` — persisted config read/write and validation
- `paperbrain/db.py` — DB connection factory and schema bootstrap SQL
- `paperbrain/models.py` — typed dataclasses for paper/chunk/card/search payloads
- `paperbrain/adapters/docling.py` — parser protocol + default adapter
- `paperbrain/adapters/llm.py` — summarizer/profile protocol + default adapter
- `paperbrain/adapters/embedding.py` — embedding protocol + default deterministic adapter
- `paperbrain/services/{setup,init,ingest,search,summarize,lint,stats,export}.py`
- `paperbrain/exporter.py` — markdown rendering and Obsidian folder layout
- `paperbrain/quality.py` — link/metadata/whitespace checks and fixes
- `paperbrain/utils.py` — slug/normalization helpers
- `tests/...` — unit and integration tests for all command flows

### Task 1: Project bootstrap and CLI skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `paperbrain/__init__.py`
- Create: `paperbrain/cli.py`
- Create: `paperbrain/models.py`
- Test: `tests/test_cli_commands.py`

- [ ] **Step 1: Write the failing test**

```python
from typer.testing import CliRunner
from paperbrain.cli import app

def test_cli_exposes_core_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    output = result.output
    for name in ["setup", "init", "ingest", "browse", "search", "summarize", "lint", "stats", "export"]:
        assert name in output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_commands.py::test_cli_exposes_core_commands -v`
Expected: FAIL with import/module error because package files do not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
# paperbrain/cli.py
import typer

app = typer.Typer(no_args_is_help=True)

@app.command()
def setup() -> None: ...
@app.command()
def init() -> None: ...
@app.command()
def ingest(path: str) -> None: ...
@app.command()
def browse(query: str) -> None: ...
@app.command()
def search(query: str) -> None: ...
@app.command()
def summarize() -> None: ...
@app.command()
def lint() -> None: ...
@app.command()
def stats() -> None: ...
@app.command()
def export() -> None: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli_commands.py::test_cli_exposes_core_commands -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml paperbrain/__init__.py paperbrain/cli.py paperbrain/models.py tests/test_cli_commands.py
git commit -m "feat: bootstrap paperbrain package and CLI surface"
```

### Task 2: Config persistence and database bootstrap (`setup` + `init`)

**Files:**
- Create: `paperbrain/config.py`
- Create: `paperbrain/db.py`
- Modify: `paperbrain/services/setup.py`
- Modify: `paperbrain/services/init.py`
- Modify: `paperbrain/cli.py`
- Test: `tests/test_config.py`
- Test: `tests/test_db_init.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_save_and_load_config_round_trip(tmp_path):
    from paperbrain.config import ConfigStore
    store = ConfigStore(tmp_path / "paperbrain.conf")
    store.save({"database_url": "postgresql://x/y"})
    assert store.load().database_url == "postgresql://x/y"
```

```python
def test_schema_sql_contains_pgvector_extension():
    from paperbrain.db import SCHEMA_SQL
    assert "CREATE EXTENSION IF NOT EXISTS vector" in SCHEMA_SQL
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py tests/test_db_init.py -v`
Expected: FAIL due missing `ConfigStore` and `SCHEMA_SQL`.

- [ ] **Step 3: Write minimal implementation**

```python
# paperbrain/config.py
from dataclasses import dataclass
from pathlib import Path

@dataclass
class AppConfig:
    database_url: str

class ConfigStore:
    ...
```

```python
# paperbrain/db.py
SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS papers (...);
"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py tests/test_db_init.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperbrain/config.py paperbrain/db.py paperbrain/services/setup.py paperbrain/services/init.py paperbrain/cli.py tests/test_config.py tests/test_db_init.py
git commit -m "feat: add config persistence and database bootstrap"
```

### Task 3: Ingestion pipeline with parser + embedding adapters

**Files:**
- Create: `paperbrain/adapters/docling.py`
- Create: `paperbrain/adapters/embedding.py`
- Create: `paperbrain/services/ingest.py`
- Modify: `paperbrain/cli.py`
- Modify: `paperbrain/db.py`
- Test: `tests/test_ingest_service.py`

- [ ] **Step 1: Write the failing test**

```python
def test_ingest_service_skips_existing_without_force(mocker):
    from paperbrain.services.ingest import IngestService
    svc = IngestService(...)
    inserted = svc.ingest_paths(["/tmp/a.pdf"], force_all=False)
    assert inserted == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ingest_service.py::test_ingest_service_skips_existing_without_force -v`
Expected: FAIL because `IngestService` is undefined.

- [ ] **Step 3: Write minimal implementation**

```python
class DoclingAdapter(Protocol):
    def parse_pdf(self, path: Path) -> ParsedPaper: ...

class EmbeddingAdapter(Protocol):
    def embed(self, chunks: list[str]) -> list[list[float]]: ...
```

```python
class IngestService:
    def ingest_paths(self, paths: list[str], force_all: bool, recursive: bool = False) -> int:
        ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ingest_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperbrain/adapters/docling.py paperbrain/adapters/embedding.py paperbrain/services/ingest.py paperbrain/cli.py paperbrain/db.py tests/test_ingest_service.py
git commit -m "feat: implement ingestion service with parser and embedding adapters"
```

### Task 4: Browse and hybrid search

**Files:**
- Create: `paperbrain/services/search.py`
- Modify: `paperbrain/cli.py`
- Modify: `paperbrain/db.py`
- Test: `tests/test_search_service.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_hybrid_score_blends_keyword_and_vector():
    from paperbrain.services.search import hybrid_score
    assert hybrid_score(keyword_rank=0.8, vector_rank=0.2, alpha=0.6) == 0.56
```

```python
def test_search_include_cards_appends_related_cards(mocker):
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_search_service.py -v`
Expected: FAIL because `hybrid_score` and search service are missing.

- [ ] **Step 3: Write minimal implementation**

```python
def hybrid_score(keyword_rank: float, vector_rank: float, alpha: float = 0.6) -> float:
    return round(alpha * keyword_rank + (1 - alpha) * vector_rank, 6)
```

```python
class SearchService:
    def browse(self, keyword: str, card_type: str = "all") -> list[dict]: ...
    def search(self, query: str, top_k: int = 10, include_cards: bool = False) -> list[dict]: ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_search_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperbrain/services/search.py paperbrain/db.py paperbrain/cli.py tests/test_search_service.py
git commit -m "feat: add browse and hybrid search services"
```

### Task 5: Summarization and card generation

**Files:**
- Create: `paperbrain/adapters/llm.py`
- Create: `paperbrain/services/summarize.py`
- Modify: `paperbrain/db.py`
- Modify: `paperbrain/cli.py`
- Test: `tests/test_summarize_service.py`

- [ ] **Step 1: Write the failing test**

```python
def test_summarize_creates_paper_person_topic_cards(mocker):
    from paperbrain.services.summarize import SummarizeService
    svc = SummarizeService(...)
    result = svc.run(force_all=True)
    assert result.paper_cards >= 1
    assert result.person_cards >= 1
    assert result.topic_cards >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_summarize_service.py::test_summarize_creates_paper_person_topic_cards -v`
Expected: FAIL due missing summarization service.

- [ ] **Step 3: Write minimal implementation**

```python
class LLMAdapter(Protocol):
    def summarize_paper(self, paper_text: str, metadata: dict) -> dict: ...
    def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]: ...
    def derive_topic_cards(self, person_cards: list[dict]) -> list[dict]: ...
```

```python
class SummarizeService:
    def run(self, force_all: bool) -> SummaryStats: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_summarize_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperbrain/adapters/llm.py paperbrain/services/summarize.py paperbrain/db.py paperbrain/cli.py tests/test_summarize_service.py
git commit -m "feat: add summarization and card generation pipeline"
```

### Task 6: Lint, stats, and export workflows

**Files:**
- Create: `paperbrain/quality.py`
- Create: `paperbrain/exporter.py`
- Create: `paperbrain/services/lint.py`
- Create: `paperbrain/services/stats.py`
- Create: `paperbrain/services/export.py`
- Modify: `paperbrain/cli.py`
- Test: `tests/test_quality.py`
- Test: `tests/test_exporter.py`
- Test: `tests/test_stats_service.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_trim_whitespace_fix():
    from paperbrain.quality import normalize_whitespace
    assert normalize_whitespace("a  b\n\n") == "a b\n"
```

```python
def test_export_writes_bidirectional_links(tmp_path):
    from paperbrain.exporter import render_paper_markdown
    md = render_paper_markdown(...)
    assert "[[people/" in md
    assert "[[topics/" in md
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_quality.py tests/test_exporter.py tests/test_stats_service.py -v`
Expected: FAIL because quality/export/stats modules are missing.

- [ ] **Step 3: Write minimal implementation**

```python
def normalize_whitespace(text: str) -> str:
    return " ".join(text.split()) + "\n"
```

```python
class ExportService:
    def export(self, output_dir: Path) -> ExportStats: ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_quality.py tests/test_exporter.py tests/test_stats_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperbrain/quality.py paperbrain/exporter.py paperbrain/services/lint.py paperbrain/services/stats.py paperbrain/services/export.py paperbrain/cli.py tests/test_quality.py tests/test_exporter.py tests/test_stats_service.py
git commit -m "feat: add lint, stats, and export services"
```

### Task 7: End-to-end CLI integration polish

**Files:**
- Modify: `paperbrain/cli.py`
- Modify: `paperbrain/services/*.py`
- Create: `tests/test_cli_integration.py`
- Modify: `README.md`

- [ ] **Step 1: Write the failing integration test**

```python
def test_search_command_runs_with_top_k_option(cli_runner, mock_services):
    result = cli_runner.invoke(app, ["search", "p53", "--top-k", "5"])
    assert result.exit_code == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_integration.py::test_search_command_runs_with_top_k_option -v`
Expected: FAIL due incomplete option wiring or service injection.

- [ ] **Step 3: Write minimal implementation**

```python
@app.command()
def search(query: str, top_k: int = typer.Option(10), include_cards: bool = typer.Option(False)):
    ...
```

- [ ] **Step 4: Run all tests**

Run: `pytest -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperbrain/cli.py paperbrain/services tests/test_cli_integration.py README.md
git commit -m "feat: finalize CLI wiring and integration docs"
```

