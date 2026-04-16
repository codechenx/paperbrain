import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import typer

try:
    import uvicorn
except ModuleNotFoundError:  # pragma: no cover - env guard
    uvicorn = None  # type: ignore[assignment]

from paperbrain.adapters.docling import DoclingParser
from paperbrain.adapters.embedding import OpenAIEmbeddingAdapter
from paperbrain.adapters.gemini_client import GeminiClient
from paperbrain.adapters.llm import GeminiSummaryAdapter, LLMAdapter, OllamaSummaryAdapter, OpenAISummaryAdapter
from paperbrain.adapters.ollama_client import OllamaCloudClient
from paperbrain.adapters.openai_client import OpenAIClient
from paperbrain.config import AppConfig, ConfigStore
from paperbrain.config import DEFAULT_EMBEDDING_MODEL, DEFAULT_SUMMARY_MODEL
from paperbrain.db import connect
from paperbrain.repositories.postgres import PostgresRepo
from paperbrain.services.export import run_export
from paperbrain.services.ingest import IngestService
from paperbrain.services.init import run_init
from paperbrain.services.lint import run_lint
from paperbrain.services.search import SearchService
from paperbrain.services.setup import run_setup
from paperbrain.services.stats import run_stats
from paperbrain.services.summarize import SummarizeService

app = typer.Typer(no_args_is_help=True, help="PaperBrain CLI")
DEFAULT_CONFIG_PATH = Path.home() / ".config" / "paperbrain" / "paperbrain.conf"


@dataclass(slots=True)
class RuntimeAdapters:
    config: AppConfig
    parser: DoclingParser
    embeddings: OpenAIEmbeddingAdapter
    llm: LLMAdapter


def _is_gemini_summary_model(summary_model: str) -> bool:
    return summary_model.strip().lower().startswith("gemini-")


def _is_ollama_summary_model(summary_model: str) -> bool:
    return summary_model.strip().lower().startswith("ollama:")


def _strip_ollama_model_prefix(summary_model: str) -> str:
    stripped = summary_model.strip()
    if not _is_ollama_summary_model(stripped):
        raise ValueError("Summary model must start with ollama:")
    model = stripped[len("ollama:") :].strip()
    if not model:
        raise ValueError("Ollama summary model must include a model name after 'ollama:'")
    return model


def build_runtime(config_path: Path) -> RuntimeAdapters:
    config = ConfigStore(config_path).load()
    summary_model = config.summary_model
    summary_uses_gemini = _is_gemini_summary_model(summary_model)
    summary_uses_ollama = _is_ollama_summary_model(summary_model)
    ollama_base_url = config.ollama_base_url.strip()
    if not config.openai_api_key.strip():
        raise ValueError("OpenAI API key is required for embeddings")
    if summary_uses_gemini and not config.gemini_api_key.strip():
        raise ValueError("Gemini API key is required for Gemini summary models")
    if summary_uses_ollama and not config.ollama_api_key.strip():
        raise ValueError("Ollama API key is required for Ollama summary models")
    if summary_uses_ollama and not ollama_base_url:
        raise ValueError("Ollama base URL is required for Ollama summary models")
    openai_client = OpenAIClient(api_key=config.openai_api_key)
    if summary_uses_gemini:
        summary_client = GeminiClient(api_key=config.gemini_api_key)
        llm: LLMAdapter = GeminiSummaryAdapter(client=summary_client, model=summary_model)
    elif summary_uses_ollama:
        summary_client = OllamaCloudClient(api_key=config.ollama_api_key, base_url=ollama_base_url)
        llm = OllamaSummaryAdapter(client=summary_client, model=_strip_ollama_model_prefix(summary_model))
    else:
        llm = OpenAISummaryAdapter(client=openai_client, model=summary_model)
    return RuntimeAdapters(
        config=config,
        parser=DoclingParser(),
        embeddings=OpenAIEmbeddingAdapter(client=openai_client, model=config.embedding_model),
        llm=llm,
    )


@contextmanager
def repo_from_url(database_url: str) -> Iterator[PostgresRepo]:
    with connect(database_url, autocommit=False) as connection:
        yield PostgresRepo(connection)


@app.command()
def setup(
    url: str = typer.Option(..., "--url", help="Postgres connection URL"),
    openai_api_key: str | None = typer.Option(None, "--openai-api-key", help="OpenAI API key"),
    gemini_api_key: str | None = typer.Option(None, "--gemini-api-key", help="Gemini API key"),
    ollama_api_key: str | None = typer.Option(None, "--ollama-api-key", help="Ollama API key"),
    ollama_base_url: str = typer.Option("https://ollama.com", "--ollama-base-url", help="Ollama base URL"),
    summary_model: str = typer.Option(DEFAULT_SUMMARY_MODEL, "--summary-model"),
    embedding_model: str = typer.Option(DEFAULT_EMBEDDING_MODEL, "--embedding-model"),
    config_path: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config-path"),
    test_connections: bool = typer.Option(
        True,
        "--test-connections/--no-test-connections",
        help="Validate database, OpenAI embeddings, and provider-aware summary connectivity before writing config",
    ),
) -> None:
    if openai_api_key is not None:
        resolved_openai_api_key = openai_api_key.strip()
    else:
        resolved_openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not resolved_openai_api_key and test_connections:
        resolved_openai_api_key = typer.prompt("OpenAI API key", hide_input=True).strip()
    if gemini_api_key is not None:
        resolved_gemini_api_key = gemini_api_key.strip()
    else:
        resolved_gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if ollama_api_key is not None:
        resolved_ollama_api_key = ollama_api_key.strip()
    else:
        resolved_ollama_api_key = os.getenv("OLLAMA_API_KEY", "").strip()
    message = run_setup(
        database_url=url,
        openai_api_key=resolved_openai_api_key,
        gemini_api_key=resolved_gemini_api_key,
        ollama_api_key=resolved_ollama_api_key,
        ollama_base_url=ollama_base_url,
        summary_model=summary_model,
        embedding_model=embedding_model,
        config_path=config_path,
        test_connections=test_connections,
    )
    typer.echo(message)


@app.command()
def init(
    url: str = typer.Option(..., "--url", help="Postgres connection URL"),
    force: bool = typer.Option(False, "--force", help="Drop and recreate all tables"),
) -> None:
    applied = run_init(database_url=url, force=force)
    typer.echo(f"Applied {applied} schema statements.")


@app.command()
def ingest(
    path: Path = typer.Argument(..., exists=True),
    force_all: bool = typer.Option(False, "--force-all"),
    recursive: bool = typer.Option(False, "--recursive"),
    config_path: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config-path"),
) -> None:
    runtime = build_runtime(config_path)
    with repo_from_url(runtime.config.database_url) as repo:
        inserted = IngestService(repo=repo, parser=runtime.parser, embeddings=runtime.embeddings).ingest_paths(
            [str(path)], force_all=force_all, recursive=recursive
        )
    typer.echo(f"Ingested {inserted} paper(s).")


@app.command()
def browse(
    keyword: str = typer.Argument(...),
    card_type: str = typer.Option("all", "--type"),
    config_path: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config-path"),
) -> None:
    runtime = build_runtime(config_path)
    with repo_from_url(runtime.config.database_url) as repo:
        rows = SearchService(repo=repo, embedder=runtime.embeddings).browse(keyword, card_type)
    if not rows:
        typer.echo("No cards found.")
        return
    for row in rows:
        typer.echo(json.dumps(row, sort_keys=True))


@app.command()
def search(
    query: str = typer.Argument(...),
    top_k: int = typer.Option(10, "--top-k"),
    include_cards: bool = typer.Option(False, "--include-cards"),
    config_path: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config-path"),
) -> None:
    runtime = build_runtime(config_path)
    with repo_from_url(runtime.config.database_url) as repo:
        rows = SearchService(repo=repo, embedder=runtime.embeddings).search(
            query, top_k=top_k, include_cards=include_cards
        )
    if not rows:
        typer.echo("No papers found.")
        return
    for row in rows:
        typer.echo(json.dumps(row, sort_keys=True))


@app.command()
def summarize(
    force_all: bool = typer.Option(False, "--force-all"),
    config_path: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config-path"),
) -> None:
    runtime = build_runtime(config_path)
    with repo_from_url(runtime.config.database_url) as repo:
        stats = SummarizeService(repo=repo, llm=runtime.llm).run(force_all=force_all)
    typer.echo(f"Summarized cards: papers={stats.paper_cards} people={stats.person_cards} topics={stats.topic_cards}")


@app.command()
def lint(config_path: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config-path")) -> None:
    config = ConfigStore(config_path).load()
    stats = run_lint(config.database_url)
    typer.echo(f"Linted {stats.checked} cards, fixed {stats.fixed}.")


@app.command()
def stats(config_path: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config-path")) -> None:
    config = ConfigStore(config_path).load()
    corpus = run_stats(config.database_url)
    typer.echo(f"Corpus stats: papers={corpus.papers} authors={corpus.authors} topics={corpus.topics}")


@app.command()
def export(
    output_dir: Path = typer.Option(Path("./paperbrain-export"), "--output-dir"),
    config_path: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config-path"),
) -> None:
    config = ConfigStore(config_path).load()
    stats = run_export(config.database_url, output_dir)
    typer.echo(
        f"Exported {stats.files_written} files (papers={stats.papers} people={stats.people} topics={stats.topics}) "
        f"to {output_dir}"
    )


@app.command()
def web(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
    reload: bool = typer.Option(False, "--reload/--no-reload"),
    config_path: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config-path"),
) -> None:
    from paperbrain.web import app as web_app

    if uvicorn is None:  # pragma: no cover - env guard
        typer.echo("uvicorn is required to run the web server", err=True)
        raise typer.Exit(code=1)

    def app_factory() -> object:
        return web_app.create_app(config_path=config_path)

    typer.echo(f"http://{host}:{port}")
    uvicorn.run(app_factory, host=host, port=port, reload=reload, factory=True)
