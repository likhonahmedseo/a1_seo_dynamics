#!/bin/bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_PATH="$APP_DIR/A1 Mail Dynamics.app"
EXECUTABLE="$APP_PATH/Contents/MacOS/A1MailDynamics"
PORT=5174
URL=""
RUNTIME_FILE="$HOME/Library/Application Support/A1MailDynamics/data/runtime/active_server.json"

if [ ! -x "$EXECUTABLE" ]; then
  echo
  echo "[ERROR] Could not find the packaged A1 Mail Dynamics executable."
  echo "Keep this file beside A1 Mail Dynamics.app."
  exit 1
fi

probe_url() {
  local candidate="$1"
  if [ -z "$candidate" ]; then
    return 1
  fi
  if curl --silent --fail --max-time 2 "$candidate/api/health" >/dev/null 2>&1; then
    URL="$candidate"
    return 0
  fi
  return 1
}

if [ -f "$RUNTIME_FILE" ]; then
  EXISTING_URL="$(python3 - <<'PY' "$RUNTIME_FILE"
import json, sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    data = {}
print(data.get("url", ""))
PY
)"
  probe_url "$EXISTING_URL" || true
fi

if [ -z "$URL" ]; then
  probe_url "http://127.0.0.1:$PORT" || true
fi

if [ -z "$URL" ]; then
  echo
  echo "Opening A1 Mail Dynamics in your browser..."
  "$EXECUTABLE" --no-window --port "$PORT" >/dev/null 2>&1 &

  for _ in $(seq 1 40); do
    if [ -f "$RUNTIME_FILE" ]; then
      DETECTED_URL="$(python3 - <<'PY' "$RUNTIME_FILE"
import json, sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    data = {}
print(data.get("url", ""))
PY
)"
      probe_url "$DETECTED_URL" && break
    fi
    probe_url "http://127.0.0.1:$PORT" && break
    sleep 0.5
  done
fi

if [ -z "$URL" ]; then
  echo
  echo "[ERROR] Browser mode could not detect a healthy local app server."
  echo "Try Open Desktop App.command first, then run this launcher again."
  exit 1
fi

echo
echo "If the page does not load immediately, wait a few seconds and refresh:"
echo "  $URL"

open "$URL"
