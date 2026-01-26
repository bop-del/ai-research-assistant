#!/bin/bash
set -e

# Navigate to project directory
cd "/Users/jens.echterling/GitHub/Development/AI research assistant"

# Load environment variables (if any)
if [ -f .env ]; then
    source .env
fi

# uv is installed in ~/.local/bin (not in launchd PATH)
UV="/Users/jens.echterling/.local/bin/uv"

# Run pipeline
$UV run ai-research-assistant run

# Export OPML and commit to GitHub (weekly backup - Mondays)
DAY_OF_WEEK=$(date +%u)
if [ "$DAY_OF_WEEK" -eq 1 ]; then
    $UV run ai-research-assistant feeds export
    git add exports/feeds.opml
    git diff --cached --quiet || git commit -m "Weekly OPML backup $(date +%Y-%m-%d)"
    git push
fi
