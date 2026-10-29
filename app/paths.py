"""
Single source of truth for filesystem paths.

Works in three modes:
  1. Dev — running from source: paths are relative to the project root.
  2. PyInstaller frozen .exe (one-file): paths are next to the .exe, so the
     same folder that holds A1MailDynamics.exe will hold .env, data/, logs/.
     This makes the build fully portable.
  3. PyInstaller frozen macOS app: writable state lives in
     ~/Library/Application Support/A1MailDynamics so the .app bundle stays
     clean and signable.

The module also loads the .env file once, so per-module load_dotenv() calls
become unnecessary (they're harmless if left in, but redundant).
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

PRODUCT_SLUG = "A1MailDynamics"


def _macos_app_support_root() -> Path:
    return Path.home() / "Library" / "Application Support" / PRODUCT_SLUG


def _linux_app_support_root() -> Path:
    xdg_home = Path.home() / ".local" / "share"
    return xdg_home / PRODUCT_SLUG


def _resolve_app_root() -> Path:
    """Where the app's writable data lives."""
    if getattr(sys, "frozen", False):
        # Windows one-folder builds remain fully portable beside the .exe.
        if sys.platform == "darwin":
            return _macos_app_support_root()
        if sys.platform.startswith("linux"):
            return _linux_app_support_root()
        return Path(sys.executable).resolve().parent
    # Running from source — project root (this file lives in app/)
    return Path(__file__).resolve().parents[1]


def _resolve_bundle_root(app_root: Path) -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", app_root))
    return app_root


def _copy_if_missing(source: Path, destination: Path) -> None:
    if not source.exists() or destination.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _parse_env_text(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()
    return values


def _upsert_env_value(text: str, key: str, value: str) -> str:
    lines = text.splitlines()
    updated = False
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and stripped.split("=", 1)[0].strip() == key:
            new_lines.append(f"{key}={value}")
            updated = True
        else:
            new_lines.append(line)
    if not updated:
        if new_lines and new_lines[-1].strip():
            new_lines.append("")
        new_lines.append(f"{key}={value}")
    return "\n".join(new_lines).rstrip() + "\n"


def _seed_runtime_env(dotenv_path: Path) -> None:
    """
    For frozen desktop builds, ensure the runtime .env file exists with
    production-safe defaults. Existing user settings are preserved.
    """
    import secrets

    text = dotenv_path.read_text(encoding="utf-8") if dotenv_path.exists() else ""
    parsed = _parse_env_text(text)
    updated_text = text
    changed = False

    if parsed.get("APP_ENV", "").strip().lower() != "production":
        updated_text = _upsert_env_value(updated_text, "APP_ENV", "production")
        changed = True

    secret = parsed.get("FLASK_SECRET_KEY", "").strip()
    if len(secret) < 32:
        updated_text = _upsert_env_value(updated_text, "FLASK_SECRET_KEY", secrets.token_hex(32))
        changed = True

    if changed:
        dotenv_path.parent.mkdir(parents=True, exist_ok=True)
        dotenv_path.write_text(updated_text, encoding="utf-8")


def _write_if_missing(destination: Path, text: str) -> None:
    if destination.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")


APP_ROOT     = _resolve_app_root()
BUNDLE_ROOT  = _resolve_bundle_root(APP_ROOT)
DATA_DIR     = APP_ROOT / "data"
RUNTIME_DIR  = DATA_DIR / "runtime"
ATTACH_DIR   = DATA_DIR / "attachments"
LOG_DIR      = APP_ROOT / "logs"
DOTENV_PATH  = APP_ROOT / ".env"
DOTENV_EXAMPLE_PATH = APP_ROOT / ".env.example"
README_PATH  = APP_ROOT / "README.md"
SAMPLE_CSV_PATH = DATA_DIR / "sample_contacts.csv"

_DEFAULT_ENV_EXAMPLE_TEXT = """# ── AI provider ──────────────────────────────────────────────────────────────
# Set AI_PROVIDER to one of: ollama, openai, claude, deepseek, qwen, kimi
AI_PROVIDER=ollama

# Ollama (local)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2

# OpenAI
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini

# Anthropic Claude
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-3-5-haiku-20241022

# DeepSeek  (get key at platform.deepseek.com)
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-chat

# Alibaba Qwen / DashScope  (get key at dashscope.console.aliyun.com)
QWEN_API_KEY=
QWEN_MODEL=qwen-plus

# Moonshot Kimi  (get key at platform.moonshot.cn)
KIMI_API_KEY=
KIMI_MODEL=moonshot-v1-8k

# ── SMTP ─────────────────────────────────────────────────────────────────────
# SMTP_SECURITY: starttls (port 587), ssl (port 465), none (port 25)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_SECURITY=starttls

# ── Booking / scheduling link ─────────────────────────────────────────────────
# Your Cal.com, Calendly, or similar URL. Appended to cold-outreach auto-replies.
# Leave empty to omit.
COLD_OUTREACH_BOOKING_URL=

# ── App runtime ───────────────────────────────────────────────────────────────
APP_ENV=production
FLASK_SECRET_KEY=
LOG_LEVEL=INFO
ALLOW_SELF_SIGNUP=true

# ── Auto follow-up defaults ───────────────────────────────────────────────────
FOLLOWUP_ENABLED=false
FOLLOWUP_DELAY_HOURS=24
FOLLOWUP_MAX_COUNT=2
"""

# Ensure writable directories exist on first import
for _d in (DATA_DIR, RUNTIME_DIR, ATTACH_DIR, LOG_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# In a one-file PyInstaller build, bundled data lives in the temporary
# extraction directory. Copy a few user-facing seed files next to the .exe so
# the app remains portable and self-contained after distribution.
if getattr(sys, "frozen", False):
    if sys.platform != "darwin":
        _copy_if_missing(BUNDLE_ROOT / "README.md", README_PATH)
    _copy_if_missing(BUNDLE_ROOT / "data" / "sample_contacts.csv", SAMPLE_CSV_PATH)
    _seed_runtime_env(DOTENV_PATH)
    _write_if_missing(DOTENV_EXAMPLE_PATH, _DEFAULT_ENV_EXAMPLE_TEXT)

# Load .env once. We pass override=True so the file beats stale process env vars.
# Done here (instead of in every service module) so the path is consistent
# across dev and frozen builds.
if DOTENV_PATH.exists():
    load_dotenv(dotenv_path=DOTENV_PATH, override=True)
