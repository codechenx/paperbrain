# PaperBrain OpenAI Full Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a fully working PaperBrain CLI with real Postgres+pgvector, Docling PDF ingestion, OpenAI embeddings/summaries, and optional live end-to-end tests.

**Architecture:** Keep Typer CLI as orchestration entrypoint and implement real behavior in focused services. Add concrete Postgres repositories and OpenAI/Docling adapters behind interfaces so commands run live while tests can still inject deterministic fakes. Store runtime config in `./config/paperbrain.conf` including OpenAI credentials and models.

**Tech Stack:** Python 3.12, Typer, psycopg3, pgvector, openai, docling, pytest

---

## Planned file structure

- Create: `paperbrain/repositories/__init__.py`
- Create: `paperbrain/repositories/postgres.py`
- Create: `paperbrain/adapters/openai_client.py`
- Modify: `pyproject.toml`
- Modify: `paperbrain/config.py`
- Modify: `paperbrain/db.py`
- Modify: `paperbrain/cli.py`
- Modify: `paperbrain/services/{setup,init,ingest,search,summarize,lint,stats,export}.py`
- Modify: `paperbrain/adapters/docling.py`
- Modify: `paperbrain/adapters/embedding.py`
- Modify: `paperbrain/adapters/llm.py`
- Modify: `paperbrain/exporter.py`
- Create/Modify tests under `tests/`

### Task 1: Dependencies and config model for local file-based credentials

**Files:**
- Modify: `pyproject.toml`
- Modify: `paperbrain/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
from pathlib import Path
from paperbrain.config import ConfigStore


def test_config_stores_openai_fields(tmp_path: Path) -> None:
    path = tmp_path / "paperbrain.conf"
    store = ConfigStore(path)
    store.save(
        database_url="postgresql://postgres:PaperBrainLocal2026ChangeMe@localhost:5432/paperbrain",
        openai_api_key="sk-test",
        summary_model="gpt-4.1-mini",
        embedding_model="text-embedding-3-small",
    )
    cfg = store.load()
    assert cfg.openai_api_key == "sk-test"
    assert cfg.summary_model == "gpt-4.1-mini"
    assert cfg.embedding_model == "text-embedding-3-small"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_config.py::test_config_stores_openai_fields -v`
Expected: FAIL because `ConfigStore.save()` does not accept OpenAI/model fields yet.

- [ ] **Step 3: Write minimal implementation**

```python
# paperbrain/config.py
from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(slots=True)
class AppConfig:
    database_url: str
    openai_api_key: str
    summary_model: str
    embedding_model: str


class ConfigStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def save(
        self,
        *,
        database_url: str,
        openai_api_key: str,
        summary_model: str,
        embedding_model: str,
    ) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = (
            "[paperbrain]\n"
            f'database_url = "{database_url}"\n'
            f'openai_api_key = "{openai_api_key}"\n'
            f'summary_model = "{summary_model}"\n'
            f'embedding_model = "{embedding_model}"\n'
        )
        self.path.write_text(body, encoding="utf-8")

    def load(self) -> AppConfig:
        parsed = tomllib.loads(self.path.read_text(encoding="utf-8"))
        section = parsed["paperbrain"]
        return AppConfig(
            database_url=section["database_url"],
            openai_api_key=section["openai_api_key"],
            summary_model=section["summary_model"],
            embedding_model=section["embedding_model"],
        )
```

```toml
# pyproject.toml (project.dependencies)
dependencies = [
  "typer>=0.12.0",
  "psycopg[binary]>=3.2.0",
  "openai>=1.51.0",
  "docling>=2.9.0",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_config.py::test_config_stores_openai_fields -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml paperbrain/config.py tests/test_config.py
git commit -m "feat: add OpenAI-aware PaperBrain config model"
```

### Task 2: Real database initialization and repository base

**Files:**
- Modify: `paperbrain/db.py`
- Create: `paperbrain/repositories/__init__.py`
- Create: `paperbrain/repositories/postgres.py`
- Modify: `tests/test_db_init.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db_init.py
from paperbrain.db import schema_statements


def test_schema_statements_include_link_tables() -> None:
    sql = "\n".join(schema_statements(force=False))
    assert "CREATE TABLE IF NOT EXISTS paper_person_links" in sql
    assert "CREATE TABLE IF NOT EXISTS paper_topic_links" in sql
    assert "CREATE TABLE IF NOT EXISTS person_topic_links" in sql
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_db_init.py::test_schema_statements_include_link_tables -v`
Expected: FAIL because link tables are not in schema.

- [ ] **Step 3: Write minimal implementation**

```python
# paperbrain/db.py
import psycopg
from contextlib import contextmanager
from collections.abc import Iterator

SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    journal TEXT NOT NULL,
    year INTEGER NOT NULL,
    authors TEXT NOT NULL,
    corresponding_authors TEXT NOT NULL,
    source_path TEXT UNIQUE NOT NULL,
    full_text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_chunks (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_embeddings (
    chunk_id TEXT PRIMARY KEY,
    embedding vector(1536) NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_cards (
    slug TEXT PRIMARY KEY,
    card_type TEXT NOT NULL,
    body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS person_cards (
    slug TEXT PRIMARY KEY,
    body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS topic_cards (
    slug TEXT PRIMARY KEY,
    body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_person_links (
    paper_slug TEXT NOT NULL,
    person_slug TEXT NOT NULL,
    PRIMARY KEY (paper_slug, person_slug)
);
CREATE TABLE IF NOT EXISTS paper_topic_links (
    paper_slug TEXT NOT NULL,
    topic_slug TEXT NOT NULL,
    PRIMARY KEY (paper_slug, topic_slug)
);
CREATE TABLE IF NOT EXISTS person_topic_links (
    person_slug TEXT NOT NULL,
    topic_slug TEXT NOT NULL,
    PRIMARY KEY (person_slug, topic_slug)
);
"""

@contextmanager
def connect(database_url: str) -> Iterator[psycopg.Connection]:
    with psycopg.connect(database_url, autocommit=False) as conn:
        yield conn
```

```python
# paperbrain/repositories/postgres.py
class PostgresRepo:
    def __init__(self, conn) -> None:
        self.conn = conn
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_db_init.py::test_schema_statements_include_link_tables -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperbrain/db.py paperbrain/repositories/__init__.py paperbrain/repositories/postgres.py tests/test_db_init.py
git commit -m "feat: add relational schema and postgres repository base"
```

### Task 3: Real OpenAI adapter implementation

**Files:**
- Create: `paperbrain/adapters/openai_client.py`
- Modify: `paperbrain/adapters/embedding.py`
- Modify: `paperbrain/adapters/llm.py`
- Create: `tests/test_openai_adapter.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_openai_adapter.py
from paperbrain.adapters.openai_client import OpenAIClient


class FakeEmbeddings:
    def create(self, model: str, input: list[str]):  # noqa: A002
        class Item:
            def __init__(self, emb):
                self.embedding = emb
        class Resp:
            data = [Item([0.1, 0.2])]
        return Resp()


class FakeResponses:
    def create(self, model: str, input: str):  # noqa: A002
        class Resp:
            output_text = "summary"
        return Resp()


class FakeSDK:
    embeddings = FakeEmbeddings()
    responses = FakeResponses()


def test_openai_client_calls_embedding_and_summary() -> None:
    client = OpenAIClient(api_key="sk-test", sdk_client=FakeSDK())
    vectors = client.embed(["chunk-a"], model="text-embedding-3-small")
    summary = client.summarize("paper text", model="gpt-4.1-mini")
    assert vectors == [[0.1, 0.2]]
    assert summary == "summary"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_openai_adapter.py::test_openai_client_calls_embedding_and_summary -v`
Expected: FAIL because `OpenAIClient` module does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
# paperbrain/adapters/openai_client.py
from openai import OpenAI


class OpenAIClient:
    def __init__(self, api_key: str, sdk_client: OpenAI | None = None) -> None:
        self.client = sdk_client or OpenAI(api_key=api_key)

    def embed(self, chunks: list[str], model: str) -> list[list[float]]:
        response = self.client.embeddings.create(model=model, input=chunks)
        return [item.embedding for item in response.data]

    def summarize(self, text: str, model: str) -> str:
        response = self.client.responses.create(model=model, input=text)
        return response.output_text.strip()
```

```python
# paperbrain/adapters/embedding.py
class OpenAIEmbeddingAdapter:
    def __init__(self, openai_client, model: str) -> None:
        self.openai_client = openai_client
        self.model = model

    def embed(self, chunks: list[str]) -> list[list[float]]:
        return self.openai_client.embed(chunks, model=self.model)
```

```python
# paperbrain/adapters/llm.py
class OpenAISummaryAdapter:
    def __init__(self, openai_client, model: str) -> None:
        self.openai_client = openai_client
        self.model = model

    def summarize_paper(self, paper_text: str, metadata: dict) -> dict:
        body = self.openai_client.summarize(f"{metadata['title']}\n\n{paper_text[:8000]}", model=self.model)
        return {"slug": metadata["slug"], "type": "article", "title": metadata["title"], "summary": body}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_openai_adapter.py::test_openai_client_calls_embedding_and_summary -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperbrain/adapters/openai_client.py paperbrain/adapters/embedding.py paperbrain/adapters/llm.py tests/test_openai_adapter.py
git commit -m "feat: add OpenAI embedding and summarization adapters"
```

### Task 4: Docling PDF parser integration and ingest pipeline

**Files:**
- Modify: `paperbrain/adapters/docling.py`
- Modify: `paperbrain/services/ingest.py`
- Modify: `paperbrain/repositories/postgres.py`
- Modify: `tests/test_ingest_service.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ingest_service.py
from pathlib import Path
from paperbrain.adapters.docling import DoclingParser


def test_docling_parser_rejects_missing_file(tmp_path: Path) -> None:
    parser = DoclingParser()
    missing = tmp_path / "missing.pdf"
    try:
        parser.parse_pdf(missing)
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        assert True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_ingest_service.py::test_docling_parser_rejects_missing_file -v`
Expected: FAIL because `DoclingParser` does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
# paperbrain/adapters/docling.py
from pathlib import Path
from paperbrain.models import ParsedPaper


class DoclingParser:
    def parse_pdf(self, path: Path) -> ParsedPaper:
        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {path}")
        from docling.document_converter import DocumentConverter

        converter = DocumentConverter()
        result = converter.convert(str(path))
        text = result.document.export_to_markdown()
        return ParsedPaper(
            title=path.stem,
            journal="Unknown Journal",
            year=1970,
            authors=[],
            corresponding_authors=[],
            full_text=text,
            source_path=str(path),
        )
```

```python
# paperbrain/services/ingest.py
chunks = chunk_words(parsed.full_text, self.chunk_size_words)
vectors = self.embeddings.embed(chunks)
paper_id = self.repo.upsert_paper(parsed, force=force_all)
self.repo.replace_chunks(paper_id, chunks, vectors)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_ingest_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperbrain/adapters/docling.py paperbrain/services/ingest.py paperbrain/repositories/postgres.py tests/test_ingest_service.py
git commit -m "feat: integrate docling parser with ingestion pipeline"
```

### Task 5: Real CLI setup/init wiring with connectivity checks

**Files:**
- Modify: `paperbrain/services/setup.py`
- Modify: `paperbrain/services/init.py`
- Modify: `paperbrain/cli.py`
- Create: `tests/test_setup_command.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_setup_command.py
from pathlib import Path
from paperbrain.services.setup import run_setup


def test_run_setup_writes_project_config(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config" / "paperbrain.conf"
    msg = run_setup(
        database_url="postgresql://postgres:PaperBrainLocal2026ChangeMe@localhost:5432/paperbrain",
        openai_api_key="sk-test",
        summary_model="gpt-4.1-mini",
        embedding_model="text-embedding-3-small",
        config_path=cfg_path,
        test_connections=False,
    )
    assert cfg_path.exists()
    assert "Saved configuration" in msg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_setup_command.py::test_run_setup_writes_project_config -v`
Expected: FAIL because `run_setup` signature lacks OpenAI fields and `test_connections`.

- [ ] **Step 3: Write minimal implementation**

```python
# paperbrain/services/setup.py
from paperbrain.config import ConfigStore
from paperbrain.db import connect
from paperbrain.adapters.openai_client import OpenAIClient


def run_setup(
    *,
    database_url: str,
    openai_api_key: str,
    summary_model: str,
    embedding_model: str,
    config_path,
    test_connections: bool = True,
) -> str:
    if test_connections:
        with connect(database_url):
            pass
        OpenAIClient(api_key=openai_api_key)
    ConfigStore(config_path).save(
        database_url=database_url,
        openai_api_key=openai_api_key,
        summary_model=summary_model,
        embedding_model=embedding_model,
    )
    return f"Saved configuration to {config_path}"
```

```python
# paperbrain/cli.py (setup command options)
openai_api_key: str = typer.Option("", "--openai-api-key", prompt=True, hide_input=True)
summary_model: str = typer.Option("gpt-4.1-mini", "--summary-model")
embedding_model: str = typer.Option("text-embedding-3-small", "--embedding-model")
config_path: Path = typer.Option(Path("./config/paperbrain.conf"), "--config-path")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_setup_command.py::test_run_setup_writes_project_config -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperbrain/services/setup.py paperbrain/services/init.py paperbrain/cli.py tests/test_setup_command.py
git commit -m "feat: implement setup/init command wiring and connectivity checks"
```

### Task 6: Hybrid search, summarize cards, and browse over persisted data

**Files:**
- Modify: `paperbrain/services/search.py`
- Modify: `paperbrain/services/summarize.py`
- Modify: `paperbrain/repositories/postgres.py`
- Modify: `tests/test_search_service.py`
- Modify: `tests/test_summarize_service.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_search_service.py
from paperbrain.services.search import hybrid_score


def test_hybrid_score_math() -> None:
    assert hybrid_score(0.8, 0.2, alpha=0.6) == 0.56
```

```python
# tests/test_summarize_service.py
def test_summarize_service_persists_all_card_types(fake_repo, fake_llm):
    service = SummarizeService(repo=fake_repo, llm=fake_llm)
    stats = service.run(force_all=True)
    assert stats.paper_cards == 1
    assert stats.person_cards == 1
    assert stats.topic_cards == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_search_service.py tests/test_summarize_service.py -v`
Expected: FAIL on repository method gaps and incomplete summarize persistence behavior.

- [ ] **Step 3: Write minimal implementation**

```python
# paperbrain/services/search.py
def hybrid_score(keyword_rank: float, vector_rank: float, alpha: float = 0.6) -> float:
    return round(alpha * keyword_rank + (1 - alpha) * vector_rank, 2)
```

```python
# paperbrain/services/summarize.py
for paper in papers:
    metadata = {
        "slug": paper.slug,
        "title": paper.title,
        "journal": paper.journal,
        "year": paper.year,
        "authors": paper.authors,
        "corresponding_authors": paper.corresponding_authors,
    }
    card = self.llm.summarize_paper(paper.full_text, metadata)
    self.repo.upsert_paper_card(card)
    paper_cards.append(card)
person_cards = self.llm.derive_person_cards(paper_cards)
topic_cards = self.llm.derive_topic_cards(person_cards)
self.repo.upsert_person_cards(person_cards)
self.repo.upsert_topic_cards(topic_cards)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_search_service.py tests/test_summarize_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperbrain/services/search.py paperbrain/services/summarize.py paperbrain/repositories/postgres.py tests/test_search_service.py tests/test_summarize_service.py
git commit -m "feat: implement hybrid retrieval and card summarization persistence"
```

### Task 7: Lint, stats, and markdown export with bidirectional links

**Files:**
- Modify: `paperbrain/quality.py`
- Modify: `paperbrain/exporter.py`
- Modify: `paperbrain/services/lint.py`
- Modify: `paperbrain/services/stats.py`
- Modify: `paperbrain/services/export.py`
- Modify: `tests/test_quality_export.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_quality_export.py
from pathlib import Path
from paperbrain.services.export import export_markdown_files


def test_export_markdown_files_writes_all(tmp_path: Path) -> None:
    count = export_markdown_files(
        tmp_path,
        {
            "papers/a.md": "# A\n",
            "people/p.md": "# P\n",
            "topics/t.md": "# T\n",
        },
    )
    assert count == 3
    assert (tmp_path / "papers" / "a.md").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_quality_export.py::test_export_markdown_files_writes_all -v`
Expected: FAIL if export path handling is incomplete.

- [ ] **Step 3: Write minimal implementation**

```python
# paperbrain/services/export.py
from pathlib import Path
from paperbrain.exporter import write_markdown


def export_markdown_files(output_dir: Path, pages: dict[str, str]) -> int:
    written = 0
    for rel, content in pages.items():
        write_markdown(output_dir / rel, content)
        written += 1
    return written
```

```python
# paperbrain/quality.py
def normalize_whitespace(text: str) -> str:
    return " ".join(text.split()) + "\n"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_quality_export.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperbrain/quality.py paperbrain/exporter.py paperbrain/services/lint.py paperbrain/services/stats.py paperbrain/services/export.py tests/test_quality_export.py
git commit -m "feat: finalize lint, stats, and markdown export workflows"
```

### Task 8: Live integration tests for OpenAI + Postgres + local PDFs

**Files:**
- Create: `tests/test_live_openai_pipeline.py`
- Modify: `README.md`

- [ ] **Step 1: Write the failing live test**

```python
# tests/test_live_openai_pipeline.py
import os
import pytest
from typer.testing import CliRunner
from paperbrain.cli import app


@pytest.mark.skipif(os.getenv("PAPERBRAIN_LIVE_TEST") != "1", reason="live test disabled")
def test_live_ingest_and_summarize_pipeline() -> None:
    assert os.getenv("OPENAI_API_KEY")
    runner = CliRunner()
    db_url = "postgresql://postgres:PaperBrainLocal2026ChangeMe@localhost:5432/paperbrain"
    setup = runner.invoke(
        app,
        [
            "setup",
            "--url",
            db_url,
            "--openai-api-key",
            os.environ["OPENAI_API_KEY"],
            "--summary-model",
            "gpt-4.1-mini",
            "--embedding-model",
            "text-embedding-3-small",
        ],
    )
    assert setup.exit_code == 0
    init = runner.invoke(app, ["init", "--url", db_url, "--force"])
    assert init.exit_code == 0
    ingest = runner.invoke(app, ["ingest", "tests/pdf", "--recursive", "--force-all"])
    assert ingest.exit_code == 0
    summarize = runner.invoke(app, ["summarize", "--force-all"])
    assert summarize.exit_code == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PAPERBRAIN_LIVE_TEST=1 OPENAI_API_KEY="$OPENAI_API_KEY" python3 -m pytest tests/test_live_openai_pipeline.py -v`
Expected: FAIL initially until CLI uses real adapters and DB repository wiring.

- [ ] **Step 3: Write minimal implementation**

```python
# paperbrain/cli.py
def _build_runtime(config_path: Path):
    cfg = ConfigStore(config_path).load()
    conn = psycopg.connect(cfg.database_url)
    repo = PostgresRepo(conn)
    oai = OpenAIClient(api_key=cfg.openai_api_key)
    parser = DoclingParser()
    embeddings = OpenAIEmbeddingAdapter(oai, cfg.embedding_model)
    summarizer = OpenAISummaryAdapter(oai, cfg.summary_model)
    return repo, parser, embeddings, summarizer
```

```markdown
# README.md (new section)
## Live test
PAPERBRAIN_LIVE_TEST=1 OPENAI_API_KEY="$OPENAI_API_KEY" python3 -m pytest tests/test_live_openai_pipeline.py -v
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest -q`
Expected: PASS (live test skipped by default).

Run: `PAPERBRAIN_LIVE_TEST=1 OPENAI_API_KEY="$OPENAI_API_KEY" python3 -m pytest tests/test_live_openai_pipeline.py -v`
Expected: PASS when Postgres/OpenAI are reachable.

- [ ] **Step 5: Commit**

```bash
git add tests/test_live_openai_pipeline.py paperbrain/cli.py README.md
git commit -m "test: add optional live end-to-end OpenAI and Postgres pipeline test"
```
