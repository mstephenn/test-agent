from __future__ import annotations
from pathlib import Path
from typing import Optional
import typer

app = typer.Typer(help="test-agent: interactive test coverage improvement")


@app.command()
def run(
    project_root: Path = typer.Argument(..., help="Path to the repo root"),
    changed: bool = typer.Option(False, "--changed", help="Only files changed vs main"),
    since: Optional[str] = typer.Option(None, "--since", help="Git ref to compare from"),
    path: Optional[Path] = typer.Option(None, "--path", help="Limit to a subdirectory"),
    provider: Optional[str] = typer.Option(None, "--provider", help="LLM provider override"),
    auto_approve: bool = typer.Option(False, "--auto-approve", help="Apply all suggestions without prompting"),
    measure: bool = typer.Option(False, "--measure", help="Re-run test suite to compute coverage delta"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show suggestions, write nothing"),
):
    typer.echo(f"Scanning {project_root} ...")


@app.command()
def init(
    project_root: Path = typer.Argument(Path("."), help="Repo root to initialise config in"),
):
    config_path = project_root / "test-agent.config.json"
    if config_path.exists():
        typer.echo("test-agent.config.json already exists.")
        raise typer.Exit(1)
    config_path.write_text(
        '{\n  "provider": "claude",\n  "excludePaths": [],\n  "maxSuggestionsPerRun": 20\n}\n'
    )
    typer.echo(f"Created {config_path}")
