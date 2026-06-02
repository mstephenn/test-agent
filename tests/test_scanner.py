from pathlib import Path
import pytest
from test_agent.scanner import scan_files, scan_test_files

def test_scan_whole_repo(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text("def foo(): pass")
    (tmp_path / "src" / "bar.py").write_text("def bar(): pass")
    files = scan_files(tmp_path, extensions=[".py"])
    assert len(files) == 2

def test_scan_excludes_paths(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "migrations").mkdir()
    (tmp_path / "src" / "app.py").write_text("")
    (tmp_path / "migrations" / "0001.py").write_text("")
    files = scan_files(tmp_path, extensions=[".py"], exclude_paths=["migrations/"])
    paths = [str(f) for f in files]
    assert not any("migrations" in p for p in paths)

def test_scan_path_scope(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "other").mkdir()
    (tmp_path / "src" / "app.py").write_text("")
    (tmp_path / "other" / "util.py").write_text("")
    files = scan_files(tmp_path, extensions=[".py"], scope_path=tmp_path / "src")
    assert len(files) == 1
    assert files[0].name == "app.py"

def test_scan_skips_test_files(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("")
    (tmp_path / "tests" / "test_app.py").write_text("")
    files = scan_files(tmp_path, extensions=[".py"])
    names = [f.name for f in files]
    assert "app.py" in names
    assert "test_app.py" not in names


def test_scan_test_files_includes_tests_not_sources(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("")
    (tmp_path / "tests" / "test_app.py").write_text("")
    files = scan_test_files(tmp_path, extensions=[".py"])
    names = [f.name for f in files]
    assert "test_app.py" in names
    assert "app.py" not in names


def test_scan_test_files_recognizes_language_patterns(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.test.ts").write_text("")
    (tmp_path / "src" / "bar_test.go").write_text("")
    (tmp_path / "src" / "OrderServiceTest.java").write_text("")
    files = scan_test_files(tmp_path, extensions=[".ts", ".go", ".java"])
    names = {f.name for f in files}
    assert names == {"foo.test.ts", "bar_test.go", "OrderServiceTest.java"}
