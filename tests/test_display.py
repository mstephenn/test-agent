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
    assert "2" in buf.getvalue()


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
