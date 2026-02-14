"""CLI entry point for content pipeline."""
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import click

from src.database import Database
from src.feed_manager import FeedManager


def get_db() -> Database:
    """Get database instance."""
    db_path = Path(__file__).parent.parent / "data" / "pipeline.db"
    return Database(db_path)


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
    if not last_run["completed_at"]:
        alerts.append("⚠️ Last run incomplete or failed")
        return {"status": "error", "alerts": alerts}

    last_run_time = datetime.fromisoformat(last_run["completed_at"]).replace(tzinfo=ZoneInfo('UTC'))
    hours_since = (datetime.now(ZoneInfo('UTC')) - last_run_time).total_seconds() / 3600

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


def _generate_recommendations(db: Database, log_dir: Path, health: dict) -> list[str]:
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

    # Check health for issues (using passed-in health dict)
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


@click.group()
def cli():
    """AI Research Assistant - Import articles, videos, and podcasts to Obsidian."""
    pass


# === Pipeline Commands ===


@cli.command()
@click.option("--dry-run", is_flag=True, help="Show what would be processed without doing it")
@click.option("--limit", "-n", type=int, default=None, help="Limit number of items to process")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed progress during execution")
@click.option("--force", is_flag=True, help="Override pipeline lock if another run is in progress")
def run(dry_run: bool, limit: int | None, verbose: bool, force: bool):
    """Run the content pipeline."""
    import logging

    from src.config import get_project_dir, load_config
    from src.logging_config import setup_logging
    from src.pipeline import PipelineLockError, run_pipeline

    # Initialize logging
    config = load_config()
    log_dir = get_project_dir() / "logs"
    retention_days = config.get("logging", {}).get("retention_days", 30)
    setup_logging(log_dir, retention_days, verbose)
    logger = logging.getLogger(__name__)
    logger.info("ai-research-assistant starting")

    db = get_db()
    try:
        result = run_pipeline(db, dry_run=dry_run, limit=limit, verbose=verbose, force=force)
    except PipelineLockError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    click.echo(f"Processed: {result.processed}, Failed: {result.failed}")
    if result.retried:
        click.echo(f"Retried: {result.retried}")
    if result.skipped:
        click.echo(f"Skipped (dry run): {result.skipped}")


@cli.command()
@click.option('--last-run', is_flag=True, help='Show detailed report of last pipeline run')
@click.option('--date', type=str, default=None, help='Show run from specific date (YYYY-MM-DD)')
@click.option('--watch', is_flag=True, help='Watch current run in real-time (updates every 2s)')
def status(last_run: bool, date: str | None, watch: bool):
    """Show pipeline status: pending items, retry queue, last run."""
    from src.database import format_timestamp

    db = get_db()

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

                    # Get most recent processed entry for current item
                    recent_cursor = db.execute(
                        "SELECT entry_title FROM processed_entries WHERE processed_at >= ? ORDER BY processed_at DESC LIMIT 1",
                        (current_run['started_at'],)
                    )
                    recent_entry = recent_cursor.fetchone()
                    current_item = recent_entry['entry_title'] if recent_entry else 'Starting...'

                    # Get total items for progress ratio
                    total_items = current_run['items_fetched']

                    # Clear line and show progress
                    sys.stdout.write(f"\r[{format_timestamp(current_run['started_at'])}] Processing {current_item[:50]}... ({processed_count}/{total_items} items)")
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

    # Handle --date flag (not yet implemented)
    if date:
        click.echo("Date filtering not yet implemented")
        return

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
            from zoneinfo import ZoneInfo
            # Parse timestamps as UTC (SQLite CURRENT_TIMESTAMP returns UTC)
            completed_dt = datetime.fromisoformat(run_data['completed_at']).replace(tzinfo=ZoneInfo('UTC'))
            started_dt = datetime.fromisoformat(run_data['started_at']).replace(tzinfo=ZoneInfo('UTC'))
            duration = completed_dt - started_dt
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
                # Determine destination from note_path using pathlib for safe parsing
                note_path_str = entry.get('note_path', '')
                if note_path_str:
                    note_path = Path(note_path_str)
                    parts = note_path.parts

                    # Find destination based on path structure
                    if 'Knowledge' in parts:
                        # Get the folder after 'Knowledge/'
                        try:
                            knowledge_idx = parts.index('Knowledge')
                            if knowledge_idx + 1 < len(parts):
                                dest = f"→ {parts[knowledge_idx + 1]}/"
                            else:
                                dest = "→ Knowledge/"
                        except (ValueError, IndexError):
                            dest = "→ Knowledge/"
                    elif 'Discarded' in parts:
                        dest = "→ Discarded"
                    else:
                        dest = "→ Clippings/"
                else:
                    dest = "→ Unknown"

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
    fm = FeedManager(db)

    # Last run info
    last_run_time = db.get_last_successful_run()
    if last_run_time:
        click.echo(f"Last successful run: {last_run_time.strftime('%Y-%m-%d %H:%M')}")
    else:
        click.echo("No previous runs")

    # Pending items
    entries = fm.fetch_new_entries()
    click.echo(f"Pending items: {len(entries)}")

    # Retry queue
    retry_entries = db.get_retry_candidates()
    click.echo(f"In retry queue: {len(retry_entries)}")

    # Feed counts
    feeds = fm.list_feeds()
    by_category = {}
    for f in feeds:
        by_category[f.category] = by_category.get(f.category, 0) + 1
    click.echo(f"Feeds: {by_category}")


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
    recommendations = _generate_recommendations(db, log_dir, health=health)

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
            if lr['completed_at']:
                click.echo(f"Last run: {format_timestamp(lr['completed_at'])}")
                click.echo(f"  Processed: {lr['items_processed']}, Failed: {lr['items_failed']}")
            else:
                click.echo(f"Last run: In progress (started {format_timestamp(lr['started_at'])})")
            click.echo()
        else:
            click.echo("No runs yet\n")

        # Trends
        click.echo(f"{days}-day trend: {trends['comparison']}")
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


# === Feed Management Commands ===


@cli.group()
def feeds():
    """Manage feed subscriptions."""
    pass


@feeds.command("add")
@click.argument("url")
@click.option(
    "--category",
    "-c",
    type=click.Choice(["articles", "youtube", "podcasts"]),
    help="Feed category (auto-detected if not specified)",
)
def feeds_add(url: str, category: str | None):
    """Add a new feed subscription."""
    db = get_db()
    fm = FeedManager(db)

    try:
        feed = fm.add_feed(url, category)
        click.echo(f"Added: {feed.title} ({feed.category})")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)


@feeds.command("remove")
@click.argument("url")
def feeds_remove(url: str):
    """Remove a feed subscription."""
    db = get_db()
    fm = FeedManager(db)

    fm.remove_feed(url)
    click.echo(f"Removed: {url}")


@feeds.command("list")
@click.option(
    "--category",
    "-c",
    type=click.Choice(["articles", "youtube", "podcasts"]),
    help="Filter by category",
)
def feeds_list(category: str | None):
    """List all feed subscriptions."""
    db = get_db()
    fm = FeedManager(db)

    feed_list = fm.list_feeds(category)
    for feed in feed_list:
        click.echo(f"[{feed.category}] {feed.title}")
        click.echo(f"    {feed.url}")


@feeds.command("export")
@click.option(
    "--output",
    "-o",
    default="exports/feeds.opml",
    help="Output file path (default: exports/feeds.opml)",
)
def feeds_export(output: str):
    """Export feeds to OPML format."""
    db = get_db()
    fm = FeedManager(db)

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fm.export_opml(output_path)
    click.echo(f"Exported to: {output_path}")


@feeds.command("import")
@click.argument("opml_file", type=click.Path(exists=True))
def feeds_import(opml_file: str):
    """Import feeds from OPML file."""
    db = get_db()
    fm = FeedManager(db)

    count = fm.import_opml(Path(opml_file))
    click.echo(f"Imported {count} feeds")


from src.setup import setup  # noqa: E402

cli.add_command(setup)

if __name__ == "__main__":
    cli()
