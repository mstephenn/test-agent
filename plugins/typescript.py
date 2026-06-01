from __future__ import annotations
import json
from pathlib import Path
from plugins.base import StackPlugin


class TypeScriptPlugin(StackPlugin):
    @property
    def name(self) -> str:
        return "TypeScript"

    def detect(self, project_root: Path) -> bool:
        return (project_root / "tsconfig.json").exists()

    @property
    def test_runner(self) -> str:
        return "jest"

    def test_file_path(self, source_file: Path, project_root: Path) -> Path:
        stem = source_file.stem
        return source_file.parent / f"{stem}.test{source_file.suffix}"

    @property
    def coverage_formats(self) -> list[str]:
        return ["json", "lcov"]

    @property
    def prompt_hints(self) -> str:
        return (
            "You are writing TypeScript tests. "
            "Use Jest with TypeScript. Follow AAA pattern. "
            "Include proper type annotations in test files."
        )

    def detect_framework(self, project_root: Path) -> str:
        pkg = project_root / "package.json"
        if pkg.exists():
            data = json.loads(pkg.read_text())
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            for fw in ("vitest", "jest", "mocha"):
                if fw in deps:
                    return fw
        return "jest"
