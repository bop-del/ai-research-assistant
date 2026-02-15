# Morning Dashboard Integration - Simplified Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add comprehensive RSS dashboard to `/morning` skill using helper functions (no class, no tests) with stats, trends, health alerts, and recommendations.

**Architecture:** Add 4 helper functions to `src/main.py` → new `stats` CLI command uses them → `/morning` skill calls `stats --json` and formats output into daily note.

**Tech Stack:** Python 3.11+, Click CLI, SQLite3, regex (log parsing)

**Prerequisites:** Must complete `2026-02-14-rss-monitoring-improvements-plan.md` first.

---

## Task 1: Add Helper Functions

**Files:**
- Modify: `src/main.py` (add before `stats` command, around line 200)

**Step 1: Add imports at top of file**

After existing imports (around line 3), add:

```python
import re
```

**Step 2: Add _calculate_trends() helper function**

Add after `get_db()` function (around line 15), before `@click.group()`:

```python
def _calculate_trends(db: Database, days: int = 7) -> dict:
    """Calculate trends comparing last N days to previous N days.

    Returns dict with recent stats, previous stats, and comparison string.
    """
    # Last N days
    cursor_recent = db.execute(
        """SELECT SUM(items_processed) as total, SUM(items_failed) as failed
           FROM pipeline_runs
           WHERE status = 'completed'
             AND completed_at >= datetime('now', ? || ' days')""",
        (f'-{days}',)
    )
    recent = cursor_recent.fetchone()

    # Previous N days (for comparison)
    cursor_previous = db.execute(
        """SELECT SUM(items_processed) as total, SUM(items_failed) as failed
           FROM pipeline_runs
           WHERE status = 'completed'
             AND completed_at >= datetime('now', ? || ' days')
             AND completed_at < datetime('now', ? || ' days')""",
        (f'-{days * 2}', f'-{days}')
    )
    previous = cursor_previous.fetchone()

    recent_total = recent["total"] or 0
    previous_total = previous["total"] or 0

    # Calculate comparison string
    if previous_total == 0:
        comparison = "N/A (no previous data)"
    else:
        pct_change = ((recent_total - previous_total) / previous_total) * 100
        if abs(pct_change) < 5:
            comparison = "→ stable"
        elif pct_change > 0:
            comparison = f"↑ {pct_change:.0f}% more"
        else:
            comparison = f"↓ {abs(pct_change):.0f}% less"

    return {
        "last_7_days": {
            "total_processed": recent_total,
            "total_failed": recent["failed"] or 0,
            "avg_per_day": recent_total / days if recent_total > 0 else 0
        },
        "previous_7_days": {
            "total_processed": previous_total,
            "total_failed": previous["failed"] or 0
        },
        "comparison": comparison
    }
```

**Step 3: Add _parse_performance() helper function**

Add after `_calculate_trends()`:

```python
def _parse_performance(log_dir: Path) -> dict:
    """Parse performance metrics from pipeline.log.

    Returns dict with avg time, slowest/fastest articles (or None if no data).
    """
    log_file = log_dir / "pipeline.log"

    if not log_file.exists():
        return {
            "avg_seconds_per_article": 0,
            "slowest": None,
            "fastest": None
        }

    content = log_file.read_text()

    # Parse per-article timing: "✓ Created: filename.md (XX.Xs)"
    pattern = r'✓ Created: (.+?\.md) \((\d+\.\d+)s\)'
    matches = re.findall(pattern, content)

    if not matches:
        return {
            "avg_seconds_per_article": 0,
            "slowest": None,
            "fastest": None
        }

    # Extract and sort by duration
    articles = [(title, float(duration)) for title, duration in matches]
    articles.sort(key=lambda x: x[1])

    avg_time = sum(t[1] for t in articles) / len(articles)

    return {
        "avg_seconds_per_article": avg_time,
        "slowest": {
            "title": articles[-1][0],
            "duration": articles[-1][1]
        },
        "fastest": {
            "title": articles[0][0],
            "duration": articles[0][1]
        }
    }
```

**Step 4: Add _calculate_health() helper function**

Add after `_parse_performance()`:

```python
def _calculate_health(db: Database, log_dir: Path) -> dict:
    """Check pipeline health and generate alerts.

    Returns dict with overall status and list of alert strings.
    """
    alerts = []

    # Use Phase 1's get_pipeline_run_details()
    last_run = db.get_pipeline_run_details()

    if not last_run:
        return {
            "status": "warning",
            "alerts": ["No pipeline runs yet"]
        }

    # Check last run time
    last_run_time = datetime.fromisoformat(last_run["completed_at"])
    hours_since = (datetime.now() - last_run_time).total_seconds() / 3600

    if hours_since > 48:
        alerts.append("⚠️ No successful run in 48 hours")
    elif hours_since > 24:
        alerts.append("⚠️ No successful run in 24 hours")

    # Check failure rate
    total_items = last_run["items_processed"] + last_run["items_failed"]
    if total_items > 0:
        failure_rate = last_run["items_failed"] / total_items
        if failure_rate > 0.25:
            alerts.append(f"❌ High failure rate: {failure_rate:.0%}")
        elif failure_rate > 0.10:
            alerts.append(f"⚠️ Elevated failure rate: {failure_rate:.0%}")

    # Check processing speed
    perf = _parse_performance(log_dir)
    if perf["avg_seconds_per_article"] > 120:
        alerts.append(f"❌ Very slow processing: {perf['avg_seconds_per_article']:.0f}s avg")
    elif perf["avg_seconds_per_article"] > 90:
        alerts.append(f"⚠️ Slow processing: {perf['avg_seconds_per_article']:.0f}s avg")

    # Determine overall status
    if any("❌" in alert for alert in alerts):
        status = "error"
    elif any("⚠️" in alert for alert in alerts):
        status = "warning"
    else:
        status = "healthy"

    return {
        "status": status,
        "alerts": alerts
    }
```

**Step 5: Add _generate_recommendations() helper function**

Add after `_calculate_health()`:

```python
def _generate_recommendations(db: Database, log_dir: Path) -> list[str]:
    """Generate actionable recommendations based on metrics.

    Returns list of recommendation strings (max 5).
    """
    recommendations = []

    # Check performance
    perf = _parse_performance(log_dir)
    if perf["avg_seconds_per_article"] > 90:
        recommendations.append(
            f"Consider feed prioritization — {perf['avg_seconds_per_article']:.0f}s avg processing time"
        )

    if perf["slowest"] and perf["slowest"]["duration"] > 120:
        title = perf["slowest"]["title"]
        duration = perf["slowest"]["duration"]
        recommendations.append(
            f"Investigate slow feed: {title} took {duration:.0f}s"
        )

    # Check health for issues
    health = _calculate_health(db, log_dir)
    if any("48 hours" in alert for alert in health["alerts"]):
        recommendations.append(
            "Verify launchd job: launchctl list | grep ai-research-assistant"
        )
    elif any("24 hours" in alert for alert in health["alerts"]):
        recommendations.append(
            "Check logs for recent run issues"
        )

    # Limit to top 5
    return recommendations[:5]
```

**Step 6: Verify syntax**

Run: `cd ~/code/ai-research-assistant && python3 -m py_compile src/main.py`

Expected: No output (success)

**Step 7: Commit**

```bash
cd ~/code/ai-research-assistant
git add src/main.py
git commit -m "feat(stats): add helper functions for dashboard metrics

Add _calculate_trends, _parse_performance, _calculate_health, _generate_recommendations.
Foundation for stats CLI command.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Add Stats CLI Command

**Files:**
- Modify: `src/main.py` (add after `status` command, around line 220)

**Step 1: Add stats command**

Add after the `status` command (after the `return` on line ~196):

```python
@cli.command()
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON for /morning skill')
@click.option('--days', '-d', type=int, default=7, help='Number of days to analyze')
def stats(output_json: bool, days: int):
    """Show comprehensive pipeline statistics and health dashboard.

    Use --json for machine-readable output (consumed by /morning skill).
    """
    from src.config import get_project_dir
    from src.database import format_timestamp
    import json as json_module

    db = get_db()
    log_dir = get_project_dir() / "logs"

    # Collect all metrics using helper functions
    last_run = db.get_pipeline_run_details()  # From Phase 1
    trends = _calculate_trends(db, days)
    performance = _parse_performance(log_dir)
    health = _calculate_health(db, log_dir)
    recommendations = _generate_recommendations(db, log_dir)

    # Build data structure
    data = {
        "last_run": last_run,
        "trends": trends,
        "performance": performance,
        "health": health,
        "recommendations": recommendations
    }

    if output_json:
        # JSON output for /morning skill consumption
        click.echo(json_module.dumps(data, indent=2, default=str))
    else:
        # Human-readable terminal output
        if data["last_run"]:
            lr = data["last_run"]
            click.echo(f"Last run: {format_timestamp(lr['completed_at'])}")
            click.echo(f"  Processed: {lr['items_processed']}, Failed: {lr['items_failed']}")
            click.echo()
        else:
            click.echo("No runs yet\n")

        # Trends
        click.echo(f"7-day trend: {trends['comparison']}")
        click.echo(f"  Recent: {trends['last_7_days']['total_processed']} items")
        click.echo(f"  Previous: {trends['previous_7_days']['total_processed']} items")
        click.echo()

        # Performance
        if performance["avg_seconds_per_article"] > 0:
            click.echo("Performance:")
            click.echo(f"  Avg: {performance['avg_seconds_per_article']:.0f}s/article")
            if performance["slowest"]:
                click.echo(f"  Slowest: {performance['slowest']['title']} ({performance['slowest']['duration']:.0f}s)")
            click.echo()

        # Health
        status_emoji = {"healthy": "✅", "warning": "⚠️", "error": "❌"}
        click.echo(f"Health: {status_emoji.get(health['status'], '?')} {health['status'].capitalize()}")
        if health["alerts"]:
            for alert in health["alerts"]:
                click.echo(f"  {alert}")
            click.echo()

        # Recommendations
        if recommendations:
            click.echo("Recommendations:")
            for i, rec in enumerate(recommendations, 1):
                click.echo(f"  {i}. {rec}")
```

**Step 2: Test stats command**

Run: `cd ~/code/ai-research-assistant && uv run ai-research-assistant stats`

Expected: Shows human-readable dashboard (or "No runs yet" if no data)

**Step 3: Test JSON output**

Run: `cd ~/code/ai-research-assistant && uv run ai-research-assistant stats --json | python3 -m json.tool`

Expected: Valid JSON structure (or error if no runs)

**Step 4: Commit**

```bash
git add src/main.py
git commit -m "feat(cli): add stats command with JSON output

Human-readable dashboard for terminal use.
JSON mode (--json) for /morning skill consumption.
Aggregates trends, performance, health, recommendations.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Update Morning Skill

**Files:**
- Modify: `Claude/skills-pkm/skills/morning/SKILL.md`

**Step 1: Add Step 5.6 after Step 5.5b**

Insert after Step 5.5b (around line 140):

```markdown
### Step 5.6: RSS Pipeline Monitoring

1. Check if ai-research-assistant is installed: `which ai-research-assistant`
2. If not found: skip silently (no error message)
3. Call `ai-research-assistant stats --json --days 7`
4. Parse JSON response
5. Format as Markdown section
6. Append `## RSS Pipeline` to daily note after `## Todoist`, before `## Capture`
   - If section exists (re-run), replace it
7. Print one-line summary: "RSS: X processed, Y failed"

**Format template (with data):**

```markdown
## RSS Pipeline

**Last run:** YYYY-MM-DD HH:MM ([logs](file:///Users/boris.diebold/code/ai-research-assistant/logs/pipeline.log))

**Processing:**
- ✓ X articles processed (YYs avg, ZZZs total)
- ✗ N failed (retry scheduled)

**7-day trend:** comparison text (X vs Y previous week)

**Performance:**
- Avg: XXs/article
- Slowest: "Title" (XXs)

**Health:** ✅/⚠️/❌ Status
[alerts if present, one per line with bullet]

**Recommendations:**
1. [Recommendation 1]
2. [Recommendation 2]
[max 5, skip section if empty]
```

**Format template (no runs yet):**

```markdown
## RSS Pipeline

**Status:** No runs yet — first automated run scheduled for 04:00 tomorrow

**Next steps:**
1. Verify launchd: `launchctl list | grep ai-research-assistant`
2. Test: `uv run ai-research-assistant run --dry-run`
```

**Error handling:**
- `which ai-research-assistant` fails → skip step silently
- `stats --json` fails → skip with terminal message only (don't fail /morning)
- JSON parse fails → skip with terminal message only
- `last_run` is null → use "no runs yet" template
```

**Step 2: Update Step 7 summary format**

Find Step 7 (around line 160) and update the template to include RSS line:

```markdown
✓ Morning complete
- Calendar: X meetings, Y focus blocks
- Todoist: X due today, Y overdue
- Clippings: X evaluated
- RSS: X processed, Y failed
- Daily note: Updated _Daily/YYYY-MM-DD.md
- Inbox: X/Y triaged
```

**Step 3: Commit**

```bash
cd ~/Library/Mobile\ Documents/iCloud~md~obsidian/Documents/Bopvault/Claude
git add skills-pkm/skills/morning/SKILL.md
git commit -m "feat(morning): add RSS pipeline monitoring dashboard

Calls ai-research-assistant stats --json.
Formats comprehensive dashboard in daily note.
Silent failure if not installed.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Update Documentation

**Files:**
- Modify: `~/code/ai-research-assistant/README-boris.md`
- Modify: `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Bopvault/PKM-LifeOS/Setup/RSS_Feed_Automation.md`

**Step 1: Update README-boris.md**

Add after existing monitoring commands section:

```markdown
### Stats Dashboard

```bash
# Comprehensive statistics dashboard
uv run ai-research-assistant stats

# JSON output (for /morning skill)
uv run ai-research-assistant stats --json

# Analyze last 14 days
uv run ai-research-assistant stats --days 14
```

**Dashboard shows:**
- Last run summary (processed, failed counts)
- 7-day trends with week-over-week comparison
- Performance metrics (avg time, slowest article)
- Health status with alerts
- Actionable recommendations (max 5)

**Integrated with /morning:** RSS pipeline section automatically added to daily note.
```

**Step 2: Update RSS_Feed_Automation.md**

Find the Monitoring section and update:

```markdown
### Status & Monitoring

```bash
# Quick status (pending items, last run time)
uv run ai-research-assistant status

# Comprehensive last run report
uv run ai-research-assistant status --last-run

# Real-time monitoring during processing
uv run ai-research-assistant status --watch

# Full dashboard with trends and recommendations
uv run ai-research-assistant stats

# View logs (real-time updates)
tail -f ~/code/ai-research-assistant/logs/pipeline.log
```

**Stats dashboard shows:**
- Run duration and timestamps (local timezone)
- Items processed: promoted to Knowledge/, discarded, or kept in Clippings/
- 7-day trends with comparison to previous week
- Performance data (average, fastest, slowest)
- Health alerts (stale runs, high failure rates)
- Actionable recommendations

**Morning integration:** The `/morning` skill automatically checks RSS pipeline health and surfaces the dashboard in your daily note under `## RSS Pipeline`.
```

**Step 3: Commit both files**

```bash
cd ~/code/ai-research-assistant
git add README-boris.md
git commit -m "docs: add stats command documentation

Document dashboard features and /morning integration.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

cd ~/Library/Mobile\ Documents/iCloud~md~obsidian/Documents/Bopvault
git add PKM-LifeOS/Setup/RSS_Feed_Automation.md
git commit -m "docs: update RSS automation with stats dashboard

Document stats command and morning skill integration.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Testing & Verification

**Manual Testing Commands:**

```bash
# Test stats CLI
cd ~/code/ai-research-assistant
uv run ai-research-assistant stats
uv run ai-research-assistant stats --json | python3 -m json.tool

# Test morning integration
/morning

# Verify daily note
cat _Daily/$(date +%Y-%m-%d).md | grep -A 20 "## RSS Pipeline"
```

**Expected Results:**
1. `stats` shows human-readable dashboard
2. `stats --json` returns valid JSON structure
3. `/morning` adds `## RSS Pipeline` section to daily note
4. Re-running `/morning` replaces section (idempotent)
5. Log file link works: `file:///Users/boris.diebold/code/ai-research-assistant/logs/pipeline.log`
6. No runs → shows "No runs yet" message with next steps
7. Errors handled gracefully (missing log file, empty database, etc.)

---

## Summary

**4 tasks total:**
1. Add 4 helper functions to `main.py`
2. Add `stats` CLI command
3. Update `/morning` SKILL.md with Step 5.6
4. Update documentation (README-boris.md, RSS_Feed_Automation.md)

**Prerequisites (from Phase 1):**
- ✅ `Database.get_pipeline_run_details()` method
- ✅ `Database.format_timestamp()` utility
- ✅ Log buffering fixes (sys.stdout.flush)

**Simplified from original plan:**
- No `StatsCollector` class
- No pytest test suite
- All code in `main.py`
- Test via manual CLI + integration testing
