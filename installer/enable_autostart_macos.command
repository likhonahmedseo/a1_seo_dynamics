#!/bin/bash
# Double-click this file in Finder to enable macOS login auto-start.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
bash "$SCRIPT_DIR/install_autostart_macos.sh"
echo
read -rp "Press Return to close this window..." _
