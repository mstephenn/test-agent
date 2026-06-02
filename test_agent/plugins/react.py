from __future__ import annotations
import json
from pathlib import Path
from test_agent.plugins.base import StackPlugin


class ReactPlugin(StackPlugin):
    @property
    def name(self) -> str:
        return "React"

    def detect(self, project_root: Path) -> bool:
        pkg = project_root / "package.json"
        if not pkg.exists():
            return False
        data = json.loads(pkg.read_text())
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        return "react" in deps

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
            "You are writing React tests. "
            "Prefer React Testing Library (@testing-library/react) with render, screen, and userEvent. "
            "Query elements by accessible role, label, or text — avoid querying by class or id. "
            "Use waitFor or findBy* queries for async state updates. "
            "Mock fetch or axios at the module level with jest.mock or vi.mock. "
            "Do not test implementation details; test observable behavior from the user's perspective. "
            "Follow AAA pattern. Do not switch frameworks or invent new test libraries."
        )

    def detect_framework(self, project_root: Path) -> str:
        pkg = project_root / "package.json"
        if pkg.exists():
            data = json.loads(pkg.read_text())
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            for fw in ("vitest", "jest"):
                if fw in deps:
                    return fw
            if "mocha" in deps:
                extras = [name for name in ("chai", "sinon") if name in deps]
                return "mocha" + (f" + {' + '.join(extras)}" if extras else "")
        return "repo default"
