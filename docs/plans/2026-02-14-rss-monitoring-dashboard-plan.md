# RSS Monitoring Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add comprehensive RSS pipeline monitoring dashboard integrated into `/morning` skill with stats, trends, health alerts, and actionable recommendations.

**Architecture:** Python `StatsCollector` class queries SQLite + parses logs → new `stats` CLI subcommand outputs JSON/text → `/morning` skill calls it and formats output into daily note `## RSS Pipeline` section.

**Tech Stack:** Python 3.11+, Click (CLI), SQLite3, regex (log parsing), pytest (testing)

---

## Task 1: Create StatsCollector Class with SQLite Queries

**Files:**
- Create: `src/stats_collector.py`
- Test: `tests/test_stats_collector.py`

**Step 1: Write failing test for StatsCollector initialization**

Create `tests/test_stats_collector.py`:

```python
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import pytest

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
    """Test StatsCollector can be initialized with database."""
    collector = StatsCollector(temp_db)
    assert collector.db == temp_db
```

**Step 2: Run test to verify it fails**

Run: `cd ~/code/ai-research-assistant && pytest tests/test_stats_collector.py::test_stats_collector_init -v`
Expected: FAIL with "No module named 'src.stats_collector'"

**Step 3: Write minimal StatsCollector class**

Create `src/stats_collector.py`:

```python
"""Statistics collector for pipeline monitoring."""
from pathlib import Path
from src.database import Database


class StatsCollector:
    """Collect pipeline statistics from database and logs."""

    def __init__(self, db: Database, log_dir: Path | None = None):
        """Initialize collector with database and optional log directory."""
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
git commit -m "feat: add StatsCollector class with init"
```

---

## Task 2: Implement Last Run Query

**Files:**
- Modify: `src/stats_collector.py`
- Modify: `tests/test_stats_collector.py`

**Step 1: Write failing test for get_last_run**

Add to `tests/test_stats_collector.py`:

```python
def test_get_last_run(temp_db):
    """Test fetching last completed run."""
    collector = StatsCollector(temp_db)
    last_run = collector.get_last_run()

    assert last_run is not None
    assert last_run["status"] == "completed"
    assert last_run["processed"] == 5
    assert last_run["failed"] == 1
    assert "timestamp" in last_run
    assert "duration_seconds" in last_run
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_stats_collector.py::test_get_last_run -v`
Expected: FAIL with "AttributeError: 'StatsCollector' object has no attribute 'get_last_run'"

**Step 3: Implement get_last_run method**

Add to `src/stats_collector.py`:

```python
from datetime import datetime

def get_last_run(self) -> dict | None:
    """Get last completed pipeline run."""
    cursor = self.db.execute(
        """SELECT started_at, completed_at, items_processed, items_failed, status
           FROM pipeline_runs
           WHERE status = 'completed'
           ORDER BY completed_at DESC LIMIT 1"""
    )
    row = cursor.fetchone()

    if not row:
        return None

    started = datetime.fromisoformat(row["started_at"])
    completed = datetime.fromisoformat(row["completed_at"])
    duration = (completed - started).total_seconds()

    return {
        "timestamp": row["completed_at"],
        "duration_seconds": duration,
        "processed": row["items_processed"],
        "failed": row["items_failed"],
        "status": row["status"]
    }
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_stats_collector.py::test_get_last_run -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/stats_collector.py tests/test_stats_collector.py
git commit -m "feat: add get_last_run query to StatsCollector"
```

---

## Task 3: Implement 7-Day Trends Query

**Files:**
- Modify: `src/stats_collector.py`
- Modify: `tests/test_stats_collector.py`

**Step 1: Write failing test for get_trends**

Add to `tests/test_stats_collector.py`:

```python
def test_get_trends(temp_db):
    """Test fetching 7-day trends with comparison."""
    # Insert more test data spanning 14 days
    now = datetime.now()
    for i in range(14):
        day_offset = timedelta(days=i)
        items = 3 if i < 7 else 2  # More items in recent 7 days
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
    assert "comparison_to_previous_week" in trends
    assert "+" in trends["comparison_to_previous_week"]  # Increase
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_stats_collector.py::test_get_trends -v`
Expected: FAIL with "AttributeError: 'StatsCollector' object has no attribute 'get_trends'"

**Step 3: Implement get_trends method**

Add to `src/stats_collector.py`:

```python
from datetime import timedelta

def get_trends(self, days: int = 7) -> dict:
    """Get trends for last N days compared to previous N days."""
    # Last N days
    cursor_recent = self.db.execute(
        """SELECT SUM(items_processed) as total, SUM(items_failed) as failed
           FROM pipeline_runs
           WHERE status = 'completed'
             AND completed_at >= datetime('now', ? || ' days')""",
        (f'-{days}',)
    )
    recent = cursor_recent.fetchone()

    # Previous N days
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

    # Calculate comparison
    if previous_total == 0:
        comparison = "N/A (no previous data)"
    else:
        pct_change = ((recent_total - previous_total) / previous_total) * 100
        if abs(pct_change) < 5:
            comparison = "→ (stable)"
        elif pct_change > 0:
            comparison = f"+{pct_change:.0f}%"
        else:
            comparison = f"{pct_change:.0f}%"

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
        "comparison_to_previous_week": comparison
    }
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_stats_collector.py::test_get_trends -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/stats_collector.py tests/test_stats_collector.py
git commit -m "feat: add 7-day trends with comparison"
```

---

## Task 4: Implement Log Parsing for Performance Metrics

**Files:**
- Modify: `src/stats_collector.py`
- Modify: `tests/test_stats_collector.py`

**Step 1: Write failing test for parse_performance**

Add to `tests/test_stats_collector.py`:

```python
def test_parse_performance(tmp_path):
    """Test parsing performance data from log file."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_file = log_dir / "pipeline.log"

    # Write test log data
    log_file.write_text("""
[16:50:23]   ✓ Created: article1.md (66.1s)
[16:51:29]   ✓ Created: article2.md (102.7s)
[16:53:17]   ✓ Created: article3.md (107.6s)
[16:57:20] Run complete (684.7s total, 5 processed, 0 failed)
""")

    db_path = tmp_path / "test.db"
    db = Database(db_path)
    collector = StatsCollector(db, log_dir)

    perf = collector.parse_performance()

    assert perf["avg_seconds_per_article"] == pytest.approx(92.13, rel=0.1)
    assert perf["slowest_article"]["title"] == "article3.md"
    assert perf["slowest_article"]["duration_seconds"] == 107.6
    assert perf["fastest_article"]["title"] == "article1.md"
    assert perf["fastest_article"]["duration_seconds"] == 66.1

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
    """Parse performance metrics from latest log file."""
    log_file = self.log_dir / "pipeline.log"

    if not log_file.exists():
        return {
            "avg_seconds_per_article": 0,
            "slowest_article": None,
            "fastest_article": None
        }

    # Read log file
    content = log_file.read_text()

    # Parse per-article timing
    pattern = r'✓ Created: (.+?\.md) \((\d+\.\d+)s\)'
    matches = re.findall(pattern, content)

    if not matches:
        return {
            "avg_seconds_per_article": 0,
            "slowest_article": None,
            "fastest_article": None
        }

    # Extract times
    articles = [(title, float(duration)) for title, duration in matches]
    articles.sort(key=lambda x: x[1])

    avg_time = sum(t[1] for t in articles) / len(articles)

    return {
        "avg_seconds_per_article": avg_time,
        "slowest_article": {
            "title": articles[-1][0],
            "duration_seconds": articles[-1][1]
        },
        "fastest_article": {
            "title": articles[0][0],
            "duration_seconds": articles[0][1]
        }
    }
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_stats_collector.py::test_parse_performance -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/stats_collector.py tests/test_stats_collector.py
git commit -m "feat: add log parsing for performance metrics"
```

---

## Task 5: Implement Health Checks and Alerts

**Files:**
- Modify: `src/stats_collector.py`
- Modify: `tests/test_stats_collector.py`

**Step 1: Write failing test for calculate_health**

Add to `tests/test_stats_collector.py`:

```python
def test_calculate_health_warnings(temp_db):
    """Test health check with warning conditions."""
    # Insert old run (>24h ago)
    old_time = datetime.now() - timedelta(hours=30)
    temp_db.execute(
        """INSERT INTO pipeline_runs
           (started_at, completed_at, items_processed, items_failed, status)
           VALUES (?, ?, ?, ?, ?)""",
        (old_time - timedelta(hours=1), old_time, 10, 2, 'completed')  # 20% failure rate
    )
    temp_db.commit()

    collector = StatsCollector(temp_db)
    health = collector.calculate_health()

    assert health["status"] == "warning"
    assert len(health["alerts"]) >= 1
    assert any("24 hours" in alert["message"] for alert in health["alerts"])
    assert any(alert["level"] == "warning" for alert in health["alerts"])
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_stats_collector.py::test_calculate_health_warnings -v`
Expected: FAIL with "AttributeError: 'StatsCollector' object has no attribute 'calculate_health'"

**Step 3: Implement calculate_health method**

Add to `src/stats_collector.py`:

```python
def calculate_health(self) -> dict:
    """Calculate health status with alerts."""
    alerts = []

    # Check last run time
    last_run = self.get_last_run()
    if last_run:
        last_run_time = datetime.fromisoformat(last_run["timestamp"])
        hours_since = (datetime.now() - last_run_time).total_seconds() / 3600

        if hours_since > 48:
            alerts.append({"level": "error", "message": "No successful run in 48 hours"})
        elif hours_since > 24:
            alerts.append({"level": "warning", "message": "No successful run in 24 hours"})

        # Check failure rate
        if last_run["processed"] + last_run["failed"] > 0:
            failure_rate = last_run["failed"] / (last_run["processed"] + last_run["failed"])
            if failure_rate > 0.25:
                alerts.append({"level": "error", "message": f"High failure rate: {failure_rate:.0%}"})
            elif failure_rate > 0.10:
                alerts.append({"level": "warning", "message": f"Elevated failure rate: {failure_rate:.0%}"})
    else:
        alerts.append({"level": "warning", "message": "No pipeline runs yet"})

    # Check average processing time
    perf = self.parse_performance()
    if perf["avg_seconds_per_article"] > 120:
        alerts.append({"level": "error", "message": f"Slow processing: {perf['avg_seconds_per_article']:.0f}s avg"})
    elif perf["avg_seconds_per_article"] > 90:
        alerts.append({"level": "warning", "message": f"Slow processing: {perf['avg_seconds_per_article']:.0f}s avg"})

    # Determine overall status
    if any(a["level"] == "error" for a in alerts):
        status = "error"
    elif any(a["level"] == "warning" for a in alerts):
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
git commit -m "feat: add health checks with warning/error alerts"
```

---

## Task 6: Implement Recommendation Engine

**Files:**
- Modify: `src/stats_collector.py`
- Modify: `tests/test_stats_collector.py`

**Step 1: Write failing test for generate_recommendations**

Add to `tests/test_stats_collector.py`:

```python
def test_generate_recommendations(temp_db, tmp_path):
    """Test recommendation generation based on metrics."""
    # Setup log with slow article
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "pipeline.log").write_text("""
[16:50:23]   ✓ Created: slow-article.md (125.0s)
""")

    collector = StatsCollector(temp_db, log_dir)
    recommendations = collector.generate_recommendations()

    assert len(recommendations) > 0
    assert any("slow" in rec.lower() for rec in recommendations)
    assert len(recommendations) <= 5  # Max 5 recommendations
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_stats_collector.py::test_generate_recommendations -v`
Expected: FAIL with "AttributeError: 'StatsCollector' object has no attribute 'generate_recommendations'"

**Step 3: Implement generate_recommendations method**

Add to `src/stats_collector.py`:

```python
def generate_recommendations(self) -> list[str]:
    """Generate actionable recommendations based on metrics."""
    recommendations = []

    # Check performance
    perf = self.parse_performance()
    if perf["avg_seconds_per_article"] > 90:
        recommendations.append(
            f"Consider feed prioritization or batching improvements — {perf['avg_seconds_per_article']:.0f}s avg processing time"
        )

    if perf["slowest_article"] and perf["slowest_article"]["duration_seconds"] > 120:
        title = perf["slowest_article"]["title"]
        duration = perf["slowest_article"]["duration_seconds"]
        recommendations.append(
            f"Investigate slow feed: {title} took {duration:.0f}s"
        )

    # Check health alerts
    health = self.calculate_health()
    for alert in health["alerts"]:
        if "No successful run" in alert["message"]:
            recommendations.append("Verify launchd job is running: launchctl list | grep ai-research-assistant")
            break

    # Limit to top 5
    return recommendations[:5]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_stats_collector.py::test_generate_recommendations -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/stats_collector.py tests/test_stats_collector.py
git commit -m "feat: add recommendation engine with max 5 items"
```

---

## Task 7: Implement Main collect_stats Method

**Files:**
- Modify: `src/stats_collector.py`
- Modify: `tests/test_stats_collector.py`

**Step 1: Write failing test for collect_stats**

Add to `tests/test_stats_collector.py`:

```python
def test_collect_stats_full(temp_db, tmp_path):
    """Test full stats collection returns complete structure."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "pipeline.log").write_text("""
[16:50:23]   ✓ Created: article1.md (85.2s)
[16:51:29]   ✓ Created: article2.md (92.1s)
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
    assert stats["last_run"]["processed"] == 5
    assert stats["health"]["status"] in ["healthy", "warning", "error"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_stats_collector.py::test_collect_stats_full -v`
Expected: FAIL with "AttributeError: 'StatsCollector' object has no attribute 'collect_stats'"

**Step 3: Implement collect_stats method**

Add to `src/stats_collector.py`:

```python
def collect_stats(self, days: int = 7) -> dict:
    """Collect all statistics and return structured data."""
    return {
        "last_run": self.get_last_run(),
        "trends": self.get_trends(days),
        "performance": self.parse_performance(),
        "health": self.calculate_health(),
        "recommendations": self.generate_recommendations()
    }
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_stats_collector.py::test_collect_stats_full -v`
Expected: PASS

**Step 5: Run all stats collector tests**

Run: `pytest tests/test_stats_collector.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add src/stats_collector.py tests/test_stats_collector.py
git commit -m "feat: add collect_stats main method"
```

---

## Task 8: Add Stats CLI Command

**Files:**
- Modify: `src/main.py`
- Create: `tests/test_stats_cli.py`

**Step 1: Write failing test for stats CLI**

Create `tests/test_stats_cli.py`:

```python
from click.testing import CliRunner
from pathlib import Path
import json

from src.main import cli
from src.database import Database


def test_stats_command_json(tmp_path):
    """Test stats command with JSON output."""
    # Setup temp database
    db_path = tmp_path / "pipeline.db"
    db = Database(db_path)

    from datetime import datetime, timedelta
    now = datetime.now()
    db.execute(
        """INSERT INTO pipeline_runs
           (started_at, completed_at, items_processed, items_failed, status)
           VALUES (?, ?, ?, ?, ?)""",
        (now - timedelta(hours=1), now, 5, 1, 'completed')
    )
    db.commit()
    db.close()

    # Mock get_db to use temp database
    import src.main
    original_get_db = src.main.get_db
    src.main.get_db = lambda: Database(db_path)

    runner = CliRunner()
    result = runner.invoke(cli, ['stats', '--json'])

    # Restore original
    src.main.get_db = original_get_db

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "last_run" in data
    assert "health" in data
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_stats_cli.py::test_stats_command_json -v`
Expected: FAIL with "Error: No such command 'stats'"

**Step 3: Add stats command to CLI**

Add to `src/main.py` after the `status` command:

```python
@cli.command()
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--days", "-d", type=int, default=7, help="Number of days to analyze")
def stats(output_json: bool, days: int):
    """Show pipeline statistics and health dashboard."""
    from src.config import get_project_dir
    from src.stats_collector import StatsCollector
    import json as json_module

    db = get_db()
    log_dir = get_project_dir() / "logs"
    collector = StatsCollector(db, log_dir)

    data = collector.collect_stats(days=days)

    if output_json:
        click.echo(json_module.dumps(data, indent=2))
    else:
        # Human-readable output
        if data["last_run"]:
            lr = data["last_run"]
            click.echo(f"Last run: {lr['timestamp']}")
            click.echo(f"  Processed: {lr['processed']}, Failed: {lr['failed']}")
            click.echo(f"  Duration: {lr['duration_seconds']:.1f}s")
        else:
            click.echo("No runs yet")

        click.echo(f"\nHealth: {data['health']['status'].upper()}")
        if data['health']['alerts']:
            for alert in data['health']['alerts']:
                click.echo(f"  [{alert['level']}] {alert['message']}")

        if data['recommendations']:
            click.echo("\nRecommendations:")
            for i, rec in enumerate(data['recommendations'], 1):
                click.echo(f"  {i}. {rec}")
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_stats_cli.py::test_stats_command_json -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/main.py tests/test_stats_cli.py
git commit -m "feat: add stats CLI command with JSON output"
```

---

## Task 9: Update Morning Skill with RSS Monitoring

**Files:**
- Modify: `Claude/skills-pkm/skills/morning/SKILL.md`

**Step 1: Read current morning skill**

Run: `cat Claude/skills-pkm/skills/morning/SKILL.md | head -50`

**Step 2: Add Step 5.6 to morning skill**

Insert after Step 5.5b (line ~140) in `Claude/skills-pkm/skills/morning/SKILL.md`:

```markdown
### Step 5.6: RSS Pipeline Monitoring

1. Check if ai-research-assistant is installed: `which ai-research-assistant`
2. If not found: skip with "RSS pipeline monitoring not available"
3. Call `ai-research-assistant stats --json --days 7`
4. Parse JSON response
5. Format as Markdown:
   - If no runs: show "No runs yet — first automated run scheduled for 04:00 tomorrow"
   - If runs exist: format full dashboard with last run, processing stats, trends, performance, health, recommendations
6. Append `## RSS Pipeline` section to daily note
   - Insert after `## Todoist` section, before `## Capture`
   - If section already exists (re-run), replace it
7. Print one-line summary to terminal: "RSS: X processed, Y failed, Z discarded"

**Format template for daily note:**

```markdown
## RSS Pipeline

**Last run:** YYYY-MM-DD HH:MM ([logs](file:///Users/boris.diebold/code/ai-research-assistant/logs/pipeline.log))

**Processing:**
- ✓ X articles processed (YYs avg, ZZZs total)
- ✗ N failed (retry scheduled)

**7-day trend:** ↑/↓/→ X% change (A vs B previous week)

**Performance:**
- Avg: XXs/article
- Range: XXs – YYs
- Slowest: "Title..." (XXs)

**Health:** ✅/⚠️/❌ Status
[alerts if present]

**Recommendations:**
1. [Recommendation 1]
2. [Recommendation 2]
[max 5]
```

**Error handling:**
- `which ai-research-assistant` fails → skip step
- `stats --json` fails → skip with error message
- JSON parse fails → skip with suggestion to run manually
- No runs in database → show "No runs yet" message
```

**Step 3: Update Step 7 summary format**

Find Step 7 in `SKILL.md` and update the template to include RSS line:

```markdown
✓ Morning complete
- Calendar: X meetings, Y focus blocks
- Todoist: X tasks due today, Y overdue
- Clippings: X evaluated → Knowledge/
- RSS: X processed, Y failed, Z discarded
- Daily note: Updated _Daily/YYYY-MM-DD.md
- Inbox: X/Y items triaged (Z remaining)
```

**Step 4: Commit**

```bash
cd ~/Library/Mobile\ Documents/iCloud~md~obsidian/Documents/Bopvault/Claude
git add skills-pkm/skills/morning/SKILL.md
git commit -m "feat: add RSS pipeline monitoring to /morning skill"
```

---

## Task 10: Integration Testing

**Files:**
- Create: `tests/test_morning_integration.py`

**Step 1: Write integration test**

Create `tests/test_morning_integration.py`:

```python
import subprocess
import json
from pathlib import Path


def test_stats_command_returns_valid_json():
    """Test that stats command returns valid JSON."""
    result = subprocess.run(
        ["ai-research-assistant", "stats", "--json"],
        capture_output=True,
        text=True
    )

    assert result.returncode == 0
    data = json.loads(result.stdout)

    # Verify structure
    assert "last_run" in data
    assert "trends" in data
    assert "performance" in data
    assert "health" in data
    assert "recommendations" in data

    # Verify health status is valid
    assert data["health"]["status"] in ["healthy", "warning", "error"]

    # Verify recommendations is a list with max 5 items
    assert isinstance(data["recommendations"], list)
    assert len(data["recommendations"]) <= 5
```

**Step 2: Run test**

Run: `pytest tests/test_morning_integration.py -v`
Expected: PASS (if ai-research-assistant has run data) or SKIP (if no data yet)

**Step 3: Manual testing**

```bash
# Test stats CLI
cd ~/code/ai-research-assistant
uv run ai-research-assistant stats
uv run ai-research-assistant stats --json
uv run ai-research-assistant stats --days 14

# Test morning integration
/morning
```

**Step 4: Commit**

```bash
cd ~/code/ai-research-assistant
git add tests/test_morning_integration.py
git commit -m "test: add integration test for stats command"
```

---

## Task 11: Update Documentation

**Files:**
- Modify: `README.md`

**Step 1: Add stats command documentation**

Add new section after "Commands" in `README.md`:

```markdown
## Monitoring

```bash
# View pipeline statistics
ai-research-assistant stats                  # Human-readable dashboard
ai-research-assistant stats --json           # JSON output (for /morning skill)
ai-research-assistant stats --days 14        # Analyze last 14 days

# Integrated into /morning skill
/morning                                     # Includes RSS pipeline monitoring
```

The stats dashboard shows:
- Last run timestamp with link to logs
- Processing metrics (articles processed, failed, discarded)
- 7-day trends with week-over-week comparison
- Performance data (average time, slowest article)
- Health alerts (stale runs, high failure rates)
- Actionable recommendations

**Morning Integration:** The `/morning` skill automatically checks RSS pipeline health and surfaces issues in your daily note.
```

**Step 2: Commit**

```bash
cd ~/code/ai-research-assistant
git add README.md
git commit -m "docs: add stats command and monitoring documentation"
```

---

## Task 12: Final Verification and Push

**Files:**
- All modified files

**Step 1: Run full test suite**

Run: `cd ~/code/ai-research-assistant && pytest -v`
Expected: All tests PASS

**Step 2: Test with real data**

```bash
# Generate fresh stats
uv run ai-research-assistant stats

# Test JSON output
uv run ai-research-assistant stats --json | jq .

# Test morning integration
/morning
```

**Step 3: Verify daily note has RSS Pipeline section**

Read today's daily note and verify `## RSS Pipeline` section exists with correct format.

**Step 4: Push to GitHub**

```bash
cd ~/code/ai-research-assistant
git log --oneline -12  # Verify all commits

git push origin boris-pkm-integration
```

**Step 5: Verify in vault**

```bash
cd ~/Library/Mobile\ Documents/iCloud~md~obsidian/Documents/Bopvault/Claude
git log --oneline -3  # Verify morning skill commit

git push origin main
```

---

## Summary

**12 tasks total:**
1. Create StatsCollector class with SQLite queries
2. Implement last run query
3. Implement 7-day trends query
4. Implement log parsing for performance metrics
5. Implement health checks and alerts
6. Implement recommendation engine
7. Implement main collect_stats method
8. Add stats CLI command
9. Update morning skill with RSS monitoring
10. Integration testing
11. Update documentation
12. Final verification and push

**Verification commands:**
```bash
# Test stats CLI
ai-research-assistant stats
ai-research-assistant stats --json | jq .

# Test morning integration
/morning

# Check daily note for RSS Pipeline section
cat _Daily/$(date +%Y-%m-%d).md
```
