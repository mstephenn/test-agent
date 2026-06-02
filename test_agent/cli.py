# test_agent/cli.py — full replacement

from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Optional
import typer
from rich.console import Console
from rich.panel import Panel

from test_agent.config import load_config
from test_agent.detector import detect_stacks
from test_agent.display import StartupDisplay, compute_structure_hash
from test_agent.executor import ExecutorAgent, ExecutorResult
from test_agent.scanner import scan_files, scan_test_files
from test_agent.coverage import parse_coverage
from test_agent.gap_finder import find_gaps
from test_agent.memory import Memory
from test_agent.session_log import SessionLog
from test_agent.repl import run_repl, Decision
from test_agent.target_resolver import read_reference_test_context, resolve_test_target
from test_agent.writer import clean_test_code, write_suggestion
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
    headless: bool = typer.Option(False, "--headless", help="Process all files unattended with parallel workers"),
    auto: bool = typer.Option(False, "--auto", help="Auto mode: approve all, fix failures, run until no files remain"),
    workers: Optional[int] = typer.Option(None, "--workers", help="Number of parallel workers for --headless/--auto (overrides config)"),
):
    config = load_config(project_root)
    if provider:
        config.provider = provider

    memory = Memory(project_root / ".test-agent" / "memory.db")
    project_root_str = str(project_root.resolve())
    structure_hash = compute_structure_hash(project_root)

    scan = memory.get_project_scan(project_root_str)
    cache_hit = scan is not None and scan["structure_hash"] == structure_hash
    cached_at = scan["last_scan_at"][:10] if cache_hit and scan else None

    stacks = detect_stacks(project_root)
    if not stacks:
        console.print("[red]No supported stack detected in this directory.[/]")
        raise typer.Exit(1)

    display = StartupDisplay()
    display.show_detection(stacks, project_root, from_cache=cache_hit, cached_at=cached_at)
    display.show_structure(project_root, from_cache=cache_hit, cached_at=cached_at)

    if not cache_hit:
        memory.save_project_scan(project_root_str, [p.name for p in stacks], structure_hash)

    session_id = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H-%M-%S")
    session_log = SessionLog(project_root=project_root, session_id=session_id)
    llm = get_provider(config.provider, model=model)
    changed_files = _get_changed_files(project_root, since) if (changed or since) else None

    # Pre-scan all source files to compute queued/already_done counts for Step 3 panel
    plugin_source_files: dict[str, list[Path]] = {}
    already_done_count = 0
    queued_count = 0
    for plugin in stacks:
        extensions = _SOURCE_EXTENSIONS.get(plugin.name, [])
        source_files = scan_files(
            project_root,
            extensions=extensions,
            exclude_paths=config.exclude_paths,
            scope_path=path,
            changed_files=changed_files,
        )
        plugin_source_files[plugin.name] = source_files
        for sf in source_files:
            rel = str(sf.relative_to(project_root))
            if memory.get_file_state(project_root_str, rel):
                already_done_count += 1
            else:
                queued_count += 1

    display.show_memory_status(
        queued=queued_count,
        already_done=already_done_count,
        last_scan_at=scan["last_scan_at"] if scan else None,
    )

    if auto:
        from test_agent.auto_runner import AutoRunner
        workers_count = workers if workers is not None else config.headless_workers
        result = AutoRunner().run(
            stacks=stacks,
            plugin_source_files=plugin_source_files,
            project_root=project_root,
            project_root_str=project_root_str,
            config=config,
            llm=llm,
            memory=memory,
            workers=workers_count,
        )
        _print_auto_summary(result)
        memory.close()
        raise typer.Exit(0)

    if headless:
        from test_agent.headless import HeadlessRunner
        workers_count = workers if workers is not None else config.headless_workers
        result = HeadlessRunner().run(
            stacks=stacks,
            plugin_source_files=plugin_source_files,
            project_root=project_root,
            project_root_str=project_root_str,
            config=config,
            llm=llm,
            memory=memory,
            workers=workers_count,
        )
        _print_headless_summary(result)
        memory.close()
        raise typer.Exit(0)

    total_suggestions = 0
    all_results = []

    executor = ExecutorAgent()
    remaining_suggestions = config.max_suggestions

    for plugin in stacks:
        source_files = plugin_source_files.get(plugin.name, [])
        coverage_data = _find_coverage_report(project_root, plugin)
        extensions = _SOURCE_EXTENSIONS.get(plugin.name, [])
        existing_tests = scan_test_files(project_root, extensions=extensions, exclude_paths=config.exclude_paths)
        framework = plugin.detect_framework(project_root)
        style_notes = memory.get_style_note("style") or ""

        for source_file in source_files:
            if remaining_suggestions <= 0:
                break

            rel_path = str(source_file.relative_to(project_root))
            if memory.get_file_state(project_root_str, rel_path):
                continue

            gaps = find_gaps(
                source_files=[source_file],
                project_root=project_root,
                coverage_data=coverage_data,
                existing_test_files=existing_tests,
            )
            gaps = [g for g in gaps if not memory.is_skipped(g.file, g.symbol)]
            gaps = gaps[:remaining_suggestions]
            if not gaps:
                continue

            console.print(f"\n[bold]●[/bold] {rel_path}")

            with ThreadPoolExecutor(max_workers=2) as pool:
                future_baseline = pool.submit(executor.run_baseline, source_file, project_root, plugin)

                writer_futures: list[tuple] = []
                for gap in gaps:
                    target = resolve_test_target(gap, project_root, plugin, existing_tests)
                    target_file_rel = str(target.path.relative_to(project_root))
                    existing_test_context = read_reference_test_context(target, existing_tests)
                    source_import_path = _source_import_path(target.path, project_root / gap.file)
                    requester = f"test-agent via {config.provider}"
                    fw = pool.submit(
                        _generate_valid_test,
                        llm=llm,
                        gap=gap,
                        plugin=plugin,
                        config=config,
                        style_notes=style_notes,
                        target_file=target_file_rel,
                        target_status=target.status,
                        framework=framework,
                        existing_test_context=existing_test_context,
                        source_import_path=source_import_path,
                        requester=requester,
                    )
                    writer_futures.append((fw, target.path))

                file_suggestions = [f.result() for f, _ in writer_futures]
                target_paths = [p for _, p in writer_futures]
                baseline = future_baseline.result()

            _print_baseline(console, baseline)
            console.print(f"  [dim][writer][/dim]    {len(file_suggestions)} suggestion(s) ready")

            results = run_repl(file_suggestions, memory=memory, auto_approve=auto_approve, dry_run=dry_run)
            all_results.extend(results)

            _apply_results_with_verify(
                results=results,
                target_paths=target_paths,
                baseline=baseline,
                dry_run=dry_run,
                project_root=project_root,
                session_id=session_id,
                session_log=session_log,
                memory=memory,
                executor=executor,
                plugin=plugin,
            )

            memory.save_file_state(project_root_str, rel_path, len(gaps))
            total_suggestions += len(file_suggestions)
            approved_count = sum(
                1 for r in results if r.decision in (Decision.APPROVED, Decision.EDITED)
            )
            remaining_suggestions -= approved_count

    if not all_results:
        console.print("[green]No coverage gaps found — nothing to do.[/]")
        raise typer.Exit(0)

    coverage_after = _run_tests_and_get_coverage(project_root, stacks) if measure and not dry_run else None
    session_log.finalize(
        provider=config.provider,
        gaps_found=total_suggestions,
        stack=[p.name for p in stacks],
        coverage_after=coverage_after,
    )
    memory.save_session(
        session_id=session_id,
        provider=config.provider,
        gaps_found=total_suggestions,
        approved=sum(1 for r in all_results if r.decision in (Decision.APPROVED, Decision.EDITED)),
        skipped=sum(1 for r in all_results if r.decision in (Decision.SKIPPED, Decision.SKIPPED_PERMANENTLY)),
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


def _get_changed_files(project_root: Path, since: Optional[str]) -> list[Path] | None:
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
        return None
    return [project_root / f.strip() for f in result.stdout.splitlines() if f.strip()]


def _generate_valid_test(
    *,
    llm,
    gap,
    plugin,
    config,
    style_notes: str,
    target_file: str,
    target_status: str,
    framework: str,
    existing_test_context: str,
    source_import_path: str,
    requester: str,
):
    feedback = ""
    last_suggestion = None
    for attempt in range(1, 4):
        attempt_style_notes = style_notes
        if feedback:
            attempt_style_notes = (
                f"{style_notes}\n\nPrevious generated output was rejected: {feedback}\n"
                f"Regenerate the test so it matches the target framework and contains raw code only."
            ).strip()
        suggestion = llm.generate_test(
            gap,
            plugin,
            config,
            attempt_style_notes,
            target_file=target_file,
            target_status=target_status,
            framework=framework,
            existing_test_context=existing_test_context,
            source_import_path=source_import_path,
            requester=requester,
        )
        last_suggestion = suggestion
        feedback = _test_code_rejection_reason(suggestion.test_code, framework, gap, source_import_path)
        if not feedback:
            return suggestion
        console.print(f"[yellow]Regenerating {gap.symbol}(): {feedback}[/]")
    return last_suggestion


def _test_code_rejection_reason(test_code: str, framework: str, gap, source_import_path: str = "") -> str:
    if test_code.strip().startswith("```"):
        return "output used Markdown code fences instead of raw code"
    cleaned = clean_test_code(test_code)
    if not cleaned:
        return "empty test code"
    lowered = cleaned.lower()
    if "assuming " in lowered or "adjust the import path" in lowered:
        return "output included assumptions instead of using repo paths"
    if framework.startswith("mocha") and _looks_like_jest(cleaned):
        return "output used Jest APIs in a Mocha/Chai/Sinon project"
    if source_import_path and source_import_path not in cleaned:
        return f"output did not import the project source from {source_import_path}"
    expected_subject = _expected_project_subject(gap)
    if expected_subject and expected_subject not in cleaned:
        return f"output did not import or exercise project subject {expected_subject}"
    return ""


def _looks_like_jest(code: str) -> bool:
    jest_markers = (
        "jest.", "jest.mock",
        ".toBe(", ".toEqual(", ".toThrow(",
        ".resolves.", ".rejects.",
        ".toBeUndefined(", ".toBeNull(", ".toBeTruthy(", ".toBeFalsy(",
    )
    return any(marker in code for marker in jest_markers)


def _expected_project_subject(gap) -> str:
    class_match = re.search(r"\bclass\s+([A-Za-z_$][\w$]*)", gap.context_lines)
    if class_match:
        return class_match.group(1)
    function_match = re.search(r"\b(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)", gap.context_lines)
    if function_match:
        return function_match.group(1)
    const_match = re.search(r"\b(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*=", gap.context_lines)
    if const_match:
        return const_match.group(1)
    return gap.symbol


def _source_import_path(target_path: Path, source_path: Path) -> str:
    import_path = Path(os_path_relpath(source_path.with_suffix(""), start=target_path.parent))
    text = import_path.as_posix()
    if not text.startswith("."):
        text = f"./{text}"
    return text


def os_path_relpath(path: Path, start: Path) -> str:
    import os
    return os.path.relpath(path, start)


def _apply_results_with_verify(
    results: list,
    target_paths: list[Path],
    baseline: ExecutorResult,
    dry_run: bool,
    project_root: Path,
    session_id: str,
    session_log: SessionLog,
    memory: Memory,
    executor: ExecutorAgent,
    plugin,
) -> None:
    for result, target_path in zip(results, target_paths):
        if result.decision in (Decision.APPROVED, Decision.EDITED) and not dry_run:
            suggestion = result.suggestion
            if result.decision == Decision.EDITED and result.final_code is not None:
                suggestion = replace(result.suggestion, test_code=result.final_code)
            write_suggestion(suggestion, project_root=project_root)
            if result.decision == Decision.EDITED:
                session_log.record_edited(suggestion.target_file)
            else:
                session_log.record_approved(suggestion.target_file)
            memory.record_outcome(session_id, suggestion.gap.file, suggestion.gap.symbol, result.decision.value)
            try:
                verify = executor.run_verify(target_path, project_root, plugin)
                _print_verify(console, verify, baseline, target_path)
            except Exception as exc:
                console.print(f"  [dim][verify][/dim]    [dim]could not run: {exc}[/dim]")
        elif result.decision == Decision.SKIPPED_PERMANENTLY:
            session_log.record_skipped()
        elif result.decision == Decision.SKIPPED:
            session_log.record_skipped()
            memory.record_outcome(session_id, result.suggestion.gap.file, result.suggestion.gap.symbol, "skipped")


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


def _print_baseline(console: Console, result: ExecutorResult) -> None:
    if result.passed == 0 and result.failed == 0 and result.errors == 0:
        return
    color = "green" if result.success else "red"
    console.print(
        f"  [dim][baseline][/dim]  [{color}]{result.passed} pass · {result.failed} fail[/{color}]"
    )


def _print_verify(console: Console, result: ExecutorResult, baseline: ExecutorResult, test_file: Path) -> None:
    delta = result.passed - baseline.passed
    delta_str = f"  [dim](+{delta} new)[/dim]" if delta > 0 else ""
    if result.success:
        console.print(
            f"  [dim][verify][/dim]    [green]✅  {result.passed} pass · {result.failed} fail[/green]{delta_str}"
        )
    else:
        console.print(
            f"  [dim][verify][/dim]    [red]❌  {result.passed} pass · {result.failed} fail[/red]"
        )
        first_fail = result.first_failure_line
        if first_fail:
            console.print(f"              [dim]{first_fail}[/dim]")
        console.print(f"              [dim](run pytest {test_file} for full output)[/dim]")


def _print_headless_summary(result) -> None:
    from test_agent.headless import HeadlessResult
    mins, secs = divmod(int(result.duration_s), 60)
    log_note = f"     {result.verify_failures} verify failures  (see .test-agent/headless.log)" if result.verify_failures else f"     0 verify failures"
    body = (
        f"  {result.files_scanned} files scanned\n"
        f"   {result.files_scanned - result.files_with_gaps} files: no gaps found\n"
        f"   {result.tests_written} tests written\n"
        f"{log_note}\n"
        f"  Duration: {mins}m {secs:02d}s"
    )
    console.print(Panel(body, title="Run Complete"))


def _print_auto_summary(result) -> None:
    from test_agent.auto_runner import AutoResult
    mins, secs = divmod(int(result.duration_s), 60)
    log_note = (
        f"     {result.fix_failures} fix failures  (see .test-agent/auto.log)"
        if result.fix_failures
        else "     0 fix failures"
    )
    fixes_note = f"   {result.fixes_applied} fixes applied\n" if result.fixes_applied else ""
    body = (
        f"  {result.files_scanned} files scanned\n"
        f"   {result.files_scanned - result.files_with_gaps} files: no gaps found\n"
        f"   {result.tests_written} tests written\n"
        f"{fixes_note}"
        f"{log_note}\n"
        f"  Duration: {mins}m {secs:02d}s"
    )
    console.print(Panel(body, title="Auto Run Complete"))


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
