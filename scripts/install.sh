#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Installing content-pipeline..."

# Create directories
mkdir -p ~/.claude/logs
mkdir -p "$PROJECT_DIR/data"
mkdir -p "$PROJECT_DIR/exports"

# Make scripts executable
chmod +x "$PROJECT_DIR/scripts/run.sh"
chmod +x "$PROJECT_DIR/scripts/uninstall.sh"

# Copy launchd plist
cp "$PROJECT_DIR/templates/com.claude.content-pipeline.plist" ~/Library/LaunchAgents/

# Load the job
launchctl load ~/Library/LaunchAgents/com.claude.content-pipeline.plist

# Set wake schedule (requires sudo)
echo "Setting wake schedule..."
sudo pmset repeat wake MTWRFSU 05:55:00

echo ""
echo "Installed successfully!"
echo ""
echo "  Pipeline will run daily at 6:00 AM"
echo "  Machine will wake at 5:55 AM"
echo ""
echo "  Manual run:   cd $PROJECT_DIR && uv run content-pipeline run"
echo "  Check status: cd $PROJECT_DIR && uv run content-pipeline status"
echo "  View logs:    tail -f ~/.claude/logs/content-pipeline.log"
