from __future__ import annotations
import requests
from test_agent.llm.base import LLMProvider


class OllamaProvider(LLMProvider):
    # Local models process one request at a time; parallelism only adds queue time
    max_workers = 1

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3") -> None:
        self._base_url = base_url
        self._model = model

    def _complete(self, system: str, user: str) -> str:
        response = requests.post(
            f"{self._base_url}/api/generate",
            json={"model": self._model, "prompt": f"{system}\n\n{user}", "stream": False},
            timeout=300,
        )
        response.raise_for_status()
        return response.json()["response"]
