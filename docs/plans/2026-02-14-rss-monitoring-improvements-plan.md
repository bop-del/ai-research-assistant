# RSS Monitoring Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add enhanced status command with --last-run/--watch modes, fix log buffering with explicit flushes, and unify logging to single pipeline.log file.

**Architecture:** Extend existing status command in src/main.py with new flags, add database query methods for pipeline run history, add sys.stdout.flush() calls after major operations in pipeline.py and skill_runner.py, update launchd plist to remove duplicate logging.

**Tech Stack:** Python 3.11+, Click CLI framework, SQLite3, existing logging_config module

---

## Phase 1: Database Query Methods

### Task 1: Add Pipeline Run History Query Method

**Files:**
- Modify: `src/database.py` (add method after existing query methods)

**Step 1: Add get_pipeline_run_details() method**

Add after line ~100 (after existing methods):

```python
def get_pipeline_run_details(self, run_id: int | None = None) -> dict | None:
    """Get detailed pipeline run information with processed entries.

    Args:
        run_id: Specific run ID, or None for most recent run

    Returns:
        Dict with run metadata and processed entries, or None if no runs found
    """
    # Get run metadata
    if run_id is None:
        run_cursor = self.execute(
            "SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT 1"
        )
    else:
        run_cursor = self.execute(
            "SELECT * FROM pipeline_runs WHERE id = ?", (run_id,)
        )

    run_row = run_cursor.fetchone()
    if not run_row:
        return None

    # Get processed entries for this run
    entries_cursor = self.execute(
        """
        SELECT
            entry_title,
            entry_url,
            processed_at,
            note_path
        FROM processed_entries
        WHERE processed_at >= ? AND processed_at <= ?
        ORDER BY processed_at ASC
        """,
        (run_row['started_at'], run_row['completed_at'] or datetime.now()),
    )
    entries = [dict(row) for row in entries_cursor.fetchall()]

    # Get retry/failed items
    failed_cursor = self.execute(
        """
        SELECT
            entry_title,
            entry_url,
            last_error
        FROM retry_queue
        WHERE last_attempt_at >= ? AND last_attempt_at <= ?
        """,
        (run_row['started_at'], run_row['completed_at'] or datetime.now()),
    )
    failed = [dict(row) for row in failed_cursor.fetchall()]

    return {
        'id': run_row['id'],
        'started_at': run_row['started_at'],
        'completed_at': run_row['completed_at'],
        'status': run_row['status'],
        'items_fetched': run_row['items_fetched'],
        'items_processed': run_row['items_processed'],
        'items_failed': run_row['items_failed'],
        'entries': entries,
        'failed': failed,
    }
```

**Step 2: Verify syntax**

Run: `cd ~/code/ai-research-assistant && python3 -m py_compile src/database.py`

Expected: No output (success)

**Step 3: Commit**

```bash
cd ~/code/ai-research-assistant
git add src/database.py
git commit -m "feat(db): add get_pipeline_run_details() query method

Returns comprehensive run data: metadata, processed entries, failed items.
Foundation for enhanced status command.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Phase 2: Enhanced Status Command

### Task 2: Add Timezone Formatting Utility

**Files:**
- Modify: `src/database.py` (add utility function at top of file)

**Step 1: Add imports**

Add to imports section (around line 4):

```python
from zoneinfo import ZoneInfo
```

**Step 2: Add format_timestamp() function**

Add after imports, before Database class:

```python
def format_timestamp(utc_str: str, tz_name: str = 'Europe/Berlin') -> str:
    """Convert UTC timestamp string to local timezone for display.

    Args:
        utc_str: UTC timestamp as string from SQLite
        tz_name: Target timezone (default: Europe/Berlin for Boris)

    Returns:
        Formatted string in local time: 'YYYY-MM-DD HH:MM:SS'
    """
    if not utc_str:
        return 'N/A'

    # SQLite CURRENT_TIMESTAMP returns UTC string
    utc_dt = datetime.fromisoformat(utc_str.replace(' ', 'T'))

    # Convert to local timezone
    local_tz = ZoneInfo(tz_name)
    local_dt = utc_dt.replace(tzinfo=ZoneInfo('UTC')).astimezone(local_tz)

    return local_dt.strftime('%Y-%m-%d %H:%M:%S')
```

**Step 3: Verify syntax**

Run: `cd ~/code/ai-research-assistant && python3 -m py_compile src/database.py`

Expected: No output (success)

**Step 4: Test timezone conversion manually**

Run:
```bash
cd ~/code/ai-research-assistant
python3 -c "
from datetime import datetime
from zoneinfo import ZoneInfo
utc_str = '2026-02-14 16:57:33'
utc_dt = datetime.fromisoformat(utc_str.replace(' ', 'T'))
local_dt = utc_dt.replace(tzinfo=ZoneInfo('UTC')).astimezone(ZoneInfo('Europe/Berlin'))
print(f'UTC: {utc_str}')
print(f'Local: {local_dt.strftime(\"%Y-%m-%d %H:%M:%S\")}')
"
```

Expected: Shows UTC and converted local time (Berlin timezone)

**Step 5: Commit**

```bash
git add src/database.py
git commit -m "feat(db): add format_timestamp() for UTC to local conversion

Converts SQLite UTC timestamps to Europe/Berlin for display.
Ensures consistent local time across status output.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

### Task 3: Implement --last-run Flag

**Files:**
- Modify: `src/main.py:60-86` (extend status command)

**Step 1: Update status command signature**

Replace lines 60-61:

```python
@cli.command()
def status():
```

With:

```python
@cli.command()
@click.option('--last-run', is_flag=True, help='Show detailed report of last pipeline run')
@click.option('--date', type=str, default=None, help='Show run from specific date (YYYY-MM-DD)')
@click.option('--watch', is_flag=True, help='Watch current run in real-time (updates every 2s)')
def status(last_run: bool, date: str | None, watch: bool):
```

**Step 2: Add --last-run implementation**

After line 61, add at beginning of function:

```python
    from src.database import format_timestamp

    db = get_db()

    # Handle --last-run flag
    if last_run:
        run_data = db.get_pipeline_run_details()
        if not run_data:
            click.echo("No pipeline runs found")
            return

        # Header
        started = format_timestamp(run_data['started_at'])
        completed = format_timestamp(run_data['completed_at']) if run_data['completed_at'] else 'In progress'

        if run_data['completed_at']:
            duration = datetime.fromisoformat(run_data['completed_at']) - datetime.fromisoformat(run_data['started_at'])
            duration_str = f"{int(duration.total_seconds() // 60)}m {int(duration.total_seconds() % 60)}s"
        else:
            duration_str = 'Running...'

        click.echo(f"Last Run: {started} - {completed} ({duration_str})")
        click.echo(f"Status: {run_data['status'].capitalize()}")
        click.echo()

        # Summary
        click.echo("Summary:")
        click.echo(f"  Processed: {run_data['items_processed']} items")
        click.echo(f"  Failed: {run_data['items_failed']}")
        click.echo()

        # Items processed
        if run_data['entries']:
            click.echo("Items Processed:")
            for entry in run_data['entries']:
                processed_time = format_timestamp(entry['processed_at'])
                # Determine destination from note_path
                note_path = entry.get('note_path', '')
                if 'Knowledge/' in note_path:
                    dest = f"→ {note_path.split('Knowledge/')[1].split('/')[0]}/"
                elif 'Discarded' in note_path:
                    dest = "→ Discarded"
                else:
                    dest = "→ Clippings/"

                click.echo(f"  ✓ {entry['entry_title']} {dest}")
            click.echo()

        # Failed items
        if run_data['failed']:
            click.echo("Failed Items:")
            for item in run_data['failed']:
                click.echo(f"  ✗ {item['entry_title']}")
                click.echo(f"    Error: {item['last_error']}")
            click.echo()

        return

    # Original status command behavior (if no flags)
```

**Step 3: Preserve original status behavior**

The rest of the function (lines 62-86) stays as-is for default `status` command.

**Step 4: Test --last-run flag**

Run: `cd ~/code/ai-research-assistant && uv run ai-research-assistant status --last-run`

Expected: Shows formatted report of last run (or "No pipeline runs found")

**Step 5: Commit**

```bash
git add src/main.py
git commit -m "feat(status): add --last-run flag with comprehensive report

Shows run summary, processed items with destinations, failed items.
All timestamps converted to local timezone.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

### Task 4: Implement --watch Mode

**Files:**
- Modify: `src/main.py` (add to status command after --last-run implementation)

**Step 1: Add --watch implementation**

After the `--last-run` block, before "Original status command behavior":

```python
    # Handle --watch flag
    if watch:
        import sys
        import time

        click.echo("Watching pipeline (Ctrl+C to exit)...\n")

        try:
            prev_count = 0
            while True:
                # Get current run (most recent with status='running')
                cursor = db.execute(
                    "SELECT * FROM pipeline_runs WHERE status = 'running' ORDER BY started_at DESC LIMIT 1"
                )
                current_run = cursor.fetchone()

                if current_run:
                    # Count processed entries since run started
                    entries_cursor = db.execute(
                        "SELECT COUNT(*) as count FROM processed_entries WHERE processed_at >= ?",
                        (current_run['started_at'],)
                    )
                    processed_count = entries_cursor.fetchone()['count']

                    # Clear line and show progress
                    sys.stdout.write(f"\r[{format_timestamp(current_run['started_at'])}] Processing... {processed_count} items completed")
                    sys.stdout.flush()

                    prev_count = processed_count
                else:
                    # No running pipeline
                    sys.stdout.write(f"\rNo pipeline currently running ({prev_count} items in last run)")
                    sys.stdout.flush()

                time.sleep(2)
        except KeyboardInterrupt:
            click.echo("\n\nWatch stopped.")
            return
```

**Step 2: Test --watch mode**

Run in terminal 1:
```bash
cd ~/code/ai-research-assistant
uv run ai-research-assistant run -n 3
```

Run in terminal 2:
```bash
cd ~/code/ai-research-assistant
uv run ai-research-assistant status --watch
```

Expected: Terminal 2 shows live updates every 2 seconds during processing

**Step 3: Commit**

```bash
git add src/main.py
git commit -m "feat(status): add --watch mode for real-time monitoring

Polls database every 2s, shows progress in-place.
Ctrl+C to exit cleanly.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Phase 3: Log Buffering Fixes

### Task 5: Add Flush After Article Processing

**Files:**
- Modify: `src/skill_runner.py`

**Step 1: Find article completion logging**

Read file to find where article processing completes (likely has `logger.info` with duration)

**Step 2: Add sys.stdout.flush() import**

Add to imports at top of file:

```python
import sys
```

**Step 3: Add flush after article completion log**

After the line that logs article completion (e.g., `logger.info(f"  ✓ Created: {title} ({duration}s)")`):

```python
sys.stdout.flush()  # Ensure real-time log updates
```

**Step 4: Test flush behavior**

Run in terminal 1:
```bash
cd ~/code/ai-research-assistant
uv run ai-research-assistant run -n 2 > /tmp/test-flush.log 2>&1 &
```

Run in terminal 2 immediately:
```bash
tail -f /tmp/test-flush.log
```

Expected: See log lines appear immediately after each article completes (not buffered until end)

**Step 5: Commit**

```bash
git add src/skill_runner.py
git commit -m "fix(logging): flush stdout after each article completes

Ensures tail -f shows real-time updates during processing.
Solves log buffering issue.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

### Task 6: Add Flush After Pipeline Operations

**Files:**
- Modify: `src/pipeline.py`

**Step 1: Add sys.stdout.flush() import**

Add to imports at top of file:

```python
import sys
```

**Step 2: Find major logging points**

Identify locations:
- After batch evaluation completes
- After pipeline run completes
- On errors/exceptions

**Step 3: Add flush after batch evaluation**

After the log line that reports batch completion (likely in evaluate-knowledge section):

```python
sys.stdout.flush()  # Ensure real-time log updates
```

**Step 4: Add flush after pipeline completion**

After the final `logger.info("Run complete...")` line:

```python
sys.stdout.flush()  # Ensure final status written immediately
```

**Step 5: Add flush in exception handlers**

After any `logger.error(...)` calls in exception handlers:

```python
sys.stdout.flush()  # Ensure errors written immediately
```

**Step 6: Commit**

```bash
git add src/pipeline.py
git commit -m "fix(logging): flush stdout after pipeline operations

Flush after batch eval, run completion, and errors.
Ensures all log output visible in real-time.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Phase 4: Unified Logging

### Task 7: Update Launchd Plist

**Files:**
- Modify: `~/Library/LaunchAgents/com.bop.ai-research-assistant.plist`

**Step 1: Read current plist**

Run: `cat ~/Library/LaunchAgents/com.bop.ai-research-assistant.plist`

Expected: See current configuration with StandardOutPath/StandardErrorPath

**Step 2: Unload current launchd job**

Run: `launchctl unload ~/Library/LaunchAgents/com.bop.ai-research-assistant.plist`

Expected: No output (success)

**Step 3: Update plist - remove manual redirection**

Edit file to:
1. Remove `>> ~/code/ai-research-assistant/logs/launchd.log 2>&1` from command string
2. Remove `<key>StandardOutPath</key>` and its `<string>` value
3. Remove `<key>StandardErrorPath</key>` and its `<string>` value

Updated ProgramArguments section should be:

```xml
<key>ProgramArguments</key>
<array>
    <string>/bin/bash</string>
    <string>-c</string>
    <string>cd ~/code/ai-research-assistant &amp;&amp; /Users/boris.diebold/.local/bin/uv run ai-research-assistant run</string>
</array>
```

**Step 4: Validate plist syntax**

Run: `plutil -lint ~/Library/LaunchAgents/com.bop.ai-research-assistant.plist`

Expected: "OK"

**Step 5: Reload launchd job**

Run: `launchctl load ~/Library/LaunchAgents/com.bop.ai-research-assistant.plist`

Expected: No output (success)

**Step 6: Verify job loaded**

Run: `launchctl list | grep ai-research-assistant`

Expected: Shows job with status

**Step 7: Delete old launchd.log**

Run: `rm ~/code/ai-research-assistant/logs/launchd.log`

Expected: File removed

---

## Phase 5: Testing & Documentation

### Task 8: Integration Testing

**Files:**
- None (testing only)

**Step 1: Test manual run with real-time monitoring**

Terminal 1:
```bash
cd ~/code/ai-research-assistant
uv run ai-research-assistant run -n 3
```

Terminal 2:
```bash
tail -f ~/code/ai-research-assistant/logs/pipeline.log
```

Expected: Terminal 2 shows updates immediately as each article completes

**Step 2: Test --last-run after completion**

Run: `cd ~/code/ai-research-assistant && uv run ai-research-assistant status --last-run`

Expected: Shows comprehensive report with:
- Run timestamps (local timezone)
- Summary (processed, failed counts)
- Item list with destinations
- Timing stats

**Step 3: Test --watch mode**

Terminal 1:
```bash
cd ~/code/ai-research-assistant
uv run ai-research-assistant run -n 5
```

Terminal 2 (start immediately):
```bash
cd ~/code/ai-research-assistant
uv run ai-research-assistant status --watch
```

Expected: Terminal 2 updates every 2 seconds showing progress

**Step 4: Verify only one log file**

Run: `ls ~/code/ai-research-assistant/logs/`

Expected: Only `pipeline.log` present (no launchd.log)

**Step 5: Test launchd automation**

Trigger manually:
```bash
launchctl start com.bop.ai-research-assistant
```

Check logs:
```bash
tail -f ~/code/ai-research-assistant/logs/pipeline.log
```

Expected: Output appears in pipeline.log only

---

### Task 9: Update Documentation

**Files:**
- Modify: `~/code/ai-research-assistant/README-boris.md`

**Step 1: Update Monitoring section**

Add after "Monitoring Commands" section:

```markdown
### Enhanced Status Commands

```bash
# Show last run with comprehensive report
uv run ai-research-assistant status --last-run

# Watch current run in real-time (2s updates)
uv run ai-research-assistant status --watch

# Show run from specific date
uv run ai-research-assistant status --date 2026-02-14
```

**Status report includes:**
- Run timestamps and duration
- Summary: processed, promoted, discarded, failed counts
- Item-by-item list with destinations
- Timing statistics
```

**Step 2: Update Log Monitoring section**

Update existing section to reference single log file:

```markdown
### Log Monitoring

**Single log file:** All output goes to `~/code/ai-research-assistant/logs/pipeline.log`

```bash
# Watch logs in real-time (shows immediate updates with flush)
tail -f ~/code/ai-research-assistant/logs/pipeline.log

# View recent entries
tail -100 ~/code/ai-research-assistant/logs/pipeline.log

# Search for errors
grep ERROR ~/code/ai-research-assistant/logs/pipeline.log
```

**Note:** `launchd.log` is no longer used. All logging handled by Python's logging_config module.
```

**Step 3: Commit README updates**

```bash
cd ~/code/ai-research-assistant
git add README-boris.md
git commit -m "docs: update monitoring commands and log file reference

Document new --last-run, --watch flags.
Clarify single pipeline.log file (launchd.log removed).

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

### Task 10: Update PKM Setup Guide

**Files:**
- Modify: `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Bopvault/PKM-LifeOS/Setup/RSS_Feed_Automation.md`

**Step 1: Update Monitoring section**

Find "Commands" or "Monitoring" section and update:

```markdown
### Status & Monitoring

```bash
# Quick status (pending items, last run time)
uv run ai-research-assistant status

# Comprehensive last run report
uv run ai-research-assistant status --last-run

# Real-time monitoring during processing
uv run ai-research-assistant status --watch

# View logs (real-time updates)
tail -f ~/code/ai-research-assistant/logs/pipeline.log
```

**Status report shows:**
- Run duration and timestamps (local timezone)
- Items processed: promoted to Knowledge/, discarded, or kept in Clippings/
- Failed items with error messages
- Timing statistics (average, fastest, slowest)
```

**Step 2: Update Log Locations table**

Find "File Locations" table and update logs entry:

```markdown
| Logs | `~/code/ai-research-assistant/logs/pipeline.log` |
```

Remove any reference to `launchd.log`.

**Step 3: Commit setup guide updates**

```bash
cd ~/Library/Mobile\ Documents/iCloud~md~obsidian/Documents/Bopvault
git add PKM-LifeOS/Setup/RSS_Feed_Automation.md
git commit -m "docs: update RSS automation monitoring commands

Document --last-run and --watch flags.
Remove launchd.log references (unified to pipeline.log).

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Testing Checklist

After implementation, verify:

- [ ] `status --last-run` shows comprehensive report with local timestamps
- [ ] `status --watch` updates every 2 seconds during processing
- [ ] `tail -f logs/pipeline.log` shows immediate updates (no buffering)
- [ ] All timestamps in logs and status match (local timezone)
- [ ] Only `logs/pipeline.log` exists (no `launchd.log`)
- [ ] Launchd automation writes to `pipeline.log` only
- [ ] Status report correctly categorizes: Promoted, Discarded, Clippings
- [ ] Failed items shown with error messages
- [ ] Timing stats calculated correctly

## Success Criteria

**Real-time monitoring works:**
- `tail -f` shows updates as they happen (flush fixes buffering)
- `--watch` provides live dashboard

**Post-run verification works:**
- `--last-run` shows everything: summary, items, timing
- Timestamps consistent across log/status

**Debugging is clear:**
- Single log file to check
- All times in local timezone
- Full audit trail in database + logs

## Related Files

- Design doc: `PKM-LifeOS/Plan/2026-02-14-rss-monitoring-improvements-design.md`
- Original logging design: `~/code/ai-research-assistant/docs/plans/2026-02-14-logging-improvements-design.md`
- Launchd plist: `~/Library/LaunchAgents/com.bop.ai-research-assistant.plist`
