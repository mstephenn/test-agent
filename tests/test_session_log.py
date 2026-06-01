import json
from pathlib import Path
from test_agent.session_log import SessionLog


def test_writes_json_file(tmp_path):
    log = SessionLog(project_root=tmp_path, session_id="2026-06-01-test")
    log.record_approved("tests/test_foo.py")
    log.record_skipped()
    log.finalize(provider="claude", gaps_found=5, coverage_before=61.2)
    session_dir = tmp_path / ".test-agent" / "sessions"
    files = list(session_dir.glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text())
    assert data["approved"] == 1
    assert data["skipped"] == 1
    assert data["coverage_before"] == 61.2
    assert data["coverage_after"] is None
    assert "tests/test_foo.py" in data["files_modified"]
