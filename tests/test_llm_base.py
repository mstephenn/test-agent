from test_agent.llm.base import TestSuggestion, LLMProvider
from test_agent.gap_finder import Gap


def test_test_suggestion_fields():
    gap = Gap(
        file="src/foo.py",
        symbol="bar",
        kind="uncovered",
        priority=1,
        context_lines="def bar(): pass"
    )
    suggestion = TestSuggestion(
        target_file="tests/test_foo.py",
        test_code="def test_bar(): assert bar() is None",
        explanation="Tests that bar() returns None",
        gap=gap,
    )
    assert suggestion.target_file == "tests/test_foo.py"
    assert suggestion.gap.symbol == "bar"
