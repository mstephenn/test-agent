from __future__ import annotations
import re
import shutil
from pathlib import Path
from test_agent.llm.base import TestSuggestion


def write_suggestion(suggestion: TestSuggestion, project_root: Path) -> None:
    target = Path(suggestion.target_file)
    test_code = clean_test_code(suggestion.test_code)
    if not target.is_absolute():
        target = project_root / target
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        _append_to_file(target, test_code)
    else:
        _write_new_file(target, test_code)


def _append_to_file(target: Path, test_code: str) -> None:
    existing = target.read_text()
    new_fn_names = _extract_function_names(test_code)
    existing_fn_names = _extract_function_names(existing)
    if new_fn_names & existing_fn_names:
        return  # skip — duplicate function names already present
    _atomic_write(target, existing.rstrip() + "\n\n" + test_code + "\n")


def _write_new_file(target: Path, test_code: str) -> None:
    _atomic_write(target, test_code + "\n")


def _atomic_write(target: Path, content: str) -> None:
    tmp = target.parent / (target.name + ".tmp")
    tmp.write_text(content)
    shutil.move(str(tmp), str(target))


def _extract_function_names(code: str) -> set[str]:
    return set(re.findall(r"def\s+(\w+)\s*\(", code))


def clean_test_code(code: str) -> str:
    stripped = code.strip()
    match = re.fullmatch(r"```(?:[a-zA-Z0-9_-]+)?\s*\n(.*)\n```", stripped, flags=re.DOTALL)
    if match:
        return match.group(1).strip()
    return stripped
