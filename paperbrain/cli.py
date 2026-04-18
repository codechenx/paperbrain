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
from paperbrain.summary_provider import SummaryProvider
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
SUPPORTED_CARD_SCOPES = ("all", "paper", "person", "topic")


@dataclass(slots=True)
class RuntimeAdapters:
    config: AppConfig
    parser: DoclingParser
    embeddings: OpenAIEmbeddingAdapter | None
    llm: LLMAdapter


def build_runtime(config_path: Path) -> RuntimeAdapters:
    provider = SummaryProvider(config_path)
    return RuntimeAdapters(
        config=provider.config,
        parser=provider.parser,
        embeddings=provider.embeddings,
        llm=provider.llm,
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
    embeddings_enabled: bool = typer.Option(
        False,
        "--embeddings-enabled/--no-embeddings-enabled",
    ),
    config_path: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config-path"),
    test_connections: bool = typer.Option(
        True,
        "--test-connections/--no-test-connections",
        help="Validate database and provider connectivity before writing config",
    ),
) -> None:
    if openai_api_key is not None:
        resolved_openai_api_key = openai_api_key.strip()
    else:
        resolved_openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    summary_uses_openai = summary_model.strip().lower().startswith("openai:")
    needs_openai_key = embeddings_enabled or summary_uses_openai
    if not resolved_openai_api_key and test_connections and needs_openai_key:
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
        embeddings_enabled=embeddings_enabled,
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
    card_scope: str | None = typer.Option(None, "--card-scope"),
    config_path: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config-path"),
) -> None:
    normalized_scope = card_scope.strip().lower() if card_scope is not None else None
    if normalized_scope is not None and normalized_scope not in SUPPORTED_CARD_SCOPES:
        allowed_values = ", ".join(SUPPORTED_CARD_SCOPES)
        raise typer.BadParameter(
            f"Allowed values: {allowed_values}",
            param_hint="'--card-scope'",
        )

    runtime = build_runtime(config_path)
    with repo_from_url(runtime.config.database_url) as repo:
        summarize_service = SummarizeService(repo=repo, llm=runtime.llm)
        stats = summarize_service.run(card_scope=normalized_scope)
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
