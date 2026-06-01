import json
import os
from pathlib import Path
import pytest
from test_agent.config import Config, load_config


def test_defaults():
    cfg = Config()
    assert cfg.provider == "claude"
    assert cfg.max_suggestions == 20
    assert cfg.exclude_paths == []


def test_load_from_file(tmp_path):
    config_file = tmp_path / "test-agent.config.json"
    config_file.write_text(json.dumps({"provider": "kimi", "maxSuggestionsPerRun": 5}))
    cfg = load_config(tmp_path)
    assert cfg.provider == "kimi"
    assert cfg.max_suggestions == 5


def test_env_var_overrides_file(tmp_path, monkeypatch):
    config_file = tmp_path / "test-agent.config.json"
    config_file.write_text(json.dumps({"provider": "openai"}))
    monkeypatch.setenv("TEST_AGENT_PROVIDER", "ollama")
    cfg = load_config(tmp_path)
    assert cfg.provider == "ollama"


def test_missing_config_file_uses_defaults(tmp_path):
    cfg = load_config(tmp_path)
    assert cfg.provider == "claude"
