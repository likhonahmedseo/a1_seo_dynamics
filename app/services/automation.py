"""
Email automation — Gmail browser mode and throttled SMTP sending.

Throttled SMTP design
─────────────────────
Sending 300–500 cold emails in one burst is the single biggest reason they
land in spam.  Inbox providers (Gmail, Outlook, Yahoo) score senders by send
rate, volume consistency, and engagement.  Bursting all at once looks like a
compromised account or a botnet.

This module solves it with:

  • Random per-email jitter  (2–8 s between emails — looks human)
  • Batch pauses             (60–120 s after every N emails — simulates a
                              person taking a break between sessions)
  • Daily send-limit cap     (prevent accidental over-sending)
  • SSE streaming progress   (UI shows sent / remaining / ETA in real time)
  • Proper MIME + headers    (multipart, List-Unsubscribe, Message-ID, etc.)
"""
from __future__ import annotations

import logging
import mimetypes
import os
import random
import smtplib
import ssl
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Generator
from urllib.parse import quote, urlencode

import app.paths  # noqa: F401 — ensures .env is loaded
from app.models import DraftEmail
from app.services.email_renderer import build_email_message

logger = logging.getLogger(__name__)


# ── Throttle configuration ────────────────────────────────────────────────────

@dataclass
class ThrottleConfig:
    """Controls send rate.  All times are in seconds."""
    delay_min: float       = 3.0    # minimum pause between individual emails
    delay_max: float       = 8.0    # maximum pause (random in [min, max])
    batch_size: int        = 20     # send N emails, then take a longer break
    batch_pause_min: float = 60.0   # minimum batch-break duration (seconds)
    batch_pause_max: float = 120.0  # maximum batch-break duration (seconds)
    daily_limit: int       = 300    # hard cap — refuse to send more than this


# Preset mapping exposed to the API
THROTTLE_PRESETS: dict[str, ThrottleConfig] = {
    "careful": ThrottleConfig(delay_min=8,  delay_max=20, batch_size=10,
                              batch_pause_min=120, batch_pause_max=180, daily_limit=100),
    "normal":  ThrottleConfig(delay_min=4,  delay_max=10, batch_size=20,
                              batch_pause_min=60,  batch_pause_max=120, daily_limit=250),
    "fast":    ThrottleConfig(delay_min=2,  delay_max=5,  batch_size=30,
                              batch_pause_min=45,  batch_pause_max=90,  daily_limit=400),
}


def throttle_config_from_env() -> ThrottleConfig:
    """Read throttle settings from env / .env (overrides preset)."""
    preset_name = os.getenv("SMTP_THROTTLE_PRESET", "normal").strip().lower()
    base = THROTTLE_PRESETS.get(preset_name, THROTTLE_PRESETS["normal"])
    return ThrottleConfig(
        delay_min       = float(os.getenv("SMTP_DELAY_MIN",       base.delay_min)),
        delay_max       = float(os.getenv("SMTP_DELAY_MAX",       base.delay_max)),
        batch_size      = int(os.getenv("SMTP_BATCH_SIZE",        base.batch_size)),
        batch_pause_min = float(os.getenv("SMTP_BATCH_PAUSE_MIN", base.batch_pause_min)),
        batch_pause_max = float(os.getenv("SMTP_BATCH_PAUSE_MAX", base.batch_pause_max)),
        daily_limit     = int(os.getenv("SMTP_DAILY_LIMIT",       base.daily_limit)),
    )


# ── Error helpers ─────────────────────────────────────────────────────────────

def _sanitize_smtp_error(exc: BaseException) -> str:
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "SMTP authentication failed. Check SMTP_USERNAME / SMTP_PASSWORD."
    if isinstance(exc, smtplib.SMTPConnectError):
        return "Could not connect to SMTP server."
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "Recipient address was refused by the server."
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return "Sender address was refused by the server."
    if isinstance(exc, smtplib.SMTPDataError):
        return "SMTP server rejected the message."
    if isinstance(exc, (TimeoutError, OSError)):
        return "Network error reaching SMTP server."
    msg = str(exc)
    return msg[:120] if msg else exc.__class__.__name__


# ── Gmail URL builder ─────────────────────────────────────────────────────────

def build_gmail_compose_url(draft: DraftEmail) -> str:
    query = urlencode({"view": "cm", "fs": "1", "tf": "1",
                       "to": draft.email, "su": draft.subject, "body": draft.body})
    return f"https://mail.google.com/mail/?{query}"


# ── Chrome helpers ────────────────────────────────────────────────────────────

def _chrome_user_data_dir() -> str:
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    return os.path.join(local_app_data, "Google", "Chrome", "User Data")


# ── Gmail browser automation ──────────────────────────────────────────────────

def send_via_gmail_browser(
    drafts: list[DraftEmail],
    limit: int | None = None,
) -> Generator[dict, None, None]:
    """
    Controls Chrome via Playwright to compose + send each draft through Gmail.
    Yields SSE-compatible dicts.
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    to_send = drafts[:limit] if limit else drafts
    total = len(to_send)
    sent_count = 0
    failed_count = 0
    user_data_dir = _chrome_user_data_dir()

    try:
        with sync_playwright() as p:
            try:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    channel="chrome",
                    headless=False,
                    args=["--profile-directory=Default", "--no-first-run",
                          "--no-default-browser-check", "--disable-infobars"],
                    slow_mo=80,
                )
            except Exception as exc:
                msg = str(exc).lower()
                if any(k in msg for k in ("running", "lock", "already", "exit")):
                    yield {"fatal": True, "error": "Chrome is open. Close ALL Chrome windows and try again."}
                else:
                    yield {"fatal": True, "error": f"Could not launch Chrome: {exc}"}
                return

            page = context.new_page()
            page.goto("https://mail.google.com/mail/u/0/", wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(2000)

            if "accounts.google.com" in page.url:
                yield {"fatal": True, "error": "Not logged into Gmail. Open Chrome, sign in, then try again."}
                context.close()
                return

            for i, draft in enumerate(to_send):
                yield {"index": i, "email": draft.email, "status": "sending", "total": total}
                try:
                    _compose_and_send(page, draft)
                    draft.status = "sent"
                    draft.error = None
                    sent_count += 1
                    yield {"index": i, "email": draft.email, "status": "sent", "total": total}
                except PWTimeout as exc:
                    draft.status = "failed"
                    draft.error = f"Timed out: {exc}"
                    failed_count += 1
                    yield {"index": i, "email": draft.email, "status": "failed",
                           "error": draft.error, "total": total}
                except Exception as exc:
                    draft.status = "failed"
                    draft.error = str(exc)
                    failed_count += 1
                    yield {"index": i, "email": draft.email, "status": "failed",
                           "error": draft.error, "total": total}

                time.sleep(random.uniform(2.0, 5.0))

            context.close()

    except Exception as exc:
        yield {"fatal": True, "error": str(exc)}
        return

    yield {"done": True, "sent": sent_count, "failed": failed_count, "total": total}


def _compose_and_send(page, draft: DraftEmail) -> None:
    from playwright.sync_api import TimeoutError as PWTimeout

    compose_url = (
        "https://mail.google.com/mail/u/0/?view=cm&fs=1&tf=1"
        f"&to={quote(draft.email)}"
        f"&su={quote(draft.subject)}"
    )
    page.goto(compose_url, wait_until="domcontentloaded", timeout=20000)

    body_sel = 'div[aria-label="Message Body"]'
    body_el = page.wait_for_selector(body_sel, timeout=15000)
    body_el.click()

    page.evaluate(
        """(text) => {
            const el = document.querySelector('div[aria-label="Message Body"]');
            if (!el) throw new Error('Body element not found');
            el.focus();
            document.execCommand('selectAll', false, null);
            document.execCommand('insertText', false, text);
        }""",
        draft.body,
    )
    page.wait_for_timeout(500)
    page.keyboard.press("Control+Enter")

    try:
        page.wait_for_selector(body_sel, state="detached", timeout=10000)
    except PWTimeout:
        try:
            send_btn = page.locator('[data-tooltip*="Send"], [aria-label*="Send"]').first
            send_btn.click(timeout=3000)
            page.wait_for_selector(body_sel, state="detached", timeout=8000)
        except (PWTimeout, Exception) as exc:
            logger.warning("Gmail send-button fallback (likely already sent): %r", exc)

    page.wait_for_timeout(1000)


# ── Throttled SMTP sender (SSE streaming) ─────────────────────────────────────

def send_via_smtp_throttled(
    drafts: list[DraftEmail],
    sender_email: str,
    sender_name: str,
    attachment_paths: list[Path] | None = None,
    throttle: ThrottleConfig | None = None,
) -> Generator[dict, None, None]:
    """
    Send drafts via SMTP with human-like throttling and full deliverability headers.

    Yields SSE-compatible dicts every step so the UI can show live progress:
      {index, email, status:"sending", total, sent, failed, eta_seconds}
      {index, email, status:"sent"|"failed", total, sent, failed}
      {index, email, status:"batch_pause", pause_seconds, batch_num}
      {done:True, sent:N, failed:N, total:N}
      {fatal:True, error:"..."}
    """
    if throttle is None:
        throttle = throttle_config_from_env()

    total = len(drafts)
    if total == 0:
        yield {"done": True, "sent": 0, "failed": 0, "total": 0}
        return

    if total > throttle.daily_limit:
        yield {
            "fatal": True,
            "error": (
                f"Campaign has {total} emails but the daily limit is {throttle.daily_limit}. "
                f"Split into smaller batches or raise the limit in Settings → Sending."
            ),
        }
        return

    # SMTP credentials
    host     = os.getenv("SMTP_HOST", "").strip()
    port     = int(os.getenv("SMTP_PORT", "587") or 587)
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    security = os.getenv("SMTP_SECURITY", "").strip().lower()
    # Legacy fallback: if SMTP_SECURITY not set, derive from old SMTP_USE_TLS
    if not security:
        use_tls_legacy = os.getenv("SMTP_USE_TLS", "true").strip().lower() == "true"
        security = "starttls" if use_tls_legacy else "ssl"

    if not host or not username or not password:
        yield {"fatal": True, "error": "SMTP settings incomplete. Go to Settings → SMTP."}
        return

    # Pre-load attachments
    attachments: list[tuple[bytes, str, str, str]] = []
    for path in (attachment_paths or []):
        if path.exists():
            mime, _ = mimetypes.guess_type(str(path))
            maintype, subtype = (mime or "application/octet-stream").split("/", 1)
            attachments.append((path.read_bytes(), maintype, subtype, path.name))

    # ETA estimate (used in progress events)
    avg_email_delay = (throttle.delay_min + throttle.delay_max) / 2
    avg_batch_pause = (throttle.batch_pause_min + throttle.batch_pause_max) / 2
    num_batch_pauses = max(0, (total - 1) // throttle.batch_size)
    estimated_seconds = int(total * avg_email_delay + num_batch_pauses * avg_batch_pause)

    sent_count = 0
    failed_count = 0

    # Open SMTP connection
    try:
        server = _open_smtp(host, port, username, password, security)
    except Exception as exc:
        yield {"fatal": True, "error": f"Could not connect to SMTP: {_sanitize_smtp_error(exc)}"}
        return

    try:
        for i, draft in enumerate(drafts):
            remaining = total - i - 1
            batches_remaining = max(0, remaining // throttle.batch_size)
            eta = int(remaining * avg_email_delay + batches_remaining * avg_batch_pause)

            yield {
                "index": i,
                "email": draft.email,
                "status": "sending",
                "total": total,
                "sent": sent_count,
                "failed": failed_count,
                "eta_seconds": eta,
            }

            # Build deliverability-optimised message
            try:
                msg = build_email_message(
                    subject=draft.subject,
                    body_text=draft.body,
                    sender_email=sender_email,
                    sender_name=sender_name,
                    recipient_email=draft.email,
                    attachments=attachments if attachments else None,
                )
            except Exception as exc:
                logger.error("Message build failed for %s: %r", draft.email, exc)
                draft.status = "failed"
                draft.error = "Could not build email message."
                failed_count += 1
                yield {"index": i, "email": draft.email, "status": "failed",
                       "error": draft.error, "total": total,
                       "sent": sent_count, "failed": failed_count}
                continue

            # Send with one auto-reconnect on transient connection drop
            draft = _try_send(server, msg, draft)
            if draft.status == "failed" and "connect" in (draft.error or "").lower():
                logger.info("Reconnecting SMTP...")
                try:
                    server.quit()
                except Exception:
                    pass
                try:
                    server = _open_smtp(host, port, username, password, security)
                    draft = _try_send(server, msg, draft)
                except Exception as exc:
                    draft.status = "failed"
                    draft.error = _sanitize_smtp_error(exc)

            if draft.status == "sent":
                sent_count += 1
            else:
                failed_count += 1

            yield {
                "index": i,
                "email": draft.email,
                "status": draft.status,
                "total": total,
                "sent": sent_count,
                "failed": failed_count,
                **({"error": draft.error} if draft.error else {}),
            }

            # Throttle — batch pause or per-email jitter
            if i < total - 1:
                emails_in_batch = (i + 1) % throttle.batch_size
                if emails_in_batch == 0:
                    pause = random.uniform(throttle.batch_pause_min, throttle.batch_pause_max)
                    batch_num = (i + 1) // throttle.batch_size
                    logger.info("Batch %d done — pausing %.0fs.", batch_num, pause)
                    yield {
                        "index": i,
                        "email": draft.email,
                        "status": "batch_pause",
                        "pause_seconds": int(pause),
                        "batch_num": batch_num,
                        "total": total,
                        "sent": sent_count,
                        "failed": failed_count,
                    }
                    time.sleep(pause)
                else:
                    time.sleep(random.uniform(throttle.delay_min, throttle.delay_max))

    finally:
        try:
            server.quit()
        except Exception:
            pass

    yield {"done": True, "sent": sent_count, "failed": failed_count,
           "total": total, "estimated_seconds": estimated_seconds}


def _open_smtp(host: str, port: int, username: str, password: str, security: str = "starttls") -> smtplib.SMTP:
    """
    Open an authenticated SMTP connection.

    security values:
      "starttls"  — plain SMTP + STARTTLS upgrade (port 587, most providers)
      "ssl"       — SMTP_SSL wrapper (port 465, implicit TLS)
      "none"      — plain/unencrypted SMTP (port 25, internal relays only)
    """
    ctx = ssl.create_default_context()
    sec = (security or "starttls").strip().lower()

    if sec == "ssl":
        server = smtplib.SMTP_SSL(host, port, context=ctx, timeout=30)
    elif sec == "none":
        server = smtplib.SMTP(host, port, timeout=30)
        server.ehlo()
    else:  # starttls (default)
        server = smtplib.SMTP(host, port, timeout=30)
        server.ehlo()
        server.starttls(context=ctx)
        server.ehlo()

    if username and password:
        server.login(username, password)
    return server


def _try_send(server: smtplib.SMTP, msg, draft: DraftEmail) -> DraftEmail:
    try:
        server.send_message(msg)
        draft.status = "sent"
        draft.error = None
    except smtplib.SMTPException as exc:
        logger.error("SMTP send failed for %s: %r", draft.email, exc)
        draft.status = "failed"
        draft.error = _sanitize_smtp_error(exc)
    except Exception as exc:
        logger.exception("Unexpected error sending to %s", draft.email)
        draft.status = "failed"
        draft.error = "Unexpected send error — check server logs."
    return draft


# ── Legacy send_via_smtp (kept for backward compatibility) ────────────────────

def send_via_smtp(
    drafts: list[DraftEmail],
    sender_email: str,
    attachment_paths: list[Path] | None = None,
) -> list[DraftEmail]:
    """Non-streaming SMTP send.  For campaigns use send_via_smtp_throttled."""
    host     = os.getenv("SMTP_HOST", "")
    port     = int(os.getenv("SMTP_PORT", "587") or 587)
    username = os.getenv("SMTP_USERNAME", "")
    password = os.getenv("SMTP_PASSWORD", "")
    security = os.getenv("SMTP_SECURITY", "").strip().lower()
    if not security:
        use_tls_legacy = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
        security = "starttls" if use_tls_legacy else "ssl"

    if not host or not username or not password:
        raise ValueError("SMTP settings incomplete. Add SMTP_HOST, SMTP_USERNAME, and SMTP_PASSWORD.")

    attachments: list[tuple[bytes, str, str, str]] = []
    for path in (attachment_paths or []):
        if path.exists():
            mime, _ = mimetypes.guess_type(str(path))
            maintype, subtype = (mime or "application/octet-stream").split("/", 1)
            attachments.append((path.read_bytes(), maintype, subtype, path.name))

    server = _open_smtp(host, port, username, password, security)
    updated: list[DraftEmail] = []
    try:
        for draft in drafts:
            msg = build_email_message(
                subject=draft.subject,
                body_text=draft.body,
                sender_email=sender_email,
                sender_name=username,
                recipient_email=draft.email,
                attachments=attachments if attachments else None,
            )
            updated.append(_try_send(server, msg, draft))
    finally:
        try:
            server.quit()
        except Exception:
            pass
    return updated
