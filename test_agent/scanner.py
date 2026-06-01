from __future__ import annotations
from pathlib import Path

_TEST_PATTERNS = ("test_", "_test.", ".test.", "_spec.", "spec.")


def scan_files(
    project_root: Path,
    extensions: list[str],
    exclude_paths: list[str] | None = None,
    scope_path: Path | None = None,
    changed_files: list[Path] | None = None,
) -> list[Path]:
    """Return source files matching criteria, excluding test files and excluded paths."""
    exclude_paths = exclude_paths or []
    search_root = scope_path or project_root
    results: list[Path] = []
    for ext in extensions:
        for f in search_root.rglob(f"*{ext}"):
            if _is_test_file(f):
                continue
            rel = str(f.relative_to(project_root))
            if any(rel.startswith(exc.rstrip("/")) for exc in exclude_paths):
                continue
            if changed_files is not None and f not in changed_files:
                continue
            results.append(f)
    return results


def _is_test_file(path: Path) -> bool:
    name = path.name.lower()
    return any(p in name for p in _TEST_PATTERNS) or "test" in path.parts or "spec" in path.parts
