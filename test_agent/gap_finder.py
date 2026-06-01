from __future__ import annotations
import ast
import re
from dataclasses import dataclass
from pathlib import Path
from test_agent.coverage import CoverageData

# Matches JS/TS function and method definitions:
# function foo(  |  async function foo(  |  foo(  |  foo = (  |  foo = async (
_JS_FN_RE = re.compile(
    r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*[(<]"
    r"|(?:^|\s)(\w+)\s*[:=]\s*(?:async\s+)?\("
    r"|(?:^|\s)(\w+)\s*\([^)]*\)\s*(?::\s*\w[\w<>, |]*?)?\s*\{",
    re.MULTILINE,
)
_JS_TEST_CALL_RE = re.compile(r"\b(\w+)\s*\(", re.MULTILINE)
_PYTHON_EXTS = {".py"}
_JS_EXTS = {".js", ".mjs", ".ts", ".tsx", ".jsx"}


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
        ext = src_file.suffix.lower()
        rel_path = str(src_file.relative_to(project_root))
        uncovered_lines = coverage_data.uncovered_lines.get(rel_path, []) if coverage_data else []
        if ext in _PYTHON_EXTS:
            gaps.extend(_gaps_from_python(src_file, rel_path, uncovered_lines, tested_symbols))
        elif ext in _JS_EXTS:
            gaps.extend(_gaps_from_js(src_file, rel_path, uncovered_lines, tested_symbols))
    return sorted(gaps, key=lambda g: g.priority)


def _gaps_from_python(
    src_file: Path,
    rel_path: str,
    uncovered_lines: list[int],
    tested_symbols: set[str],
) -> list[Gap]:
    try:
        source = src_file.read_text()
        tree = ast.parse(source)
    except SyntaxError:
        return []
    gaps = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        symbol = node.name
        if symbol.startswith("__") and symbol.endswith("__"):
            continue
        if symbol in tested_symbols:
            continue
        context = ast.get_source_segment(source, node) or ""
        kind, priority = _classify_python(node, symbol, uncovered_lines)
        gaps.append(Gap(file=rel_path, symbol=symbol, kind=kind, priority=priority, context_lines=context[:1000]))
    return gaps


def _gaps_from_js(
    src_file: Path,
    rel_path: str,
    uncovered_lines: list[int],
    tested_symbols: set[str],
) -> list[Gap]:
    try:
        source = src_file.read_text()
    except OSError:
        return []
    gaps = []
    seen: set[str] = set()
    for match in _JS_FN_RE.finditer(source):
        symbol = next(g for g in match.groups() if g)
        if symbol in seen or symbol in tested_symbols:
            continue
        if symbol in {"if", "for", "while", "switch", "catch", "return", "const", "let", "var"}:
            continue
        seen.add(symbol)
        is_private = symbol.startswith("_") or symbol.startswith("#")
        has_throw = "throw " in source[match.start():match.start() + 500]
        if has_throw:
            kind, priority = "error-path", 2
        elif is_private:
            kind, priority = "uncovered", 4
        else:
            kind, priority = "uncovered", 1
        context = source[match.start():match.start() + 500]
        gaps.append(Gap(file=rel_path, symbol=symbol, kind=kind, priority=priority, context_lines=context))
    return gaps


def _classify_python(node: ast.FunctionDef | ast.AsyncFunctionDef, symbol: str, uncovered_lines: list[int]) -> tuple[str, int]:
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
    symbols: set[str] = set()
    for tf in test_files:
        ext = tf.suffix.lower()
        try:
            source = tf.read_text()
        except OSError:
            continue
        if ext in _PYTHON_EXTS:
            try:
                tree = ast.parse(source)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        if isinstance(node.func, ast.Name):
                            symbols.add(node.func.id)
                        elif isinstance(node.func, ast.Attribute):
                            symbols.add(node.func.attr)
            except SyntaxError:
                pass
        elif ext in _JS_EXTS:
            for match in _JS_TEST_CALL_RE.finditer(source):
                symbols.add(match.group(1))
    return symbols
