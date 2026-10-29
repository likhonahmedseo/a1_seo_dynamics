#!/bin/bash
# Double-click in Finder to start the dev environment on macOS.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
bash "$SCRIPT_DIR/start_web_dev.sh"
