from pathlib import Path
import pytest
from plugins.javascript import JavaScriptPlugin
from plugins.python import PythonPlugin
from plugins.typescript import TypeScriptPlugin
from test_agent.detector import detect_stacks

PYTHON_ROOT = Path("tests/fixtures/sample_repos/python_project")
JS_ROOT = Path("tests/fixtures/sample_repos/js_project")

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

def test_js_plugin_detects_package_json():
    plugin = JavaScriptPlugin()
    assert plugin.detect(JS_ROOT) is True

def test_js_plugin_detects_jest(tmp_path):
    (tmp_path / "package.json").write_text('{"devDependencies":{"jest":"^29"}}')
    plugin = JavaScriptPlugin()
    assert plugin.detect_framework(tmp_path) == "jest"

def test_ts_plugin_preferred_over_js_when_tsconfig_present(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "tsconfig.json").write_text("{}")
    ts_plugin = TypeScriptPlugin()
    assert ts_plugin.detect(tmp_path) is True



def test_detect_single_stack_python():
    stacks = detect_stacks(PYTHON_ROOT)
    assert len(stacks) == 1
    assert stacks[0].name == "Python"


def test_detect_js_stack():
    stacks = detect_stacks(JS_ROOT)
    assert len(stacks) == 1
    assert stacks[0].name == "JavaScript"


def test_detect_polyglot(tmp_path):
    (tmp_path / "requirements.txt").write_text("flask")
    (tmp_path / "package.json").write_text('{"name":"app"}')
    stacks = detect_stacks(tmp_path)
    names = {s.name for s in stacks}
    assert "Python" in names
    assert "JavaScript" in names
