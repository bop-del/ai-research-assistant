"""Claude Code skill invocation."""
import logging
import os
import re
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from src.config import get_folder, get_project_dir, get_skills_path, get_vault_path, load_config
from src.models import Entry


@contextmanager
def timer(operation_name: str, logger: logging.Logger):
    """Context manager to time operations and log duration."""
    start = time.perf_counter()
    try:
        yield
    finally:
        duration = time.perf_counter() - start
        logger.debug(f"{operation_name} took {duration:.1f}s")


# Patterns indicating content that will never be extractable (no point retrying)
PERMANENT_FAILURE_PATTERNS = [
    "paywall",
    "behind a paywall",
    "subscription required",
    "subscribers only",
    "premium content",
    "sign in to read",
    "this article appears to be behind",
    "could only extract the headline",
    "copy/paste the article text",
]


@dataclass
class SkillResult:
    """Result from running a skill."""

    success: bool
    note_path: Path | None
    error: str | None
    stdout: str
    stderr: str
    permanent: bool = False


class SkillRunner:
    """Invoke Claude Code skills via CLI."""

    def __init__(self, config: dict | None = None):
        self._config = config or load_config()
        self._vault_path = get_vault_path(self._config)
        self._skills_path = get_skills_path()
        self._mcp_config_path = get_project_dir() / "config" / "mcp-minimal.json"
        self.logger = logging.getLogger(__name__)
        self._skill_config = {
            "articles": {
                "skill": "article",
                "timeout": self._config["processing"]["article_timeout"],
                "output_folder": get_folder("article", self._config),
            },
            "youtube": {
                "skill": "youtube",
                "timeout": self._config["processing"]["youtube_timeout"],
                "output_folder": get_folder("youtube", self._config),
            },
            "podcasts": {
                "skill": "podcast",
                "timeout": self._config["processing"]["podcast_timeout"],
                "output_folder": get_folder("clippings", self._config),
            },
        }

    @property
    def vault_path(self) -> Path:
        return self._vault_path

    def validate_skills(self) -> list[str]:
        """Check that all required skills are installed.

        Returns list of missing skill names. Empty list means all OK.
        """
        missing = []
        for category, config in self._skill_config.items():
            skill_name = config["skill"]
            # Check in plugin directory (pkm: namespace)
            plugin_path = self._vault_path / "Claude" / "skills-pkm" / "skills" / skill_name
            if not plugin_path.exists():
                missing.append(skill_name)
        return missing

    def run_skill(self, entry: Entry) -> SkillResult:
        """Invoke appropriate skill for entry and verify output."""
        config = self._skill_config[entry.category]
        skill_name = config["skill"]
        timeout = config["timeout"]
        output_folder = config["output_folder"]

        self.logger.info(f"Processing: {entry.title}")
        start_time = time.perf_counter()

        try:
            # Allow nested Claude sessions by unsetting CLAUDECODE env var
            env = os.environ.copy()
            env["CLAUDECODE"] = ""

            self.logger.debug(f"Invoking /pkm:{skill_name} for {entry.url}")
            result = subprocess.run(
                [
                    "claude",
                    "--plugin-dir",
                    str(self._vault_path / "Claude/skills-pkm"),
                    "--plugin-dir",
                    str(self._vault_path / "Claude/skills-cto"),
                    "--mcp-config",
                    str(self._mcp_config_path),
                    "--print",
                    "--dangerously-skip-permissions",
                    f"/pkm:{skill_name} {entry.url}",
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
        except subprocess.TimeoutExpired:
            duration = time.perf_counter() - start_time
            self.logger.error(f"  ✗ Skill timed out after {timeout}s")
            return SkillResult(
                success=False,
                note_path=None,
                error=f"Skill timed out after {timeout} seconds",
                stdout="",
                stderr="",
            )
        except FileNotFoundError:
            duration = time.perf_counter() - start_time
            self.logger.error(f"  ✗ Claude CLI not found in PATH")
            return SkillResult(
                success=False,
                note_path=None,
                error="Claude CLI not found. Ensure 'claude' is in PATH.",
                stdout="",
                stderr="",
            )

        duration = time.perf_counter() - start_time

        if result.returncode != 0:
            # Error might be in stdout or stderr depending on the CLI
            error_output = result.stderr.strip() or result.stdout.strip()
            self.logger.error(f"  ✗ Skill failed ({duration:.1f}s): {error_output[:200]}")
            return SkillResult(
                success=False,
                note_path=None,
                error=f"Skill exited with code {result.returncode}: {error_output[:200]}",
                stdout=result.stdout,
                stderr=result.stderr,
            )

        # Extract note path from skill output
        note_path = self._extract_note_path(result.stdout, output_folder)

        if note_path is None:
            # Check if this is a permanent failure (paywall, etc.)
            output_lower = result.stdout.lower()
            is_permanent = any(p in output_lower for p in PERMANENT_FAILURE_PATTERNS)
            error_msg = (
                "Content behind paywall or not extractable"
                if is_permanent
                else "Skill completed but no note path found in output"
            )
            self.logger.warning(f"  ✗ Skill completed but no note path found ({duration:.1f}s)")
            return SkillResult(
                success=False,
                note_path=None,
                error=error_msg,
                stdout=result.stdout,
                stderr=result.stderr,
                permanent=is_permanent,
            )

        if not note_path.exists():
            self.logger.warning(f"  ✗ Note path not found: {note_path} ({duration:.1f}s)")
            return SkillResult(
                success=False,
                note_path=None,
                error=f"Skill reported creating note but file not found: {note_path}",
                stdout=result.stdout,
                stderr=result.stderr,
            )

        self.logger.info(f"  ✓ Created: {note_path.name} ({duration:.1f}s)")
        return SkillResult(
            success=True,
            note_path=note_path,
            error=None,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    def _extract_note_path(self, stdout: str, folder: str) -> Path | None:
        """Extract note path from skill output.

        Skills typically output lines like:
        - "Done. I've saved the article analysis to **Clippings/Title.md**."
        - "Done. I've created the note at `Clippings/Title.md`."
        - "Note saved to Clippings/Youtube extractions/Title.md"
        - "Successfully wrote note to Clippings/Article extractions/Title.md"
        """
        output_dir = self._vault_path / folder

        # Pattern 1: **Folder/Filename.md** (bold markdown)
        bold_pattern = r"\*\*([^*]+\.md)\*\*"
        match = re.search(bold_pattern, stdout)
        if match:
            relative_path = match.group(1)
            if "/" in relative_path:
                return self._vault_path / relative_path
            return output_dir / relative_path

        # Pattern 2: `Folder/Filename.md` (backtick code format)
        backtick_pattern = r"`([^`]+\.md)`"
        match = re.search(backtick_pattern, stdout)
        if match:
            relative_path = match.group(1)
            if "/" in relative_path:
                return self._vault_path / relative_path
            return output_dir / relative_path

        # Pattern 3: Folder/path.md (allows spaces in filename, stops at .md)
        path_pattern = rf"({re.escape(folder)}/[^\n]+?\.md)"
        match = re.search(path_pattern, stdout)
        if match:
            return self._vault_path / match.group(1)

        # Pattern 4: "wrote/written/saved/created ... to/at/in path.md"
        action_pattern = r"(?:wrote|written|saved|created)[^\n]*?(?:to|at|in)\s+([A-Za-z][^\n]+?\.md)"
        match = re.search(action_pattern, stdout, re.IGNORECASE)
        if match:
            filename = match.group(1).strip()
            if "/" in filename:
                return self._vault_path / filename
            return output_dir / filename

        return None
