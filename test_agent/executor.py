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
