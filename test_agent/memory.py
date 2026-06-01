from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class Memory:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS skipped_symbols (
                file TEXT,
                symbol TEXT,
                skipped_at TEXT,
                PRIMARY KEY (file, symbol)
            );
            CREATE TABLE IF NOT EXISTS style_notes (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS suggestion_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                file TEXT,
                symbol TEXT,
                outcome TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                timestamp TEXT,
                provider TEXT,
                gaps_found INTEGER,
                approved INTEGER,
                skipped INTEGER,
                coverage_before REAL,
                coverage_after REAL
            );
            CREATE TABLE IF NOT EXISTS project_scans (
                project_root    TEXT PRIMARY KEY,
                last_scan_at    TEXT,
                detected_stacks TEXT,
                structure_hash  TEXT
            );
            CREATE TABLE IF NOT EXISTS file_states (
                project_root TEXT,
                file_path    TEXT,
                processed_at TEXT,
                gaps_found   INTEGER,
                PRIMARY KEY (project_root, file_path)
            );
        """)
        self._conn.commit()

    def skip_permanently(self, file: str, symbol: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO skipped_symbols VALUES (?, ?, ?)",
            (file, symbol, _now()),
        )
        self._conn.commit()

    def is_skipped(self, file: str, symbol: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM skipped_symbols WHERE file=? AND symbol=?", (file, symbol)
        ).fetchone()
        return row is not None

    def record_outcome(self, session_id: str, file: str, symbol: str, outcome: str) -> None:
        self._conn.execute(
            "INSERT INTO suggestion_history (session_id, file, symbol, outcome, created_at) VALUES (?,?,?,?,?)",
            (session_id, file, symbol, outcome, _now()),
        )
        self._conn.commit()

    def get_history(self, file: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM suggestion_history WHERE file=?", (file,)
        ).fetchall()
        return [dict(r) for r in rows]

    def save_style_note(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO style_notes VALUES (?, ?, ?)", (key, value, _now())
        )
        self._conn.commit()

    def get_style_note(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM style_notes WHERE key=?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def save_session(
        self,
        session_id: str,
        provider: str,
        gaps_found: int,
        approved: int,
        skipped: int,
        coverage_before: float | None = None,
        coverage_after: float | None = None,
    ) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?,?,?)",
            (session_id, _now(), provider, gaps_found, approved, skipped, coverage_before, coverage_after),
        )
        self._conn.commit()

    def list_sessions(self) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM sessions ORDER BY timestamp DESC").fetchall()
        return [dict(r) for r in rows]

    def get_project_scan(self, project_root: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM project_scans WHERE project_root=?", (project_root,)
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["detected_stacks"] = json.loads(result["detected_stacks"])
        return result

    def save_project_scan(self, project_root: str, stacks: list[str], structure_hash: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO project_scans VALUES (?,?,?,?)",
            (project_root, _now(), json.dumps(stacks), structure_hash),
        )
        self._conn.commit()

    def get_file_state(self, project_root: str, file_path: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM file_states WHERE project_root=? AND file_path=?",
            (project_root, file_path),
        ).fetchone()
        return dict(row) if row else None

    def save_file_state(self, project_root: str, file_path: str, gaps_found: int) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO file_states VALUES (?,?,?,?)",
            (project_root, file_path, _now(), gaps_found),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
