from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from test_agent.gap_finder import Gap
from test_agent.config import Config
from test_agent.plugins.base import StackPlugin


@dataclass
class TestSuggestion:
    """Represents a suggested test for a coverage gap."""
    target_file: str
    test_code: str
    explanation: str
    gap: Gap


TestSuggestion.__test__ = False  # Prevent pytest from trying to collect this class


class LLMProvider(ABC):
    """Abstract base class for LLM-based test generation."""

    @abstractmethod
    def generate_test(
        self,
        gap: Gap,
        plugin: StackPlugin,
        config: Config,
        style_notes: str = "",
    ) -> TestSuggestion:
        """Generate a test suggestion for the given gap."""

    def _build_system_prompt(self, plugin: StackPlugin, style_notes: str) -> str:
        """Build the system prompt from plugin hints and style notes."""
        base = plugin.prompt_hints
        if style_notes:
            base += f"\n\nExisting test style in this repo:\n{style_notes}"
        return base

    def _build_user_prompt(self, gap: Gap) -> str:
        """Build the user prompt from the gap details."""
        return (
            f"Write tests for the following function that has no test coverage.\n\n"
            f"File: {gap.file}\n"
            f"Function: {gap.symbol}\n"
            f"Gap type: {gap.kind}\n\n"
            f"Source:\n```\n{gap.context_lines}\n```\n\n"
            f"Requirements:\n"
            f"- One test function per case\n"
            f"- Assert meaningful behavior, not just 'does not throw'\n"
            f"- Include the error path if present\n"
            f"- Return ONLY the test code block, no explanation"
        )


def get_provider(provider_name: str) -> LLMProvider:
    """
    Factory function to get an LLM provider by name.

    Args:
        provider_name: Name of the provider ('claude', 'openai', 'kimi', 'ollama')

    Returns:
        An instance of the requested LLMProvider

    Raises:
        ValueError: If provider_name is not recognized
    """
    from test_agent.llm.claude import ClaudeProvider
    from test_agent.llm.openai import OpenAIProvider
    from test_agent.llm.kimi import KimiProvider
    from test_agent.llm.ollama import OllamaProvider

    providers = {
        "claude": ClaudeProvider,
        "openai": OpenAIProvider,
        "kimi": KimiProvider,
        "ollama": OllamaProvider,
    }
    if provider_name not in providers:
        raise ValueError(f"Unknown provider: {provider_name}. Choose from {list(providers)}")
    return providers[provider_name]()
