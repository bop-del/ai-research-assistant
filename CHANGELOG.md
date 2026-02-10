# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

## [0.3.0] - 2026-02-10

Repository made public and hardened for open-source visibility.

### Added

- **Pipeline lock** — prevents concurrent pipeline runs using `fcntl.flock()`; second invocation exits with clear error message and PID of holding process
- **`--force` flag** — `ai-research-assistant run --force` bypasses the lock when needed
- **Permanent failure detection** — paywalled and inaccessible content is detected via pattern matching on skill output, skipping the retry queue with a `[PERMANENT]` log prefix and paywall count in notifications
- **SECURITY.md** — vulnerability reporting policy
- **Contributing policy** — README section clarifying this is a personal project

### Changed

- **Repository made public** — open for viewing and forking
- **Project renamed** to `ai-research-assistant` (dropped `-for-obsidian` suffix)
- **GitHub settings** — issues, wiki, and projects disabled; branch protection enabled; topics added for discoverability

## [0.2.0] - 2026-02-10

First shareable release. Skills merged into this repository and the project generalized so anyone with an Obsidian vault and Claude Code can use it.

### Added

- **Setup wizard** (`ai-research-assistant setup`) — interactive first-time setup and silent upgrade mode
- **Interest profile linking** — setup wizard asks whether to create a new profile or link an existing file in the vault
- **Cross-platform scheduling** — `--install-schedule` supports cron on Linux in addition to launchd on macOS; other platforms get manual setup instructions
- **Configuration system** — layered YAML config (`config/defaults.yaml` + `config/user.yaml`) with deep merge
- **Jinja2 skill templates** — skills stored as templates in `skills/_templates/`, rendered during setup with user config
- **Infrastructure templates** — MCP config, run script, and launchd plist generated from templates
- **Interest profile template** — shipped template copied to vault during setup
- **Dependency checker** — setup verifies `claude`, `yt-dlp`, and `npx` are installed
- **Upgrade flow** — `git pull && uv sync && ai-research-assistant setup` re-renders all templates from existing config

### Changed

- **Skills bundled** — article, youtube, podcast, and evaluate-knowledge skills now live in this repo (previously in separate `obsidian-workflow-skills` repo)
- **All paths configurable** — vault path, folder structure, and interest profile name read from config instead of hardcoded
- **Generic suggestion headers** — "For Work" / "For Personal Life" instead of personal references
- **Dynamic knowledge base discovery** — evaluate-knowledge skill lists existing subfolders instead of using a hardcoded category table
- **Project renamed** to `ai-research-assistant-for-obsidian` (later shortened to `ai-research-assistant` in 0.3.0)

### Removed

- Hardcoded vault path (`~/Obsidian/Professional vault/`)
- Hardcoded skill paths and class-level `SKILL_CONFIG`
- `config/settings.yaml` (replaced by `defaults.yaml` + `user.yaml`)
- `scripts/install.sh` (replaced by setup wizard)

## [0.1.0] - 2026-01-19

Initial release. RSS pipeline with feed management, retry queue, and Claude Code skill invocation.

### Added

- RSS feed management (add, list, remove, OPML import/export)
- Pipeline orchestration with SQLite tracking
- Skill runner invoking Claude Code CLI (`/article`, `/youtube`, `/podcast`)
- Retry queue with exponential backoff (1h, 4h, 12h, 24h)
- Post-processing with `/evaluate-knowledge` skill
- Dry-run mode and verbose output
- Scheduled runs via launchd (macOS)
