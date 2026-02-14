"""CLI entry point for content pipeline."""
from datetime import datetime
from pathlib import Path

import click

from src.database import Database
from src.feed_manager import FeedManager


def get_db() -> Database:
    """Get database instance."""
    db_path = Path(__file__).parent.parent / "data" / "pipeline.db"
    return Database(db_path)


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
