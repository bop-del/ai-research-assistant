"""Tests for database module."""
import tempfile
from pathlib import Path


def test_database_creates_tables():
    """Database should create all required tables on init."""
    from src.database import Database

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)

        # Check tables exist
        tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = {row[0] for row in tables}

        assert "feeds" in table_names
        assert "processed_entries" in table_names
        assert "retry_queue" in table_names
        assert "pipeline_runs" in table_names


def test_is_processed_returns_false_for_new_entry():
    """is_processed should return False for entries not in database."""
    from src.database import Database

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)

        assert db.is_processed("some-guid-123") is False


def test_mark_processed_and_is_processed():
    """mark_processed should make is_processed return True."""
    from src.database import Database

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)

        # First add a feed
        db.execute(
            "INSERT INTO feeds (url, title, category) VALUES (?, ?, ?)",
            ("https://example.com/feed", "Test Feed", "articles"),
        )
        db.commit()

        # Mark entry as processed
        db.mark_processed(
            entry_guid="guid-123",
            feed_id=1,
            entry_url="https://example.com/article",
            entry_title="Test Article",
            note_path=Path("/vault/Clippings/test.md"),
        )

        assert db.is_processed("guid-123") is True


def test_record_run_start_and_complete():
    """Pipeline run should be trackable from start to completion."""
    from src.database import Database

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)

        # Start a run
        run_id = db.record_run_start()
        assert run_id == 1

        # Complete the run
        db.record_run_complete(run_id, processed=5, failed=1)

        # Verify
        row = db.execute("SELECT * FROM pipeline_runs WHERE id = ?", (run_id,)).fetchone()
        assert row["status"] == "completed"
        assert row["items_processed"] == 5
        assert row["items_failed"] == 1


def test_get_last_successful_run():
    """get_last_successful_run should return timestamp of last completed run."""
    from src.database import Database

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)

        # No runs yet
        assert db.get_last_successful_run() is None

        # Add a completed run
        run_id = db.record_run_start()
        db.record_run_complete(run_id, processed=3, failed=0)

        # Should now have a timestamp
        last_run = db.get_last_successful_run()
        assert last_run is not None


def test_add_to_retry_queue_and_get_candidates():
    """Failed entries should be added to retry queue with backoff."""
    from src.database import Database

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)

        # Add a feed first
        db.execute(
            "INSERT INTO feeds (url, title, category) VALUES (?, ?, ?)",
            ("https://example.com/feed", "Test Feed", "articles"),
        )
        db.commit()

        # Add to retry queue
        db.add_to_retry_queue(
            entry_guid="guid-456",
            feed_id=1,
            entry_url="https://example.com/article",
            entry_title="Failed Article",
            category="articles",
            error="Connection timeout",
        )

        # Should not be immediately available (1 hour backoff)
        candidates = db.get_retry_candidates()
        assert len(candidates) == 0

        # Manually set next_retry to now for testing
        db.execute(
            "UPDATE retry_queue SET next_retry_at = CURRENT_TIMESTAMP WHERE entry_guid = ?",
            ("guid-456",),
        )
        db.commit()

        # Now should be available
        candidates = db.get_retry_candidates()
        assert len(candidates) == 1
        assert candidates[0]["entry_guid"] == "guid-456"


def test_get_pipeline_run_details_no_runs():
    """get_pipeline_run_details should return None when no runs exist."""
    from src.database import Database

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)

        result = db.get_pipeline_run_details()
        assert result is None


def test_get_pipeline_run_details_most_recent():
    """get_pipeline_run_details should return most recent run by default."""
    from src.database import Database
    import time

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)

        # Create a feed for processed entries
        db.execute(
            "INSERT INTO feeds (url, title, category) VALUES (?, ?, ?)",
            ("https://example.com/feed", "Test Feed", "articles"),
        )
        db.commit()

        # Create two runs with time separation to ensure distinct timestamps
        run_id_1 = db.record_run_start()
        db.mark_processed(
            entry_guid="guid-1",
            feed_id=1,
            entry_url="https://example.com/article1",
            entry_title="Article 1",
            note_path=Path("/vault/Clippings/article1.md"),
        )
        db.record_run_complete(run_id_1, processed=1, failed=0)

        # Sleep to ensure second run has different timestamps
        time.sleep(1)

        run_id_2 = db.record_run_start()
        db.mark_processed(
            entry_guid="guid-2",
            feed_id=1,
            entry_url="https://example.com/article2",
            entry_title="Article 2",
            note_path=Path("/vault/Knowledge/AI/article2.md"),
        )
        db.record_run_complete(run_id_2, processed=1, failed=0)

        # Should return most recent run (run_id_2)
        result = db.get_pipeline_run_details()
        assert result is not None
        assert result['id'] == run_id_2
        assert result['status'] == 'completed'
        assert result['items_processed'] == 1
        assert result['items_failed'] == 0
        assert len(result['entries']) == 1
        assert result['entries'][0]['entry_title'] == 'Article 2'


def test_get_pipeline_run_details_specific_run():
    """get_pipeline_run_details should return specific run when run_id provided."""
    from src.database import Database

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)

        # Create a feed
        db.execute(
            "INSERT INTO feeds (url, title, category) VALUES (?, ?, ?)",
            ("https://example.com/feed", "Test Feed", "articles"),
        )
        db.commit()

        # Create first run
        run_id_1 = db.record_run_start()
        db.mark_processed(
            entry_guid="guid-old",
            feed_id=1,
            entry_url="https://example.com/old",
            entry_title="Old Article",
            note_path=Path("/vault/Clippings/old.md"),
        )
        db.record_run_complete(run_id_1, processed=1, failed=0)

        # Create second run
        run_id_2 = db.record_run_start()
        db.record_run_complete(run_id_2, processed=0, failed=0)

        # Request first run specifically
        result = db.get_pipeline_run_details(run_id=run_id_1)
        assert result is not None
        assert result['id'] == run_id_1
        assert result['items_processed'] == 1
        assert len(result['entries']) == 1
        assert result['entries'][0]['entry_title'] == 'Old Article'


def test_get_pipeline_run_details_with_failed_items():
    """get_pipeline_run_details should include failed items from retry queue."""
    from src.database import Database

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)

        # Create a feed
        db.execute(
            "INSERT INTO feeds (url, title, category) VALUES (?, ?, ?)",
            ("https://example.com/feed", "Test Feed", "articles"),
        )
        db.commit()

        # Start a run
        run_id = db.record_run_start()

        # Add a failed item to retry queue during the run
        db.add_to_retry_queue(
            entry_guid="guid-failed",
            feed_id=1,
            entry_url="https://example.com/failed",
            entry_title="Failed Article",
            category="articles",
            error="Network timeout",
        )

        # Complete the run
        db.record_run_complete(run_id, processed=0, failed=1)

        # Get run details
        result = db.get_pipeline_run_details(run_id=run_id)
        assert result is not None
        assert result['items_failed'] == 1
        assert len(result['failed']) == 1
        assert result['failed'][0]['entry_title'] == 'Failed Article'
        assert result['failed'][0]['last_error'] == 'Network timeout'


def test_clips_processed_table_exists():
    """Test that clips_processed table is created."""
    from src.database import Database

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)
        cursor = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='clips_processed'")
        assert cursor.fetchone() is not None


def test_is_clip_processed_false_for_new_file():
    """Test that new clip is not marked as processed."""
    from src.database import Database

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)
        assert not db.is_clip_processed("/path/to/clip.md")


def test_mark_clip_processed():
    """Test marking a clip as processed."""
    from src.database import Database

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)
        db.mark_clip_processed(
            file_path="/path/to/clip.md",
            note_path="/path/to/note.md",
            promoted=True,
            category="AI-Acceleration"
        )
        assert db.is_clip_processed("/path/to/clip.md")


def test_mark_clip_processed_duplicate_ignores():
    """Test that marking same clip twice doesn't error."""
    from src.database import Database

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)
        db.mark_clip_processed("/path/to/clip.md", "/path/to/note.md", True, "AI")
        # Should not raise error
        db.mark_clip_processed("/path/to/clip.md", "/path/to/note.md", True, "AI")
