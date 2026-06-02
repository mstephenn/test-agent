from __future__ import annotations
import os
import subprocess
import tempfile
from dataclasses import dataclass
from enum import Enum
from rich.console import Console
from rich.syntax import Syntax
from rich.rule import Rule
from test_agent.llm.base import TestSuggestion
from test_agent.memory import Memory

console = Console()


class Decision(Enum):
    APPROVED = "approved"
    SKIPPED = "skipped"
    EDITED = "edited"
    SKIPPED_PERMANENTLY = "skipped_permanently"
    QUIT = "quit"


@dataclass
class REPLResult:
    suggestion: TestSuggestion
    decision: Decision
    final_code: str | None = None  # set when edited


def run_repl(
    suggestions: list[TestSuggestion],
    memory: Memory,
    auto_approve: bool = False,
    dry_run: bool = False,
) -> list[REPLResult]:
    results: list[REPLResult] = []
    total = len(suggestions)
    approved = skipped = 0

    for i, suggestion in enumerate(suggestions, 1):
        console.print(Rule())
        console.print(f"[bold cyan][{i}/{total}][/] [yellow]{suggestion.gap.file}[/] → [green]{suggestion.target_file}[/]")
        console.print(f"[dim]Requester:[/] {_requester_label(suggestion)}")
        console.print(f"[dim]Target:[/] {_target_label(suggestion)}")
        console.print(f"[dim]Gap:[/] {suggestion.gap.symbol}() — {suggestion.gap.kind}")
        console.print()
        syntax = Syntax(suggestion.test_code, _syntax_for_stack(suggestion.stack), theme="monokai", line_numbers=False)
        console.print(syntax)
        console.print()
        console.print(f"[dim]✦ {approved} approved · {skipped} skipped · {total - i} remaining[/]")
        console.print()

        if auto_approve:
            results.append(REPLResult(suggestion, Decision.APPROVED, suggestion.test_code))
            approved += 1
            continue

        decision, final_code = _prompt(suggestion)

        if decision == Decision.QUIT:
            results.append(REPLResult(suggestion, Decision.QUIT))
            break
        elif decision == Decision.APPROVED:
            approved += 1
            results.append(REPLResult(suggestion, Decision.APPROVED, suggestion.test_code))
        elif decision == Decision.EDITED:
            approved += 1
            results.append(REPLResult(suggestion, Decision.EDITED, final_code))
        elif decision == Decision.SKIPPED_PERMANENTLY:
            skipped += 1
            memory.skip_permanently(suggestion.gap.file, suggestion.gap.symbol)
            results.append(REPLResult(suggestion, Decision.SKIPPED_PERMANENTLY))
        else:
            skipped += 1
            results.append(REPLResult(suggestion, Decision.SKIPPED))

    return results


def _prompt(suggestion: TestSuggestion) -> tuple[Decision, str | None]:
    console.print("[bold][[green]y[/]] approve  [[red]n[/]] skip  [[yellow]e[/]] edit  [[magenta]s[/]] skip permanently  [[dim]q[/]] quit  [[dim]?[/]] explain[/]")
    while True:
        key = console.input("> ").strip().lower()
        if key == "y":
            return Decision.APPROVED, None
        if key == "n":
            return Decision.SKIPPED, None
        if key == "e":
            edited = _open_in_editor(suggestion.test_code)
            return Decision.EDITED, edited
        if key == "s":
            return Decision.SKIPPED_PERMANENTLY, None
        if key == "q":
            return Decision.QUIT, None
        if key == "?":
            console.print(f"[italic dim]{suggestion.explanation}[/]")
        else:
            console.print("[dim]Enter y / n / e / s / q / ?[/]")


def _open_in_editor(code: str) -> str:
    editor = os.environ.get("EDITOR", "vim")
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(code)
        fname = f.name
    subprocess.call([editor, fname])
    with open(fname) as f:
        return f.read()


def _syntax_for_stack(stack: str) -> str:
    return {
        "Python": "python",
        "JavaScript": "javascript",
        "TypeScript": "typescript",
        "Java": "java",
        "Ruby": "ruby",
        "Go": "go",
    }.get(stack, "python")


def _requester_label(suggestion: TestSuggestion) -> str:
    requester = suggestion.requester or "test-agent"
    stack = f", {suggestion.stack} stack" if suggestion.stack else ""
    framework = f", {suggestion.framework}" if suggestion.framework else ""
    return f"{requester}{stack}{framework}"


def _target_label(suggestion: TestSuggestion) -> str:
    return f"{suggestion.target_file} ({suggestion.target_status})"
