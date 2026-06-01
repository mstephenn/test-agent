from __future__ import annotations
from test_agent.llm.openai import OpenAIProvider


class KimiProvider(OpenAIProvider):
    def __init__(self) -> None:
        super().__init__(
            base_url="https://api.moonshot.ai/v1",
            api_key_env="MOONSHOT_API_KEY",
        )
        self._model = "kimi-k2.6"
