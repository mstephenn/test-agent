from __future__ import annotations
from pathlib import Path
import requests
from test_agent.llm.base import LLMProvider, TestSuggestion
from test_agent.gap_finder import Gap
from test_agent.config import Config
from plugins.base import StackPlugin


class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3") -> None:
        self._base_url = base_url
        self._model = model

    def generate_test(
        self,
        gap: Gap,
        plugin: StackPlugin,
        config: Config,
        style_notes: str = "",
    ) -> TestSuggestion:
        system = self._build_system_prompt(plugin, style_notes)
        user = self._build_user_prompt(gap)
        prompt = f"{system}\n\n{user}"
        response = requests.post(
            f"{self._base_url}/api/generate",
            json={"model": self._model, "prompt": prompt, "stream": False},
            timeout=120,
        )
        response.raise_for_status()
        test_code = response.json()["response"].strip()
        target = str(plugin.test_file_path(Path(gap.file), Path(".")))
        return TestSuggestion(
            target_file=target,
            test_code=test_code,
            explanation=f"Tests {gap.symbol}() — {gap.kind}",
            gap=gap,
        )
