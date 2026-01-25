# AI Research Assistant

Automated research pipeline that fetches articles, YouTube videos, and podcasts from RSS feeds and creates structured Obsidian notes using Claude Code skills.

## Features

- **Feed Management**: Subscribe to RSS feeds via CLI
- **Multi-Format Support**: Articles, YouTube, Podcasts
- **Personalized Summaries**: Uses your interest profile for relevant insights
- **Automatic Retry**: Failed items retry with exponential backoff
- **Daily Automation**: Runs automatically via launchd

## Quick Start

```bash
# Install dependencies
uv sync

# Install required skills (see Prerequisites)

# Add some feeds
uv run ai-research-assistant feeds add "https://stratechery.com/feed/" -c articles

# Run manually
uv run ai-research-assistant run

# Check status
uv run ai-research-assistant status
```

## Prerequisites

### 1. Claude Code Skills

This pipeline requires skills from [obsidian-workflow-skills](https://github.com/jensechterling/obsidian-workflow-skills):

```bash
# Clone the skills repo
git clone https://github.com/jensechterling/obsidian-workflow-skills.git

# Install skills to Claude Code
cd obsidian-workflow-skills
./install.sh
```

Required skills: `article`, `youtube`, `podcast`

### 2. Obsidian Vault

Skills write notes to your Obsidian vault. Ensure you have:
- Vault at `~/Obsidian/Professional vault/` (or update `VAULT_PATH` in `src/skill_runner.py`)
- `interest-profile.md` in vault root for personalized suggestions

## Installation

```bash
# Clone repo
git clone https://github.com/jensechterling/ai-research-assistant.git
cd ai-research-assistant

# Install dependencies
uv sync

# Install automation (runs daily at 6 AM)
./scripts/install.sh
```

## Commands

| Command | Description |
|---------|-------------|
| `ai-research-assistant run` | Run the pipeline |
| `ai-research-assistant run --limit N` | Process only N items (for testing) |
| `ai-research-assistant run --dry-run` | Preview without processing |
| `ai-research-assistant status` | Show pending items and stats |
| `ai-research-assistant feeds add URL` | Add a feed |
| `ai-research-assistant feeds list` | List all feeds |
| `ai-research-assistant feeds export` | Export to OPML |
| `ai-research-assistant feeds import FILE` | Import from OPML |

## Dependencies

- Python 3.11+
- uv (package manager)
- Claude Code CLI
- [obsidian-workflow-skills](https://github.com/jensechterling/obsidian-workflow-skills)

## License

MIT
