from __future__ import annotations
import hashlib
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.tree import Tree

_EXCLUDED_DIRS = frozenset({
    "venv", "__pycache__", ".git", ".pytest_cache",
    ".mypy_cache", "node_modules", ".tox", ".venv",
})
_MAX_ITEMS_PER_DIR = 5
_DETECTION_MARKERS: dict[str, list[str]] = {
    "Python": ["pyproject.toml", "requirements.txt", "setup.py", "setup.cfg"],
    "TypeScript": ["tsconfig.json"],
    "JavaScript": ["package.json"],
    "Java": ["pom.xml", "build.gradle"],
    "Ruby": ["Gemfile"],
    "Go": ["go.mod"],
}


_STRUCTURE_HASH_CAP = 10_000


def compute_structure_hash(project_root: Path) -> str:
    """Return an md5 hex digest of non-excluded paths + sizes under project_root."""
    entries = []
    capped = False
    for p in project_root.rglob("*"):
        try:
            rel = p.relative_to(project_root)
        except ValueError:
            continue
        if any(part in _EXCLUDED_DIRS for part in rel.parts):
            continue
        size = p.stat().st_size if p.is_file() else 0
        entries.append(f"{rel}:{size}")
        if len(entries) >= _STRUCTURE_HASH_CAP:
            capped = True
            break
    payload = sorted(entries)
    if capped:
        payload.append("(capped)")
    return hashlib.md5("\n".join(payload).encode()).hexdigest()


class StartupDisplay:
    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console()

    def show_detection(
        self,
        stacks: list,
        project_root: Path,
        from_cache: bool = False,
        cached_at: str | None = None,
    ) -> None:
        lines = []
        for plugin in stacks:
            if from_cache:
                suffix = f"  (cached from {cached_at})" if cached_at else "  (cached)"
                lines.append(f"[green]✓[/green] [bold]{plugin.name}[/bold][dim]{suffix}[/dim]")
            else:
                marker = _find_marker(plugin.name, project_root)
                suffix = f"  {marker}" if marker else ""
                lines.append(f"[green]✓[/green] [bold]{plugin.name}[/bold][dim]{suffix}[/dim]")
        body = "\n".join(lines) if lines else "[red]No stacks detected[/red]"
        self._console.print(Panel(body, title="Step 1 · Language Detection", title_align="left"))

    def show_structure(
        self,
        project_root: Path,
        from_cache: bool = False,
        cached_at: str | None = None,
    ) -> None:
        if from_cache:
            suffix = f"  (cached from {cached_at})" if cached_at else "  (cached)"
            body = f"[bold]{project_root.name}/[/bold][dim]{suffix}[/dim]"
            self._console.print(Panel(body, title="Step 2 · Project Structure", title_align="left"))
            return
        tree = Tree(f"[bold]{project_root.name}/[/bold]")
        _build_tree(tree, project_root, depth=0, max_depth=3)
        self._console.print(Panel(tree, title="Step 2 · Project Structure", title_align="left"))

    def show_memory_status(
        self,
        queued: int,
        already_done: int,
        last_scan_at: str | None = None,
    ) -> None:
        lines = []
        if last_scan_at:
            ts = last_scan_at[:16].replace("T", " ")
            lines.append(f"[dim]Last scan:[/dim] {ts}")
        total = queued + already_done
        lines.append(
            f"[bold]{total}[/bold] [dim]files tracked  ·  [/dim]"
            f"[bold]{already_done}[/bold] [dim]already processed[/dim]"
        )
        lines.append(f"[bold green]{queued}[/bold green] [dim]files queued for this run[/dim]")
        self._console.print(Panel("\n".join(lines), title="Step 3 · Session Memory", title_align="left"))


def _find_marker(language: str, project_root: Path) -> str:
    for marker in _DETECTION_MARKERS.get(language, []):
        if (project_root / marker).exists():
            return marker
    return ""


def _build_tree(node: Tree, directory: Path, depth: int, max_depth: int) -> None:
    if depth >= max_depth:
        return
    try:
        entries = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name))
    except PermissionError:
        return
    visible = [e for e in entries if e.name not in _EXCLUDED_DIRS]
    shown = visible[:_MAX_ITEMS_PER_DIR]
    hidden_count = len(visible) - len(shown)
    for entry in shown:
        if entry.is_dir():
            branch = node.add(f"[bold]{entry.name}/[/bold]")
            _build_tree(branch, entry, depth + 1, max_depth)
        else:
            label = f"[dim]{entry.name}[/dim]" if _is_test_filename(entry.name) else entry.name
            node.add(label)
    if hidden_count > 0:
        node.add(f"[dim]... {hidden_count} more[/dim]")


def _is_test_filename(name: str) -> bool:
    lowered = name.lower()
    return "test" in lowered or "spec" in lowered
