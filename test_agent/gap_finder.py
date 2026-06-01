from __future__ import annotations
import ast
from dataclasses import dataclass
from pathlib import Path
from test_agent.coverage import CoverageData


@dataclass
class Gap:
    """Represents a coverage gap found in source code."""
    file: str
    symbol: str
    kind: str          # "uncovered" | "partial" | "no-assertion" | "error-path"
    priority: int      # 1=public API, 2=error path, 3=partial branch, 4=internal
    context_lines: str


def find_gaps(
    source_files: list[Path],
    project_root: Path,
    coverage_data: CoverageData | None,
    existing_test_files: list[Path],
) -> list[Gap]:
    """
    Analyze source files for test coverage gaps.

    Args:
        source_files: List of Python source files to analyze
        project_root: Root directory for relative path calculation
        coverage_data: Optional coverage data from parsed reports
        existing_test_files: List of existing test files to check for references

    Returns:
        Sorted list of Gap objects, prioritized by importance
    """
    tested_symbols = _collect_tested_symbols(existing_test_files)
    gaps: list[Gap] = []
    for src_file in source_files:
        try:
            tree = ast.parse(src_file.read_text())
        except SyntaxError:
            continue
        rel_path = str(src_file.relative_to(project_root))
        uncovered_lines = coverage_data.uncovered_lines.get(rel_path, []) if coverage_data else []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            symbol = node.name
            if symbol.startswith("__") and symbol.endswith("__"):
                continue
            if symbol in tested_symbols:
                continue
            context = ast.get_source_segment(src_file.read_text(), node) or ""
            kind, priority = _classify(node, symbol, uncovered_lines)
            gaps.append(Gap(
                file=rel_path,
                symbol=symbol,
                kind=kind,
                priority=priority,
                context_lines=context[:1000],
            ))
    return sorted(gaps, key=lambda g: g.priority)


def _classify(node: ast.FunctionDef | ast.AsyncFunctionDef, symbol: str, uncovered_lines: list[int]) -> tuple[str, int]:
    """
    Classify a function gap by kind and priority.

    Error paths (functions with raise statements) are always priority 2.
    Private functions are priority 4.
    Public uncovered functions are priority 1.

    Args:
        node: AST node representing the function
        symbol: Function name
        uncovered_lines: Line numbers marked as uncovered by coverage tool

    Returns:
        Tuple of (kind, priority)
    """
    has_raise = any(isinstance(n, (ast.Raise, ast.ExceptHandler)) for n in ast.walk(node))
    is_private = symbol.startswith("_")

    if has_raise:
        return "error-path", 2

    if is_private:
        return "uncovered", 4

    return "uncovered", 1


def _collect_tested_symbols(test_files: list[Path]) -> set[str]:
    """
    Extract all function/method names called in test files.

    Args:
        test_files: List of test file paths

    Returns:
        Set of symbol names referenced in tests
    """
    symbols: set[str] = set()
    for tf in test_files:
        try:
            tree = ast.parse(tf.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    symbols.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    symbols.add(node.func.attr)
    return symbols
