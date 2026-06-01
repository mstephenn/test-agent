from pathlib import Path
import textwrap
import pytest
from test_agent.gap_finder import find_gaps, Gap


def test_finds_uncovered_function(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "math_utils.py").write_text(textwrap.dedent("""
        def add(a, b):
            return a + b

        def subtract(a, b):
            return a - b
    """))
    gaps = find_gaps(
        source_files=[src / "math_utils.py"],
        project_root=tmp_path,
        coverage_data=None,
        existing_test_files=[],
    )
    symbols = [g.symbol for g in gaps]
    assert "add" in symbols
    assert "subtract" in symbols


def test_covered_function_not_in_gaps(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (src / "utils.py").write_text("def add(a, b): return a + b\n")
    (tests_dir / "test_utils.py").write_text("def test_add(): assert add(1,2)==3\n")
    gaps = find_gaps(
        source_files=[src / "utils.py"],
        project_root=tmp_path,
        coverage_data=None,
        existing_test_files=[tests_dir / "test_utils.py"],
    )
    # add is referenced in test file, so not flagged as fully uncovered
    assert not any(g.symbol == "add" for g in gaps)


def test_gap_priority_error_path_is_2(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "svc.py").write_text(textwrap.dedent("""
        def process(data):
            if data is None:
                raise ValueError("no data")
            return data
    """))
    gaps = find_gaps(
        source_files=[src / "svc.py"],
        project_root=tmp_path,
        coverage_data=None,
        existing_test_files=[],
    )
    error_gaps = [g for g in gaps if g.kind == "error-path"]
    assert all(g.priority == 2 for g in error_gaps)
