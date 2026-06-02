from __future__ import annotations
import os
from openai import OpenAI
from test_agent.llm.openai import OpenAIProvider


class KimiProvider(OpenAIProvider):
    def __init__(self) -> None:
        self._client = OpenAI(
            api_key=os.environ["MOONSHOT_API_KEY"],
            base_url="https://api.moonshot.ai/v1",
        )
        self._model = "kimi-k2.6"

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
