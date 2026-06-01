from __future__ import annotations
from pathlib import Path
from test_agent.plugins.base import StackPlugin


class PythonPlugin(StackPlugin):
    @property
    def name(self) -> str:
        return "Python"

    def detect(self, project_root: Path) -> bool:
        markers = ["requirements.txt", "pyproject.toml", "setup.py", "setup.cfg"]
        return any((project_root / m).exists() for m in markers)

    @property
    def test_runner(self) -> str:
        return "pytest"

    def test_file_path(self, source_file: Path, project_root: Path) -> Path:
        # Infer mirror placement: src/foo/bar.py → tests/test_bar.py
        rel = source_file.relative_to(project_root)
        parts = list(rel.parts)
        filename = "test_" + parts[-1]
        # Replace leading source dir with tests/
        if parts[0] in ("src", "lib", "app"):
            parts = ["tests"] + parts[1:-1] + [filename]
        else:
            parts = ["tests"] + parts[:-1] + [filename]
        return project_root / Path(*parts)

    @property
    def coverage_formats(self) -> list[str]:
        return ["lcov", "json", "xml"]

    @property
    def prompt_hints(self) -> str:
        return (
            "You are writing Python tests. "
            "Use pytest. Follow the Arrange-Act-Assert pattern. "
            "Use fixtures over setUp/tearDown. "
            "One assert per test function unless testing a sequence. "
            "Do not use mocks unless the dependency is I/O or network."
        )

    def detect_framework(self, project_root: Path) -> str:
        for candidate in ["pyproject.toml", "requirements.txt", "setup.cfg"]:
            p = project_root / candidate
            if p.exists() and "pytest" in p.read_text():
                return "pytest"
        return "unittest"
