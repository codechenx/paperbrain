from pathlib import Path

import typer

from paperbrain.services.init import build_init_sql
from paperbrain.services.setup import run_setup

app = typer.Typer(no_args_is_help=True, help="PaperBrain CLI")


@app.command()
def setup(
    url: str = typer.Option(..., "--url", help="Postgres connection URL"),
    config_path: Path = typer.Option(Path("~/.config/paperbrain.conf").expanduser(), "--config-path"),
) -> None:
    message = run_setup(database_url=url, config_path=config_path)
    typer.echo(message)


@app.command()
def init(
    url: str = typer.Option(..., "--url", help="Postgres connection URL"),
    force: bool = typer.Option(False, "--force", help="Drop and recreate all tables"),
) -> None:
    _ = url
    statements = build_init_sql(force=force)
    typer.echo(f"Prepared {len(statements)} schema statements.")


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

