from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path


class StackPlugin(ABC):
    @abstractmethod
    def detect(self, project_root: Path) -> bool:
        """Return True if this plugin applies to the given project."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable stack name, e.g. 'Python'."""

    @property
    @abstractmethod
    def test_runner(self) -> str:
        """Command to run the test suite, e.g. 'pytest'."""

    @abstractmethod
    def test_file_path(self, source_file: Path, project_root: Path) -> Path:
        """Given a source file path, return the expected test file path."""

    @property
    @abstractmethod
    def coverage_formats(self) -> list[str]:
        """Coverage report formats this stack produces, e.g. ['lcov', 'json']."""

    @property
    @abstractmethod
    def prompt_hints(self) -> str:
        """Stack-specific instructions injected into the LLM system prompt."""

    @abstractmethod
    def detect_framework(self, project_root: Path) -> str:
        """Return the test framework in use, e.g. 'pytest', 'jest'."""
