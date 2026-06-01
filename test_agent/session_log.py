from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path


class SessionLog:
    def __init__(self, project_root: Path, session_id: str) -> None:
        self._project_root = project_root
        self._session_id = session_id
        self._approved = 0
        self._skipped = 0
        self._edited = 0
        self._files_modified: list[str] = []

    def record_approved(self, file: str) -> None:
        self._approved += 1
        if file not in self._files_modified:
            self._files_modified.append(file)

    def record_skipped(self) -> None:
        self._skipped += 1

    def record_edited(self, file: str) -> None:
        self._edited += 1
        if file not in self._files_modified:
            self._files_modified.append(file)

    def finalize(
        self,
        provider: str,
        gaps_found: int,
        coverage_before: float | None = None,
        coverage_after: float | None = None,
        stack: list[str] | None = None,
        scope: str = "whole-repo",
    ) -> dict:
        data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": self._session_id,
            "stack": stack or [],
            "scope": scope,
            "provider": provider,
            "gaps_found": gaps_found,
            "approved": self._approved,
            "skipped": self._skipped,
            "edited": self._edited,
            "coverage_before": coverage_before,
            "coverage_after": coverage_after,
            "files_modified": self._files_modified,
        }
        out_dir = self._project_root / ".test-agent" / "sessions"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{self._session_id}.json").write_text(json.dumps(data, indent=2))
        return data
