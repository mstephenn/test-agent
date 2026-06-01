from __future__ import annotations
import json
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    provider: str = "claude"
    stack: str | None = None
    test_framework: str | None = None
    test_placement: str | None = None  # "mirror" | "colocated" | None=auto
    exclude_paths: list[str] = field(default_factory=list)
    max_suggestions: int = 20


def load_config(project_root: Path) -> Config:
    cfg = Config()
    config_file = project_root / "test-agent.config.json"
    if config_file.exists():
        data = json.loads(config_file.read_text())
        if "provider" in data:
            cfg.provider = data["provider"]
        if "stack" in data:
            cfg.stack = data["stack"]
        if "testFramework" in data:
            cfg.test_framework = data["testFramework"]
        if "testPlacement" in data:
            cfg.test_placement = data["testPlacement"]
        if "excludePaths" in data:
            cfg.exclude_paths = data["excludePaths"]
        if "maxSuggestionsPerRun" in data:
            cfg.max_suggestions = data["maxSuggestionsPerRun"]
    env_provider = os.environ.get("TEST_AGENT_PROVIDER")
    if env_provider:
        cfg.provider = env_provider
    return cfg
