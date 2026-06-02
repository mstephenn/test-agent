from __future__ import annotations
import json
import re
from pathlib import Path
from test_agent.plugins.base import StackPlugin

# Angular 14+ introduced standalone components; Angular 10+ replaced async() with waitForAsync().
_LEGACY_THRESHOLD = 10


class AngularPlugin(StackPlugin):
    def __init__(self) -> None:
        self._project_root: Path | None = None

    @property
    def name(self) -> str:
        return "Angular"

    def detect(self, project_root: Path) -> bool:
        pkg = project_root / "package.json"
        if not pkg.exists():
            return False
        data = json.loads(pkg.read_text())
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        detected = "@angular/core" in deps
        if detected:
            self._project_root = project_root
        return detected

    @property
    def test_runner(self) -> str:
        return "ng test --watch=false"

    def test_file_path(self, source_file: Path, project_root: Path) -> Path:
        return source_file.parent / (source_file.stem + ".spec" + source_file.suffix)

    @property
    def coverage_formats(self) -> list[str]:
        return ["json", "lcov"]

    def _major_version(self, project_root: Path) -> int | None:
        """Return the major version of @angular/core, or None if unresolvable."""
        pkg = project_root / "package.json"
        if not pkg.exists():
            return None
        data = json.loads(pkg.read_text())
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        raw = deps.get("@angular/core", "")
        match = re.search(r"(\d+)", raw)
        return int(match.group(1)) if match else None

    def _is_legacy(self, project_root: Path) -> bool:
        """Return True for Angular < 10 (uses async/declarations/debugElement style)."""
        version = self._major_version(project_root)
        # If version is unresolvable, check existing spec files for the legacy async import.
        if version is None:
            return self._specs_use_legacy_async(project_root)
        return version < _LEGACY_THRESHOLD

    def _specs_use_legacy_async(self, project_root: Path) -> bool:
        """Detect legacy async() usage by scanning existing .spec.ts files."""
        for spec in project_root.rglob("*.spec.ts"):
            if "{ async }" in spec.read_text() or "{ async," in spec.read_text():
                return True
        return False

    @property
    def prompt_hints(self) -> str:
        legacy = self._is_legacy(self._project_root) if self._project_root else False
        base = (
            "You are writing Angular tests using Jasmine and Karma (or Jest if jest-preset-angular is present). "
            "Use TestBed.configureTestingModule to configure the testing module. "
            "Use ComponentFixture for component interaction. "
            "Import HttpClientTestingModule and HttpTestingController for HTTP calls. "
            "Test files use the .spec.ts suffix. "
            "CRITICAL: match the import style, async wrapper, and component accessor patterns "
            "already present in the repo's existing .spec.ts files exactly. "
            "Follow AAA pattern. Do not switch frameworks or invent new test libraries. "
        )
        if legacy:
            return base + (
                "This project uses the pre-Angular 10 testing style: "
                "import async from '@angular/core/testing' (not waitForAsync), "
                "wrap beforeEach with async(), "
                "use fixture.debugElement.componentInstance to access the component instance, "
                "use fixture.debugElement.nativeElement for DOM access, "
                "declare components in the declarations array (no standalone components), "
                "use RouterTestingModule for routing, "
                "and use spyOn(...).and.returnValue() for Jasmine spies."
            )
        return base + (
            "This project uses the modern Angular testing style: "
            "import waitForAsync from '@angular/core/testing' (not the deprecated async), "
            "wrap beforeEach with waitForAsync(), "
            "use fixture.componentInstance to access the component instance, "
            "prefer standalone component imports over declarations where applicable, "
            "use provideRouter() instead of RouterTestingModule where available, "
            "and use jasmine.createSpy() or jest.spyOn() as appropriate."
        )

    def detect_framework(self, project_root: Path) -> str:
        pkg = project_root / "package.json"
        if pkg.exists():
            data = json.loads(pkg.read_text())
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            if "jest-preset-angular" in deps or "jest" in deps:
                return "jest"
        return "jasmine"
