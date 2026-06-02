from __future__ import annotations
import os
from openai import OpenAI
from test_agent.llm.base import LLMProvider


class OpenAIProvider(LLMProvider):
    def __init__(self, base_url: str | None = None, api_key_env: str = "OPENAI_API_KEY") -> None:
        self._client = OpenAI(
            api_key=os.environ[api_key_env],
            base_url=base_url,
        )
        self._model = "gpt-4o"

    def _complete(self, system: str, user: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=1024,
        )
        return response.choices[0].message.content
