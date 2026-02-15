# Morning Dashboard Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build on monitoring improvements to add comprehensive RSS dashboard integrated into `/morning` skill with stats, trends, health alerts, and recommendations.

**Architecture:** Create `StatsCollector` class that uses existing database query methods from monitoring improvements → new `stats` CLI subcommand outputs JSON/text → `/morning` skill calls it and formats output into daily note `## RSS Pipeline` section.

**Tech Stack:** Python 3.11+, Click (CLI), SQLite3, regex (log parsing), pytest (testing)

**Prerequisites:** Must complete `2026-02-14-rss-monitoring-improvements-plan.md` first - this plan depends on:
- `Database.get_pipeline_run_details()` method
- `Database.format_timestamp()` utility
- Log buffering fixes (sys.stdout.flush)

---

## Task 1: Create StatsCollector Class

**Files:**
- Create: `src/stats_collector.py`
- Create: `tests/test_stats_collector.py`

**Step 1: Write failing test for StatsCollector**

Create `tests/test_stats_collector.py`:

```python
import pytest
from pathlib import Path
from datetime import datetime, timedelta

from src.stats_collector import StatsCollector
from src.database import Database


@pytest.fixture
def temp_db(tmp_path):
    """Create temporary database with test data."""
    db_path = tmp_path / "test.db"
    db = Database(db_path)

    # Insert test pipeline_runs
    now = datetime.now()
    db.execute(
        """INSERT INTO pipeline_runs
           (started_at, completed_at, items_processed, items_failed, status)
           VALUES (?, ?, ?, ?, ?)""",
        (now - timedelta(hours=1), now, 5, 1, 'completed')
    )
    db.commit()

    yield db
    db.close()


def test_stats_collector_init(temp_db):
    """Test StatsCollector initialization."""
    collector = StatsCollector(temp_db)
    assert collector.db == temp_db
```

**Step 2: Run test to verify it fails**

Run: `cd ~/code/ai-research-assistant && pytest tests/test_stats_collector.py::test_stats_collector_init -v`
Expected: FAIL with "No module named 'src.stats_collector'"

**Step 3: Create minimal StatsCollector class**

Create `src/stats_collector.py`:

```python
"""Statistics collector for pipeline monitoring dashboard."""
from pathlib import Path
from src.database import Database


class StatsCollector:
    """Collect and format pipeline statistics for dashboard display."""

    def __init__(self, db: Database, log_dir: Path | None = None):
        """Initialize collector.

        Args:
            db: Database instance
            log_dir: Optional log directory path (defaults to project logs/)
        """
        self.db = db
        self.log_dir = log_dir or Path(__file__).parent.parent / "logs"
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_stats_collector.py::test_stats_collector_init -v`
Expected: PASS

**Step 5: Commit**

```bash
cd ~/code/ai-research-assistant
git add src/stats_collector.py tests/test_stats_collector.py
git commit -m "feat(stats): add StatsCollector class skeleton

Foundation for dashboard metrics collection.
Leverages existing Database methods from monitoring improvements.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Add 7-Day Trends Calculation

**Files:**
- Modify: `src/stats_collector.py`
- Modify: `tests/test_stats_collector.py`

**Step 1: Write failing test for get_trends**

Add to `tests/test_stats_collector.py`:

```python
def test_get_trends(temp_db):
    """Test 7-day trend calculation with comparison."""
    # Insert data for last 14 days
    now = datetime.now()
    for i in range(14):
        day_offset = timedelta(days=i)
        items = 3 if i < 7 else 2  # More items in recent week
        temp_db.execute(
            """INSERT INTO pipeline_runs
               (started_at, completed_at, items_processed, items_failed, status)
               VALUES (?, ?, ?, ?, ?)""",
            (now - day_offset - timedelta(hours=1), now - day_offset, items, 0, 'completed')
        )
    temp_db.commit()

    collector = StatsCollector(temp_db)
    trends = collector.get_trends(days=7)

    assert trends["last_7_days"]["total_processed"] == 21  # 7 * 3
    assert trends["previous_7_days"]["total_processed"] == 14  # 7 * 2
    assert "comparison" in trends
    assert "+" in trends["comparison"]  # Should show increase
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_stats_collector.py::test_get_trends -v`
Expected: FAIL with "AttributeError: 'StatsCollector' object has no attribute 'get_trends'"

**Step 3: Implement get_trends method**

Add to `src/stats_collector.py`:

```python
def get_trends(self, days: int = 7) -> dict:
    """Calculate trends comparing last N days to previous N days.

    Args:
        days: Number of days to analyze (default: 7)

    Returns:
        Dict with recent stats, previous stats, and percentage comparison
    """
    # Last N days
    cursor_recent = self.db.execute(
        """SELECT SUM(items_processed) as total, SUM(items_failed) as failed
           FROM pipeline_runs
           WHERE status = 'completed'
             AND completed_at >= datetime('now', ? || ' days')""",
        (f'-{days}',)
    )
    recent = cursor_recent.fetchone()

    # Previous N days (for comparison)
    cursor_previous = self.db.execute(
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

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_stats_collector.py::test_get_trends -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/stats_collector.py tests/test_stats_collector.py
git commit -m "feat(stats): add 7-day trends with week-over-week comparison

Calculates totals and generates comparison string with arrow indicators.
Foundation for trend display in dashboard.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Add Performance Metrics from Logs

**Files:**
- Modify: `src/stats_collector.py`
- Modify: `tests/test_stats_collector.py`

**Step 1: Write failing test for parse_performance**

Add to `tests/test_stats_collector.py`:

```python
def test_parse_performance(tmp_path):
    """Test performance metric extraction from logs."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_file = log_dir / "pipeline.log"

    # Write test log data
    log_file.write_text("""
[16:50:23]   ✓ Created: article1.md (66.1s)
[16:51:29]   ✓ Created: article2.md (102.7s)
[16:53:17]   ✓ Created: article3.md (107.6s)
""")

    db_path = tmp_path / "test.db"
    db = Database(db_path)
    collector = StatsCollector(db, log_dir)

    perf = collector.parse_performance()

    assert perf["avg_seconds_per_article"] == pytest.approx(92.13, rel=0.1)
    assert perf["slowest"]["title"] == "article3.md"
    assert perf["slowest"]["duration"] == 107.6
    assert perf["fastest"]["title"] == "article1.md"
    assert perf["fastest"]["duration"] == 66.1

    db.close()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_stats_collector.py::test_parse_performance -v`
Expected: FAIL with "AttributeError: 'StatsCollector' object has no attribute 'parse_performance'"

**Step 3: Implement parse_performance method**

Add to `src/stats_collector.py`:

```python
import re

def parse_performance(self) -> dict:
    """Parse performance metrics from latest log file.

    Returns:
        Dict with avg time, slowest/fastest articles (or None if no log data)
    """
    log_file = self.log_dir / "pipeline.log"

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

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_stats_collector.py::test_parse_performance -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/stats_collector.py tests/test_stats_collector.py
git commit -m "feat(stats): add log parsing for performance metrics

Extracts per-article timing from pipeline.log.
Calculates avg, identifies slowest/fastest articles.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Add Health Check Logic

**Files:**
- Modify: `src/stats_collector.py`
- Modify: `tests/test_stats_collector.py`

**Step 1: Write failing test for calculate_health**

Add to `tests/test_stats_collector.py`:

```python
def test_calculate_health_warnings(temp_db):
    """Test health checks with warning conditions."""
    from datetime import datetime, timedelta

    # Insert old run (>24h ago) with high failure rate
    old_time = datetime.now() - timedelta(hours=30)
    temp_db.execute(
        """INSERT INTO pipeline_runs
           (started_at, completed_at, items_processed, items_failed, status)
           VALUES (?, ?, ?, ?, ?)""",
        (old_time - timedelta(hours=1), old_time, 8, 2, 'completed')  # 20% failure rate
    )
    temp_db.commit()

    collector = StatsCollector(temp_db)
    health = collector.calculate_health()

    assert health["status"] in ["warning", "error"]
    assert len(health["alerts"]) >= 1
    # Should have alert about stale run
    assert any("24 hours" in alert or "48 hours" in alert for alert in health["alerts"])
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_stats_collector.py::test_calculate_health_warnings -v`
Expected: FAIL with "AttributeError: 'StatsCollector' object has no attribute 'calculate_health'"

**Step 3: Implement calculate_health method**

Add to `src/stats_collector.py`:

```python
from datetime import datetime

def calculate_health(self) -> dict:
    """Check pipeline health and generate alerts.

    Returns:
        Dict with overall status and list of alert strings
    """
    alerts = []

    # Use existing get_pipeline_run_details from monitoring improvements
    last_run = self.db.get_pipeline_run_details()

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
    perf = self.parse_performance()
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

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_stats_collector.py::test_calculate_health_warnings -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/stats_collector.py tests/test_stats_collector.py
git commit -m "feat(stats): add health check with warning/error detection

Checks: stale runs, failure rate, processing speed.
Returns status (healthy/warning/error) with alert list.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Add Recommendation Engine

**Files:**
- Modify: `src/stats_collector.py`
- Modify: `tests/test_stats_collector.py`

**Step 1: Write failing test for generate_recommendations**

Add to `tests/test_stats_collector.py`:

```python
def test_generate_recommendations(temp_db, tmp_path):
    """Test recommendation generation."""
    # Setup slow article in logs
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "pipeline.log").write_text("""
[16:50:23]   ✓ Created: slow-article.md (125.0s)
""")

    collector = StatsCollector(temp_db, log_dir)
    recs = collector.generate_recommendations()

    assert len(recs) > 0
    assert len(recs) <= 5  # Max 5 recommendations
    assert any("slow" in rec.lower() for rec in recs)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_stats_collector.py::test_generate_recommendations -v`
Expected: FAIL with "AttributeError: 'StatsCollector' object has no attribute 'generate_recommendations'"

**Step 3: Implement generate_recommendations method**

Add to `src/stats_collector.py`:

```python
def generate_recommendations(self) -> list[str]:
    """Generate actionable recommendations based on metrics.

    Returns:
        List of recommendation strings (max 5)
    """
    recommendations = []

    # Check performance
    perf = self.parse_performance()
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
    health = self.calculate_health()
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

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_stats_collector.py::test_generate_recommendations -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/stats_collector.py tests/test_stats_collector.py
git commit -m "feat(stats): add recommendation engine (max 5 items)

Generates actionable suggestions based on performance and health.
Priority-sorted, capped at 5 recommendations.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Add Main collect_stats Method

**Files:**
- Modify: `src/stats_collector.py`
- Modify: `tests/test_stats_collector.py`

**Step 1: Write failing test for collect_stats**

Add to `tests/test_stats_collector.py`:

```python
def test_collect_stats_full(temp_db, tmp_path):
    """Test full stats collection."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "pipeline.log").write_text("""
[16:50:23]   ✓ Created: article1.md (85.2s)
""")

    # Insert test run
    now = datetime.now()
    temp_db.execute(
        """INSERT INTO pipeline_runs
           (started_at, completed_at, items_processed, items_failed, status)
           VALUES (?, ?, ?, ?, ?)""",
        (now - timedelta(hours=1), now, 5, 1, 'completed')
    )
    temp_db.commit()

    collector = StatsCollector(temp_db, log_dir)
    stats = collector.collect_stats(days=7)

    assert "last_run" in stats
    assert "trends" in stats
    assert "performance" in stats
    assert "health" in stats
    assert "recommendations" in stats
    assert stats["last_run"]["items_processed"] == 5
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_stats_collector.py::test_collect_stats_full -v`
Expected: FAIL with "AttributeError: 'StatsCollector' object has no attribute 'collect_stats'"

**Step 3: Implement collect_stats method**

Add to `src/stats_collector.py`:

```python
def collect_stats(self, days: int = 7) -> dict:
    """Collect all statistics for dashboard display.

    Args:
        days: Number of days for trend analysis

    Returns:
        Complete stats dict with all metrics
    """
    return {
        "last_run": self.db.get_pipeline_run_details(),  # From monitoring improvements
        "trends": self.get_trends(days),
        "performance": self.parse_performance(),
        "health": self.calculate_health(),
        "recommendations": self.generate_recommendations()
    }
```

**Step 4: Run all tests**

Run: `pytest tests/test_stats_collector.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/stats_collector.py tests/test_stats_collector.py
git commit -m "feat(stats): add collect_stats main method

Aggregates all metrics into single structure.
Ready for CLI command integration.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Add Stats CLI Command

**Files:**
- Modify: `src/main.py`

**Step 1: Add stats command after status command**

Add after the `status` command (around line 87):

```python
@cli.command()
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON for /morning skill')
@click.option('--days', '-d', type=int, default=7, help='Number of days to analyze')
def stats(output_json: bool, days: int):
    """Show comprehensive pipeline statistics and health dashboard.

    Use --json for machine-readable output (consumed by /morning skill).
    """
    from src.config import get_project_dir
    from src.stats_collector import StatsCollector
    import json as json_module

    db = get_db()
    log_dir = get_project_dir() / "logs"
    collector = StatsCollector(db, log_dir)

    data = collector.collect_stats(days=days)

    if output_json:
        # JSON output for /morning skill consumption
        click.echo(json_module.dumps(data, indent=2, default=str))
    else:
        # Human-readable terminal output
        from src.database import format_timestamp

        if data["last_run"]:
            lr = data["last_run"]
            click.echo(f"Last run: {format_timestamp(lr['completed_at'])}")
            click.echo(f"  Processed: {lr['items_processed']}, Failed: {lr['items_failed']}")
            click.echo()
        else:
            click.echo("No runs yet\n")

        # Trends
        trends = data["trends"]
        click.echo(f"7-day trend: {trends['comparison']}")
        click.echo(f"  Recent: {trends['last_7_days']['total_processed']} items")
        click.echo(f"  Previous: {trends['previous_7_days']['total_processed']} items")
        click.echo()

        # Performance
        perf = data["performance"]
        if perf["avg_seconds_per_article"] > 0:
            click.echo("Performance:")
            click.echo(f"  Avg: {perf['avg_seconds_per_article']:.0f}s/article")
            if perf["slowest"]:
                click.echo(f"  Slowest: {perf['slowest']['title']} ({perf['slowest']['duration']:.0f}s)")
            click.echo()

        # Health
        health = data["health"]
        status_emoji = {"healthy": "✅", "warning": "⚠️", "error": "❌"}
        click.echo(f"Health: {status_emoji.get(health['status'], '?')} {health['status'].capitalize()}")
        if health["alerts"]:
            for alert in health["alerts"]:
                click.echo(f"  {alert}")
            click.echo()

        # Recommendations
        if data["recommendations"]:
            click.echo("Recommendations:")
            for i, rec in enumerate(data["recommendations"], 1):
                click.echo(f"  {i}. {rec}")
```

**Step 2: Test stats command**

Run: `cd ~/code/ai-research-assistant && uv run ai-research-assistant stats`

Expected: Shows human-readable dashboard

**Step 3: Test JSON output**

Run: `cd ~/code/ai-research-assistant && uv run ai-research-assistant stats --json | jq .`

Expected: Valid JSON structure

**Step 4: Commit**

```bash
git add src/main.py
git commit -m "feat(cli): add stats command with JSON output

Provides human-readable dashboard for terminal use.
JSON mode for /morning skill consumption.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Update Morning Skill Integration

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

**Format template:**

```markdown
## RSS Pipeline

**Last run:** YYYY-MM-DD HH:MM ([logs](file:///Users/boris.diebold/code/ai-research-assistant/logs/pipeline.log))

**Processing:**
- ✓ X articles processed (YYs avg, ZZZs total)
- ✗ N failed (retry scheduled)

**7-day trend:** ↑/↓/→ comparison text

**Performance:**
- Avg: XXs/article
- Slowest: "Title" (XXs)

**Health:** ✅/⚠️/❌ Status
[alerts if present, one per line]

**Recommendations:**
1. [Recommendation]
[max 5, skip if empty]
```

**No runs yet template:**

```markdown
## RSS Pipeline

**Status:** No runs yet — first automated run scheduled for 04:00 tomorrow

**Next steps:**
1. Verify launchd: `launchctl list | grep ai-research-assistant`
2. Test: `uv run ai-research-assistant run --dry-run`
```

**Error handling:**
- `which` fails → skip step silently
- `stats --json` fails → skip with terminal message only
- JSON parse fails → skip with terminal message only
```

**Step 2: Update Step 7 summary**

Find Step 7 and update to include RSS line:

```markdown
✓ Morning complete
- Calendar: X meetings, Y focus blocks
- Todoist: X due today, Y overdue
- Clippings: X evaluated
- RSS: X processed, Y failed ← NEW
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

## Task 9: Update Documentation

**Files:**
- Modify: `~/code/ai-research-assistant/README-boris.md`

**Step 1: Add Stats Command section**

Add after existing monitoring commands:

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
- Last run summary
- 7-day trends with comparison
- Performance metrics (avg time, slowest article)
- Health status with alerts
- Actionable recommendations (max 5)

**Integrated with /morning:** RSS pipeline section automatically added to daily note.
```

**Step 2: Commit**

```bash
cd ~/code/ai-research-assistant
git add README-boris.md
git commit -m "docs: add stats command documentation

Document dashboard features and /morning integration.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 10: Integration Testing

**Files:**
- None (testing only)

**Step 1: Test stats CLI standalone**

```bash
cd ~/code/ai-research-assistant
uv run ai-research-assistant stats
uv run ai-research-assistant stats --json | jq .
```

Expected: Dashboard shows, JSON validates

**Step 2: Test /morning integration**

Run: `/morning`

Expected: Daily note has `## RSS Pipeline` section with formatted dashboard

**Step 3: Test re-run idempotency**

Run: `/morning` again on same day

Expected: `## RSS Pipeline` section replaced (not duplicated)

**Step 4: Verify log file link**

Click the `([logs](file://...))` link in daily note

Expected: Opens pipeline.log in editor

**Step 5: Test with no runs**

Delete all runs from database temporarily:

```bash
sqlite3 ~/code/ai-research-assistant/data/pipeline.db "DELETE FROM pipeline_runs"
```

Run: `/morning`

Expected: Shows "No runs yet" message with next steps

**Step 6: Restore database and verify**

```bash
cd ~/code/ai-research-assistant
uv run ai-research-assistant run -n 2
```

Then run `/morning` again.

Expected: Full dashboard appears

---

## Summary

**10 tasks total:**
1. Create StatsCollector class skeleton
2. Add 7-day trends calculation
3. Add performance metrics from logs
4. Add health check logic
5. Add recommendation engine
6. Add main collect_stats method
7. Add stats CLI command
8. Update morning skill integration
9. Update documentation
10. Integration testing

**Prerequisites completed** (from monitoring improvements plan):
- ✅ `Database.get_pipeline_run_details()` method
- ✅ `Database.format_timestamp()` utility
- ✅ Log buffering fixes (sys.stdout.flush)

**Verification commands:**
```bash
# Test stats CLI
ai-research-assistant stats
ai-research-assistant stats --json | jq .

# Test morning integration
/morning

# Verify daily note
cat _Daily/$(date +%Y-%m-%d).md | grep -A 20 "## RSS Pipeline"
```
