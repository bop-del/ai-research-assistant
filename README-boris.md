# Boris's RSS Feed Automation

Fork of [jensechterling/ai-research-assistant](https://github.com/jensechterling/ai-research-assistant) customized for Boris's PKM workflow.

## Upstream Repository

Original: https://github.com/jensechterling/ai-research-assistant
Fork: https://github.com/bop-del/ai-research-assistant

## Changes from Upstream

- **Skill invocations**: Uses `pkm:article`, `pkm:youtube`, `pkm:podcast` namespace
- **Auto-evaluation**: Runs `pkm:evaluate-knowledge` after each item processed
- **Vault path**: Points to Bopvault Obsidian vault
- **Output folders**: `Clippings/Articles/`, `Clippings/YouTube/`, `Clippings/Podcasts/`
- **Profile loading**: Uses Boris's existing `boris-profile.md` and `work-profile.md`

## Installation

### Prerequisites

- Python 3.11+
- [uv package manager](https://docs.astral.sh/uv/)
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code)
- yt-dlp: `brew install yt-dlp`

### Setup

```bash
# Clone repository
cd ~/code
git clone https://github.com/bop-del/ai-research-assistant.git
cd ai-research-assistant

# Install dependencies
uv sync

# Run setup wizard
uv run ai-research-assistant setup
# Vault path: /Users/boris.diebold/Library/Mobile Documents/iCloud~md~obsidian/Documents/Bopvault
# Articles: Clippings/Articles/
# YouTube: Clippings/YouTube/
# Podcasts: Clippings/Podcasts/

# Verify
uv run ai-research-assistant --help
```

## Automation

### Launchd (Daily 4:00 AM)

**Configuration:** `~/Library/LaunchAgents/com.bop.ai-research-assistant.plist`

**Schedule:** Daily at 4:00 AM

**Logs:** `~/code/ai-research-assistant/logs/pipeline.log`

**Commands:**
```bash
# Load job
launchctl load ~/Library/LaunchAgents/com.bop.ai-research-assistant.plist

# Check status
launchctl list | grep ai-research-assistant

# Manual trigger (testing)
launchctl start com.bop.ai-research-assistant

# Reload after changes
launchctl unload ~/Library/LaunchAgents/com.bop.ai-research-assistant.plist
launchctl load ~/Library/LaunchAgents/com.bop.ai-research-assistant.plist

# View logs
tail -f ~/code/ai-research-assistant/logs/pipeline.log
```

### Wake from Sleep

**Configuration:** Wake Mac at 3:55 AM daily (5 min before RSS processing)

```bash
# Set wake schedule
sudo pmset repeat wakeorpoweron MTWRFSU 03:55:00

# Verify
sudo pmset -g sched
# Should show:
# Repeating power events:
#   wakeorpoweron  MTWRFSU  03:55:00

# Cancel (if needed)
sudo pmset repeat cancel
```

**Daily sequence:**
1. **3:55 AM** - Mac wakes from sleep (pmset)
2. **4:00 AM** - RSS feeds processed (launchd → `uv run ai-research-assistant run`)
3. Articles processed through `/pkm:article`
4. Auto-evaluation via `/pkm:evaluate-knowledge`
5. Promotion to `Knowledge/` or discard to `Clippings/Discarded/`
6. Mac can sleep again

### Integration with /morning

The `/morning` skill includes RSS processing with smart skip logic:

```bash
# Morning routine checks:
# 1. Did feeds run today? (SQLite query)
# 2. If no → run ai-research-assistant
# 3. If yes → skip (already processed by launchd)
```

This ensures feeds are always processed, even if:
- Mac was off/asleep at 4 AM
- Launchd job failed
- User runs `/morning` before 4 AM

## Commands

### Daily Operations

```bash
# Manual processing
cd ~/code/ai-research-assistant
uv run ai-research-assistant run

# Preview without processing
uv run ai-research-assistant run --dry-run

# Verbose output
uv run ai-research-assistant run -v

# Check status
uv run ai-research-assistant status
```

### Feed Management

```bash
# List feeds
uv run ai-research-assistant feeds list

# Add feed
uv run ai-research-assistant feeds add <url> -c articles
uv run ai-research-assistant feeds add <url> -c youtube
uv run ai-research-assistant feeds add <url> -c podcasts

# Remove feed
uv run ai-research-assistant feeds remove <url>

# Export/import OPML
uv run ai-research-assistant feeds export > feeds.opml
uv run ai-research-assistant feeds import feeds.opml
```

### Monitoring

#### Enhanced Status Commands

```bash
# Quick status (pending items, last run time)
uv run ai-research-assistant status

# Show last run with comprehensive report
uv run ai-research-assistant status --last-run

# Watch current run in real-time (2s updates)
uv run ai-research-assistant status --watch

# Show run from specific date
uv run ai-research-assistant status --date 2026-02-14
```

**Status report includes:**
- Run timestamps and duration (local timezone)
- Summary: processed, promoted, discarded, failed counts
- Item-by-item list with destinations (Knowledge/, Clippings/, Discarded)
- Timing statistics

#### Log Monitoring

**Single log file:** All output goes to `~/code/ai-research-assistant/logs/pipeline.log`

```bash
# Watch logs in real-time (shows immediate updates with flush)
tail -f ~/code/ai-research-assistant/logs/pipeline.log

# View recent entries
tail -100 ~/code/ai-research-assistant/logs/pipeline.log

# Search for errors
grep ERROR ~/code/ai-research-assistant/logs/pipeline.log
```

**Note:** `launchd.log` is no longer used. All logging handled by Python's logging_config module.

#### Database Queries

```bash
# Check failed items
uv run ai-research-assistant status --failed

# Review discarded articles
cat ~/Library/Mobile\ Documents/iCloud~md~obsidian/Documents/Bopvault/Clippings/Discarded/discard-log.md

# Check last run timestamp
sqlite3 ~/code/ai-research-assistant/data/feeds.db \
  "SELECT MAX(processed_at) FROM feed_items WHERE DATE(processed_at) = DATE('now');"

# View recent items
sqlite3 ~/code/ai-research-assistant/data/feeds.db \
  "SELECT url, processed_at, status FROM feed_items ORDER BY processed_at DESC LIMIT 10;"
```

## Processing Pipeline

```
RSS Feed → FeedManager → SkillRunner → /pkm:article → Clippings/Articles/
                ↓                                           ↓
         SQLite tracking                        /pkm:evaluate-knowledge
                                                            ↓
                                             Knowledge/ OR Clippings/Discarded/
```

**Flow:**
1. **FeedManager** fetches new RSS items
2. **SQLite** prevents duplicate processing
3. **SkillRunner** invokes `/pkm:article` (or youtube/podcast)
4. Article saved to `Clippings/Articles/`
5. **Auto-evaluation** runs `/pkm:evaluate-knowledge`
6. **Relevance filter** (based on `boris-profile.md` interests):
   - Relevant → promoted to `Knowledge/<domain>/`
   - Tangential → discarded to `Clippings/Discarded/` with log entry

## File Locations

| Purpose | Path |
|---------|------|
| Repository | `~/code/ai-research-assistant/` |
| Database | `~/code/ai-research-assistant/data/feeds.db` |
| Logs | `~/code/ai-research-assistant/logs/pipeline.log` |
| Launchd plist | `~/Library/LaunchAgents/com.bop.ai-research-assistant.plist` |
| Feed config | Managed via CLI (`feeds add/remove`) |
| Articles output | `Clippings/Articles/` |
| Promoted notes | `Knowledge/<domain>/` |
| Discarded notes | `Clippings/Discarded/` + `discard-log.md` |

## Troubleshooting

### Launchd not running

```bash
# Check if job is loaded
launchctl list | grep ai-research-assistant

# Reload job
launchctl unload ~/Library/LaunchAgents/com.bop.ai-research-assistant.plist
launchctl load ~/Library/LaunchAgents/com.bop.ai-research-assistant.plist

# Test manually
launchctl start com.bop.ai-research-assistant

# Check logs
tail -f ~/code/ai-research-assistant/logs/pipeline.log
```

### Mac not waking at 3:55 AM

```bash
# Verify wake schedule
sudo pmset -g sched

# Should show:
# Repeating power events:
#   wakeorpoweron  MTWRFSU  03:55:00

# Re-apply if missing
sudo pmset repeat wakeorpoweron MTWRFSU 03:55:00
```

### Duplicate processing

SQLite database prevents duplicates. If items are reprocessed:

```bash
# Check database integrity
sqlite3 ~/code/ai-research-assistant/data/feeds.db "SELECT COUNT(*) FROM feed_items;"

# View processed URLs
sqlite3 ~/code/ai-research-assistant/data/feeds.db \
  "SELECT url, processed_at FROM feed_items ORDER BY processed_at DESC LIMIT 20;"
```

### Skills not found

Ensure Claude Code can find the PKM skills:

```bash
# Test skill invocation
claude skill pkm:article --help

# Check plugin directory
ls -la ~/Library/Mobile\ Documents/iCloud~md~obsidian/Documents/Bopvault/Claude/skills-pkm/

# Verify skill registration
claude --list-skills | grep pkm:
```

### Processing errors

```bash
# View recent errors in logs
grep ERROR ~/code/ai-research-assistant/logs/pipeline.log

# Check failed items
uv run ai-research-assistant status --failed

# Retry failed items
uv run ai-research-assistant run  # Auto-retries with exponential backoff
```

## Upstream Sync

Keep fork updated with upstream changes:

```bash
cd ~/code/ai-research-assistant

# Add upstream remote (if not already added)
git remote add upstream https://github.com/jensechterling/ai-research-assistant.git

# Fetch upstream changes
git fetch upstream

# View changes
git log HEAD..upstream/main --oneline

# Merge (may need to resolve conflicts in skill invocations)
git merge upstream/main

# Resolve conflicts if needed (likely in SkillRunner.py)
# Ensure pkm: namespace is preserved

# Push to fork
git push origin main
```

## Configuration Files

### Launchd Plist

Location: `~/Library/LaunchAgents/com.bop.ai-research-assistant.plist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.bop.ai-research-assistant</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>cd ~/code/ai-research-assistant &amp;&amp; /Users/boris.diebold/.local/bin/uv run ai-research-assistant run</string>
    </array>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>4</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/Users/boris.diebold/.local/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>

    <key>LaunchOnlyOnce</key>
    <false/>
</dict>
</plist>
```

**Note:** All logging is handled by Python's logging_config module writing to `pipeline.log`. No manual redirection or StandardOutPath/StandardErrorPath needed.

## Related Documentation

- **PKM Setup:** `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Bopvault/PKM-LifeOS/Setup/RSS_Feed_Automation.md`
- **Design doc:** `PKM-LifeOS/Plan/2026-02-14-rss-feed-automation-design.md`
- **Implementation plan:** `PKM-LifeOS/Plan/2026-02-14-rss-feed-automation-plan.md`
- **Morning skill:** `Claude/skills-pkm/skills/morning/SKILL.md`
- **Evaluate skill:** `Claude/skills-pkm/skills/evaluate-knowledge/SKILL.md`

## Status

**Setup completed:** 2026-02-14

**Automation status:** ✅ Active
- Launchd: Loaded, scheduled daily 4:00 AM
- Wake schedule: Configured (3:55 AM daily)
- Integration: `/morning` skill updated with RSS processing step

**Next steps:**
- Monitor discard-log.md for false positives/negatives (weekly)
- Tune feed selection based on signal/noise ratio (2-3 weeks)
- Consider PR to upstream (backlog item 3e) after validation period
