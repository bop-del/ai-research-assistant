"""Tests for clips processing pipeline."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.database import Database


def test_process_single_clip_skips_if_already_processed():
    """Test that process_single_clip skips files already in clips_processed table."""
    from src.clips_pipeline import process_single_clip

    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup database
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)

        # Setup test file
        vault_path = Path(tmpdir) / "vault"
        vault_path.mkdir()
        unprocessed_dir = vault_path / "Clippings" / "Unprocessed"
        unprocessed_dir.mkdir(parents=True)
        test_file = unprocessed_dir / "test-clip.md"
        test_file.write_text("# Test Clip\nURL: https://example.com")

        # Mark file as already processed
        db.mark_clip_processed(str(test_file), note_path=None, promoted=False, category=None)

        # Process should skip
        with patch('subprocess.run') as mock_run:
            result = process_single_clip(test_file, db, vault_path)

            # Should not call subprocess
            mock_run.assert_not_called()
            assert result is None


def test_process_single_clip_calls_process_clippings():
    """Test that process_single_clip invokes /pkm:process-clippings skill."""
    from src.clips_pipeline import process_single_clip

    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup database
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)

        # Setup test file
        vault_path = Path(tmpdir) / "vault"
        vault_path.mkdir()
        unprocessed_dir = vault_path / "Clippings" / "Unprocessed"
        unprocessed_dir.mkdir(parents=True)
        test_file = unprocessed_dir / "test-clip.md"
        test_file.write_text("# Test Clip\nURL: https://example.com")

        # Setup mock subprocess
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="Success", stderr="")

            result = process_single_clip(test_file, db, vault_path)

            # Verify subprocess was called with correct arguments
            assert mock_run.called
            call_args = mock_run.call_args
            cmd = call_args[0][0]  # First positional arg is the command list

            # Verify command structure
            assert 'claude' in cmd
            assert '--plugin-dir' in cmd
            assert '--print' in cmd
            assert '--dangerously-skip-permissions' in cmd
            # Skill invocation is now a single string with file path
            skill_arg = f'/pkm:process-clippings "{test_file}"'
            assert skill_arg in cmd

            # Verify environment variable
            env = call_args[1].get('env', {})
            assert env.get('CLAUDECODE') == ""

            # Verify timeout
            assert call_args[1].get('timeout') == 600
