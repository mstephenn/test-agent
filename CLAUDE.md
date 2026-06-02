# test-agent

Language-agnostic CLI that finds test coverage gaps in a repo and generates test suggestions interactively via LLM.

## What It Does

1. Detects the project's language stack from well-known config files.
2. Scans source files and existing tests to find uncovered symbols (functions, classes, methods).
3. Calls an LLM provider to generate a test for each gap.
4. Presents suggestions in an interactive REPL — approve, edit, skip, or permanently ignore.
5. Writes approved tests to the correct location and verifies they pass.

## Running the CLI

```bash
# Interactive mode (default)
test-agent run /path/to/repo

# Unattended — parallel workers, no prompts
test-agent run /path/to/repo --headless

# Fully autonomous — approve all, auto-fix failures, loop until done
test-agent run /path/to/repo --auto

# Scaffold config file
test-agent init
```

## Project Layout

```
test_agent/
  cli.py              # Typer entry point — all subcommands live here
  config.py           # Config dataclass + JSON/env loader
  detector.py         # Stack detection (Python, TS, JS, Java, Ruby, Go)
  gap_finder.py       # Finds uncovered symbols from source + coverage data
  scanner.py          # File-system scan helpers
  coverage.py         # Parses lcov / coverage.json / jacoco reports
  memory.py           # SQLite-backed per-repo state (skips, style notes, sessions)
  repl.py             # Interactive REPL (y/n/e/s/q/?)
  executor.py         # Runs test suite baseline + post-write verify
  writer.py           # Writes approved suggestions to disk
  target_resolver.py  # Resolves where a test file should live
  headless.py         # --headless mode (parallel, no prompts)
  auto_runner.py      # --auto mode (approve all + fix loop)
  display.py          # Rich startup panels
  session_log.py      # Per-session JSONL log
  llm/
    base.py           # LLMProvider ABC + TestSuggestion dataclass
    claude.py         # Anthropic Claude provider
    openai.py         # OpenAI provider
    kimi.py           # Kimi (Moonshot AI) provider — extends OpenAI
    ollama.py         # Local Ollama provider
  plugins/
    base.py           # StackPlugin ABC
    python.py / javascript.py / typescript.py / java.py / ruby.py / go.py
    react.py / angular.py
```

## Key Conventions

- **Stack detection** lives in `detector.py`; each plugin handles prompt hints, test runner invocation, and framework detection.
- **LLM providers** extend `LLMProvider` in `llm/base.py`. Only `_complete(system, user)` needs to be implemented.
- **Memory** is a per-repo SQLite at `.test-agent/memory.db` (git-ignored). Never commit it.
- **Gap finding** operates on parsed AST / text heuristics — no regex on raw LLM output for test validation.
- All LLM API keys are read from environment variables — never hardcode keys.

## Environment Variables

| Variable | Provider |
|---|---|
| `ANTHROPIC_API_KEY` | Claude |
| `OPENAI_API_KEY` | OpenAI |
| `MOONSHOT_API_KEY` | Kimi |

Ollama requires no key (local server at `http://localhost:11434`).

## Dev Setup

```bash
pipx install --editable .
pip install -e ".[dev]"
pytest
```

## Code Practices

- Follow DRY — no duplicated gap-detection or prompt-building logic across providers.
- Avoid code smell; remove dead/commented code before merging.
- JSDoc / docstrings only where the why is non-obvious.
- Never commit directly to `main`.
