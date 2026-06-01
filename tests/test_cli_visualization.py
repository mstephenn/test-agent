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
