from typer.testing import CliRunner

from paperbrain.cli import app


def test_cli_exposes_core_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    output = result.output
    for name in [
        "setup",
        "init",
        "ingest",
        "browse",
        "search",
        "summarize",
        "lint",
        "stats",
        "export",
        "web",
    ]:
        assert name in output
