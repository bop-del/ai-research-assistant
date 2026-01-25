"""Tests for skill runner module."""
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.models import Entry


def test_skill_runner_selects_correct_skill():
    """SkillRunner should select skill based on category."""
    from src.skill_runner import SkillRunner

    runner = SkillRunner()

    assert runner.SKILL_CONFIG["articles"]["skill"] == "article"
    assert runner.SKILL_CONFIG["youtube"]["skill"] == "youtube"
    assert runner.SKILL_CONFIG["podcasts"]["skill"] == "podcast"


def test_skill_runner_runs_command():
    """SkillRunner should invoke claude CLI with correct arguments."""
    from src.skill_runner import SkillRunner

    runner = SkillRunner()

    entry = Entry(
        guid="test-123",
        title="Test Article",
        url="https://example.com/article",
        content="",
        author=None,
        published_at=datetime.now(),
        feed_id=1,
        feed_title="Test Feed",
        category="articles",
    )

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Done. I've saved the article analysis to **Clippings/Test Article.md**.",
            stderr="",
        )

        # Mock path.exists() to return True
        with patch.object(Path, "exists", return_value=True):
            result = runner.run_skill(entry)

        # Verify command was called correctly
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "claude" in call_args
        assert "--dangerously-skip-permissions" in call_args
        assert "/article https://example.com/article" in " ".join(call_args)


def test_extract_note_path_bold_markdown():
    """Should extract path from **Folder/File.md** format."""
    from src.skill_runner import SkillRunner

    runner = SkillRunner()
    stdout = "Done. I've saved the article analysis to **Clippings/Test Article.md**."

    path = runner._extract_note_path(stdout, "Clippings")

    assert path is not None
    assert path.name == "Test Article.md"
    assert "Clippings" in str(path)


def test_extract_note_path_nested_folder():
    """Should extract path from nested folder format."""
    from src.skill_runner import SkillRunner

    runner = SkillRunner()
    stdout = "Note saved to **Clippings/Youtube extractions/Video Title.md**"

    path = runner._extract_note_path(stdout, "Clippings/Youtube extractions")

    assert path is not None
    assert path.name == "Video Title.md"
    assert "Youtube extractions" in str(path)


def test_extract_note_path_backtick_format():
    """Should extract path from `Folder/File.md` backtick format."""
    from src.skill_runner import SkillRunner

    runner = SkillRunner()
    stdout = "Done. I've created the note at `Clippings/Netflix Article.md`."

    path = runner._extract_note_path(stdout, "Clippings")

    assert path is not None
    assert path.name == "Netflix Article.md"
    assert "Clippings" in str(path)
