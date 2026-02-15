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


def test_process_batch_clips_finds_unprocessed():
    """Test that process_batch_clips finds all .md files and processes new ones."""
    from src.clips_pipeline import process_batch_clips

    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup database
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)

        # Setup vault structure
        vault_path = Path(tmpdir) / "vault"
        vault_path.mkdir()
        unprocessed_dir = vault_path / "Clippings" / "Unprocessed"
        unprocessed_dir.mkdir(parents=True)

        # Create test files
        clip1 = unprocessed_dir / "clip1.md"
        clip2 = unprocessed_dir / "clip2.md"
        clip3 = unprocessed_dir / "clip3.md"
        clip1.write_text("# Clip 1\nURL: https://example.com/1")
        clip2.write_text("# Clip 2\nURL: https://example.com/2")
        clip3.write_text("# Clip 3\nURL: https://example.com/3")

        # Mark clip2 as already processed
        db.mark_clip_processed(str(clip2), note_path=None, promoted=False, category=None)

        # Mock subprocess to track calls
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="Success", stderr="")

            # Run batch processing
            process_batch_clips(db, vault_path)

            # Should have called subprocess twice (clip1 and clip3, not clip2)
            assert mock_run.call_count == 2

            # Verify the correct files were processed
            processed_files = []
            for call in mock_run.call_args_list:
                cmd = call[0][0]
                # Extract filename from command
                for arg in cmd:
                    if 'clip' in str(arg) and '.md' in str(arg):
                        processed_files.append(Path(arg).name)

            assert 'clip1.md' in str(processed_files)
            assert 'clip3.md' in str(processed_files)
            assert 'clip2.md' not in str(processed_files)
