from __future__ import annotations

import dataclasses
import json
import threading
import time
import traceback
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel

from test_agent.executor import ExecutorAgent
from test_agent.gap_finder import find_gaps
from test_agent.memory import Memory
from test_agent.scanner import scan_test_files
from test_agent.target_resolver import read_reference_test_context, resolve_test_target
from test_agent.writer import write_suggestion


_SOURCE_EXTENSIONS: dict[str, list[str]] = {
    "Python": [".py"],
    "JavaScript": [".js", ".mjs"],
    "TypeScript": [".ts", ".tsx"],
    "Java": [".java"],
    "Ruby": [".rb"],
    "Go": [".go"],
}
_BAR_WIDTH = 36
_MAX_RECENT = 10
_MAX_FIX_ATTEMPTS = 3


@dataclass
class FileOutcome:
    rel_path: str
    tests_written: int
    fixes_applied: int
    fix_failures: int
    had_error: bool = False


@dataclass
class AutoResult:
    files_scanned: int
    files_with_gaps: int
    tests_written: int
    fixes_applied: int
    fix_failures: int
    duration_s: float


class _State:
    """Thread-safe counters and worker phase map for the Live dashboard."""

    def __init__(self, total: int) -> None:
        self.total = total
        self._lock = threading.Lock()
        self._done = 0
        self._tests_written = 0
        self._fixes_applied = 0
        self._fix_failures = 0
        self._files_with_gaps = 0
        self._start = time.monotonic()
        self._active: dict[str, str] = {}
        self._recent: deque[FileOutcome] = deque(maxlen=_MAX_RECENT)

    def set_phase(self, filename: str, phase: str) -> None:
        with self._lock:
            self._active[filename] = phase

    def clear(self, filename: str) -> None:
        with self._lock:
            self._active.pop(filename, None)

    def record_done(self, outcome: FileOutcome) -> None:
        with self._lock:
            self._done += 1
            self._tests_written += outcome.tests_written
            self._fixes_applied += outcome.fixes_applied
            self._fix_failures += outcome.fix_failures
            if outcome.tests_written > 0 or outcome.fix_failures > 0:
                self._files_with_gaps += 1
            self._recent.appendleft(outcome)

    def snapshot(self) -> tuple:
        with self._lock:
            return (
                self._done,
                self.total,
                self._tests_written,
                self._fixes_applied,
                self._fix_failures,
                dict(self._active),
                list(self._recent),
                time.monotonic() - self._start,
            )

    @property
    def tests_written(self) -> int:
        with self._lock:
            return self._tests_written

    @property
    def fixes_applied(self) -> int:
        with self._lock:
            return self._fixes_applied

    @property
    def fix_failures(self) -> int:
        with self._lock:
            return self._fix_failures

    @property
    def files_with_gaps(self) -> int:
        with self._lock:
            return self._files_with_gaps


def _render(state: _State) -> Group:
    done, total, written, fixes, fix_fails, active, recent, elapsed = state.snapshot()

    filled = int(done / total * _BAR_WIDTH) if total else 0
    bar = "[green]" + "█" * filled + "[/green]" + "░" * (_BAR_WIDTH - filled)
    eta_str = ""
    if 0 < done < total:
        remaining_s = elapsed / done * (total - done)
        mins, secs = divmod(int(remaining_s), 60)
        eta_str = f"  ·  ~{mins}m {secs:02d}s left"

    stats = f"  {done} done  ·  {len(active)} active  ·  {written} tests written"
    if fixes:
        stats += f"  ·  {fixes} fixes applied"
    if fix_fails:
        stats += f"  ·  [red]{fix_fails} fix failures[/red]"
    progress_body = f"  {bar}  {done} / {total}{eta_str}\n{stats}"

    worker_lines = [
        f"  [{i}]  {fname:<42}  {phase}..."
        for i, (fname, phase) in enumerate(list(active.items()), start=1)
    ] or ["  (idle)"]

    completed_lines = []
    for outcome in recent:
        if outcome.had_error:
            icon, detail = "[red]✗[/red]", "error during processing"
        elif outcome.fix_failures:
            icon = "[yellow]⚠[/yellow]"
            detail = f"{outcome.tests_written} test(s) · fix failed after {_MAX_FIX_ATTEMPTS} attempts"
        elif outcome.fixes_applied:
            icon = "[cyan]✓[/cyan]"
            detail = f"{outcome.tests_written} test(s) · {outcome.fixes_applied} fix(es) applied"
        elif outcome.tests_written:
            icon, detail = "[green]✓[/green]", f"{outcome.tests_written} test(s) written"
        else:
            icon, detail = "[dim]·[/dim]", "no gaps"
        completed_lines.append(f"  {icon}  {outcome.rel_path:<44}  {detail}")

    return Group(
        Panel(progress_body, title="[bold]test-agent auto[/bold]"),
        Panel("\n".join(worker_lines), title="Active Workers"),
        Panel("\n".join(completed_lines) or "  (none yet)", title=f"Completed (last {_MAX_RECENT})"),
    )


def _source_import_path(target_path: Path, source_path: Path) -> str:
    import os
    rel = os.path.relpath(source_path.with_suffix(""), start=target_path.parent)
    text = Path(rel).as_posix()
    return text if text.startswith(".") else f"./{text}"


def _append_failure_log(log_path: Path, file: str, symbol: str, test_file: str, error_output: str) -> None:
    entry = json.dumps({"file": file, "symbol": symbol, "test_file": test_file, "error_output": error_output})
    with open(log_path, "a") as fh:
        fh.write(entry + "\n")


def _generate_with_retry(*, llm, gap, plugin, config, style_notes, target_file, target_status, framework, existing_test_context, source_import_path, requester):
    """Generate a valid test with up to 3 retries on format rejection."""
    from test_agent.cli import _test_code_rejection_reason

    feedback = ""
    last_suggestion = None
    for _ in range(3):
        notes = style_notes if not feedback else (
            f"{style_notes}\n\nPrevious output rejected: {feedback}\nReturn raw code only."
        ).strip()
        suggestion = llm.generate_test(
            gap, plugin, config, notes,
            target_file=target_file, target_status=target_status,
            framework=framework, existing_test_context=existing_test_context,
            source_import_path=source_import_path, requester=requester,
        )
        last_suggestion = suggestion
        feedback = _test_code_rejection_reason(suggestion.test_code, framework, gap, source_import_path)
        if not feedback:
            return suggestion
    return last_suggestion


class AutoRunner:
    """
    Processes all source files unattended:
      - auto-approves every generated test
      - on verify failure, invokes LLM fix loop (up to _MAX_FIX_ATTEMPTS)
      - runs until every queued file is processed
      - displays a Rich Live dashboard throughout
    """

    def run(
        self,
        stacks: list,
        plugin_source_files: dict[str, list[Path]],
        project_root: Path,
        project_root_str: str,
        config,
        llm,
        memory: Memory,
        workers: int,
    ) -> AutoResult:
        from test_agent.cli import _find_coverage_report

        work: list[tuple] = []
        for plugin in stacks:
            for sf in plugin_source_files.get(plugin.name, []):
                rel = str(sf.relative_to(project_root))
                if not memory.get_file_state(project_root_str, rel):
                    work.append((plugin, sf))

        plugin_meta: dict[str, dict] = {}
        for plugin in stacks:
            extensions = _SOURCE_EXTENSIONS.get(plugin.name, [])
            plugin_meta[plugin.name] = {
                "existing_tests": scan_test_files(project_root, extensions=extensions, exclude_paths=config.exclude_paths),
                "coverage_data": _find_coverage_report(project_root, plugin),
                "framework": plugin.detect_framework(project_root),
                "style_notes": memory.get_style_note("style") or "",
            }

        db_path = project_root / ".test-agent" / "memory.db"
        log_path = project_root / ".test-agent" / "auto.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        effective_workers = min(workers, llm.max_workers) if llm.max_workers else workers
        state = _State(total=len(work))
        start = time.monotonic()
        console = Console()

        with Live(_render(state), console=console, refresh_per_second=4) as live:
            with ThreadPoolExecutor(max_workers=effective_workers) as pool:
                futs = {
                    pool.submit(
                        self._process_file,
                        plugin, sf, db_path, project_root, project_root_str,
                        config, llm, log_path, state, live, plugin_meta[plugin.name],
                    ): sf
                    for plugin, sf in work
                }
                for fut in as_completed(futs):
                    try:
                        fut.result()
                    except Exception:
                        pass
                    live.update(_render(state))

        return AutoResult(
            files_scanned=len(work),
            files_with_gaps=state.files_with_gaps,
            tests_written=state.tests_written,
            fixes_applied=state.fixes_applied,
            fix_failures=state.fix_failures,
            duration_s=time.monotonic() - start,
        )

    def _process_file(
        self,
        plugin,
        sf: Path,
        db_path: Path,
        project_root: Path,
        project_root_str: str,
        config,
        llm,
        log_path: Path,
        state: _State,
        live: Live,
        meta: dict,
    ) -> None:
        filename = sf.name
        tests_written = fixes_applied = fix_failures = 0
        had_error = False

        try:
            mem = Memory(db_path)
            try:
                state.set_phase(filename, "scanning")
                live.update(_render(state))

                gaps = find_gaps(
                    source_files=[sf],
                    project_root=project_root,
                    coverage_data=meta["coverage_data"],
                    existing_test_files=meta["existing_tests"],
                )
                gaps = [g for g in gaps if not mem.is_skipped(g.file, g.symbol)]
                rel = str(sf.relative_to(project_root))

                if not gaps:
                    mem.save_file_state(project_root_str, rel, 0)
                    return

                executor = ExecutorAgent()

                for i, gap in enumerate(gaps, 1):
                    target = resolve_test_target(gap, project_root, plugin, meta["existing_tests"])
                    target_file_rel = str(target.path.relative_to(project_root))
                    existing_test_context = read_reference_test_context(target, meta["existing_tests"])
                    source_import_path = _source_import_path(target.path, project_root / gap.file)

                    state.set_phase(filename, f"gap {i}/{len(gaps)} generating")
                    live.update(_render(state))

                    suggestion = _generate_with_retry(
                        llm=llm, gap=gap, plugin=plugin, config=config,
                        style_notes=meta["style_notes"], target_file=target_file_rel,
                        target_status=target.status, framework=meta["framework"],
                        existing_test_context=existing_test_context,
                        source_import_path=source_import_path,
                        requester=f"test-agent auto via {config.provider}",
                    )

                    if not suggestion:
                        continue

                    state.set_phase(filename, f"gap {i}/{len(gaps)} writing")
                    live.update(_render(state))

                    # Snapshot pre-write content so the fix loop can restore + retry cleanly
                    pre_write = target.path.read_text() if target.path.exists() else None
                    write_suggestion(suggestion, project_root=project_root)
                    tests_written += 1

                    state.set_phase(filename, f"gap {i}/{len(gaps)} verifying")
                    live.update(_render(state))

                    verify = executor.run_verify(target.path, project_root, plugin)

                    if not verify.success:
                        current_code = suggestion.test_code
                        fixed = False

                        for attempt in range(1, _MAX_FIX_ATTEMPTS + 1):
                            state.set_phase(filename, f"gap {i}/{len(gaps)} fixing ({attempt}/{_MAX_FIX_ATTEMPTS})")
                            live.update(_render(state))

                            fixed_code = llm.fix_test(
                                test_code=current_code,
                                error_output=verify.output,
                                gap=gap,
                                target_file=target_file_rel,
                                plugin=plugin,
                                framework=meta["framework"],
                            )

                            # Restore to pre-write state, then apply fixed version
                            if pre_write is not None:
                                target.path.write_text(pre_write)
                            elif target.path.exists():
                                target.path.unlink()

                            write_suggestion(
                                dataclasses.replace(suggestion, test_code=fixed_code),
                                project_root=project_root,
                            )

                            state.set_phase(filename, f"gap {i}/{len(gaps)} re-verifying ({attempt}/{_MAX_FIX_ATTEMPTS})")
                            live.update(_render(state))

                            verify = executor.run_verify(target.path, project_root, plugin)
                            if verify.success:
                                fixes_applied += 1
                                fixed = True
                                break
                            current_code = fixed_code

                        if not fixed:
                            fix_failures += 1
                            _append_failure_log(log_path, gap.file, gap.symbol, str(target.path), verify.output)

                # Only mark done when tests were actually written (or file had no gaps)
                if tests_written > 0 and fix_failures == 0:
                    mem.save_file_state(project_root_str, rel, len(gaps))

            except Exception:
                had_error = True
                traceback.print_exc()
            finally:
                mem.close()

        except Exception:
            had_error = True
            traceback.print_exc()
        finally:
            state.clear(filename)
            state.record_done(FileOutcome(
                rel_path=str(sf.relative_to(project_root)),
                tests_written=tests_written,
                fixes_applied=fixes_applied,
                fix_failures=fix_failures,
                had_error=had_error,
            ))
            live.update(_render(state))
