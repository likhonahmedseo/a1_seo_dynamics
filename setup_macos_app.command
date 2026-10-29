#!/bin/bash
# One-click macOS setup: builds the desktop app and optionally enables auto-start.
# Double-click in Finder, or run from Terminal: bash setup_macos_app.command
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo
echo "================================================="
echo "  A1 Mail Dynamics — macOS Setup"
echo "================================================="
echo

# ── 1. Check prerequisites ──────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] Python 3 is not installed."
    echo "Install it from https://www.python.org/downloads/ or via Homebrew:"
    echo "  brew install python"
    exit 1
fi

PYTHON_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")
if [ "$PYTHON_MINOR" -lt 11 ]; then
    echo "[ERROR] Python 3.11+ is required (found 3.$PYTHON_MINOR)."
    echo "Upgrade at https://www.python.org/downloads/"
    exit 1
fi

if ! command -v node &>/dev/null; then
    echo "[ERROR] Node.js is not installed."
    echo "Install it from https://nodejs.org/ or via Homebrew:"
    echo "  brew install node"
    exit 1
fi

NODE_MAJOR=$(node -e "process.stdout.write(process.versions.node.split('.')[0])")
if [ "$NODE_MAJOR" -lt 18 ]; then
    echo "[ERROR] Node.js 18+ is required (found $NODE_MAJOR)."
    echo "Upgrade at https://nodejs.org/"
    exit 1
fi

echo "✓ Python $(python3 --version | awk '{print $2}') detected"
echo "✓ Node.js $(node --version) detected"
echo

# ── 2. Build the app ─────────────────────────────────────────────────────────
echo "Building the macOS desktop app (this takes 2–4 minutes)..."
echo
python3 installer/build.py --platform macos

echo
echo "================================================="
echo "  Build complete!"
echo "================================================="

ARCH=$(python3 -c "import platform; m=platform.machine().lower(); print('arm64' if m in ('arm64','aarch64') else 'x64')")
RELEASE_DIR="release_dist/A1MailDynamics-macos-$ARCH"

echo
echo "App bundle: dist/A1 Mail Dynamics.app"
echo "Release folder: $RELEASE_DIR"
echo "ZIP archive: $RELEASE_DIR.zip"
echo

# ── 3. Optional auto-start ────────────────────────────────────────────────────
echo -n "Enable auto-start at login? (minimized, no admin required) [y/N] "
read -r AUTOSTART
if [[ "${AUTOSTART,,}" == "y" ]]; then
    bash installer/install_autostart_macos.sh
fi

echo
echo "================================================="
echo "  DONE"
echo "================================================="
echo
echo "To open the app:"
echo "  open \"$RELEASE_DIR/A1 Mail Dynamics.app\""
echo "  — or double-click 'Open Desktop App.command' in $RELEASE_DIR/"
echo
echo "To open in browser only:"
echo "  double-click 'Open in Browser.command' in $RELEASE_DIR/"
echo
read -rp "Press Return to close this window..." _
