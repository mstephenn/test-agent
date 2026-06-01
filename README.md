# test-agent

Language-agnostic CLI that finds coverage gaps and generates test suggestions interactively via LLM.

## Install

```bash
pipx install test-agent
```

## Usage

```bash
test-agent run /path/to/repo                  # whole repo
test-agent run /path/to/repo --changed        # only files changed vs main
test-agent run /path/to/repo --since v1.2.0   # files changed since git ref
test-agent run /path/to/repo --path src/      # specific directory
test-agent run /path/to/repo --provider kimi  # LLM provider override
test-agent run /path/to/repo --dry-run        # show suggestions, write nothing
test-agent run /path/to/repo --auto-approve   # apply all without prompting
test-agent run /path/to/repo --measure        # re-run suite, show coverage delta
test-agent init                               # scaffold config in current dir
```

## Config

Optional `test-agent.config.json` at repo root:

```json
{
  "provider": "claude",
  "excludePaths": ["migrations/", "scripts/"],
  "maxSuggestionsPerRun": 20
}
```

## Providers

| Provider | Env var | Config value |
|---|---|---|
| Claude (Anthropic) | `ANTHROPIC_API_KEY` | `"claude"` |
| OpenAI | `OPENAI_API_KEY` | `"openai"` |
| Kimi (Moonshot AI) | `MOONSHOT_API_KEY` | `"kimi"` |
| Ollama (local) | — | `"ollama"` |

## Supported Stacks

Auto-detected from project files:

| Stack | Detection file |
|---|---|
| Python | `requirements.txt`, `pyproject.toml`, `setup.py` |
| TypeScript | `tsconfig.json` |
| JavaScript | `package.json` |
| Java | `pom.xml`, `build.gradle` |
| Ruby | `Gemfile` |
| Go | `go.mod` |

## Interactive REPL

Each suggestion is shown with syntax highlighting. Keys:

| Key | Action |
|---|---|
| `y` | Approve — write test to file |
| `n` | Skip this run |
| `e` | Edit in `$EDITOR` before applying |
| `s` | Skip permanently (never suggest again) |
| `q` | Quit session |
| `?` | Explain this suggestion |

## Session Memory

Per-repo SQLite database at `.test-agent/memory.db` (add to `.gitignore`). Tracks:
- Permanently skipped symbols
- Style notes (extracted from existing tests, injected into every LLM prompt)
- Full suggestion history and session metrics
