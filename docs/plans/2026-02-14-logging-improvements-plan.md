# Enhanced Logging Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add comprehensive logging with daily rotating files, timing instrumentation, and progress output for debugging, performance monitoring, and audit trails.

**Architecture:** Python logging with dual handlers (file + console), timing decorators, and enhanced skill output parsing.

**Tech Stack:** Python 3.11+, logging.handlers.TimedRotatingFileHandler, time.perf_counter()

---

## Task 1: Create Logging Configuration Module

**Files:**
- Create: `src/logging_config.py`

**Step 1: Create logging configuration file**

```python
"""Logging configuration for ai-research-assistant."""
import logging
import logging.handlers
from pathlib import Path
from datetime import datetime, timedelta


def setup_logging(log_dir: Path, retention_days: int = 30, verbose: bool = False):
    """Configure dual logging handlers (file + console).

    Args:
        log_dir: Directory for log files (created if missing)
        retention_days: How many days of logs to keep
        verbose: If True, set console to DEBUG level
    """
    # Create log directory
    log_dir.mkdir(parents=True, exist_ok=True)

    # Clean up old logs
    cleanup_old_logs(log_dir, retention_days)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture everything

    # Remove existing handlers (avoid duplicates)
    root_logger.handlers.clear()

    # File handler - daily rotation, DEBUG level
    log_file = log_dir / f"{datetime.now().strftime('%Y-%m-%d')}.log"
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=log_file,
        when='midnight',
        interval=1,
        backupCount=retention_days,
        encoding='utf-8',
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # Console handler - INFO level (or DEBUG if verbose)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    console_formatter = logging.Formatter('[%(asctime)s] %(message)s', datefmt='%H:%M:%S')
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    return root_logger


def cleanup_old_logs(log_dir: Path, retention_days: int):
    """Delete log files older than retention_days."""
    if not log_dir.exists():
        return

    cutoff_date = datetime.now() - timedelta(days=retention_days)

    for log_file in log_dir.glob('*.log'):
        try:
            # Parse YYYY-MM-DD.log format
            date_str = log_file.stem
            file_date = datetime.strptime(date_str, '%Y-%m-%d')

            if file_date < cutoff_date:
                log_file.unlink()
                logging.debug(f"Deleted old log file: {log_file.name}")
        except (ValueError, OSError):
            # Skip files that don't match date format or can't be deleted
            continue
```

**Step 2: Test syntax**

```bash
cd ~/code/ai-research-assistant
python3 -m py_compile src/logging_config.py
```

Expected: No syntax errors

**Step 3: Commit**

```bash
git add src/logging_config.py
git commit -m "feat: add logging configuration module

Daily rotating log files with dual handlers (file + console).
Automatic cleanup of logs older than retention_days.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Add Logging Configuration to Config Files

**Files:**
- Modify: `config/defaults.yaml`

**Step 1: Add logging configuration**

Add to `config/defaults.yaml`:
```yaml
logging:
  retention_days: 30
  level: INFO  # Can override with --verbose flag
```

**Step 2: Verify YAML syntax**

```bash
cd ~/code/ai-research-assistant
python3 -c "import yaml; yaml.safe_load(open('config/defaults.yaml'))"
```

Expected: No errors

**Step 3: Commit**

```bash
git add config/defaults.yaml
git commit -m "config: add logging retention and level settings

Default: 30 days retention, INFO level console output.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Initialize Logging in Main Entry Point

**Files:**
- Modify: `src/main.py`

**Step 1: Import logging config and update initialization**

Find the current logging setup (likely around line 36):
```python
logging.basicConfig(level=logging.INFO, format="%(message)s")
```

Replace with:
```python
from src.logging_config import setup_logging
from src.config import get_project_dir, load_config

# ...later in the main function, before any logging calls...

config = load_config()
log_dir = get_project_dir() / "logs"
retention_days = config.get("logging", {}).get("retention_days", 30)
verbose = "--verbose" in sys.argv  # Or however verbose flag is parsed

setup_logging(log_dir, retention_days, verbose)
logger = logging.getLogger(__name__)
logger.info("ai-research-assistant starting")
```

**Step 2: Test startup**

```bash
cd ~/code/ai-research-assistant
uv run ai-research-assistant --help
```

Expected: No errors, help text displayed

**Step 3: Verify log file created**

```bash
ls -la ~/code/ai-research-assistant/logs/
```

Expected: `YYYY-MM-DD.log` file exists

**Step 4: Commit**

```bash
git add src/main.py
git commit -m "feat: initialize logging on startup

Creates logs/ directory and daily log file.
Respects --verbose flag for console DEBUG output.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Add Timing Decorator for Skill Runner

**Files:**
- Modify: `src/skill_runner.py`

**Step 1: Add timing context manager at top of file**

After imports, add:
```python
import time
from contextlib import contextmanager

@contextmanager
def timer(operation_name: str, logger: logging.Logger):
    """Context manager to time operations and log duration."""
    start = time.perf_counter()
    try:
        yield
    finally:
        duration = time.perf_counter() - start
        logger.debug(f"{operation_name} took {duration:.1f}s")
```

**Step 2: Add logger to SkillRunner class**

Find `__init__` method and add:
```python
self.logger = logging.getLogger(__name__)
```

**Step 3: Wrap run_skill method with timing**

Find `run_skill` method, add timing and logging:

```python
def run_skill(self, entry: Entry) -> SkillResult:
    """Invoke appropriate skill for entry and verify output."""
    config = self._skill_config[entry.category]
    skill_name = config["skill"]
    timeout = config["timeout"]
    output_folder = config["output_folder"]

    self.logger.info(f"Processing: {entry.title}")
    self.logger.debug(f"Invoking /pkm:{skill_name} for {entry.url}")

    start_time = time.perf_counter()

    try:
        # ... existing subprocess code ...

        # After subprocess completes successfully:
        duration = time.perf_counter() - start_time

        if result.returncode == 0:
            note_path = self._extract_note_path(result.stdout, output_folder)
            if note_path:
                self.logger.info(f"  ✓ Created: {note_path.name} ({duration:.1f}s)")
                return SkillResult(success=True, note_path=note_path, ...)
            else:
                self.logger.warning(f"  ✗ Skill completed but no note path found ({duration:.1f}s)")
                return SkillResult(success=False, ...)
        else:
            self.logger.error(f"  ✗ Skill failed ({duration:.1f}s): {result.stderr[:200]}")
            return SkillResult(success=False, ...)
```

**Step 4: Test syntax**

```bash
python3 -m py_compile src/skill_runner.py
```

Expected: No errors

**Step 5: Commit**

```bash
git add src/skill_runner.py
git commit -m "feat: add timing and enhanced logging to skill runner

Per-entry timing with success/failure logging.
DEBUG logs show skill invocation details.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Add Pipeline Run Timing

**Files:**
- Modify: `src/pipeline.py`

**Step 1: Add timing to pipeline run**

Find `_run_pipeline_inner` function, wrap with timing:

```python
def _run_pipeline_inner(...):
    start_time = time.perf_counter()

    logger.info(f"Starting run ({len(entries)} new entries" +
                (f", {len(retries)} retries" if retries else "") +
                (f", limited to {limit})" if limit else ")"))

    # ... existing processing code ...

    # At the end, before return:
    duration = time.perf_counter() - start_time
    logger.info(f"Run complete ({duration:.1f}s total, {result.processed} processed, {result.failed} failed)")

    return result
```

**Step 2: Add import**

At top of file:
```python
import time
```

**Step 3: Test syntax**

```bash
python3 -m py_compile src/pipeline.py
```

Expected: No errors

**Step 4: Commit**

```bash
git add src/pipeline.py
git commit -m "feat: add total pipeline run timing

Logs start and completion with total duration.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Enhance evaluate-knowledge Skill Output

**Files:**
- Modify: `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Bopvault/Claude/skills-pkm/skills/evaluate-knowledge/SKILL.md`

**Step 1: Read current workflow section**

Find the main evaluation loop in the SKILL.md

**Step 2: Add timing and progress output instructions**

Update the workflow to include (add after Step 4 "Evaluate & Enhance"):

```markdown
### Progress Output

Before processing notes, count total and initialize timing:

```python
from time import perf_counter

notes_to_process = [list of notes after skip check]
total = len(notes_to_process)
timings = []
promoted_count = 0
discarded_count = 0
```

For each note being evaluated:

```python
start = perf_counter()

# ... existing evaluation logic ...

duration = perf_counter() - start
timings.append(duration)

print(f"[{len(timings)}/{total}] Evaluating: {note_name} ({duration:.1f}s)")
```

After all notes processed, print batch summary:

```python
total_time = sum(timings)
avg_time = total_time / len(timings) if timings else 0

print(f"✓ Batch complete: {promoted_count} promoted to Knowledge/, {discarded_count} discarded ({total_time:.1f}s total, avg {avg_time:.1f}s/note)")
```
```

**Step 3: Update the evaluation loop section**

Add explicit timing instrumentation to the evaluation steps (Step 4):

```markdown
### Step 4: Evaluate & Enhance (per note)

**Timing:** Wrap this entire step with timing:

```python
start_time = perf_counter()

# ... all evaluation logic here ...

duration = perf_counter() - start_time
print(f"[{current_index}/{total_notes}] Evaluating: {note_filename} ({duration:.1f}s)")
```
```

**Step 4: Commit changes to vault**

```bash
cd ~/Library/Mobile\ Documents/iCloud~md~obsidian/Documents/Bopvault
git add Claude/skills-pkm/skills/evaluate-knowledge/SKILL.md
git commit -m "feat: add progress output and timing to evaluate-knowledge

Per-note progress: [N/Total] Evaluating: note.md (X.Xs)
Batch summary with total/avg timing and result counts.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Capture evaluate-knowledge Output in Pipeline

**Files:**
- Modify: `src/pipeline.py`

**Step 1: Locate evaluate-knowledge invocation**

Find the batch processing code (around line 271):
```python
subprocess.run(
    [
        "claude",
        "--plugin-dir",
        str(vault_path / "Claude/skills-pkm"),
        ...
        f"/pkm:evaluate-knowledge {file_list}",
    ],
    timeout=600,
    capture_output=True,
    env=env,
)
```

**Step 2: Capture and log stdout**

Change to:
```python
result = subprocess.run(
    [
        "claude",
        "--plugin-dir",
        str(vault_path / "Claude/skills-pkm"),
        "--plugin-dir",
        str(vault_path / "Claude/skills-cto"),
        "--print",
        "--dangerously-skip-permissions",
        f"/pkm:evaluate-knowledge {file_list}",
    ],
    timeout=600,
    capture_output=True,
    text=True,
    env=env,
)

# Log the skill's progress output
if result.stdout:
    for line in result.stdout.strip().split('\n'):
        if line.strip():
            logger.info(f"  {line}")

if result.returncode != 0:
    logger.warning(f"  Batch {batch_idx}/{len(batches)} failed: {result.stderr[:200]}")
```

**Step 3: Test syntax**

```bash
python3 -m py_compile src/pipeline.py
```

Expected: No errors

**Step 4: Commit**

```bash
git add src/pipeline.py
git commit -m "feat: capture and log evaluate-knowledge progress output

Pipeline now logs per-note progress and batch summaries from the skill.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Integration Testing

**Files:**
- None (testing)

**Step 1: Run pipeline with verbose mode**

```bash
cd ~/code/ai-research-assistant
uv run ai-research-assistant run -n 5 --verbose
```

Expected output:
- Console shows timestamps: `[HH:MM:SS]`
- Per-entry timing: `✓ Created: note.md (X.Xs)`
- Evaluate-knowledge progress: `[1/5] Evaluating: note.md (X.Xs)`
- Batch summary: `Batch 1/1 done (X.Xs, N promoted, M discarded)`
- Total timing: `Run complete (X.Xs total, 5 processed, 0 failed)`

**Step 2: Verify log file**

```bash
cat ~/code/ai-research-assistant/logs/$(date +%Y-%m-%d).log
```

Expected:
- DEBUG entries present
- Timestamps with milliseconds
- All console output also in file
- Additional DEBUG details not shown in console

**Step 3: Test log rotation**

```bash
# Check that old log files would be cleaned up
ls -la ~/code/ai-research-assistant/logs/
```

Expected: Only recent log files present (based on retention_days)

**Step 4: Test without verbose**

```bash
uv run ai-research-assistant run -n 5
```

Expected:
- Console shows INFO only (no DEBUG spam)
- File still contains DEBUG entries
- Clean, readable output

**Step 5: Document findings**

Create a summary of:
- Log file location
- Example output format
- Performance metrics observed

---

## Task 9: Update Documentation

**Files:**
- Modify: `README-boris.md`

**Step 1: Add logging section**

After "## Monitoring" section, add:

```markdown
## Logging

**Log files:** `~/code/ai-research-assistant/logs/YYYY-MM-DD.log`

Daily rotating logs with automatic cleanup (30 day retention).

**Log levels:**
- File: DEBUG (all details)
- Console: INFO (summary only)

**Verbose mode:**
```bash
uv run ai-research-assistant run --verbose  # Shows DEBUG in console too
```

**View logs:**
```bash
# Today's log
tail -f ~/code/ai-research-assistant/logs/$(date +%Y-%m-%d).log

# Last 100 lines
tail -100 ~/code/ai-research-assistant/logs/$(date +%Y-%m-%d).log

# Search for errors
grep ERROR ~/code/ai-research-assistant/logs/*.log

# Performance analysis
grep "Created:" ~/code/ai-research-assistant/logs/$(date +%Y-%m-%d).log
```

**Configuration:**
- Retention days: `config/user.yaml` → `logging.retention_days: 30`
```

**Step 2: Commit**

```bash
git add README-boris.md
git commit -m "docs: add logging section to README

Explains log files, levels, verbose mode, and common queries.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 10: Final Verification and Cleanup

**Files:**
- None (verification)

**Step 1: Run full test with logging**

```bash
cd ~/code/ai-research-assistant
uv run ai-research-assistant run -n 10 --verbose
```

Verify:
- [ ] Timestamps in console output
- [ ] Per-entry timing logged
- [ ] Evaluate-knowledge shows progress
- [ ] Log file created with DEBUG entries
- [ ] No errors or warnings

**Step 2: Check log file size**

```bash
ls -lh ~/code/ai-research-assistant/logs/*.log
```

Verify logs are reasonable size (< 1MB per day typical)

**Step 3: Test log retention cleanup**

Create a fake old log and verify cleanup:
```bash
touch ~/code/ai-research-assistant/logs/2025-01-01.log
uv run ai-research-assistant status
ls ~/code/ai-research-assistant/logs/2025-01-01.log
```

Expected: Old log file deleted (if > 30 days old)

**Step 4: Push to GitHub**

```bash
cd ~/code/ai-research-assistant
git push origin boris-pkm-integration
```

**Step 5: Document completion**

Verify all features work:
- ✓ Daily rotating log files
- ✓ Per-entry timing
- ✓ Per-article evaluation timing
- ✓ Batch summaries
- ✓ Total pipeline timing
- ✓ Automatic log cleanup
- ✓ Verbose mode toggle

---

## Testing Checklist

After implementation, verify:

- [ ] Log files created in `~/code/ai-research-assistant/logs/`
- [ ] Daily rotation works (filename format: `YYYY-MM-DD.log`)
- [ ] Console shows timestamps: `[HH:MM:SS]`
- [ ] Per-entry timing: `✓ Created: note.md (12.3s)`
- [ ] Evaluate-knowledge progress: `[1/5] Evaluating: note.md (3.2s)`
- [ ] Batch summary: `Batch 1/1 done (14.3s, 4 promoted, 1 discarded)`
- [ ] Total timing: `Run complete (39.5s total, 5 processed, 0 failed)`
- [ ] File has DEBUG entries, console doesn't (unless --verbose)
- [ ] Old logs cleaned up after retention_days
- [ ] No performance degradation
- [ ] Logs persist across runs
- [ ] Launchd-compatible (all output captured to file)

## Success Criteria

**Debugging:**
- Can grep logs for errors: `grep ERROR logs/*.log`
- Stack traces in log files
- DEBUG details available without cluttering console

**Performance:**
- Can identify slow feeds: `grep "Created:" logs/YYYY-MM-DD.log | sort -t'(' -k2 -n`
- Average evaluation time visible
- Total run time tracked

**Audit:**
- Can review "what ran last Tuesday?": `cat logs/2026-02-11.log`
- Historical record of all processing
- No data loss between runs

---

**Related Files:**
- Design doc: `docs/plans/2026-02-14-logging-improvements-design.md`
- Logging config: `src/logging_config.py`
- Skill to update: `Claude/skills-pkm/skills/evaluate-knowledge/SKILL.md`
