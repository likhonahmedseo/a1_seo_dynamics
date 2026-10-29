#!/bin/bash
# Removes the A1 Mail Dynamics macOS LaunchAgent (disables login auto-start).
set -euo pipefail

LABEL="com.a1technovation.a1maildynamics"
PLIST_PATH="$HOME/Library/LaunchAgents/$LABEL.plist"

if [ ! -f "$PLIST_PATH" ]; then
    echo
    echo "Auto-start is not currently enabled (plist not found)."
    exit 0
fi

launchctl unload "$PLIST_PATH" 2>/dev/null || true
rm -f "$PLIST_PATH"

echo
echo "=== Auto-start disabled ==="
echo "A1 Mail Dynamics will no longer launch at login."
