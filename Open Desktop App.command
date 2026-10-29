#!/bin/bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_PATH="$APP_DIR/A1 Mail Dynamics.app"

if [ ! -d "$APP_PATH" ]; then
  echo
  echo "[ERROR] A1 Mail Dynamics.app was not found beside this launcher."
  echo "Keep this file in the same folder as the app bundle."
  exit 1
fi

open "$APP_PATH"
