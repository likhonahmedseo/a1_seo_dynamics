#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# A1 Mail Dynamics — Production Web Server Starter (macOS / Linux)
#
# Runs the Waitress WSGI server with the production-built React frontend.
# No Docker required. Suitable for a VPS, Mac server, or local LAN deployment.
#
# Prerequisites:
#   • Python 3.11+  (pip available)
#   • Node.js 18+   (npm available)
#   • .env configured (copy from .env.example)
#
# Usage:
#   chmod +x start_web_production.sh
#   ./start_web_production.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"
CLIENT_DIR="$PROJECT_ROOT/client"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${GREEN}[A1]${NC} $*"; }
warn()  { echo -e "${YELLOW}[A1]${NC} $*"; }
error() { echo -e "${RED}[A1]${NC} $*"; exit 1; }
step()  { echo -e "${CYAN}[A1]${NC} $*"; }

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  A1 Mail Dynamics — Production Web Server"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo

# ── .env guard ────────────────────────────────────────────────────────────────
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    if [ -f "$PROJECT_ROOT/.env.example" ]; then
        warn ".env not found — copying from .env.example."
        warn "Edit .env before production use (add FLASK_SECRET_KEY, SMTP creds, etc.)."
        cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
    else
        error ".env file is missing. Create it from .env.example."
    fi
fi

# Force production mode
grep -qE "^APP_ENV=" "$PROJECT_ROOT/.env" \
    && sed -i.bak 's/^APP_ENV=.*/APP_ENV=production/' "$PROJECT_ROOT/.env" \
    || echo "APP_ENV=production" >> "$PROJECT_ROOT/.env"

# Validate secret key length
SECRET_LINE="$(grep -E "^FLASK_SECRET_KEY=" "$PROJECT_ROOT/.env" || true)"
SECRET_VALUE="${SECRET_LINE#*=}"
if [ ${#SECRET_VALUE} -lt 32 ]; then
    NEW_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i.bak "s/^FLASK_SECRET_KEY=.*/FLASK_SECRET_KEY=$NEW_SECRET/" "$PROJECT_ROOT/.env" \
        || echo "FLASK_SECRET_KEY=$NEW_SECRET" >> "$PROJECT_ROOT/.env"
    info "Generated a new FLASK_SECRET_KEY."
fi
rm -f "$PROJECT_ROOT/.env.bak"

# ── Python venv ───────────────────────────────────────────────────────────────
step "[1/4] Setting up Python environment..."
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi
PYTHON="$VENV_DIR/bin/python3"
[ -f "$PYTHON" ] || PYTHON="$VENV_DIR/bin/python"
"$PYTHON" -m pip install --quiet --upgrade pip
"$PYTHON" -m pip install --quiet -r "$PROJECT_ROOT/requirements.txt"
info "Python environment ready."

# ── Frontend build ────────────────────────────────────────────────────────────
step "[2/4] Building React frontend..."
if [ -f "$CLIENT_DIR/package-lock.json" ]; then
    npm --prefix "$CLIENT_DIR" ci --silent
else
    npm --prefix "$CLIENT_DIR" install --silent
fi
npm --prefix "$CLIENT_DIR" run build
info "Frontend build complete → client/dist/"

# ── Playwright (optional — Gmail automation) ──────────────────────────────────
step "[3/4] Checking Playwright browser..."
"$PYTHON" -m playwright install chrome 2>/dev/null \
    || "$PYTHON" -m playwright install chromium 2>/dev/null \
    || warn "Playwright install skipped — Gmail automation won't work."

# ── Runtime dirs ──────────────────────────────────────────────────────────────
mkdir -p "$PROJECT_ROOT/data/runtime" "$PROJECT_ROOT/data/attachments" "$PROJECT_ROOT/logs"

# ── Start server ──────────────────────────────────────────────────────────────
step "[4/4] Starting Waitress production server..."

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-5000}"

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  App URL:  http://$HOST:$PORT"
echo "  Logs:     logs/app.log"
echo "  Press Ctrl+C to stop."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo

# Open browser on macOS
if command -v open &>/dev/null && [ "$HOST" = "127.0.0.1" ]; then
    (sleep 2 && open "http://$HOST:$PORT") &
fi

cd "$PROJECT_ROOT"
export APP_ENV=production
export PYTHONUNBUFFERED=1
exec "$PYTHON" -m app.main
