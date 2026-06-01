from __future__ import annotations
from pathlib import Path
from plugins.base import StackPlugin


class GoPlugin(StackPlugin):
    @property
    def name(self) -> str:
        return "Go"

    def detect(self, project_root: Path) -> bool:
        return (project_root / "go.mod").exists()

    @property
    def test_runner(self) -> str:
        return "go test ./..."

    def test_file_path(self, source_file: Path, project_root: Path) -> Path:
        # foo/bar.go → foo/bar_test.go
        return source_file.parent / (source_file.stem + "_test.go")

    @property
    def coverage_formats(self) -> list[str]:
        return ["lcov"]

    @property
    def prompt_hints(self) -> str:
        return (
            "You are writing Go tests using the standard testing package. "
            "Use table-driven tests where appropriate. "
            "Name test functions Test<FunctionName>. "
            "Use t.Run() for subtests."
        )

    def detect_framework(self, project_root: Path) -> str:
        return "go test"
