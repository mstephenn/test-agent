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
