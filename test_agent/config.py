from __future__ import annotations
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

_JSON_TO_FIELD: dict[str, str] = {
    "provider": "provider",
    "stack": "stack",
    "testFramework": "test_framework",
    "testPlacement": "test_placement",
    "excludePaths": "exclude_paths",
    "maxSuggestionsPerRun": "max_suggestions",
}


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
        for json_key, field_name in _JSON_TO_FIELD.items():
            if json_key in data:
                setattr(cfg, field_name, data[json_key])
    env_provider = os.environ.get("TEST_AGENT_PROVIDER")
    if env_provider:
        cfg.provider = env_provider
    return cfg
