import pytest
from pathlib import Path
from test_agent.memory import Memory


@pytest.fixture
def mem(tmp_path):
    return Memory(tmp_path / ".test-agent" / "memory.db")


def test_skip_permanently(mem):
    mem.skip_permanently("src/foo.py", "bar")
    assert mem.is_skipped("src/foo.py", "bar") is True


def test_not_skipped_by_default(mem):
    assert mem.is_skipped("src/foo.py", "baz") is False


def test_record_outcome(mem):
    mem.record_outcome(session_id="s1", file="src/foo.py", symbol="bar", outcome="approved")
    history = mem.get_history(file="src/foo.py")
    assert len(history) == 1
    assert history[0]["outcome"] == "approved"


def test_save_and_get_style_notes(mem):
    mem.save_style_note("fixture_style", "uses conftest fixtures")
    assert mem.get_style_note("fixture_style") == "uses conftest fixtures"


def test_save_session(mem):
    mem.save_session(session_id="s1", provider="claude", gaps_found=5, approved=3, skipped=2)
    sessions = mem.list_sessions()
    assert len(sessions) == 1
    assert sessions[0]["approved"] == 3


def test_close_renders_connection_unusable(tmp_path):
    import pytest
    m = Memory(tmp_path / ".test-agent" / "memory.db")
    m.close()
    with pytest.raises(Exception):
        m.is_skipped("src/foo.py", "bar")
