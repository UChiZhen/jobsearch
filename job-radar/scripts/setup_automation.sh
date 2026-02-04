#!/bin/bash
# Setup script for Job Radar automation on macOS

set -e

PLIST_NAME="com.jobradar.weekly"
PLIST_SOURCE="$(dirname "$0")/../config/${PLIST_NAME}.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"

echo "🤖 Job Radar Automation Setup"
echo "=============================="
echo ""

# Check if already loaded
if launchctl list | grep -q "$PLIST_NAME"; then
    echo "⚠️  Unloading existing job..."
    launchctl unload "$PLIST_DEST" 2>/dev/null || true
fi

# Copy plist to LaunchAgents
echo "📝 Installing plist to ~/Library/LaunchAgents/"
cp "$PLIST_SOURCE" "$PLIST_DEST"

# Load the agent
echo "🚀 Loading launchd agent..."
launchctl load "$PLIST_DEST"

# Verify
if launchctl list | grep -q "$PLIST_NAME"; then
    echo ""
    echo "✅ Job Radar automation installed!"
    echo "   Schedule: Every Sunday at 9:00 AM"
    echo ""
    echo "📋 Useful commands:"
    echo "   View status:   launchctl list | grep jobradar"
    echo "   Unload:        launchctl unload $PLIST_DEST"
    echo "   Run manually:  launchctl start $PLIST_NAME"
    echo "   View logs:     tail -f ~/jobsearch/job-radar/logs/radar.log"
else
    echo "❌ Failed to load agent"
    exit 1
fi
