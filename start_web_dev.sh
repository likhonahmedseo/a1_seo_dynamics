#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# A1 Mail Dynamics — Web Development Starter (macOS / Linux)
#
# Starts the Flask backend on port 5000 and the Vite dev server on port 5173.
# Hot-reload is active on both ends. Navigate to http://localhost:5173
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"
CLIENT_DIR="$PROJECT_ROOT/client"

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

info()  { echo -e "${GREEN}[A1]${NC} $*"; }
warn()  { echo -e "${YELLOW}[A1]${NC} $*"; }
error() { echo -e "${RED}[A1]${NC} $*"; }

# ── Prerequisite checks ───────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    error "Python 3 is not installed. Install from https://python.org"
    exit 1
fi
if ! command -v node &>/dev/null; then
    error "Node.js is not installed. Install from https://nodejs.org"
    exit 1
fi

# ── Python virtual environment ────────────────────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    info "Creating Python virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

PYTHON="$VENV_DIR/bin/python3"
if [ ! -f "$PYTHON" ]; then
    PYTHON="$VENV_DIR/bin/python"
fi

info "Installing / updating Python dependencies..."
"$PYTHON" -m pip install --quiet --upgrade pip
"$PYTHON" -m pip install --quiet -r "$PROJECT_ROOT/requirements.txt"

# ── Playwright browser (needed for Gmail automation) ──────────────────────────
info "Checking Playwright browser..."
"$PYTHON" -m playwright install chrome 2>/dev/null \
    || "$PYTHON" -m playwright install chromium 2>/dev/null \
    || warn "Playwright install skipped — Gmail automation won't be available."

# ── Node dependencies ─────────────────────────────────────────────────────────
info "Installing Node dependencies..."
if [ -f "$CLIENT_DIR/package-lock.json" ]; then
    npm --prefix "$CLIENT_DIR" ci --silent
else
    npm --prefix "$CLIENT_DIR" install --silent
fi

# ── Copy .env.example → .env if needed ───────────────────────────────────────
if [ ! -f "$PROJECT_ROOT/.env" ] && [ -f "$PROJECT_ROOT/.env.example" ]; then
    warn ".env not found — copying from .env.example (edit before production use)."
    cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
fi

# ── Launch servers ────────────────────────────────────────────────────────────
cleanup() {
    info "Shutting down servers..."
    kill "$FLASK_PID" "$VITE_PID" 2>/dev/null || true
    wait "$FLASK_PID" "$VITE_PID" 2>/dev/null || true
    info "Done."
}
trap cleanup EXIT INT TERM

info "Starting Flask backend on http://127.0.0.1:5000 ..."
cd "$PROJECT_ROOT"
PYTHONUNBUFFERED=1 "$PYTHON" -m app.main &
FLASK_PID=$!

info "Starting Vite dev server on http://localhost:5173 ..."
npm --prefix "$CLIENT_DIR" run dev &
VITE_PID=$!

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  A1 Mail Dynamics — Dev Mode"
echo ""
echo "  Frontend (hot-reload):  http://localhost:5173"
echo "  Backend API:            http://127.0.0.1:5000"
echo ""
echo "  Press Ctrl+C to stop both servers."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo

# Open browser after short delay
sleep 2
if command -v open &>/dev/null; then
    open "http://localhost:5173"
elif command -v xdg-open &>/dev/null; then
    xdg-open "http://localhost:5173" &
fi

wait "$FLASK_PID" "$VITE_PID"
