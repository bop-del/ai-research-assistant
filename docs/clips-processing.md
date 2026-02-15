# Clips Processing

Instant processing for web clipper captures using fswatch monitoring and Claude Code skills.

## Overview

The clips processing pipeline provides near-instant (<2s) processing of web articles captured via Obsidian Web Clipper or similar tools. Files dropped into `Clippings/Unprocessed/` are automatically detected, processed through `/pkm:process-clippings` and `/pkm:evaluate-knowledge`, and promoted to the appropriate Knowledge/ category or discarded if not relevant.

**Flow:**
```
Web Clipper → Clippings/Unprocessed/ → fswatch → /process-clippings → /evaluate-knowledge → Knowledge/ or Discarded/
                                                                                           ↓
                                                                       Daily Note (## On-Demand Knowledge)
```

**Processing time:** ~1-2 seconds detection delay + 30-120 seconds skill processing

## Components

### 1. fswatch Monitoring (Instant Detection)

**Launch agent:** `~/Library/LaunchAgents/com.bop.ai-research-clips-watch.plist`
- Watches `Clippings/Unprocessed/` for new `.md` files
- Triggers processing within ~1s of file creation
- Runs continuously while logged in

**Wrapper script:** `~/code/ai-research-assistant/scripts/watch-clips.sh`
- Invokes `ai-research-assistant clips --file <path>` when files are detected
- Logs to `logs/clips-watch.log`

### 2. Processing Pipeline

**Skill workflow:**
1. **`/pkm:process-clippings`** — Triages the clip (article, YouTube, podcast, or personal reference)
2. **`/pkm:article`** (or `/youtube`, `/podcast`) — Processes content, generates structured note
3. **`/pkm:evaluate-knowledge`** — Evaluates against interest profile, promotes or discards

**Database tracking:** `data/pipeline.db` → `clips_processed` table
- Tracks processed file paths to prevent duplicates
- Records promotion status and category
- Used by hourly safety net to catch missed files

### 3. Hourly Safety Net (Batch Mode)

**Launch agent:** `~/Library/LaunchAgents/com.bop.ai-research-clips-batch.plist`
- Runs hourly to catch any files missed by fswatch
- Scans `Clippings/Unprocessed/` for unprocessed files
- Skips files already in database (instant processing already ran)

**When it runs:** Every hour on the hour

### 4. Daily Note Integration

When a clip is promoted to Knowledge/, an entry is automatically added to today's daily note under `## On-Demand Knowledge`:

```markdown
## On-Demand Knowledge

- **[[Article Title]]** → AI-Engineering — *Just now*
  > Key insight summary from evaluation
```

**Section placement:**
- If `## On-Demand Knowledge` exists: appends to that section
- If not: creates section before `## Capture` (or at end if no Capture section)

## Setup

### Initial Installation

The clips processing system is installed automatically via:

```bash
cd ~/code/ai-research-assistant
uv run ai-research-assistant setup
```

This installs:
1. fswatch (via Homebrew if needed)
2. fswatch wrapper script (`scripts/watch-clips.sh`)
3. Two launchd plists (instant watch + hourly batch)
4. Database schema for `clips_processed` table

### Manual Installation

If you need to reinstall or install on a different machine:

```bash
# Install fswatch
brew install fswatch

# Load launchd agents
launchctl load ~/Library/LaunchAgents/com.bop.ai-research-clips-watch.plist
launchctl load ~/Library/LaunchAgents/com.bop.ai-research-clips-batch.plist

# Verify they're running
launchctl list | grep clips
```

Expected output:
```
-    0    com.bop.ai-research-clips-batch
-    0    com.bop.ai-research-clips-watch
```

### Uninstall

To disable clips processing:

```bash
# Unload launchd agents
launchctl unload ~/Library/LaunchAgents/com.bop.ai-research-clips-watch.plist
launchctl unload ~/Library/LaunchAgents/com.bop.ai-research-clips-batch.plist

# Optional: Remove plists
rm ~/Library/LaunchAgents/com.bop.ai-research-clips-watch.plist
rm ~/Library/LaunchAgents/com.bop.ai-research-clips-batch.plist
```

## Commands

### Process Single Clip

```bash
# Process a specific file
ai-research-assistant clips --file "Clippings/Unprocessed/article.md"
```

Use case: Manual processing or debugging

### Process All Unprocessed Clips (Batch)

```bash
# Process all files in Unprocessed/
ai-research-assistant clips
```

Use case:
- Manual batch processing
- Recovery after fswatch downtime
- Initial processing of backlog

### Check Processing Status

```bash
# View clips processing logs
tail -f ~/code/ai-research-assistant/logs/clips-watch.log

# Check launchd agent status
launchctl list | grep clips

# View database entries
sqlite3 ~/code/ai-research-assistant/data/pipeline.db "SELECT * FROM clips_processed ORDER BY processed_at DESC LIMIT 10;"
```

## Monitoring

### Real-Time Monitoring

Watch the instant processing log:

```bash
tail -f ~/code/ai-research-assistant/logs/clips-watch.log
```

Expected output when a file is added:
```
[2026-02-15 10:23:14] [CLIPS] Processing: article-title.md
[2026-02-15 10:24:02] [CLIPS] ✓ Processed: article-title.md
```

### Batch Processing Logs

Check hourly batch runs:

```bash
grep "\[CLIPS\]" ~/code/ai-research-assistant/logs/pipeline.log | tail -20
```

### Database Queries

See recently processed clips:

```bash
sqlite3 ~/code/ai-research-assistant/data/pipeline.db <<EOF
SELECT
  datetime(processed_at, 'localtime') as time,
  file_path,
  promoted,
  category
FROM clips_processed
ORDER BY processed_at DESC
LIMIT 10;
EOF
```

Check promotion rate:

```bash
sqlite3 ~/code/ai-research-assistant/data/pipeline.db <<EOF
SELECT
  promoted,
  COUNT(*) as count,
  ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM clips_processed), 1) as percent
FROM clips_processed
GROUP BY promoted;
EOF
```

## Troubleshooting

### Files Not Being Processed

**Check fswatch is running:**
```bash
launchctl list | grep clips-watch
```

If not listed:
```bash
launchctl load ~/Library/LaunchAgents/com.bop.ai-research-clips-watch.plist
```

**Check logs for errors:**
```bash
tail -50 ~/code/ai-research-assistant/logs/clips-watch.log
```

**Manually process to test:**
```bash
cd ~/code/ai-research-assistant
uv run ai-research-assistant clips --file "Clippings/Unprocessed/test.md"
```

### Processing Takes Too Long

Expected timing:
- Detection: 1-2 seconds (fswatch delay)
- Processing: 30-120 seconds (depends on article length and Claude API response time)

If processing exceeds 5 minutes, check:
1. Claude Code CLI is responding: `claude --version`
2. MCP server is running: Check Obsidian vault connection
3. API rate limits: Check Claude API status

### Daily Note Not Updated

**Verify daily note exists:**
```bash
ls -la ~/path/to/vault/_Daily/$(date +%Y-%m-%d).md
```

Create it manually if missing (morning routine usually creates it).

**Check promotion status in database:**
```bash
sqlite3 ~/code/ai-research-assistant/data/pipeline.db \
  "SELECT file_path, promoted, category FROM clips_processed ORDER BY processed_at DESC LIMIT 5;"
```

If `promoted = 0`, the article was discarded by `/evaluate-knowledge` (not relevant to interests).

**Check daily note format:**
- Section must be named exactly `## On-Demand Knowledge` (case-sensitive)
- Entries are inserted before `## Capture` if that section exists

### Duplicate Processing

The database prevents duplicate processing, but if you see duplicates:

**Check database for file:**
```bash
sqlite3 ~/code/ai-research-assistant/data/pipeline.db \
  "SELECT * FROM clips_processed WHERE file_path LIKE '%filename%';"
```

**Clear database entry to reprocess:**
```bash
sqlite3 ~/code/ai-research-assistant/data/pipeline.db \
  "DELETE FROM clips_processed WHERE file_path = '/full/path/to/file.md';"
```

### Hourly Batch Not Running

**Check batch agent status:**
```bash
launchctl list | grep clips-batch
```

**Check when it last ran:**
```bash
grep "Batch processing" ~/code/ai-research-assistant/logs/pipeline.log | tail -5
```

**Manually trigger batch:**
```bash
cd ~/code/ai-research-assistant
uv run ai-research-assistant clips
```

## Integration with Existing Workflows

### Morning Routine

The `/pkm:morning` skill does NOT run clips processing (clips are handled instantly via fswatch).

The morning routine DOES check for new Knowledge/ entries and displays them in the daily briefing.

### RSS Pipeline

Clips processing and RSS processing are independent:
- **RSS:** Scheduled (daily at 4 AM) → fetches feeds → processes articles → evaluates → promotes
- **Clips:** Instant (on file creation) → processes clip → evaluates → promotes

Both use the same `/pkm:article` and `/pkm:evaluate-knowledge` skills.

### Manual Clipping Workflow

**Recommended workflow:**
1. Use Obsidian Web Clipper → save to `Clippings/Unprocessed/`
2. Wait 1-2 seconds for fswatch detection
3. Check `logs/clips-watch.log` or today's daily note for results
4. If promoted: find in Knowledge/ category
5. If discarded: check `Clippings/Discarded/discard-log.md` for reason

## Performance

**Typical metrics:**
- Detection latency: 1-2 seconds
- Processing time: 30-120 seconds per article
- Hourly batch overhead: 0-5 seconds if no backlog
- Database queries: <100ms

**Throughput:**
- Instant mode: 1 clip at a time (sequential)
- Batch mode: Up to 6 clips per batch (respects `/evaluate-knowledge` batch limit)

**Resource usage:**
- fswatch: ~5 MB RAM (negligible CPU when idle)
- Processing: ~200 MB RAM during skill execution (transient)
- Database: <1 MB (100s of clips tracked)

## Advanced Configuration

### Adjust Hourly Batch Frequency

Edit `~/Library/LaunchAgents/com.bop.ai-research-clips-batch.plist`:

```xml
<key>StartCalendarInterval</key>
<dict>
    <key>Minute</key>
    <integer>0</integer>  <!-- Change to different minute, or add multiple intervals -->
</dict>
```

Reload:
```bash
launchctl unload ~/Library/LaunchAgents/com.bop.ai-research-clips-batch.plist
launchctl load ~/Library/LaunchAgents/com.bop.ai-research-clips-batch.plist
```

### Change Watch Directory

Edit `scripts/watch-clips.sh`:

```bash
WATCH_DIR="${VAULT_PATH}/Clippings/Unprocessed"  # Change to different folder
```

Reload fswatch agent:
```bash
launchctl unload ~/Library/LaunchAgents/com.bop.ai-research-clips-watch.plist
launchctl load ~/Library/LaunchAgents/com.bop.ai-research-clips-watch.plist
```

### Disable Daily Note Integration

The daily note integration is automatic when a clip is promoted. To disable:

Edit `src/clips_pipeline.py` and comment out the `append_to_daily_note()` call (lines 85-89).

This is not recommended — the daily note integration is the primary notification mechanism.

## Files and Locations

| Component | Location |
|-----------|----------|
| Clips processing code | `src/clips_pipeline.py` |
| CLI command | `src/main.py` → `clips` command |
| fswatch wrapper script | `scripts/watch-clips.sh` |
| Instant watch agent | `~/Library/LaunchAgents/com.bop.ai-research-clips-watch.plist` |
| Hourly batch agent | `~/Library/LaunchAgents/com.bop.ai-research-clips-batch.plist` |
| Watch log | `logs/clips-watch.log` |
| Batch log | `logs/pipeline.log` (search for `[CLIPS]`) |
| Database | `data/pipeline.db` → `clips_processed` table |
| Unprocessed clips | `Clippings/Unprocessed/` (in Obsidian vault) |
| Processed notes | `Clippings/Articles/` (or `Youtube/`, `Podcasts/`) |
| Promoted notes | `Knowledge/<category>/` |
| Discarded notes | `Clippings/Discarded/` |
