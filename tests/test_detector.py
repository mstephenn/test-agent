from pathlib import Path
import pytest
from plugins.python import PythonPlugin

PYTHON_ROOT = Path("tests/fixtures/sample_repos/python_project")

def test_python_plugin_detects_requirements_txt():
    plugin = PythonPlugin()
    assert plugin.detect(PYTHON_ROOT) is True

def test_python_plugin_rejects_non_python(tmp_path):
    plugin = PythonPlugin()
    assert plugin.detect(tmp_path) is False

def test_python_plugin_test_file_path():
    plugin = PythonPlugin()
    src = PYTHON_ROOT / "src" / "math_utils.py"
    expected = PYTHON_ROOT / "tests" / "test_math_utils.py"
    assert plugin.test_file_path(src, PYTHON_ROOT) == expected

def test_python_plugin_detects_pytest(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\ndependencies=["pytest"]')
    plugin = PythonPlugin()
    assert plugin.detect_framework(tmp_path) == "pytest"
