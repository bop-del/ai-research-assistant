"""Logging configuration for ai-research-assistant."""
import logging
import logging.handlers
from pathlib import Path
from datetime import datetime, timedelta


def setup_logging(log_dir: Path, retention_days: int = 30, verbose: bool = False):
    """Configure dual logging handlers (file + console).

    Args:
        log_dir: Directory for log files (created if missing)
        retention_days: How many days of logs to keep
        verbose: If True, set console to DEBUG level
    """
    # Create log directory
    log_dir.mkdir(parents=True, exist_ok=True)

    # Clean up old logs
    cleanup_old_logs(log_dir, retention_days)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture everything

    # Remove existing handlers (avoid duplicates)
    root_logger.handlers.clear()

    # File handler - daily rotation, DEBUG level
    log_file = log_dir / f"{datetime.now().strftime('%Y-%m-%d')}.log"
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=log_file,
        when='midnight',
        interval=1,
        backupCount=retention_days,
        encoding='utf-8',
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # Console handler - INFO level (or DEBUG if verbose)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    console_formatter = logging.Formatter('[%(asctime)s] %(message)s', datefmt='%H:%M:%S')
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    return root_logger


def cleanup_old_logs(log_dir: Path, retention_days: int):
    """Delete log files older than retention_days."""
    if not log_dir.exists():
        return

    cutoff_date = datetime.now() - timedelta(days=retention_days)

    for log_file in log_dir.glob('*.log'):
        try:
            # Parse YYYY-MM-DD.log format
            date_str = log_file.stem
            file_date = datetime.strptime(date_str, '%Y-%m-%d')

            if file_date < cutoff_date:
                log_file.unlink()
                logging.debug(f"Deleted old log file: {log_file.name}")
        except (ValueError, OSError):
            # Skip files that don't match date format or can't be deleted
            continue
