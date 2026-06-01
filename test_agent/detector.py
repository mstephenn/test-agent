from __future__ import annotations
from pathlib import Path
from plugins.base import StackPlugin
from plugins.python import PythonPlugin
from plugins.javascript import JavaScriptPlugin
from plugins.typescript import TypeScriptPlugin
from plugins.java import JavaPlugin
from plugins.ruby import RubyPlugin
from plugins.go import GoPlugin

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
