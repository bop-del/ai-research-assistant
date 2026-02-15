#!/bin/bash
# fswatch wrapper for instant clip processing

VAULT="/Users/boris.diebold/Library/Mobile Documents/iCloud~md~obsidian/Documents/Bopvault"
PROJECT_DIR="$HOME/code/ai-research-assistant"

cd "$PROJECT_DIR" || exit 1

# Monitor Unprocessed/ for new .md files
/opt/homebrew/bin/fswatch -0 --event Created \
  "$VAULT/Clippings/Unprocessed" \
  -e ".*" -i "\\.md$" | \
while read -d "" event; do
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Detected: $event"
  /Users/boris.diebold/.local/bin/uv run ai-research-assistant clips --file "$event"
done
