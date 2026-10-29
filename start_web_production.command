#!/bin/bash
# Double-click in Finder to start the production web server on macOS.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
bash "$SCRIPT_DIR/start_web_production.sh"
read -rp "Press Return to close this window..." _
