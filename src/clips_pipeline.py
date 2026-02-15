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

            # TODO: Parse skill output to check if promoted and extract details
            # Expected output format from skill:
            # PROMOTED: yes|no
            # CATEGORY: <category>
            # TITLE: <title>
            # INSIGHT: <insight>
            # For now, we'll mark as processed without promotion tracking

            # Check if output indicates promotion
            promoted = False
            category = None
            title = None
            insight = None

            # Simple parsing (TODO: enhance this based on actual skill output format)
            output_lines = result.stdout.split("\n")
            for line in output_lines:
                if line.startswith("PROMOTED:"):
                    promoted = line.split(":", 1)[1].strip().lower() == "yes"
                elif line.startswith("CATEGORY:"):
                    category = line.split(":", 1)[1].strip()
                elif line.startswith("TITLE:"):
                    title = line.split(":", 1)[1].strip()
                elif line.startswith("INSIGHT:"):
                    insight = line.split(":", 1)[1].strip()

            # If promoted, append to daily note
            if promoted and title and category and insight:
                try:
                    append_to_daily_note(title, category, insight, vault_path)
                except Exception as e:
                    logger.error(f"[CLIPS] Failed to append to daily note: {e}")

            # Mark as processed
            db.mark_clip_processed(str(file_path), note_path=None, promoted=promoted, category=category)
        else:
            logger.error(f"[CLIPS] ✗ Failed: {file_path.name}: {result.stderr}")

    except subprocess.TimeoutExpired:
        logger.error(f"[CLIPS] ✗ Timeout: {file_path.name}")
    except Exception as e:
        logger.error(f"[CLIPS] ✗ Exception: {file_path.name}: {e}")


def process_batch_clips(db: Database | None = None, vault_path: Path | None = None) -> None:
    """Batch process all clips in Unprocessed/ (hourly safety net).

    Args:
        db: Database instance (optional, will create if not provided)
        vault_path: Path to the Obsidian vault root (optional, will load from config)
    """
    from .config import get_vault_path, load_config

    if vault_path is None:
        config = load_config()
        vault_path = get_vault_path(config)

    if db is None:
        db_path = Path(__file__).parent.parent / "data" / "pipeline.db"
        db = Database(db_path)

    unprocessed_dir = vault_path / "Clippings" / "Unprocessed"

    if not unprocessed_dir.exists():
        logger.info("[CLIPS] No Unprocessed/ directory found")
        return

    # Find all .md files
    clip_files = list(unprocessed_dir.glob("*.md"))

    if not clip_files:
        logger.info("[CLIPS] No unprocessed clips found")
        return

    logger.info(f"[CLIPS] Batch processing {len(clip_files)} clips")

    processed = 0
    skipped = 0

    for clip_file in clip_files:
        if db.is_clip_processed(str(clip_file)):
            skipped += 1
            continue

        process_single_clip(clip_file, db, vault_path)
        processed += 1

    logger.info(f"[CLIPS] Batch complete: {processed} processed, {skipped} already done")


def append_to_daily_note(
    article_title: str,
    category: str,
    insight: str,
    vault_path: Path | None = None,
) -> None:
    """Append promoted article to today's daily note under ## On-Demand Knowledge.

    Args:
        article_title: Title of the promoted article
        category: Knowledge category (e.g., "AI-Engineering")
        insight: Key insight summary
        vault_path: Path to vault root (optional, will load from config)

    Creates the section if it doesn't exist. Inserts before ## Capture or appends at end.
    """
    from datetime import datetime

    if vault_path is None:
        from .config import get_vault_path, load_config
        config = load_config()
        vault_path = get_vault_path(config)

    # Get today's date
    today = datetime.now().strftime("%Y-%m-%d")
    daily_note_path = vault_path / "_Daily" / f"{today}.md"

    # Check if daily note exists
    if not daily_note_path.exists():
        logger.warning(f"[CLIPS] Daily note not found: {daily_note_path}")
        return

    # Read current content
    content = daily_note_path.read_text()
    lines = content.split("\n")

    # Prepare entry to append (two-line format)
    entry = f"- **[[{article_title}]]** → {category} — *Just now*\n  > {insight}"

    # Check if ## On-Demand Knowledge section exists
    section_idx = None
    capture_idx = None

    for i, line in enumerate(lines):
        if line.strip() == "## On-Demand Knowledge":
            section_idx = i
        elif line.strip() == "## Capture":
            capture_idx = i

    if section_idx is not None:
        # Section exists - find where to insert (before next ## or before ## Capture)
        insert_idx = len(lines)  # default: end of file
        for i in range(section_idx + 1, len(lines)):
            if lines[i].startswith("## ") and lines[i].strip() != "## On-Demand Knowledge":
                insert_idx = i
                break

        # Insert entry (with blank line if needed)
        if insert_idx > section_idx + 1 and lines[insert_idx - 1].strip() != "":
            lines.insert(insert_idx, "")
        lines.insert(insert_idx, entry)

    else:
        # Section doesn't exist - create it
        if capture_idx is not None:
            # Insert before ## Capture
            lines.insert(capture_idx, "")
            lines.insert(capture_idx, entry)
            lines.insert(capture_idx, "## On-Demand Knowledge")
        else:
            # Append at end
            if lines[-1].strip() != "":
                lines.append("")
            lines.append("## On-Demand Knowledge")
            lines.append(entry)

    # Write updated content
    daily_note_path.write_text("\n".join(lines))
    logger.info(f"[CLIPS] Appended to daily note: {article_title}")
