from __future__ import annotations

import json
import os
import re
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
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
_BAR_WIDTH = 30


@dataclass
class HeadlessResult:
    files_scanned: int
    files_with_gaps: int
    tests_written: int
    verify_failures: int
    duration_s: float


class _State:
    """Thread-safe counters and worker phase map for the Live display."""

    def __init__(self, total: int) -> None:
        self.total = total
        self._lock = threading.Lock()
        self._done = 0
        self._failed = 0
        self._tests_written = 0
        self._start = time.monotonic()
        self._active: dict[str, str] = {}  # filename → phase

    def set_phase(self, filename: str, phase: str) -> None:
        with self._lock:
            self._active[filename] = phase

    def clear(self, filename: str) -> None:
        with self._lock:
            self._active.pop(filename, None)

    def record_done(self, *, wrote: int, had_failure: bool) -> None:
        with self._lock:
            self._done += 1
            self._tests_written += wrote
            if had_failure:
                self._failed += 1

    def snapshot(self) -> tuple[int, int, int, int, dict[str, str], float]:
        with self._lock:
            return (
                self._done,
                self._failed,
                self._tests_written,
                self.total,
                dict(self._active),
                time.monotonic() - self._start,
            )

    @property
    def tests_written(self) -> int:
        with self._lock:
            return self._tests_written

    @property
    def verify_failures(self) -> int:
        with self._lock:
            return self._failed


def _render(state: _State) -> Group:
    done, failed, _written, total, active, elapsed = state.snapshot()

    filled = int(done / total * _BAR_WIDTH) if total else 0
    bar = "[green]" + "█" * filled + "[/green]" + "░" * (_BAR_WIDTH - filled)
    eta_str = ""
    if 0 < done < total:
        remaining_s = elapsed / done * (total - done)
        mins, secs = divmod(int(remaining_s), 60)
        eta_str = f"  ·  ~{mins}m {secs}s remaining"

    progress_body = (
        f"  {bar}  {done} / {total} files\n"
        f"  {len(active)} active  ·  {done} done  ·  {failed} failed{eta_str}"
    )

    worker_lines = [
        f"  [{i}]  {fname:<42}  {phase}..."
        for i, (fname, phase) in enumerate(list(active.items()), start=1)
    ] or ["  (idle)"]

    return Group(
        Panel(progress_body, title="Progress"),
        Panel("\n".join(worker_lines), title="Active Workers"),
    )


def _append_failure_log(log_path: Path, file: str, symbol: str, test_file: str, error_output: str) -> None:
    entry = json.dumps({"file": file, "symbol": symbol, "test_file": test_file, "error_output": error_output})
    with open(log_path, "a") as fh:
        fh.write(entry + "\n")


def _source_import_path(target_path: Path, source_path: Path) -> str:
    rel = os.path.relpath(source_path.with_suffix(""), start=target_path.parent)
    text = Path(rel).as_posix()
    return text if text.startswith(".") else f"./{text}"


def _generate_test_headless(*, llm, gap, plugin, config, style_notes, target_file, target_status, framework, existing_test_context, source_import_path, requester):
    """Generate a valid test suggestion with up to 3 retries; silent (no console output)."""
    from test_agent.cli import _test_code_rejection_reason  # lazy — avoids circular import at load time

    feedback = ""
    last_suggestion = None
    for _ in range(3):
        attempt_notes = style_notes
        if feedback:
            attempt_notes = (
                f"{style_notes}\n\nPrevious generated output was rejected: {feedback}\n"
                "Regenerate the test so it matches the target framework and contains raw code only."
            ).strip()
        suggestion = llm.generate_test(
            gap, plugin, config, attempt_notes,
            target_file=target_file, target_status=target_status,
            framework=framework, existing_test_context=existing_test_context,
            source_import_path=source_import_path, requester=requester,
        )
        last_suggestion = suggestion
        feedback = _test_code_rejection_reason(suggestion.test_code, framework, gap, source_import_path)
        if not feedback:
            return suggestion
    return last_suggestion


class HeadlessRunner:
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
    ) -> HeadlessResult:
        from test_agent.cli import _find_coverage_report  # lazy — avoids circular import at load time

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
        log_path = project_root / ".test-agent" / "headless.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        state = _State(total=len(work))
        files_with_gaps = 0
        start = time.monotonic()
        effective_workers = min(workers, llm.max_workers) if llm.max_workers else workers

        console = Console()
        with Live(_render(state), console=console, refresh_per_second=4) as live:
            with ThreadPoolExecutor(max_workers=effective_workers) as outer:
                futs = {
                    outer.submit(
                        self._process_file,
                        plugin, sf, db_path, project_root, project_root_str,
                        config, llm, log_path, state, live, plugin_meta[plugin.name],
                    ): sf
                    for plugin, sf in work
                }
                for fut in as_completed(futs):
                    try:
                        had_gaps = fut.result()
                        if had_gaps:
                            files_with_gaps += 1
                    except Exception:
                        pass
                    live.update(_render(state))

        return HeadlessResult(
            files_scanned=len(work),
            files_with_gaps=files_with_gaps,
            tests_written=state.tests_written,
            verify_failures=state.verify_failures,
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
    ) -> bool:
        filename = sf.name
        wrote_count = 0
        had_failure = False
        had_gaps = False

        try:
            mem = Memory(db_path)
            try:
                state.set_phase(filename, "baseline")
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
                    return False

                had_gaps = True
                executor = ExecutorAgent()

                for gap in gaps:
                    target = resolve_test_target(gap, project_root, plugin, meta["existing_tests"])
                    target_file_rel = str(target.path.relative_to(project_root))
                    existing_test_context = read_reference_test_context(target, meta["existing_tests"])
                    source_import_path = _source_import_path(target.path, project_root / gap.file)

                    state.set_phase(filename, "generating")
                    live.update(_render(state))

                    with ThreadPoolExecutor(max_workers=2) as inner:
                        baseline_fut = inner.submit(executor.run_baseline, sf, project_root, plugin)
                        gen_fut = inner.submit(
                            _generate_test_headless,
                            llm=llm, gap=gap, plugin=plugin, config=config,
                            style_notes=meta["style_notes"], target_file=target_file_rel,
                            target_status=target.status, framework=meta["framework"],
                            existing_test_context=existing_test_context,
                            source_import_path=source_import_path,
                            requester=f"test-agent headless via {config.provider}",
                        )
                        baseline_fut.result()  # join; result used by spec, not currently needed
                        suggestion = gen_fut.result()

                    if not suggestion:
                        continue

                    state.set_phase(filename, "writing")
                    live.update(_render(state))
                    write_suggestion(suggestion, project_root=project_root)
                    wrote_count += 1

                    state.set_phase(filename, "verifying")
                    live.update(_render(state))
                    verify = executor.run_verify(target.path, project_root, plugin)
                    if not verify.success:
                        had_failure = True
                        _append_failure_log(log_path, gap.file, gap.symbol, str(target.path), verify.output)

                mem.save_file_state(project_root_str, rel, len(gaps))
            finally:
                mem.close()
        except Exception:
            had_failure = True
            traceback.print_exc()

        state.clear(filename)
        state.record_done(wrote=wrote_count, had_failure=had_failure)
        live.update(_render(state))
        return had_gaps
