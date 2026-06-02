from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from test_agent.plugins.base import StackPlugin

if TYPE_CHECKING:
    from test_agent.gap_finder import Gap


@dataclass(frozen=True)
class TestTarget:
    path: Path
    status: str  # "existing file" | "new file"


def resolve_test_target(
    gap: Gap,
    project_root: Path,
    plugin: StackPlugin,
    existing_test_files: list[Path],
) -> TestTarget:
    source_file = project_root / gap.file
    expected = plugin.test_file_path(source_file, project_root)
    learned = _learned_fallback_path(source_file, project_root, plugin, existing_test_files)
    if learned and expected.exists() and not learned.exists() and not _same_parent_root(expected, learned, project_root):
        return TestTarget(path=learned, status="new file")
    if expected.exists():
        return TestTarget(path=expected, status="existing file")

    match = _best_existing_test_file(source_file, expected, project_root, existing_test_files)
    if match:
        return TestTarget(path=match, status="existing file")

    if learned:
        return TestTarget(path=learned, status="new file")

    return TestTarget(path=expected, status="new file")


def read_existing_test_context(target: TestTarget, max_chars: int = 2000) -> str:
    if target.status != "existing file":
        return ""
    return _read_excerpt(target.path, max_chars)


def read_reference_test_context(target: TestTarget, existing_test_files: list[Path], max_chars: int = 2000) -> str:
    context = read_existing_test_context(target, max_chars=max_chars)
    if context:
        return context
    reference = _best_reference_test_file(target.path, existing_test_files)
    if not reference:
        return ""
    return _read_excerpt(reference, max_chars)


def _read_excerpt(path: Path, max_chars: int) -> str:
    try:
        content = path.read_text()
    except OSError:
        return ""
    return content[:max_chars]


def _best_reference_test_file(target_path: Path, existing_test_files: list[Path]) -> Path | None:
    if not existing_test_files:
        return None
    target_suffix = _test_suffix(target_path)
    ranked: list[tuple[int, str, Path]] = []
    for test_file in existing_test_files:
        score = 0
        if _test_suffix(test_file) == target_suffix:
            score += 20
        common = _common_suffix_len(target_path.parent.parts, test_file.parent.parts)
        score += min(common, 4) * 10
        ranked.append((-score, str(test_file), test_file))
    ranked.sort()
    return ranked[0][2]


def _best_existing_test_file(
    source_file: Path,
    expected: Path,
    project_root: Path,
    existing_test_files: list[Path],
) -> Path | None:
    if not existing_test_files:
        return None

    source_stem = source_file.stem
    source_parts = _meaningful_parts(source_file.relative_to(project_root).with_suffix(""))
    ranked: list[tuple[int, str, Path]] = []

    for test_file in existing_test_files:
        test_stem = _normalized_test_stem(test_file)
        test_parts = _meaningful_parts(test_file.relative_to(project_root).with_suffix(""))
        score = 0

        if test_file == expected:
            score += 100
        if test_stem == source_stem:
            score += 60
        elif source_stem in test_stem or test_stem in source_stem:
            score += 25

        common_suffix = _common_suffix_len(source_parts[:-1], test_parts[:-1])
        score += min(common_suffix, 4) * 10

        if source_stem in test_parts:
            score += 10
        if expected.parent == test_file.parent:
            score += 8

        if score >= 50:
            ranked.append((-score, str(test_file), test_file))

    if not ranked:
        return None
    ranked.sort()
    return ranked[0][2]


def _learned_fallback_path(
    source_file: Path,
    project_root: Path,
    plugin: StackPlugin,
    existing_test_files: list[Path],
) -> Path | None:
    if not existing_test_files:
        return None
    if plugin.name in {"TypeScript", "JavaScript"}:
        return _learned_js_ts_fallback_path(source_file, project_root, existing_test_files)
    return None


def _learned_js_ts_fallback_path(
    source_file: Path,
    project_root: Path,
    existing_test_files: list[Path],
) -> Path | None:
    rel_source = source_file.relative_to(project_root)
    tests_root = _dominant_tests_root(project_root, existing_test_files)
    if not tests_root:
        return None

    suffix = _dominant_test_suffix(existing_test_files, tests_root, project_root)
    domain = _source_domain(rel_source)
    test_stem = _camelized_source_stem(source_file.stem)
    return tests_root / domain / f"{test_stem}{suffix}{source_file.suffix}"


def _dominant_tests_root(project_root: Path, existing_test_files: list[Path]) -> Path | None:
    counts: dict[Path, int] = {}
    for test_file in existing_test_files:
        try:
            rel = test_file.relative_to(project_root)
        except ValueError:
            continue
        if rel.parts and rel.parts[0] in {"tests", "test", "spec"}:
            root = project_root / rel.parts[0]
            counts[root] = counts.get(root, 0) + 1
    if not counts:
        return None
    return sorted(counts.items(), key=lambda item: (-item[1], str(item[0])))[0][0]


def _dominant_test_suffix(existing_test_files: list[Path], tests_root: Path, project_root: Path) -> str:
    counts: dict[str, int] = {}
    for test_file in existing_test_files:
        try:
            test_file.relative_to(tests_root)
        except ValueError:
            continue
        suffix = _test_suffix(test_file)
        if suffix:
            counts[suffix] = counts.get(suffix, 0) + 1
    if not counts:
        return ".test"
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _source_domain(rel_source: Path) -> str:
    parts = rel_source.parts
    stem_parts = rel_source.stem.split(".")
    if len(stem_parts) > 1 and parts[0] in {"src", "lib", "app"} and len(parts) >= 2:
        if parts[1] in {"services", "service", "daos", "dao", "routes", "route", "handlers", "handler"}:
            return stem_parts[0]
    if len(parts) >= 2 and parts[0] in {"src", "lib", "app"}:
        return parts[1]
    return parts[0] if len(parts) > 1 else "unit"


def _camelized_source_stem(stem: str) -> str:
    parts = [part for part in stem.split(".") if part]
    if len(parts) <= 1:
        return stem
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def _test_suffix(path: Path) -> str:
    stem = path.stem
    for suffix in (".spec", ".test", "_spec", "_test"):
        if stem.endswith(suffix):
            return suffix
    return ""


def _same_parent_root(left: Path, right: Path, project_root: Path) -> bool:
    try:
        left_root = left.relative_to(project_root).parts[0]
        right_root = right.relative_to(project_root).parts[0]
    except (IndexError, ValueError):
        return False
    return left_root == right_root


def _normalized_test_stem(path: Path) -> str:
    stem = path.stem
    for prefix in ("test_",):
        if stem.startswith(prefix):
            stem = stem[len(prefix):]
    for suffix in ("_test", "_spec", ".test", ".spec", "Test"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
    return stem


def _meaningful_parts(path: Path) -> tuple[str, ...]:
    ignored = {"src", "lib", "app", "tests", "test", "spec", "main", "java"}
    return tuple(part for part in path.parts if part not in ignored)


def _common_suffix_len(left: tuple[str, ...], right: tuple[str, ...]) -> int:
    count = 0
    for a, b in zip(reversed(left), reversed(right)):
        if a != b:
            break
        count += 1
    return count
