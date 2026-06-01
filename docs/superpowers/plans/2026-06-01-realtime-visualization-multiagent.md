# Real-time Visualization + Multi-Agent Writer/Executor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add rich real-time startup panels, memory-based file-skip, and concurrent writer+executor agents (baseline → generate → verify) to `test-agent run`.

**Architecture:** Three new/modified components — `display.py` (startup panels), `executor.py` (subprocess test runner), `memory.py` extensions (two new tables) — wired together in a refactored `cli.py` run command that uses `ThreadPoolExecutor` to run baseline + writer concurrently per file, then verify after approval.

**Tech Stack:** Python 3.11+, Rich (panels/tree), `concurrent.futures.ThreadPoolExecutor`, `subprocess`, SQLite via existing `Memory` class.

---

## File Map

| File | Change | Responsibility |
|---|---|---|
| `test_agent/memory.py` | modify | Add `project_scans` + `file_states` tables and 4 CRUD methods |
| `test_agent/display.py` | **create** | `StartupDisplay` class, `compute_structure_hash` |
| `test_agent/executor.py` | **create** | `ExecutorAgent`, `ExecutorResult`, `_parse_pytest_output` |
| `test_agent/cli.py` | modify | Startup panels, pre-scan, concurrent per-file loop, verify |
| `tests/test_memory.py` | modify | Tests for new memory methods |
| `tests/test_display.py` | **create** | Tests for `StartupDisplay` and `compute_structure_hash` |
| `tests/test_executor.py` | **create** | Tests for `ExecutorAgent` and `_parse_pytest_output` |
| `tests/test_cli_visualization.py` | **create** | Tests for `_print_baseline` and `_print_verify` helpers |

---

## Task 1: Memory — project_scans and file_states tables

**Files:**
- Modify: `test_agent/memory.py`
- Modify: `tests/test_memory.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_memory.py`:

```python
def test_save_and_get_project_scan(mem):
    mem.save_project_scan("/path/to/project", ["Python"], "abc123")
    result = mem.get_project_scan("/path/to/project")
    assert result is not None
    assert result["detected_stacks"] == ["Python"]
    assert result["structure_hash"] == "abc123"


def test_get_project_scan_returns_none_for_unknown(mem):
    assert mem.get_project_scan("/nonexistent") is None


def test_save_project_scan_overwrites_existing(mem):
    mem.save_project_scan("/path", ["Python"], "hash1")
    mem.save_project_scan("/path", ["Python", "TypeScript"], "hash2")
    result = mem.get_project_scan("/path")
    assert result["structure_hash"] == "hash2"
    assert len(result["detected_stacks"]) == 2


def test_save_and_get_file_state(mem):
    mem.save_file_state("/path/to/project", "test_agent/cli.py", 3)
    result = mem.get_file_state("/path/to/project", "test_agent/cli.py")
    assert result is not None
    assert result["gaps_found"] == 3
    assert result["file_path"] == "test_agent/cli.py"


def test_get_file_state_returns_none_for_unknown(mem):
    assert mem.get_file_state("/path", "nonexistent.py") is None


def test_save_file_state_overwrites_existing(mem):
    mem.save_file_state("/path", "src/foo.py", 2)
    mem.save_file_state("/path", "src/foo.py", 5)
    result = mem.get_file_state("/path", "src/foo.py")
    assert result["gaps_found"] == 5
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd test-agent && source venv/bin/activate && pytest tests/test_memory.py -v -k "project_scan or file_state"
```

Expected: 6 failures — `AttributeError: 'Memory' object has no attribute 'save_project_scan'`

- [ ] **Step 3: Add `import json` to `memory.py`**

At the top of `test_agent/memory.py`, add `import json` after the existing imports.

- [ ] **Step 4: Add new tables to `_init_schema`**

In `test_agent/memory.py`, inside `_init_schema`, append to the `executescript` string:

```python
            CREATE TABLE IF NOT EXISTS project_scans (
                project_root    TEXT PRIMARY KEY,
                last_scan_at    TEXT,
                detected_stacks TEXT,
                structure_hash  TEXT
            );
            CREATE TABLE IF NOT EXISTS file_states (
                project_root TEXT,
                file_path    TEXT,
                processed_at TEXT,
                gaps_found   INTEGER,
                PRIMARY KEY (project_root, file_path)
            );
```

- [ ] **Step 5: Add the four new methods to `Memory`**

Add after the `close` method in `test_agent/memory.py`:

```python
    def get_project_scan(self, project_root: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM project_scans WHERE project_root=?", (project_root,)
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["detected_stacks"] = json.loads(result["detected_stacks"])
        return result

    def save_project_scan(self, project_root: str, stacks: list[str], structure_hash: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO project_scans VALUES (?,?,?,?)",
            (project_root, _now(), json.dumps(stacks), structure_hash),
        )
        self._conn.commit()

    def get_file_state(self, project_root: str, file_path: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM file_states WHERE project_root=? AND file_path=?",
            (project_root, file_path),
        ).fetchone()
        return dict(row) if row else None

    def save_file_state(self, project_root: str, file_path: str, gaps_found: int) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO file_states VALUES (?,?,?,?)",
            (project_root, file_path, _now(), gaps_found),
        )
        self._conn.commit()
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/test_memory.py -v
```

Expected: all tests pass (including original 6 + new 6)

- [ ] **Step 7: Commit**

```bash
git add test_agent/memory.py tests/test_memory.py
git commit -m "feat: add project_scans and file_states tables to Memory"
```

---

## Task 2: display.py — StartupDisplay and compute_structure_hash

**Files:**
- Create: `test_agent/display.py`
- Create: `tests/test_display.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_display.py`:

```python
from __future__ import annotations
import pytest
from io import StringIO
from pathlib import Path
from rich.console import Console
from test_agent.display import StartupDisplay, compute_structure_hash
from test_agent.plugins.python import PythonPlugin


@pytest.fixture
def cap():
    buf = StringIO()
    con = Console(file=buf, width=80, highlight=False, markup=True)
    return con, buf


def test_show_detection_fresh_includes_language_and_marker(tmp_path, cap):
    con, buf = cap
    (tmp_path / "pyproject.toml").touch()
    StartupDisplay(console=con).show_detection([PythonPlugin()], tmp_path, from_cache=False)
    out = buf.getvalue()
    assert "Python" in out
    assert "pyproject.toml" in out
    assert "Step 1" in out


def test_show_detection_cached_shows_cached_label(tmp_path, cap):
    con, buf = cap
    StartupDisplay(console=con).show_detection([PythonPlugin()], tmp_path, from_cache=True, cached_at="2026-05-30")
    out = buf.getvalue()
    assert "Python" in out
    assert "cached" in out.lower()


def test_show_structure_excludes_venv(tmp_path, cap):
    con, buf = cap
    (tmp_path / "venv").mkdir()
    (tmp_path / "venv" / "lib.py").touch()
    (tmp_path / "src.py").touch()
    StartupDisplay(console=con).show_structure(tmp_path, from_cache=False)
    out = buf.getvalue()
    assert "venv" not in out
    assert "src.py" in out


def test_show_structure_caps_items_with_overflow_label(tmp_path, cap):
    con, buf = cap
    for i in range(8):
        (tmp_path / f"file{i}.py").touch()
    StartupDisplay(console=con).show_structure(tmp_path, from_cache=False)
    assert "more" in buf.getvalue()


def test_show_structure_cached_does_not_build_tree(tmp_path, cap):
    con, buf = cap
    (tmp_path / "src.py").touch()
    StartupDisplay(console=con).show_structure(tmp_path, from_cache=True, cached_at="2026-05-30")
    out = buf.getvalue()
    assert "Step 2" in out
    assert "cached" in out.lower()


def test_show_memory_status_shows_all_counts(tmp_path, cap):
    con, buf = cap
    StartupDisplay(console=con).show_memory_status(queued=5, already_done=3, last_scan_at="2026-05-30T14:32:00")
    out = buf.getvalue()
    assert "5" in out
    assert "3" in out
    assert "2026-05-30" in out


def test_show_memory_status_no_last_scan(tmp_path, cap):
    con, buf = cap
    StartupDisplay(console=con).show_memory_status(queued=2, already_done=0, last_scan_at=None)
    out = buf.getvalue()
    assert "2" in out


def test_compute_structure_hash_excludes_venv(tmp_path):
    (tmp_path / "venv").mkdir()
    (tmp_path / "venv" / "lib.py").touch()
    (tmp_path / "src.py").touch()
    h1 = compute_structure_hash(tmp_path)
    (tmp_path / "venv" / "other.py").touch()
    h2 = compute_structure_hash(tmp_path)
    assert h1 == h2


def test_compute_structure_hash_changes_on_new_file(tmp_path):
    (tmp_path / "src.py").touch()
    h1 = compute_structure_hash(tmp_path)
    (tmp_path / "new.py").touch()
    h2 = compute_structure_hash(tmp_path)
    assert h1 != h2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_display.py -v
```

Expected: `ModuleNotFoundError: No module named 'test_agent.display'`

- [ ] **Step 3: Create `test_agent/display.py`**

```python
from __future__ import annotations
import hashlib
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.tree import Tree

_EXCLUDED_DIRS = frozenset({
    "venv", "__pycache__", ".git", ".pytest_cache",
    ".mypy_cache", "node_modules", ".tox", ".venv",
})
_MAX_ITEMS_PER_DIR = 5
_DETECTION_MARKERS: dict[str, list[str]] = {
    "Python": ["pyproject.toml", "requirements.txt", "setup.py", "setup.cfg"],
    "TypeScript": ["tsconfig.json"],
    "JavaScript": ["package.json"],
    "Java": ["pom.xml", "build.gradle"],
    "Ruby": ["Gemfile"],
    "Go": ["go.mod"],
}


def compute_structure_hash(project_root: Path) -> str:
    """Return an md5 hex digest of all non-excluded paths under project_root."""
    paths = []
    for p in project_root.rglob("*"):
        try:
            rel = p.relative_to(project_root)
        except ValueError:
            continue
        if any(part in _EXCLUDED_DIRS for part in rel.parts):
            continue
        paths.append(str(rel))
    return hashlib.md5("\n".join(sorted(paths)).encode()).hexdigest()


class StartupDisplay:
    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console()

    def show_detection(
        self,
        stacks: list,
        project_root: Path,
        from_cache: bool = False,
        cached_at: str | None = None,
    ) -> None:
        lines = []
        for plugin in stacks:
            if from_cache:
                suffix = f"  (cached from {cached_at})" if cached_at else "  (cached)"
                lines.append(f"[green]✓[/green] [bold]{plugin.name}[/bold][dim]{suffix}[/dim]")
            else:
                marker = _find_marker(plugin.name, project_root)
                suffix = f"  {marker}" if marker else ""
                lines.append(f"[green]✓[/green] [bold]{plugin.name}[/bold][dim]{suffix}[/dim]")
        body = "\n".join(lines) if lines else "[red]No stacks detected[/red]"
        self._console.print(Panel(body, title="Step 1 · Language Detection", title_align="left"))

    def show_structure(
        self,
        project_root: Path,
        from_cache: bool = False,
        cached_at: str | None = None,
    ) -> None:
        if from_cache:
            suffix = f"  (cached from {cached_at})" if cached_at else "  (cached)"
            body = f"[bold]{project_root.name}/[/bold][dim]{suffix}[/dim]"
            self._console.print(Panel(body, title="Step 2 · Project Structure", title_align="left"))
            return
        tree = Tree(f"[bold]{project_root.name}/[/bold]")
        _build_tree(tree, project_root, depth=0, max_depth=3)
        self._console.print(Panel(tree, title="Step 2 · Project Structure", title_align="left"))

    def show_memory_status(
        self,
        queued: int,
        already_done: int,
        last_scan_at: str | None = None,
    ) -> None:
        lines = []
        if last_scan_at:
            ts = last_scan_at[:16].replace("T", " ")
            lines.append(f"[dim]Last scan:[/dim] {ts}")
        total = queued + already_done
        lines.append(
            f"[bold]{total}[/bold] [dim]files tracked  ·  [/dim]"
            f"[bold]{already_done}[/bold] [dim]already processed[/dim]"
        )
        lines.append(f"[bold green]{queued}[/bold green] [dim]files queued for this run[/dim]")
        self._console.print(Panel("\n".join(lines), title="Step 3 · Session Memory", title_align="left"))


def _find_marker(language: str, project_root: Path) -> str:
    for marker in _DETECTION_MARKERS.get(language, []):
        if (project_root / marker).exists():
            return marker
    return ""


def _build_tree(node: Tree, directory: Path, depth: int, max_depth: int) -> None:
    if depth >= max_depth:
        return
    try:
        entries = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name))
    except PermissionError:
        return
    visible = [e for e in entries if e.name not in _EXCLUDED_DIRS]
    shown = visible[:_MAX_ITEMS_PER_DIR]
    hidden_count = len(visible) - len(shown)
    for entry in shown:
        if entry.is_dir():
            branch = node.add(f"[bold]{entry.name}/[/bold]")
            _build_tree(branch, entry, depth + 1, max_depth)
        else:
            label = f"[dim]{entry.name}[/dim]" if _is_test_filename(entry.name) else entry.name
            node.add(label)
    if hidden_count > 0:
        node.add(f"[dim]... {hidden_count} more[/dim]")


def _is_test_filename(name: str) -> bool:
    lowered = name.lower()
    return "test" in lowered or "spec" in lowered
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_display.py -v
```

Expected: all 9 tests pass

- [ ] **Step 5: Commit**

```bash
git add test_agent/display.py tests/test_display.py
git commit -m "feat: add StartupDisplay and compute_structure_hash"
```

---

## Task 3: executor.py — ExecutorAgent and ExecutorResult

**Files:**
- Create: `test_agent/executor.py`
- Create: `tests/test_executor.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_executor.py`:

```python
from __future__ import annotations
import subprocess
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from test_agent.executor import ExecutorAgent, ExecutorResult, _parse_pytest_output
from test_agent.plugins.python import PythonPlugin


def test_parse_pytest_output_all_passed():
    result = _parse_pytest_output("...\n3 passed in 0.12s", 120)
    assert result.passed == 3
    assert result.failed == 0
    assert result.errors == 0
    assert result.success is True
    assert result.duration_ms == 120


def test_parse_pytest_output_mixed():
    output = "FAILED tests/test_foo.py::test_bar - AssertionError\n2 passed, 1 failed in 0.34s"
    result = _parse_pytest_output(output, 340)
    assert result.passed == 2
    assert result.failed == 1
    assert result.success is False


def test_parse_pytest_output_import_error():
    output = "ERROR tests/test_foo.py - ImportError: No module named 'x'\n1 error in 0.02s"
    result = _parse_pytest_output(output, 20)
    assert result.errors == 1
    assert result.success is False


def test_parse_pytest_output_truncates_to_20_lines():
    output = "\n".join(f"line {i}" for i in range(30))
    result = _parse_pytest_output(output, 0)
    assert len(result.output.splitlines()) <= 20


def test_executor_result_first_failure_line():
    result = ExecutorResult(
        passed=1, failed=1, errors=0, duration_ms=100,
        output="FAILED tests/test_foo.py::test_bar - AssertionError: expected True",
        success=False,
    )
    assert "AssertionError" in result.first_failure_line


def test_executor_result_first_failure_line_empty_when_success():
    result = ExecutorResult(passed=3, failed=0, errors=0, duration_ms=50, output="3 passed", success=True)
    assert result.first_failure_line == ""


def test_run_baseline_returns_zero_when_no_test_file_exists(tmp_path):
    source_file = tmp_path / "scanner.py"
    source_file.touch()
    result = ExecutorAgent().run_baseline(source_file, tmp_path, PythonPlugin())
    assert result.passed == 0
    assert result.failed == 0
    assert result.success is True


def test_run_verify_calls_subprocess_with_test_file(tmp_path):
    test_file = tmp_path / "tests" / "test_scanner.py"
    test_file.parent.mkdir()
    test_file.write_text("def test_nothing(): pass\n")
    mock_proc = MagicMock(stdout="1 passed in 0.01s", stderr="")
    with patch("subprocess.run", return_value=mock_proc) as mock_run:
        result = ExecutorAgent().run_verify(test_file, tmp_path, PythonPlugin())
    assert mock_run.called
    cmd = mock_run.call_args[0][0]
    assert str(test_file) in cmd
    assert result.passed == 1


def test_run_verify_handles_timeout(tmp_path):
    test_file = tmp_path / "tests" / "test_scanner.py"
    test_file.parent.mkdir()
    test_file.touch()
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="pytest", timeout=60)):
        result = ExecutorAgent().run_verify(test_file, tmp_path, PythonPlugin())
    assert result.errors == 1
    assert result.success is False
    assert "timed out" in result.output


def test_run_verify_handles_missing_runner(tmp_path):
    test_file = tmp_path / "tests" / "test_foo.py"
    test_file.parent.mkdir()
    test_file.touch()
    with patch("subprocess.run", side_effect=FileNotFoundError("pytest not found")):
        result = ExecutorAgent().run_verify(test_file, tmp_path, PythonPlugin())
    assert result.errors == 1
    assert result.success is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_executor.py -v
```

Expected: `ModuleNotFoundError: No module named 'test_agent.executor'`

- [ ] **Step 3: Create `test_agent/executor.py`**

```python
from __future__ import annotations
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ExecutorResult:
    passed: int
    failed: int
    errors: int
    duration_ms: int
    output: str
    success: bool

    @property
    def first_failure_line(self) -> str:
        for line in self.output.splitlines():
            if line.startswith("FAILED") or line.startswith("ERROR"):
                return line.split(" - ", 1)[-1] if " - " in line else line
        return ""


class ExecutorAgent:
    def run_baseline(self, source_file: Path, project_root: Path, plugin) -> ExecutorResult:
        """Run existing tests for source_file; returns zero result if no test file found."""
        test_file = self._find_test_file(source_file, project_root)
        if not test_file.exists():
            return ExecutorResult(passed=0, failed=0, errors=0, duration_ms=0, output="", success=True)
        return self._run(test_file, project_root, plugin)

    def run_verify(self, test_file: Path, project_root: Path, plugin) -> ExecutorResult:
        """Run the specified test file after it has been written."""
        return self._run(test_file, project_root, plugin)

    def _find_test_file(self, source_file: Path, project_root: Path) -> Path:
        stem = source_file.stem
        candidates = [
            project_root / "tests" / f"test_{stem}.py",
            source_file.parent / f"test_{stem}.py",
        ]
        for c in candidates:
            if c.exists():
                return c
        return candidates[0]

    def _run(self, test_file: Path, project_root: Path, plugin) -> ExecutorResult:
        runner_parts = plugin.test_runner.split()
        start = time.monotonic()
        try:
            proc = subprocess.run(
                runner_parts + [str(test_file), "--tb=line", "-q"],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            return ExecutorResult(
                passed=0, failed=0, errors=1,
                duration_ms=60000, output="timed out after 60s", success=False,
            )
        except FileNotFoundError as exc:
            return ExecutorResult(
                passed=0, failed=0, errors=1,
                duration_ms=0, output=str(exc), success=False,
            )
        duration_ms = int((time.monotonic() - start) * 1000)
        return _parse_pytest_output(proc.stdout + proc.stderr, duration_ms)


def _parse_pytest_output(output: str, duration_ms: int) -> ExecutorResult:
    passed = failed = errors = 0
    m = re.search(r"(\d+) passed", output)
    if m:
        passed = int(m.group(1))
    m = re.search(r"(\d+) failed", output)
    if m:
        failed = int(m.group(1))
    m = re.search(r"(\d+) error", output)
    if m:
        errors = int(m.group(1))
    truncated = "\n".join(output.strip().splitlines()[:20])
    return ExecutorResult(
        passed=passed,
        failed=failed,
        errors=errors,
        duration_ms=duration_ms,
        output=truncated,
        success=failed == 0 and errors == 0,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_executor.py -v
```

Expected: all 11 tests pass

- [ ] **Step 5: Commit**

```bash
git add test_agent/executor.py tests/test_executor.py
git commit -m "feat: add ExecutorAgent for baseline and verify test runs"
```

---

## Task 4: cli.py — startup display wiring

**Files:**
- Modify: `test_agent/cli.py`
- Create: `tests/test_cli_visualization.py`

- [ ] **Step 1: Write failing tests for the two new print helpers**

Create `tests/test_cli_visualization.py`:

```python
from __future__ import annotations
from io import StringIO
from pathlib import Path
from rich.console import Console
from test_agent.executor import ExecutorResult
from test_agent.cli import _print_baseline, _print_verify


def _con():
    buf = StringIO()
    return Console(file=buf, width=80, highlight=False, markup=True), buf


def test_print_baseline_shows_pass_and_fail_count():
    con, buf = _con()
    result = ExecutorResult(passed=3, failed=1, errors=0, duration_ms=100, output="", success=False)
    _print_baseline(con, result)
    out = buf.getvalue()
    assert "3" in out
    assert "1" in out


def test_print_baseline_silent_when_no_tests_exist():
    con, buf = _con()
    result = ExecutorResult(passed=0, failed=0, errors=0, duration_ms=0, output="", success=True)
    _print_baseline(con, result)
    assert buf.getvalue() == ""


def test_print_verify_success_shows_delta():
    con, buf = _con()
    baseline = ExecutorResult(passed=3, failed=0, errors=0, duration_ms=0, output="", success=True)
    verify = ExecutorResult(passed=4, failed=0, errors=0, duration_ms=100, output="", success=True)
    _print_verify(con, verify, baseline, Path("tests/test_foo.py"))
    out = buf.getvalue()
    assert "4" in out
    assert "+1" in out


def test_print_verify_failure_shows_error_hint():
    con, buf = _con()
    baseline = ExecutorResult(passed=3, failed=0, errors=0, duration_ms=0, output="", success=True)
    verify = ExecutorResult(
        passed=3, failed=1, errors=0, duration_ms=100,
        output="FAILED tests/test_foo.py::test_bar - AssertionError: wrong value",
        success=False,
    )
    _print_verify(con, verify, baseline, Path("tests/test_foo.py"))
    out = buf.getvalue()
    assert "AssertionError" in out
    assert "test_foo.py" in out
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_cli_visualization.py -v
```

Expected: `ImportError: cannot import name '_print_baseline' from 'test_agent.cli'`

- [ ] **Step 3: Add new imports to `cli.py`**

At the top of `test_agent/cli.py`, add these imports after the existing ones:

```python
from concurrent.futures import ThreadPoolExecutor
from test_agent.display import StartupDisplay, compute_structure_hash
from test_agent.executor import ExecutorAgent, ExecutorResult
```

- [ ] **Step 4: Add `_print_baseline` and `_print_verify` helpers to `cli.py`**

Add these two functions at the bottom of `test_agent/cli.py` (before or after `_find_coverage_report`):

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_cli_visualization.py -v
```

Expected: all 4 tests pass

- [ ] **Step 6: Replace the startup block at the top of `run()` in `cli.py`**

Replace this existing block at the start of `run()`:

```python
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

    total_suggestions = 0
    all_results = []
```

With this new startup block:

```python
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

    total_suggestions = 0
    all_results = []
```

- [ ] **Step 7: Run the full test suite to confirm nothing broken**

```bash
pytest -x -q
```

Expected: all existing tests still pass (cli changes don't affect unit tests)

- [ ] **Step 8: Commit**

```bash
git add test_agent/cli.py tests/test_cli_visualization.py
git commit -m "feat: add startup display panels and pre-scan to cli run command"
```

---

## Task 5: cli.py — concurrent per-file loop with verify

**Files:**
- Modify: `test_agent/cli.py`

- [ ] **Step 1: Replace the per-plugin loop in `run()`**

Find the existing per-plugin loop (starts with `for plugin in stacks:`) and replace it entirely with the following. The old loop starts after the `all_results = []` line and runs to `memory.close()`.

Replace from `for plugin in stacks:` through (but not including) the `if not all_results:` block with:

```python
    executor = ExecutorAgent()
    remaining_suggestions = config.max_suggestions

    for plugin in stacks:
        source_files = plugin_source_files.get(plugin.name, [])
        coverage_data = _find_coverage_report(project_root, plugin)
        extensions = _SOURCE_EXTENSIONS.get(plugin.name, [])
        existing_tests = scan_test_files(
            project_root, extensions=extensions, exclude_paths=config.exclude_paths
        )
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

            results = run_repl(
                file_suggestions, memory=memory, auto_approve=auto_approve, dry_run=dry_run
            )
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
            remaining_suggestions -= len(file_suggestions)
```

- [ ] **Step 2: Add `_apply_results_with_verify` and remove `_apply_results`**

Delete the existing `_apply_results` function entirely and add `_apply_results_with_verify` in its place:

```python
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
            memory.record_outcome(
                session_id, suggestion.gap.file, suggestion.gap.symbol, result.decision.value
            )
            try:
                verify = executor.run_verify(target_path, project_root, plugin)
                _print_verify(console, verify, baseline, target_path)
            except Exception as exc:
                console.print(f"  [dim][verify][/dim]    [dim]could not run: {exc}[/dim]")
        elif result.decision == Decision.SKIPPED_PERMANENTLY:
            session_log.record_skipped()
        elif result.decision == Decision.SKIPPED:
            session_log.record_skipped()
            memory.record_outcome(
                session_id, result.suggestion.gap.file, result.suggestion.gap.symbol, "skipped"
            )
```

- [ ] **Step 3: Run the full test suite**

```bash
pytest -x -q
```

Expected: all tests pass

- [ ] **Step 4: Smoke-test against the project itself**

```bash
cd test-agent && source venv/bin/activate && python -m test_agent run . --dry-run --path test_agent/
```

Expected output: Three startup panels (Language Detection, Project Structure, Session Memory) print, then per-file bullets with `[baseline]` and `[writer]` lines appear, then the REPL prompts as before. No Python errors.

- [ ] **Step 5: Commit**

```bash
git add test_agent/cli.py
git commit -m "feat: concurrent writer+executor per file with verify after approval"
```

---

## Verification Checklist

After all tasks complete:

```bash
# Full test suite
pytest -v

# Smoke run against itself (dry-run, no LLM needed to see panels)
python -m test_agent run . --dry-run --provider ollama --path test_agent/ 2>/dev/null | head -40

# Second run — should show cached panels for detection + structure
python -m test_agent run . --dry-run --provider ollama --path test_agent/ 2>/dev/null | head -20
```

Expected on second run: "Step 1" panel shows `(cached from ...)`, "Step 2" panel shows `(cached from ...)`, "Step 3" panel shows files already processed from first run.
