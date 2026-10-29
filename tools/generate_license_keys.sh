#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON=".venv/bin/python3"

if [[ ! -f "$PYTHON" ]]; then
  echo "[ERROR] Virtual environment not found at $PYTHON"
  echo "Create it with: python3 -m venv .venv && .venv/bin/pip install cryptography"
  exit 1
fi

"$PYTHON" tools/generate_license_keys.py --private-key private/vendor-license-private.pem
