from __future__ import annotations
import json
from pathlib import Path
from test_agent.plugins.base import StackPlugin


class JavaScriptPlugin(StackPlugin):
    @property
    def name(self) -> str:
        return "JavaScript"

    def detect(self, project_root: Path) -> bool:
        return (project_root / "package.json").exists() and not (project_root / "tsconfig.json").exists()

    @property
    def test_runner(self) -> str:
        return "npm test"

    def test_file_path(self, source_file: Path, project_root: Path) -> Path:
        return source_file.parent / (source_file.stem + ".test" + source_file.suffix)

    @property
    def coverage_formats(self) -> list[str]:
        return ["json", "lcov"]

    @property
    def prompt_hints(self) -> str:
        return (
            "You are writing JavaScript tests. "
            "Use the test framework, assertion library, mocking library, imports, and file style already present in the repo. "
            "Use describe/it blocks and follow AAA pattern. "
            "Do not switch frameworks or invent new test libraries."
        )

    def detect_framework(self, project_root: Path) -> str:
        pkg = project_root / "package.json"
        if pkg.exists():
            data = json.loads(pkg.read_text())
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            if "mocha" in deps:
                extras = [name for name in ("chai", "sinon") if name in deps]
                return "mocha" + (f" + {' + '.join(extras)}" if extras else "")
            for fw in ("vitest", "jest"):
                if fw in deps:
                    return fw
        return "repo default"
