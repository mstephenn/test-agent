from __future__ import annotations
from pathlib import Path
from test_agent.plugins.base import StackPlugin
from test_agent.plugins.python import PythonPlugin
from test_agent.plugins.javascript import JavaScriptPlugin
from test_agent.plugins.typescript import TypeScriptPlugin
from test_agent.plugins.java import JavaPlugin
from test_agent.plugins.ruby import RubyPlugin
from test_agent.plugins.go import GoPlugin

_ALL_PLUGINS: list[StackPlugin] = [
    TypeScriptPlugin(),  # must come before JavaScript
    JavaScriptPlugin(),
    PythonPlugin(),
    JavaPlugin(),
    RubyPlugin(),
    GoPlugin(),
]


def detect_stacks(project_root: Path) -> list[StackPlugin]:
    """Return all plugins whose detect() returns True for this project root."""
    return [p for p in _ALL_PLUGINS if p.detect(project_root)]
