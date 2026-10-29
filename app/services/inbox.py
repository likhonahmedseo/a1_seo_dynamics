from __future__ import annotations

import email
import imaplib
import logging
import os
import threading
import time
from datetime import datetime, timedelta
from email.header import decode_header as _decode_header

import app.paths  # noqa: F401 — ensures .env is loaded
from app.logging_config import mask_email

logger = logging.getLogger(__name__)


class InboxMonitor:
    """
    Background thread that polls Gmail IMAP every 2 minutes for new replies.
    When a reply is found, it fires reply_callback(reply_info_dict).
    """

    POLL_INTERVAL = 120  # seconds

    def __init__(self, reply_callback):
        self._callback = reply_callback
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._running = False
        self._last_checked: datetime | None = None
        self._pending_replies: int = 0
        # Keep track of already-processed UIDs to avoid double-firing
        self._seen_uids: set[str] = set()

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="InboxMonitor")
        self._thread.start()
        self._running = True
        logger.info("InboxMonitor started.")

    def stop(self) -> None:
        self._stop_event.set()
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None
        logger.info("InboxMonitor stopped.")

    def status(self) -> dict:
        return {
            "running": self._running,
            "last_checked": self._last_checked.isoformat() if self._last_checked else None,
            "poll_interval_seconds": self.POLL_INTERVAL,
            "replies_processed": len(self._seen_uids),
        }

    # ── Internal loop ─────────────────────────────────────────────────────────

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._check_inbox()
            except Exception as exc:
                logger.error(f"InboxMonitor check failed: {exc}")
            self._last_checked = datetime.utcnow()
            # Wait for the interval, but wake immediately if stop is called
            self._stop_event.wait(timeout=self.POLL_INTERVAL)

    def _check_inbox(self) -> None:
        host = os.getenv("IMAP_HOST", "imap.gmail.com")
        try:
            port = int(os.getenv("IMAP_PORT", "993"))
        except ValueError:
            port = 993
        # Prefer dedicated IMAP creds; fall back to SMTP creds for convenience (Gmail)
        username = os.getenv("IMAP_USERNAME") or os.getenv("SMTP_USERNAME", "")
        password = os.getenv("IMAP_PASSWORD") or os.getenv("SMTP_PASSWORD", "")

        if not username or not password:
            raise ValueError(
                "IMAP credentials not configured. "
                "Set IMAP_USERNAME / IMAP_PASSWORD (or SMTP_USERNAME / SMTP_PASSWORD) in .env."
            )

        with imaplib.IMAP4_SSL(host, port) as imap:
            try:
                imap.login(username, password)
            except imaplib.IMAP4.error as exc:
                # Don't log the password; just the failure class
                raise RuntimeError(f"IMAP login failed for {mask_email(username)}: authentication rejected") from exc
            imap.select("INBOX")

            # Only look at messages from the last 7 days
            since = (datetime.now() - timedelta(days=7)).strftime("%d-%b-%Y")
            _, data = imap.search(None, f'(SINCE "{since}")')

            if not data or not data[0]:
                return

            for uid in data[0].decode().split():
                if uid in self._seen_uids:
                    continue
                self._seen_uids.add(uid)

                try:
                    _, msg_data = imap.fetch(uid, "(RFC822)")
                    raw = msg_data[0][1]
                    parsed = email.message_from_bytes(raw)

                    subject  = _header_str(parsed.get("Subject", ""))
                    from_hdr = parsed.get("From", "")
                    body     = _extract_body(parsed)

                    # Only process actual replies (not our own sent messages)
                    is_reply = (
                        subject.strip().lower().startswith("re:")
                        or parsed.get("In-Reply-To") is not None
                    )
                    # Skip empty bodies
                    if not is_reply or not body.strip():
                        continue

                    reply_info = {
                        "uid": uid,
                        "message_id": parsed.get("Message-ID", "").strip(),
                        "from": from_hdr,
                        "subject": subject,
                        "body": body,
                        # Normalised subject without "Re:" prefix for thread matching
                        "original_subject": subject.strip().lower().lstrip("re:").strip(),
                        "received_at": datetime.utcnow().isoformat(),
                    }

                    logger.info("Reply detected from %s (subject hash=%d)", mask_email(from_hdr), hash(subject) & 0xFFFF)
                    self._callback(reply_info)

                except Exception as exc:
                    logger.error("Error processing IMAP uid=%s: %r", uid, exc)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _header_str(value: str) -> str:
    """Decode a possibly encoded email header string to plain text."""
    parts = _decode_header(value)
    decoded: list[str] = []
    for chunk, charset in parts:
        if isinstance(chunk, bytes):
            decoded.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(str(chunk))
    return "".join(decoded)


def _extract_body(msg: email.message.Message) -> str:
    """Extract plain-text body, stripping quoted original lines."""
    body = ""

    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    body = payload.decode(charset, errors="replace")
                    break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            body = payload.decode(charset, errors="replace")

    # Remove quoted lines (starts with ">") and "On ... wrote:" lines
    clean: list[str] = []
    for line in body.split("\n"):
        stripped = line.strip()
        if stripped.startswith(">"):
            continue
        if stripped.lower().startswith("on ") and stripped.endswith("wrote:"):
            break  # everything after this is quoted
        clean.append(line)

    return "\n".join(clean).strip()
