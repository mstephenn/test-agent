from __future__ import annotations
import os
import anthropic
from pathlib import Path
from test_agent.llm.base import LLMProvider, TestSuggestion
from test_agent.gap_finder import Gap
from test_agent.config import Config
from plugins.base import StackPlugin


class ClaudeProvider(LLMProvider):
    def __init__(self) -> None:
        self._client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def generate_test(
        self,
        gap: Gap,
        plugin: StackPlugin,
        config: Config,
        style_notes: str = "",
    ) -> TestSuggestion:
        system = self._build_system_prompt(plugin, style_notes)
        user = self._build_user_prompt(gap)
        message = self._client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        test_code = message.content[0].text.strip()
        target = str(plugin.test_file_path(Path(gap.file), Path(".")))
        return TestSuggestion(
            target_file=target,
            test_code=test_code,
            explanation=f"Tests {gap.symbol}() — {gap.kind}",
            gap=gap,
        )
