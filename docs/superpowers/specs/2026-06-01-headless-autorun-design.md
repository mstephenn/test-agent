# Headless Auto-Run for Large Projects

**Date:** 2026-06-01  
**Status:** Approved

---

## Overview

Add a `--headless` mode to `test-agent run` that processes all files in a project automatically with no REPL interaction, using parallel file workers and a Rich Live progress display. Designed for projects with 1000+ files where an unattended overnight run is required.

---

## Architecture

Two changes to the existing codebase:

| Component | File | Change |
|---|---|---|
| Headless runner | `test_agent/headless.py` | new |
| CLI wiring | `test_agent/cli.py` | add `--headless` + `--workers` flags, route to headless runner |

The existing interactive `run()` loop is untouched. `--headless` is a branch at the top of `run()` that hands off to `HeadlessRunner` after the startup panels print.

---

## Concurrency Model

```
outer: ThreadPoolExecutor(max_workers=N)   ← N files in parallel
  per file:
    inner: ThreadPoolExecutor(max_workers=2)
      Thread A: executor.run_baseline(source_file)
      Thread B: llm.generate_test(gap)     ← one gap at a time per file
    (join both)
    write_suggestion() immediately
    executor.run_verify()
    record result
```

N defaults to 4, configurable via `--workers` flag or `headlessWorkers` in `test-agent.config.json`.

---

## Progress Display

Rich `Live` display with two panels, updated in real time:

```
╭─ Progress ─────────────────────────────────────────────────╮
│  ████████████████░░░░░░░░░░░░  247 / 1000 files            │
│  4 active  ·  241 done  ·  6 failed  ·  ~18 min remaining  │
╰────────────────────────────────────────────────────────────╯

╭─ Active Workers ───────────────────────────────────────────╮
│  [1]  test_agent/scanner.py        writing scan_files...   │
│  [2]  test_agent/gap_finder.py     baseline running...     │
│  [3]  test_agent/coverage.py       generating...           │
│  [4]  test_agent/memory.py         verifying...            │
╰────────────────────────────────────────────────────────────╯
```

Worker phases (shown in Active Workers panel): `baseline` → `generating` → `writing` → `verifying` → `done` / `failed`.

**Final summary** (replaces Live display on completion):

```
╭─ Run Complete ─────────────────────────────────────────────╮
│  1000 files scanned                                        │
│   847 files: no gaps found                                 │
│   147 tests written                                        │
│     6 verify failures  (see .test-agent/headless.log)      │
│  Duration: 23m 14s                                         │
╰────────────────────────────────────────────────────────────╯
```

**Failure log:** `.test-agent/headless.log` — one JSON line per verify failure containing `file`, `symbol`, `test_file`, `error_output`. Appended to across runs (not overwritten).

---

## `headless.py` — HeadlessRunner

### Public interface

```python
class HeadlessRunner:
    def run(
        self,
        stacks: list[StackPlugin],
        plugin_source_files: dict[str, list[Path]],
        project_root: Path,
        project_root_str: str,
        config,
        llm,
        memory: Memory,
        workers: int,
    ) -> HeadlessResult
```

### `HeadlessResult` dataclass

```python
@dataclass
class HeadlessResult:
    files_scanned: int
    files_with_gaps: int
    tests_written: int
    verify_failures: int
    duration_s: float
```

### Per-file worker (`_process_file`)

```
1. find_gaps() for this file
2. filter skipped symbols via memory.is_skipped()
3. for each gap:
   a. resolve_test_target(), compute import path
   b. ThreadPoolExecutor(2): baseline + writer concurrently
   c. write_suggestion() immediately
   d. executor.run_verify() → append to failure log if not success
4. memory.save_file_state()
5. update shared progress counters
6. report phase transitions to Live display
```

### Thread safety

- Each file worker gets its own `Memory` instance pointing to the same `.test-agent/memory.db`. WAL mode is enabled at connection time (`PRAGMA journal_mode=WAL`) to allow concurrent readers + one writer without locking errors.
- Shared progress counters (`done`, `failed`, `written`) protected by `threading.Lock`.
- Rich `Live` console is thread-safe for updates.

### Failure handling

- `_generate_valid_test` raises or returns empty → skip gap, continue to next gap.
- `run_verify` fails → write the test anyway, append failure to log, increment `failed` counter.
- Unhandled exception in a worker → mark file as failed, log traceback, continue other workers. Never abort the run.

---

## CLI Wiring (`cli.py`)

### New flags

```bash
test-agent run /path/to/repo --headless
test-agent run /path/to/repo --headless --workers 8
```

### Config additions (`test-agent.config.json`)

```json
{
  "headlessWorkers": 4
}
```

`--workers` flag overrides the config value. Config value overrides the hardcoded default of 4.

`config.py` must add `headless_workers: int = 4` to the `Config` dataclass and `"headlessWorkers": "headless_workers"` to `_JSON_TO_FIELD`.

### Routing

```python
# After startup panels:
if headless:
    workers_count = workers or config.headless_workers
    result = HeadlessRunner().run(
        stacks=stacks,
        plugin_source_files=plugin_source_files,
        project_root=project_root,
        project_root_str=project_root_str,
        config=config,
        llm=llm,
        memory=memory,
        workers=workers_count,
    )
    _print_headless_summary(result)
    memory.close()
    raise typer.Exit(0)
# else: existing interactive loop unchanged
```

### `compute_structure_hash` optimization

For projects with 1000+ files, the current full `rglob("*")` is slow. The hash function is updated to:
1. Walk with `rglob("*")`, collecting `str(rel_path) + str(size)` pairs
2. Stop collecting after 10,000 entries (cap)
3. If capped, append `"(capped)"` to the sorted list before hashing — ensures the hash still changes if files are added/removed within the first 10,000

---

## Out of Scope

- Async/await refactor of LLM providers
- Rate-limit retry logic (deferred — handled by LLM provider layer)
- `--headless` writing to a different output directory (always writes in-place)
- Dry-run mode for headless (use interactive `--dry-run` for previewing)
