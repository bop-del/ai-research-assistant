"""Tests for permanent failure handling in the pipeline."""
import logging
from datetime import datetime
from unittest.mock import MagicMock

from src.models import Entry
from src.pipeline import PipelineResult, send_notification
from src.skill_runner import SkillResult


def _make_entry(guid="test-123", title="Test Article"):
    """Create a test entry."""
    return Entry(
        guid=guid,
        title=title,
        url="https://example.com/article",
        content="",
        author=None,
        published_at=datetime.now(),
        feed_id=1,
        feed_title="Test Feed",
        category="articles",
    )


def test_permanent_failure_skips_retry_queue(monkeypatch):
    """Permanent failures should not be added to the retry queue."""
    from src.pipeline import _run_pipeline_inner

    db = MagicMock()
    db.get_last_successful_run.return_value = None
    db.get_retry_candidates.return_value = []
    db.record_run_start.return_value = 1
    db.is_processed.return_value = False

    entry = _make_entry()
    feed_manager = MagicMock()
    feed_manager.fetch_new_entries.return_value = [entry]
    monkeypatch.setattr("src.pipeline.FeedManager", lambda _db: feed_manager)

    skill_runner = MagicMock()
    skill_runner.validate_skills.return_value = []
    skill_runner.run_skill.return_value = SkillResult(
        success=False,
        note_path=None,
        error="Content behind paywall or not extractable",
        stdout="This article appears to be behind a paywall",
        stderr="",
        permanent=True,
    )
    monkeypatch.setattr("src.pipeline.SkillRunner", lambda: skill_runner)

    result = _run_pipeline_inner(db, dry_run=False, limit=None, verbose=False)

    db.add_to_retry_queue.assert_not_called()
    assert result.permanent_failures == 1
    assert result.failed == 0


def test_transient_failure_still_retries(monkeypatch):
    """Transient failures should be added to the retry queue as before."""
    from src.pipeline import _run_pipeline_inner

    db = MagicMock()
    db.get_last_successful_run.return_value = None
    db.get_retry_candidates.return_value = []
    db.record_run_start.return_value = 1
    db.is_processed.return_value = False

    entry = _make_entry()
    feed_manager = MagicMock()
    feed_manager.fetch_new_entries.return_value = [entry]
    monkeypatch.setattr("src.pipeline.FeedManager", lambda _db: feed_manager)

    skill_runner = MagicMock()
    skill_runner.validate_skills.return_value = []
    skill_runner.run_skill.return_value = SkillResult(
        success=False,
        note_path=None,
        error="Skill completed but no note path found in output",
        stdout="I processed something",
        stderr="",
        permanent=False,
    )
    monkeypatch.setattr("src.pipeline.SkillRunner", lambda: skill_runner)

    result = _run_pipeline_inner(db, dry_run=False, limit=None, verbose=False)

    db.add_to_retry_queue.assert_called_once()
    assert result.failed == 1
    assert result.permanent_failures == 0


def test_permanent_failure_count_in_result(monkeypatch):
    """PipelineResult should track permanent and transient failures separately."""
    from src.pipeline import _run_pipeline_inner

    db = MagicMock()
    db.get_last_successful_run.return_value = None
    db.get_retry_candidates.return_value = []
    db.record_run_start.return_value = 1
    db.is_processed.return_value = False

    entries = [
        _make_entry(guid="perm-1", title="Paywalled 1"),
        _make_entry(guid="perm-2", title="Paywalled 2"),
        _make_entry(guid="trans-1", title="Transient failure"),
    ]
    feed_manager = MagicMock()
    feed_manager.fetch_new_entries.return_value = entries
    monkeypatch.setattr("src.pipeline.FeedManager", lambda _db: feed_manager)

    call_count = 0

    def mock_run_skill(entry):
        nonlocal call_count
        call_count += 1
        if entry.guid.startswith("perm"):
            return SkillResult(
                success=False, note_path=None,
                error="Content behind paywall or not extractable",
                stdout="paywall", stderr="", permanent=True,
            )
        return SkillResult(
            success=False, note_path=None,
            error="Skill completed but no note path found in output",
            stdout="no path", stderr="", permanent=False,
        )

    skill_runner = MagicMock()
    skill_runner.validate_skills.return_value = []
    skill_runner.run_skill.side_effect = mock_run_skill
    monkeypatch.setattr("src.pipeline.SkillRunner", lambda: skill_runner)

    result = _run_pipeline_inner(db, dry_run=False, limit=None, verbose=False)

    assert result.permanent_failures == 2
    assert result.failed == 1


def test_permanent_failure_logs_warning(monkeypatch, caplog):
    """Permanent failures should be logged with [PERMANENT] prefix."""
    from src.pipeline import _run_pipeline_inner

    db = MagicMock()
    db.get_last_successful_run.return_value = None
    db.get_retry_candidates.return_value = []
    db.record_run_start.return_value = 1
    db.is_processed.return_value = False

    entry = _make_entry(title="Premium Article")
    feed_manager = MagicMock()
    feed_manager.fetch_new_entries.return_value = [entry]
    monkeypatch.setattr("src.pipeline.FeedManager", lambda _db: feed_manager)

    skill_runner = MagicMock()
    skill_runner.validate_skills.return_value = []
    skill_runner.run_skill.return_value = SkillResult(
        success=False, note_path=None,
        error="Content behind paywall or not extractable",
        stdout="paywall", stderr="", permanent=True,
    )
    monkeypatch.setattr("src.pipeline.SkillRunner", lambda: skill_runner)

    with caplog.at_level(logging.WARNING, logger="src.pipeline"):
        _run_pipeline_inner(db, dry_run=False, limit=None, verbose=False)

    assert "[PERMANENT]" in caplog.text
    assert "Premium Article" in caplog.text


def test_notification_includes_permanent_count():
    """Notification message should include permanent failure count."""
    result = PipelineResult(
        processed=3,
        failed=1,
        permanent_failures=2,
        failures=[(_make_entry(title="Failed One"), "some error")],
    )

    # Capture the notification message by checking what send_notification builds
    # We test the message logic, not the osascript call
    from unittest.mock import patch

    with patch("subprocess.run") as mock_run:
        send_notification(result)

    call_args = mock_run.call_args[0][0]
    osascript_cmd = call_args[2]
    assert "2 skipped (paywall)" in osascript_cmd


def test_notification_no_permanent_failures():
    """Notification without permanent failures should not mention paywall."""
    result = PipelineResult(processed=5, failed=0, permanent_failures=0)

    from unittest.mock import patch

    with patch("subprocess.run") as mock_run:
        send_notification(result)

    call_args = mock_run.call_args[0][0]
    osascript_cmd = call_args[2]
    assert "paywall" not in osascript_cmd
    assert "Processed 5 items" in osascript_cmd
