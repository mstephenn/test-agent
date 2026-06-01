from __future__ import annotations
import os
from pathlib import Path
from openai import OpenAI
from test_agent.llm.base import LLMProvider, TestSuggestion
from test_agent.gap_finder import Gap
from test_agent.config import Config
from plugins.base import StackPlugin


class OpenAIProvider(LLMProvider):
    def __init__(self, base_url: str | None = None, api_key_env: str = "OPENAI_API_KEY") -> None:
        self._client = OpenAI(
            api_key=os.environ[api_key_env],
            base_url=base_url,
        )
        self._model = "gpt-4o"

    def generate_test(
        self,
        gap: Gap,
        plugin: StackPlugin,
        config: Config,
        style_notes: str = "",
    ) -> TestSuggestion:
        system = self._build_system_prompt(plugin, style_notes)
        user = self._build_user_prompt(gap)
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=1024,
        )
        test_code = response.choices[0].message.content.strip()
        target = str(plugin.test_file_path(Path(gap.file), Path(".")))
        return TestSuggestion(
            target_file=target,
            test_code=test_code,
            explanation=f"Tests {gap.symbol}() — {gap.kind}",
            gap=gap,
        )
