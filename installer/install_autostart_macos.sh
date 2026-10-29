#!/bin/bash
# Installs a macOS LaunchAgent so A1 Mail Dynamics starts (minimized) at login.
# No admin rights required — runs entirely in the user's space.
set -euo pipefail

LABEL="com.a1technovation.a1maildynamics"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$PLIST_DIR/$LABEL.plist"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

APP_PATH="$PROJECT_ROOT/dist/A1 Mail Dynamics.app"
if [ ! -d "$APP_PATH" ]; then
    APP_PATH="$PROJECT_ROOT/release_dist/A1MailDynamics-macos-$(uname -m 2>/dev/null || echo arm64)/A1 Mail Dynamics.app"
fi
if [ ! -d "$APP_PATH" ]; then
    echo
    echo "[ERROR] Could not find A1 Mail Dynamics.app."
    echo "Build the app first: installer/build_macos.command"
    exit 1
fi

EXECUTABLE="$APP_PATH/Contents/MacOS/A1MailDynamics"
if [ ! -x "$EXECUTABLE" ]; then
    echo "[ERROR] Executable not found inside the app bundle: $EXECUTABLE"
    exit 1
fi

mkdir -p "$PLIST_DIR"

cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$EXECUTABLE</string>
        <string>--minimized</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>$HOME/Library/Logs/A1MailDynamics-agent.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/Library/Logs/A1MailDynamics-agent.log</string>
</dict>
</plist>
PLIST

# Reload the agent if it is already loaded
if launchctl list "$LABEL" &>/dev/null 2>&1; then
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
fi
launchctl load "$PLIST_PATH"

echo
echo "=== Auto-start enabled ==="
echo "A1 Mail Dynamics will launch (minimized) every time you sign in."
echo "Plist: $PLIST_PATH"
echo
echo "To disable auto-start run:"
echo "  installer/uninstall_autostart_macos.sh"
