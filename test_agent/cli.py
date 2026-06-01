# test_agent/cli.py — full replacement

from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console

from test_agent.config import load_config
from test_agent.detector import detect_stacks
from test_agent.scanner import scan_files
from test_agent.coverage import parse_coverage
from test_agent.gap_finder import find_gaps
from test_agent.memory import Memory
from test_agent.session_log import SessionLog
from test_agent.repl import run_repl, Decision
from test_agent.writer import write_suggestion
from test_agent.llm.base import get_provider

app = typer.Typer(help="test-agent: interactive test coverage improvement")
console = Console()

_SOURCE_EXTENSIONS = {
    "Python": [".py"],
    "JavaScript": [".js", ".mjs"],
    "TypeScript": [".ts", ".tsx"],
    "Java": [".java"],
    "Ruby": [".rb"],
    "Go": [".go"],
}


@app.command()
def run(
    project_root: Path = typer.Argument(Path("."), help="Path to the repo root (defaults to current directory)"),
    changed: bool = typer.Option(False, "--changed", help="Only files changed vs main"),
    since: Optional[str] = typer.Option(None, "--since", help="Git ref to compare from"),
    path: Optional[Path] = typer.Option(None, "--path", help="Limit to a subdirectory"),
    provider: Optional[str] = typer.Option(None, "--provider", help="LLM provider override"),
    model: Optional[str] = typer.Option(None, "--model", help="Model name override (e.g. qwen2.5-coder for Ollama)"),
    auto_approve: bool = typer.Option(False, "--auto-approve"),
    measure: bool = typer.Option(False, "--measure", help="Re-run tests after applying suggestions"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show suggestions, write nothing"),
):
    config = load_config(project_root)
    if provider:
        config.provider = provider

    stacks = detect_stacks(project_root)
    if not stacks:
        console.print("[red]No supported stack detected in this directory.[/]")
        raise typer.Exit(1)

    console.print(f"[bold]Detected:[/] {', '.join(p.name for p in stacks)}")

    memory = Memory(project_root / ".test-agent" / "memory.db")
    session_id = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H-%M-%S")
    session_log = SessionLog(project_root=project_root, session_id=session_id)
    llm = get_provider(config.provider, model=model)

    changed_files = _get_changed_files(project_root, since) if (changed or since) else None

    all_suggestions = []

    for plugin in stacks:
        extensions = _SOURCE_EXTENSIONS.get(plugin.name, [])
        source_files = scan_files(
            project_root,
            extensions=extensions,
            exclude_paths=config.exclude_paths,
            scope_path=path,
            changed_files=changed_files,
        )
        coverage_data = _find_coverage_report(project_root, plugin)
        existing_tests = scan_files(project_root, extensions=extensions, exclude_paths=config.exclude_paths)

        gaps = find_gaps(
            source_files=source_files,
            project_root=project_root,
            coverage_data=coverage_data,
            existing_test_files=existing_tests,
        )
        gaps = [g for g in gaps if not memory.is_skipped(g.file, g.symbol)]
        gaps = gaps[: config.max_suggestions]

        style_notes = memory.get_style_note("style") or ""

        for gap in gaps:
            with console.status(f"Generating test for [cyan]{gap.symbol}()[/]..."):
                suggestion = llm.generate_test(gap, plugin, config, style_notes)
            all_suggestions.append(suggestion)

    if not all_suggestions:
        console.print("[green]No coverage gaps found — nothing to do.[/]")
        raise typer.Exit(0)

    results = run_repl(all_suggestions, memory=memory, auto_approve=auto_approve, dry_run=dry_run)

    for result in results:
        if result.decision in (Decision.APPROVED, Decision.EDITED) and not dry_run:
            write_suggestion(result.suggestion, project_root=project_root)
            session_log.record_approved(result.suggestion.target_file)
            memory.record_outcome(session_id, result.suggestion.gap.file, result.suggestion.gap.symbol, result.decision.value)
        elif result.decision == Decision.SKIPPED_PERMANENTLY:
            session_log.record_skipped()
        elif result.decision == Decision.SKIPPED:
            session_log.record_skipped()
            memory.record_outcome(session_id, result.suggestion.gap.file, result.suggestion.gap.symbol, "skipped")

    coverage_after = _run_tests_and_get_coverage(project_root, stacks) if measure and not dry_run else None
    session_log.finalize(
        provider=config.provider,
        gaps_found=len(all_suggestions),
        stack=[p.name for p in stacks],
        coverage_after=coverage_after,
    )
    memory.save_session(
        session_id=session_id,
        provider=config.provider,
        gaps_found=len(all_suggestions),
        approved=sum(1 for r in results if r.decision in (Decision.APPROVED, Decision.EDITED)),
        skipped=sum(1 for r in results if r.decision in (Decision.SKIPPED, Decision.SKIPPED_PERMANENTLY)),
    )
    memory.close()


@app.command()
def init(
    project_root: Path = typer.Argument(Path("."), help="Repo root to initialise config in"),
):
    config_path = project_root / "test-agent.config.json"
    if config_path.exists():
        console.print("[yellow]test-agent.config.json already exists.[/]")
        raise typer.Exit(1)
    config_path.write_text(
        '{\n  "provider": "claude",\n  "excludePaths": [],\n  "maxSuggestionsPerRun": 20\n}\n'
    )
    console.print(f"[green]Created[/] {config_path}")


def _get_changed_files(project_root: Path, since: Optional[str]) -> list[Path]:
    import subprocess
    ref = since or "main"
    result = subprocess.run(
        ["git", "diff", "--name-only", ref],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        console.print(f"[yellow]Warning: git diff failed, scanning all files.[/]")
        return []
    return [project_root / f.strip() for f in result.stdout.splitlines() if f.strip()]


def _run_tests_and_get_coverage(project_root: Path, stacks) -> float | None:
    """Run the test suite and return line coverage percentage, or None on failure."""
    import subprocess
    runner = stacks[0].test_runner if stacks else "pytest"
    result = subprocess.run(
        runner.split() + ["--cov", "--cov-report=json", "-q"],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    coverage_json = project_root / "coverage.json"
    if coverage_json.exists():
        import json
        try:
            data = json.loads(coverage_json.read_text())
            return data.get("totals", {}).get("percent_covered")
        except Exception:
            pass
    return None


def _find_coverage_report(project_root: Path, plugin) -> object | None:
    candidates = [
        project_root / "coverage" / "lcov.info",
        project_root / "htmlcov" / "coverage.json",
        project_root / ".nyc_output" / "out.json",
        project_root / "coverage.xml",
        project_root / "target" / "site" / "jacoco" / "jacoco.xml",
    ]
    for c in candidates:
        if c.exists():
            try:
                return parse_coverage(c)
            except Exception:
                continue
    return None
