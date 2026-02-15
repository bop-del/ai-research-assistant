"""Clips processing pipeline - invokes Claude Code skills to process captured clips."""

import logging
import os
import subprocess
from pathlib import Path

from .database import Database

logger = logging.getLogger(__name__)


def process_single_clip(file_path: Path, db: Database, vault_path: Path | None = None) -> None:
    """Process a single clip file using /pkm:process-clippings skill.

    Args:
        file_path: Path to the clip file to process
        db: Database instance for tracking processed clips
        vault_path: Path to the Obsidian vault root (optional)
    """
    # Skip if already processed
    if db.is_clip_processed(str(file_path)):
        logger.info(f"[CLIPS] Already processed: {file_path.name}")
        return

    logger.info(f"[CLIPS] Processing: {file_path.name}")

    # Construct plugin directory paths
    plugin_dir_pkm = vault_path / "Claude" / "skills-pkm"
    plugin_dir_cto = vault_path / "Claude" / "skills-cto"

    # Build command
    cmd = [
        "claude",
        "--plugin-dir", str(plugin_dir_pkm),
        "--plugin-dir", str(plugin_dir_cto),
        "--print",
        "--dangerously-skip-permissions",
        f"/pkm:process-clippings \"{file_path}\"",
    ]

    # Setup environment
    env = {**os.environ, "CLAUDECODE": ""}

    try:
        # Run Claude Code skill
        result = subprocess.run(
            cmd,
            env=env,
            timeout=600,
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            logger.info(f"[CLIPS] ✓ Processed: {file_path.name}")
            # Mark as processed (skill will set note_path, promoted, category later)
            db.mark_clip_processed(str(file_path), note_path=None, promoted=False, category=None)
        else:
            logger.error(f"[CLIPS] ✗ Failed: {file_path.name}: {result.stderr}")

    except subprocess.TimeoutExpired:
        logger.error(f"[CLIPS] ✗ Timeout: {file_path.name}")
    except Exception as e:
        logger.error(f"[CLIPS] ✗ Exception: {file_path.name}: {e}")


def process_batch_clips() -> None:
    """Process all unprocessed clips in batch.

    TODO: Implementation in next task.
    """
    pass


def append_to_daily_note(article_title: str, category: str, insight: str) -> None:
    """Append processed clip summary to today's daily note.

    TODO: Implementation in next task.
    """
    pass
