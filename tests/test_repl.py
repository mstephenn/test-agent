from test_agent.gap_finder import Gap
from test_agent.llm.base import TestSuggestion
from test_agent.repl import _requester_label, _target_label


def test_repl_metadata_labels_include_requester_and_target_status():
    suggestion = TestSuggestion(
        target_file="tests/test_math_utils.py",
        test_code="def test_add(): pass",
        explanation="x",
        gap=Gap(file="src/math_utils.py", symbol="add", kind="uncovered", priority=1, context_lines=""),
        target_status="existing file",
        requester="test-agent via kimi",
        stack="Python",
        framework="pytest",
    )

    assert _requester_label(suggestion) == "test-agent via kimi, Python stack, pytest"
    assert _target_label(suggestion) == "tests/test_math_utils.py (existing file)"
