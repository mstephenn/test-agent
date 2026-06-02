from pathlib import Path
import pytest
from test_agent.writer import write_suggestion
from test_agent.llm.base import TestSuggestion
from test_agent.gap_finder import Gap


def _make_suggestion(target: str, code: str) -> TestSuggestion:
    gap = Gap(file="src/foo.py", symbol="bar", kind="uncovered", priority=1, context_lines="")
    return TestSuggestion(target_file=target, test_code=code, explanation="x", gap=gap)


def test_creates_new_file(tmp_path):
    suggestion = _make_suggestion(str(tmp_path / "tests" / "test_foo.py"), "def test_bar(): pass\n")
    write_suggestion(suggestion, project_root=tmp_path)
    assert (tmp_path / "tests" / "test_foo.py").exists()
    assert "def test_bar" in (tmp_path / "tests" / "test_foo.py").read_text()


def test_appends_to_existing_file(tmp_path):
    test_file = tmp_path / "tests" / "test_foo.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_existing(): pass\n")
    suggestion = _make_suggestion(str(test_file), "def test_new(): pass\n")
    write_suggestion(suggestion, project_root=tmp_path)
    content = test_file.read_text()
    assert "test_existing" in content
    assert "test_new" in content


def test_does_not_duplicate_function(tmp_path):
    test_file = tmp_path / "tests" / "test_foo.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_bar(): pass\n")
    suggestion = _make_suggestion(str(test_file), "def test_bar(): assert True\n")
    write_suggestion(suggestion, project_root=tmp_path)
    content = test_file.read_text()
    assert content.count("def test_bar") == 1


def test_strips_markdown_code_fence_before_writing(tmp_path):
    suggestion = _make_suggestion(
        str(tmp_path / "tests" / "test_foo.py"),
        "```python\ndef test_bar(): pass\n```",
    )
    write_suggestion(suggestion, project_root=tmp_path)
    content = (tmp_path / "tests" / "test_foo.py").read_text()
    assert "```" not in content
    assert "def test_bar" in content
