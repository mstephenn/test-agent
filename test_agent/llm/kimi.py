from __future__ import annotations
import os
import httpx
from openai import OpenAI
from test_agent.llm.openai import OpenAIProvider


class KimiProvider(OpenAIProvider):
    def __init__(self) -> None:
        # Kimi For Coding keys (sk-kimi-*) require the coding endpoint
        # and a User-Agent identifying as an approved coding agent
        self._client = OpenAI(
            api_key=os.environ["MOONSHOT_API_KEY"],
            base_url="https://api.kimi.com/coding/v1",
            http_client=httpx.Client(
                headers={"User-Agent": "claude-code/1.0"},
            ),
        )
        self._model = "kimi-for-coding"
