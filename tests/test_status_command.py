"""Tests for status command with --last-run flag."""
import tempfile
from pathlib import Path
from click.testing import CliRunner


def test_status_last_run_no_runs():
    """status --last-run should show message when no runs exist."""
    from src.database import Database
    from src.main import cli

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)

        # Override get_db to use test database
        import src.main
        original_get_db = src.main.get_db
        src.main.get_db = lambda: db

        try:
            runner = CliRunner()
            result = runner.invoke(cli, ['status', '--last-run'])

            assert result.exit_code == 0
            assert "No pipeline runs found" in result.output
        finally:
            src.main.get_db = original_get_db


def test_status_last_run_with_completed_run():
    """status --last-run should show comprehensive report of last run."""
    from src.database import Database
    from src.main import cli

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)

        # Create a feed
        db.execute(
            "INSERT INTO feeds (url, title, category) VALUES (?, ?, ?)",
            ("https://example.com/feed", "Test Feed", "articles"),
        )
        db.commit()

        # Create a completed run with processed entries
        run_id = db.record_run_start()

        # Add processed entries with different destinations
        db.mark_processed(
            entry_guid="guid-1",
            feed_id=1,
            entry_url="https://example.com/article1",
            entry_title="Article in Knowledge",
            note_path=Path("/vault/Knowledge/AI-Engineering/article1.md"),
        )
        db.mark_processed(
            entry_guid="guid-2",
            feed_id=1,
            entry_url="https://example.com/article2",
            entry_title="Article in Clippings",
            note_path=Path("/vault/Clippings/Articles/article2.md"),
        )
        db.mark_processed(
            entry_guid="guid-3",
            feed_id=1,
            entry_url="https://example.com/article3",
            entry_title="Discarded Article",
            note_path=Path("/vault/Discarded/article3.md"),
        )

        db.record_run_complete(run_id, processed=3, failed=0)

        # Override get_db to use test database
        import src.main
        original_get_db = src.main.get_db
        src.main.get_db = lambda: db

        try:
            runner = CliRunner()
            result = runner.invoke(cli, ['status', '--last-run'])

            assert result.exit_code == 0

            # Check header is present
            assert "Last Run:" in result.output
            assert "Status:" in result.output

            # Check summary section
            assert "Summary:" in result.output
            assert "Processed: 3 items" in result.output
            assert "Failed: 0" in result.output

            # Check items processed section
            assert "Items Processed:" in result.output
            assert "Article in Knowledge" in result.output
            assert "Article in Clippings" in result.output
            assert "Discarded Article" in result.output

            # Check destinations are shown
            assert "→ AI-Engineering/" in result.output
            assert "→ Clippings/" in result.output
            assert "→ Discarded" in result.output
        finally:
            src.main.get_db = original_get_db


def test_status_last_run_with_failed_items():
    """status --last-run should show failed items with errors."""
    from src.database import Database
    from src.main import cli

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)

        # Create a feed
        db.execute(
            "INSERT INTO feeds (url, title, category) VALUES (?, ?, ?)",
            ("https://example.com/feed", "Test Feed", "articles"),
        )
        db.commit()

        # Create a run with failed item
        run_id = db.record_run_start()

        # Add a failed item
        db.add_to_retry_queue(
            entry_guid="guid-failed",
            feed_id=1,
            entry_url="https://example.com/failed",
            entry_title="Failed Article",
            category="articles",
            error="Network timeout",
        )

        db.record_run_complete(run_id, processed=0, failed=1)

        # Override get_db to use test database
        import src.main
        original_get_db = src.main.get_db
        src.main.get_db = lambda: db

        try:
            runner = CliRunner()
            result = runner.invoke(cli, ['status', '--last-run'])

            assert result.exit_code == 0

            # Check failed items section
            assert "Failed Items:" in result.output
            assert "Failed Article" in result.output
            assert "Error: Network timeout" in result.output
        finally:
            src.main.get_db = original_get_db


def test_status_watch_not_implemented_message():
    """status --watch should show not implemented message in Task 3."""
    from src.database import Database
    from src.main import cli

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)

        # Override get_db to use test database
        import src.main
        original_get_db = src.main.get_db
        src.main.get_db = lambda: db

        try:
            runner = CliRunner()
            result = runner.invoke(cli, ['status', '--watch'])

            assert result.exit_code == 0
            assert "Watch mode not yet implemented" in result.output
        finally:
            src.main.get_db = original_get_db
