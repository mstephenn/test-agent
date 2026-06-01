# Real-time Visualization + Multi-Agent Writer/Executor

**Date:** 2026-06-01  
**Status:** Approved

---

## Overview

Add rich real-time output to `test-agent run` with three startup panels (language detection, project structure, memory status), memory-based cache skipping for already-processed projects and files, and a per-file concurrent writer+executor model that shows baseline test results, generates suggestions, and verifies the written test passes.

---

## Architecture

Four changes to the codebase:

| Component | File | Change |
|---|---|---|
| Startup visualization | `test_agent/display.py` | new |
| Test executor agent | `test_agent/executor.py` | new |
| Memory extensions | `test_agent/memory.py` | modified |
| CLI orchestration | `test_agent/cli.py` | modified |

No new dependencies. Uses `concurrent.futures` (stdlib), `subprocess` (already used), Rich (already installed). LLM layer is untouched.

---

## Concurrency Model

Per source file:

```
ThreadPoolExecutor(max_workers=2)
  ├── Thread A: executor.run_baseline(source_file)   ← subprocess pytest
  └── Thread B: llm.generate_test(gap)               ← LLM call
      (join both)
      → REPL: show suggestion + baseline result
      → user approves → write_suggestion()
      → executor.run_verify(test_file)               ← sequential, after write
      → show verify result
```

Verify is intentionally sequential — it depends on the file having been written.

---

## `display.py`

`StartupDisplay` class with three methods:

- `show_detection(stacks, project_root, from_cache)` — Rich Panel listing detected stacks with detection files
- `show_structure(project_root, from_cache)` — Rich Tree Panel, depth capped at 3 levels
- `show_memory_status(memory, project_root, queued, already_done)` — Panel with session stats

**Tree rendering rules:**
- Excludes: `venv/`, `__pycache__/`, `.git/`, `.pytest_cache/`
- Beyond 5 items per directory → "N more files..."
- Source files default color, test files dim

**Structure hash:** `hashlib.md5` of `sorted(str(p) for p in project_root.rglob("*"))` — fast, no file reads.

**Cached variant** (hash matches stored value):
```
╭─ Step 1 · Language Detection ──────────────────╮
│  ✓ Python   (cached from 2026-05-30)           │
╰────────────────────────────────────────────────╯
```

**Fresh variant:**
```
╭─ Step 1 · Language Detection ──────────────────╮
│  ✓ Python   pyproject.toml                     │
╰────────────────────────────────────────────────╯

╭─ Step 2 · Project Structure ───────────────────╮
│  test-agent/                                   │
│  ├── test_agent/                               │
│  │   ├── cli.py                                │
│  │   └── 8 more files...                       │
│  └── tests/                                    │
│      └── 12 test files                         │
╰────────────────────────────────────────────────╯

╭─ Step 3 · Session Memory ──────────────────────╮
│  Last scan: 2026-05-30 14:32                   │
│  8 files tracked · 3 already processed         │
│  5 files queued for this run                   │
╰────────────────────────────────────────────────╯
```

---

## `executor.py`

### `ExecutorResult`

```python
@dataclass
class ExecutorResult:
    passed: int
    failed: int
    errors: int
    duration_ms: int
    output: str      # raw pytest -q output, truncated to 20 lines
    success: bool    # True if failed == 0 and errors == 0
```

### Methods

- `run_baseline(source_file, project_root, plugin) -> ExecutorResult`  
  Finds the corresponding test file (mirrors `target_resolver` logic: `tests/test_<stem>.py`). If no test file exists, returns a zero result silently.

- `run_verify(test_file, project_root, plugin) -> ExecutorResult`  
  Runs the specific test file just written.

Both methods invoke the plugin's `test_runner` via `subprocess.run` scoped to the single file.

### Inline display

```
● test_agent/scanner.py
  [baseline]  4 pass · 0 fail
  [writer]    Generating scan_files()... done

  ┌── Suggested test ──────────────────────────┐
  │  def test_scan_files_excludes_tests(): ...  │
  └────────────────────────────────────────────┘

  Approve? [y/n/e/s/q/?]  y

  [verify]    ✅  5 pass · 0 fail  (+1 new)
```

**Verify failure:**
```
  [verify]    ❌  4 pass · 1 fail
              AssertionError: expected [] got [...]
              (run pytest tests/test_scanner.py for full output)
```

The REPL proceeds regardless — test was written, user can fix manually.

**Error resilience:** if `run_baseline` or `run_verify` raises (pytest not installed, runner misconfigured) → dim warning printed, execution continues. Writer thread is unaffected.

---

## Memory Extensions (`memory.py`)

### New tables

```sql
CREATE TABLE IF NOT EXISTS project_scans (
    project_root  TEXT PRIMARY KEY,
    last_scan_at  TEXT,
    detected_stacks TEXT,   -- JSON array e.g. ["Python"]
    structure_hash  TEXT
);

CREATE TABLE IF NOT EXISTS file_states (
    project_root TEXT,
    file_path    TEXT,      -- relative to project_root
    processed_at TEXT,
    gaps_found   INTEGER,
    PRIMARY KEY (project_root, file_path)
);
```

### New methods

- `get_project_scan(project_root) -> dict | None`
- `save_project_scan(project_root, stacks, structure_hash)`
- `get_file_state(project_root, file_path) -> dict | None`
- `save_file_state(project_root, file_path, gaps_found)`

### Cache invalidation

Structure hash is recomputed on every run (cheap). If it differs from the stored hash → re-run detection and structure steps, update memory. File state is only invalidated by explicit re-processing (no mtime check in v1 — user can force reprocess with a future `--reprocess` flag).

---

## CLI Orchestration (`cli.py`)

New execution order for `run` command:

```
1. load config
2. compute structure_hash
3. StartupDisplay.show_detection(...)       ← cached or fresh
4. StartupDisplay.show_structure(...)       ← cached or fresh
5. StartupDisplay.show_memory_status(...)   ← always fresh
6. for each plugin:
     for each source_file:
       if memory.get_file_state(file) exists → skip (counted in Step 3)
       with ThreadPoolExecutor(max_workers=2):
         future_baseline = pool.submit(executor.run_baseline, ...)
         future_writer   = pool.submit(llm.generate_test, ...)
         baseline = future_baseline.result()
         suggestion = future_writer.result()
       print inline baseline + writer status
       run_repl([suggestion], baseline=baseline, ...)
       if approved:
         write_suggestion(...)
         verify = executor.run_verify(...)
         print inline verify result
         memory.save_file_state(...)
```

**`run_repl`** is unchanged internally — receives `baseline` as display context only. REPL key bindings (`y/n/e/s/q/?`) stay exactly as-is.

**`--measure` flag** still runs the full suite at the end. Per-file verify is additive.

---

## Out of Scope

- Integration test execution (requires environment setup outside this agent's scope)
- `--reprocess` flag to force re-run on already-processed files (parked for later)
- Async/await refactor of LLM providers
- Per-file parallelism across multiple files simultaneously (one file at a time, two threads within)
