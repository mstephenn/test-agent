from __future__ import annotations
from pathlib import Path
from plugins.base import StackPlugin


class RubyPlugin(StackPlugin):
    @property
    def name(self) -> str:
        return "Ruby"

    def detect(self, project_root: Path) -> bool:
        return (project_root / "Gemfile").exists()

    @property
    def test_runner(self) -> str:
        return "bundle exec rspec"

    def test_file_path(self, source_file: Path, project_root: Path) -> Path:
        # lib/foo/bar.rb → spec/foo/bar_spec.rb
        rel = source_file.relative_to(project_root)
        parts = list(rel.parts)
        if parts[0] == "lib":
            parts[0] = "spec"
        parts[-1] = Path(parts[-1]).stem + "_spec.rb"
        return project_root / Path(*parts)

    @property
    def coverage_formats(self) -> list[str]:
        return ["lcov", "json"]

    @property
    def prompt_hints(self) -> str:
        return (
            "You are writing Ruby tests using RSpec. "
            "Use describe/context/it blocks. Follow AAA. "
            "Use let/subject over instance variables."
        )

    def detect_framework(self, project_root: Path) -> str:
        gemfile = project_root / "Gemfile"
        if gemfile.exists() and "rspec" in gemfile.read_text():
            return "rspec"
        return "minitest"
