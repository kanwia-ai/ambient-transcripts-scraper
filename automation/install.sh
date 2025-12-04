#!/bin/bash
# Install script for transcript-sync launchd agent
#
# Usage: ./install.sh
#
# This script:
# 1. Prompts for the ANTHROPIC_API_KEY
# 2. Generates the plist with correct paths
# 3. Installs to ~/Library/LaunchAgents/
# 4. Loads the agent

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PLIST_TEMPLATE="$SCRIPT_DIR/com.user.transcript-sync.plist"
PLIST_NAME="com.user.transcript-sync.plist"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
PLIST_DEST="$LAUNCH_AGENTS_DIR/$PLIST_NAME"

echo "=========================================="
echo "Transcript Sync - launchd Installation"
echo "=========================================="
echo ""
echo "Project directory: $PROJECT_DIR"
echo ""

# Check if already installed
if [ -f "$PLIST_DEST" ]; then
    echo "Existing installation found."
    read -p "Do you want to reinstall? (y/n): " REINSTALL
    if [ "$REINSTALL" != "y" ]; then
        echo "Aborting."
        exit 0
    fi
    # Unload existing
    launchctl unload "$PLIST_DEST" 2>/dev/null || true
fi

# Get API key
if [ -z "$ANTHROPIC_API_KEY" ]; then
    read -sp "Enter your ANTHROPIC_API_KEY: " ANTHROPIC_API_KEY
    echo ""
fi

if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "Error: ANTHROPIC_API_KEY is required"
    exit 1
fi

# Create logs directory
mkdir -p "$PROJECT_DIR/logs"

# Create LaunchAgents directory if needed
mkdir -p "$LAUNCH_AGENTS_DIR"

# Generate plist with correct paths
sed -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" \
    -e "s|__ANTHROPIC_API_KEY__|$ANTHROPIC_API_KEY|g" \
    "$PLIST_TEMPLATE" > "$PLIST_DEST"

echo "Generated plist at: $PLIST_DEST"

# Load the agent
launchctl load "$PLIST_DEST"

echo ""
echo "Installation complete!"
echo ""
echo "The sync will run daily at 8:00 AM."
echo ""
echo "Commands:"
echo "  View status:    launchctl list | grep transcript"
echo "  Run now:        launchctl start com.user.transcript-sync"
echo "  View logs:      tail -f $PROJECT_DIR/logs/sync.log"
echo "  Uninstall:      launchctl unload $PLIST_DEST && rm $PLIST_DEST"
echo ""
