from __future__ import annotations
import os
import anthropic
from test_agent.llm.base import LLMProvider


class ClaudeProvider(LLMProvider):
    def __init__(self) -> None:
        self._client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def _complete(self, system: str, user: str) -> str:
        message = self._client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return message.content[0].text
