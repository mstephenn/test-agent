from __future__ import annotations
import re
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
    target_status: str = "new file"
    requester: str = "test-agent"
    stack: str = ""
    framework: str = ""


TestSuggestion.__test__ = False  # Prevent pytest from trying to collect this class


class LLMProvider(ABC):
    """Abstract base class for LLM-based test generation."""

    @property
    def max_workers(self) -> int | None:
        """Maximum parallel workers this provider can serve. None = use configured value."""
        return None

    @abstractmethod
    def _complete(self, system: str, user: str) -> str:
        """Call the underlying API and return raw text."""

    def generate_test(
        self,
        gap: Gap,
        plugin: StackPlugin,
        config: Config,
        style_notes: str = "",
        target_file: str = "",
        target_status: str = "new file",
        framework: str = "",
        existing_test_context: str = "",
        source_import_path: str = "",
        requester: str = "test-agent",
    ) -> TestSuggestion:
        """Generate a test suggestion for the given gap."""
        system = self._build_system_prompt(plugin, style_notes, framework)
        user = self._build_user_prompt(gap, target_file, target_status, existing_test_context, source_import_path)
        test_code = self._strip_fences(self._complete(system, user))
        return TestSuggestion(
            target_file=target_file,
            test_code=test_code,
            explanation=f"Tests {gap.symbol}() — {gap.kind}",
            gap=gap,
            target_status=target_status,
            requester=requester,
            stack=plugin.name,
            framework=framework,
        )

    def fix_test(
        self,
        *,
        test_code: str,
        error_output: str,
        gap: Gap,
        target_file: str,
        plugin: StackPlugin,
        framework: str = "",
    ) -> str:
        """Regenerate failing test code given pytest error output."""
        system = self._build_system_prompt(plugin, "", framework)
        user = self._build_fix_prompt(test_code, error_output, gap, target_file)
        return self._strip_fences(self._complete(system, user))

    def _strip_fences(self, text: str) -> str:
        """Remove markdown code fences that LLMs add despite being told not to."""
        return re.sub(r"^```[^\n]*\n(.*)\n```\s*$", r"\1", text.strip(), flags=re.DOTALL)

    def _build_system_prompt(self, plugin: StackPlugin, style_notes: str, framework: str = "") -> str:
        """Build the system prompt from plugin hints and style notes."""
        base = plugin.prompt_hints
        if framework:
            base += f"\nDetected test framework/library: {framework}."
        if style_notes:
            base += f"\n\nExisting test style in this repo:\n{style_notes}"
        return base

    def _build_user_prompt(
        self,
        gap: Gap,
        target_file: str = "",
        target_status: str = "new file",
        existing_test_context: str = "",
        source_import_path: str = "",
    ) -> str:
        """Build the user prompt from the gap details."""
        target_details = f"Target test file: {target_file} ({target_status})\n" if target_file else ""
        import_details = f"Import the subject under test from: {source_import_path}\n" if source_import_path else ""
        existing_details = (
            f"\nExisting target test file excerpt. Append compatible tests and reuse its imports/style:\n"
            f"```\n{existing_test_context}\n```\n"
        ) if existing_test_context else ""
        return (
            f"Write tests for the following function that has no test coverage.\n\n"
            f"File: {gap.file}\n"
            f"Function: {gap.symbol}\n"
            f"Gap type: {gap.kind}\n\n"
            f"{target_details}"
            f"{import_details}"
            f"Source:\n```\n{gap.context_lines}\n```\n\n"
            f"{existing_details}"
            f"Requirements:\n"
            f"- Test the project code shown above, not a third-party SDK/client directly\n"
            f"- Import and exercise the function/class/method from the source file; do not recreate its internals in the test\n"
            f"- Do not invent config modules, fixtures, services, or import paths"
            f" that are not shown in the source or existing test excerpt\n"
            f"- One test function per case\n"
            f"- Assert meaningful behavior, not just 'does not throw'\n"
            f"- Include the error path if present\n"
            f"- Use the existing test library, imports, fixtures, and style when a target file already exists\n"
            f"- Return raw test code only, with no Markdown fences and no explanation"
        )

    def _build_fix_prompt(self, test_code: str, error_output: str, gap: Gap, target_file: str) -> str:
        """Build a prompt asking the LLM to fix a failing test."""
        return (
            f"The following test was generated but failed when executed.\n\n"
            f"Source file: {gap.file}\n"
            f"Function under test: {gap.symbol}\n"
            f"Test file: {target_file}\n\n"
            f"Failing test code:\n```\n{test_code}\n```\n\n"
            f"Pytest output:\n```\n{error_output}\n```\n\n"
            f"Fix the test so it passes. Requirements:\n"
            f"- Preserve all existing imports from the original test\n"
            f"- Keep testing the same function ({gap.symbol})\n"
            f"- Return raw code only — no Markdown fences, no explanation"
        )


def get_provider(provider_name: str, model: str | None = None) -> LLMProvider:
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
    instance = providers[provider_name]()
    if model:
        instance._model = model
    return instance
