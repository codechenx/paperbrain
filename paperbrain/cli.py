import os
from pathlib import Path

import typer

from paperbrain.config import DEFAULT_EMBEDDING_MODEL, DEFAULT_SUMMARY_MODEL
from paperbrain.services.init import run_init
from paperbrain.services.setup import run_setup

app = typer.Typer(no_args_is_help=True, help="PaperBrain CLI")


@app.command()
def setup(
    url: str = typer.Option(..., "--url", help="Postgres connection URL"),
    openai_api_key: str | None = typer.Option(None, "--openai-api-key", help="OpenAI API key"),
    summary_model: str = typer.Option(DEFAULT_SUMMARY_MODEL, "--summary-model"),
    embedding_model: str = typer.Option(DEFAULT_EMBEDDING_MODEL, "--embedding-model"),
    config_path: Path = typer.Option(Path("./config/paperbrain.conf"), "--config-path"),
    test_connections: bool = typer.Option(
        True,
        "--test-connections/--no-test-connections",
        help="Validate database and OpenAI connectivity before writing config",
    ),
) -> None:
    if openai_api_key is not None:
        resolved_openai_api_key = openai_api_key.strip()
    else:
        resolved_openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not resolved_openai_api_key and test_connections:
        resolved_openai_api_key = typer.prompt("OpenAI API key", hide_input=True).strip()
    message = run_setup(
        database_url=url,
        openai_api_key=resolved_openai_api_key,
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
) -> None:
    typer.echo(f"Ingest scaffold ready for path={path} force_all={force_all} recursive={recursive}")


@app.command()
def browse(
    keyword: str = typer.Argument(...),
    card_type: str = typer.Option("all", "--type"),
) -> None:
    typer.echo(f"Browse scaffold ready for keyword={keyword} type={card_type}")


@app.command()
def search(
    query: str = typer.Argument(...),
    top_k: int = typer.Option(10, "--top-k"),
    include_cards: bool = typer.Option(False, "--include-cards"),
) -> None:
    typer.echo(f"Search scaffold ready for query={query} top_k={top_k} include_cards={include_cards}")


@app.command()
def summarize(force_all: bool = typer.Option(False, "--force-all")) -> None:
    typer.echo(f"Summarize scaffold ready force_all={force_all}")


@app.command()
def lint() -> None:
    typer.echo("Lint scaffold ready")


@app.command()
def stats() -> None:
    typer.echo("Stats scaffold ready")


@app.command()
def export(output_dir: Path = typer.Option(Path("./paperbrain-export"), "--output-dir")) -> None:
    typer.echo(f"Export scaffold ready output_dir={output_dir}")
