from __future__ import annotations

import logging
import os
import re
import smtplib
import ssl
from datetime import datetime, timedelta
from email.message import EmailMessage
from typing import Any, Callable

from app.logging_config import mask_email
from app.services.ai import classify_reply, generate_auto_reply, generate_follow_up

logger = logging.getLogger(__name__)

AUTO_REPLY_SEND_DELAY_SECONDS = 30 * 60
FOLLOW_UP_SEND_DELAY_SECONDS = 5 * 60


def _norm(addr: str) -> str:
    """Lowercase + trim email for comparison/storage keys."""
    return (addr or "").strip().lower()


# ── Follow-up config (read live from env each call so settings updates apply) ─

def _followup_config() -> dict[str, Any]:
    return {
        "enabled":      os.getenv("FOLLOWUP_ENABLED", "false").strip().lower() == "true",
        "delay_hours":  max(1, int(os.getenv("FOLLOWUP_DELAY_HOURS", "24") or 24)),
        "max_count":    max(1, int(os.getenv("FOLLOWUP_MAX_COUNT", "2") or 2)),
    }


def _pending_send_delay_seconds(classification: str | None) -> int:
    if classification == "follow_up":
        return FOLLOW_UP_SEND_DELAY_SECONDS
    return AUTO_REPLY_SEND_DELAY_SECONDS

# Safety limits
MAX_AUTO_REPLIES = 3

# If any of these appear in a reply body, close the thread permanently
STOP_PHRASES = frozenset({
    "unsubscribe",
    "remove me",
    "remove from",
    "stop emailing",
    "stop contacting",
    "not interested",
    "no thank you",
    "no thanks",
    "please don't",
    "do not contact",
    "don't contact",
    "opt out",
})


class ConversationManager:
    """
    Manages per-contact conversation threads.
    - Receives reply dicts from InboxMonitor
    - Classifies reply intent via AI
    - Generates auto-replies via AI
    - Sends replies via SMTP
    - Persists all threads in state storage
    """

    def __init__(
        self,
        load_state_fn: Callable[[], dict[str, Any]],
        save_state_fn: Callable[..., None],
        get_config_fn: Callable[[], dict[str, Any]],
    ) -> None:
        self._load_state = load_state_fn
        self._save_state = save_state_fn
        self._get_config = get_config_fn

    # ── Public getters ────────────────────────────────────────────────────────

    def get_all(self) -> list[dict[str, Any]]:
        return self._load_state().get("conversations", [])

    def get_by_email(self, addr: str) -> dict[str, Any] | None:
        return next(
            (c for c in self.get_all() if _norm(c["email"]) == _norm(addr)),
            None,
        )

    # ── Bootstrap from sent drafts ────────────────────────────────────────────

    def init_from_drafts(self, drafts: list[dict[str, Any]]) -> None:
        """
        Create a fresh conversation thread for every draft that was just sent.
        Called by the /api/generate and /api/send-gmail endpoints after sending.
        """
        convs = self.get_all()
        existing = {_norm(c["email"]) for c in convs}

        for draft in drafts:
            if draft.get("status") != "sent":
                continue
            addr_norm = _norm(draft["email"])
            if not addr_norm or addr_norm in existing:
                continue

            convs.append(_new_thread(
                email=addr_norm,  # store normalised so future lookups are stable
                initial_body=draft.get("body", ""),
                initial_subject=draft.get("subject", ""),
            ))
            existing.add(addr_norm)

        self._save_state(conversations=convs)

    # ── Reply processing pipeline ─────────────────────────────────────────────

    def process_reply(self, reply_info: dict[str, Any]) -> None:
        """
        Main entry point called by InboxMonitor for each new reply.
        Runs the full classify → generate → send pipeline.
        """
        sender = _norm(_extract_email(reply_info.get("from", "")))
        body   = reply_info.get("body", "").strip()
        message_id = (reply_info.get("message_id") or "").strip()

        if not sender or not body:
            return

        masked = mask_email(sender)
        convs = self.get_all()
        if message_id and self._reply_already_recorded(convs, message_id):
            logger.info("Reply %s already processed for %s — skipping.", message_id, masked)
            return
        conv  = next((c for c in convs if _norm(c["email"]) == sender), None)

        if conv is None:
            # Unsolicited reply — create a thread so we can track it
            conv = _new_thread(email=sender)
            convs.append(conv)

        # --- Guard rails ---
        if conv["status"] in ("not_interested", "closed"):
            logger.info("Thread with %s is closed — skipping.", masked)
            return

        if conv["auto_reply_count"] >= MAX_AUTO_REPLIES:
            conv["status"] = "limit_reached"
            self._save_state(conversations=convs)
            logger.info("Max auto-replies reached for %s.", masked)
            return

        # --- Log their inbound message ---
        inbound: dict[str, Any] = {
            "direction": "received",
            "body": body,
            "subject": reply_info.get("subject", ""),
            "timestamp": datetime.utcnow().isoformat(),
            "classification": None,
        }
        if message_id:
            inbound["message_id"] = message_id
        conv["messages"].append(inbound)

        # --- Check for explicit opt-out ---
        body_lower = body.lower()
        if any(phrase in body_lower for phrase in STOP_PHRASES):
            inbound["classification"] = "not_interested"
            conv["status"] = "not_interested"
            self._save_state(conversations=convs)
            logger.info("Stop phrase detected from %s. Closing thread.", masked)
            return

        # --- Classify reply ---
        config = self._get_config()
        try:
            classification = classify_reply(body)
        except Exception as exc:
            logger.error("Classification failed for %s: %r", masked, exc)
            classification = "other"

        inbound["classification"] = classification

        if classification == "not_interested":
            conv["status"] = "not_interested"
            self._save_state(conversations=convs)
            return

        if classification == "out_of_office":
            # Don't reply, just track it
            conv["last_activity"] = datetime.utcnow().isoformat()
            self._save_state(conversations=convs)
            return

        # --- Generate auto-reply ---
        try:
            reply_body = generate_auto_reply(
                thread_messages=conv["messages"],
                latest_reply=body,
                classification=classification,
                config_dict=config,
            )
        except Exception as exc:
            logger.error("Auto-reply generation failed for %s: %r", masked, exc, exc_info=True)
            inbound["error"] = "AI generation failed (see server logs)."
            self._save_state(conversations=convs)
            return

        if reply_body == "SKIP":
            self._save_state(conversations=convs)
            return

        # --- Queue auto-reply as pending ---
        original_subject = reply_info.get("subject", "")
        reply_subject = (
            original_subject if original_subject.lower().startswith("re:")
            else f"Re: {original_subject}"
        )

        conv["pending_auto_reply"] = {
            "subject": reply_subject,
            "body": reply_body,
            "classification": classification,
            "generated_at": datetime.utcnow().isoformat(),
            "auto_send_after_seconds": _pending_send_delay_seconds(classification),
        }

        self._save_state(conversations=convs)
        logger.info("Auto-reply generated and pending approval for %s", masked)

    def check_followups(self) -> None:
        """
        Scan threads for ones that need a follow-up and queue an AI-drafted
        follow-up as a pending_auto_reply.
        """
        cfg = _followup_config()
        if not cfg["enabled"]:
            return

        now = datetime.utcnow()
        cutoff = now - timedelta(hours=cfg["delay_hours"])
        max_count = cfg["max_count"]

        convs = self.get_all()
        changed = False

        for conv in convs:
            # Skip if thread is closed / opted-out / capped
            if conv.get("status") in ("not_interested", "closed", "limit_reached", "out_of_office"):
                continue
            if conv.get("follow_up_count", 0) >= max_count:
                continue
            # Don't pile a follow-up on top of a pending reply
            if conv.get("pending_auto_reply"):
                continue
            # Only follow up when the last message direction is "sent"
            messages = conv.get("messages", [])
            if not messages or messages[-1].get("direction") != "sent":
                continue
            # Time check
            outbound_iso = conv.get("last_outbound_at") or messages[-1].get("timestamp")
            if not outbound_iso:
                continue
            try:
                outbound_at = datetime.fromisoformat(outbound_iso)
            except ValueError:
                continue
            if outbound_at > cutoff:
                continue

            # Generate the follow-up
            masked = mask_email(conv["email"])
            follow_up_n = conv.get("follow_up_count", 0) + 1
            try:
                config_dict = self._get_config()
                subject, body = generate_follow_up(
                    thread_messages=messages,
                    config_dict=config_dict,
                    follow_up_number=follow_up_n,
                )
            except Exception:
                logger.exception("Follow-up generation failed for %s", masked)
                continue

            if not body.strip():
                continue

            conv["pending_auto_reply"] = {
                "subject":        subject if subject else "Following up",
                "body":           body,
                "classification": "follow_up",
                "generated_at":   now.isoformat(),
                "auto_send_after_seconds": _pending_send_delay_seconds("follow_up"),
            }
            changed = True
            logger.info(
                "Follow-up #%d queued for %s (silent for %dh)",
                follow_up_n, masked, int((now - outbound_at).total_seconds() / 3600),
            )

        if changed:
            self._save_state(conversations=convs)

    def check_pending_replies(self) -> None:
        """Called periodically to auto-send pending drafts once their delay elapses."""
        convs = self.get_all()
        changed = False
        now = datetime.utcnow()

        for conv in convs:
            pending = conv.get("pending_auto_reply")
            if pending:
                gen_at_str = pending.get("generated_at")
                if gen_at_str:
                    try:
                        gen_at = datetime.fromisoformat(gen_at_str)
                    except ValueError:
                        continue

                    send_after_seconds = int(
                        pending.get("auto_send_after_seconds")
                        or _pending_send_delay_seconds(pending.get("classification"))
                    )
                    if (now - gen_at).total_seconds() >= send_after_seconds:
                        self._send_and_clear_pending(conv, pending)
                        changed = True

        if changed:
            self._save_state(conversations=convs)

    def approve_pending_reply(self, addr: str, edited_body: str | None = None) -> None:
        convs = self.get_all()
        conv = next((c for c in convs if _norm(c["email"]) == _norm(addr)), None)
        if not conv or "pending_auto_reply" not in conv:
            raise ValueError(f"No pending reply found for {addr}")
        
        pending = conv["pending_auto_reply"]
        if edited_body is not None:
            pending["body"] = edited_body
        
        self._send_and_clear_pending(conv, pending)
        self._save_state(conversations=convs)

    def cancel_pending_reply(self, addr: str) -> None:
        convs = self.get_all()
        conv = next((c for c in convs if _norm(c["email"]) == _norm(addr)), None)
        if not conv or "pending_auto_reply" not in conv:
            raise ValueError(f"No pending reply found for {addr}")
        
        del conv["pending_auto_reply"]
        self._save_state(conversations=convs)

    def _send_and_clear_pending(self, conv: dict[str, Any], pending: dict[str, Any]) -> None:
        sender = conv["email"]
        reply_subject = pending["subject"]
        reply_body = pending["body"]
        classification = pending.get("classification", "auto_reply")

        outbound: dict[str, Any] = {
            "direction": "sent",
            "subject": reply_subject,
            "body": reply_body,
            "timestamp": datetime.utcnow().isoformat(),
            "classification": classification,
        }

        try:
            _smtp_send(
                to_email=sender,
                subject=reply_subject,
                body=reply_body,
            )
            now_iso = datetime.utcnow().isoformat()
            conv["last_activity"]    = now_iso
            conv["last_outbound_at"] = now_iso

            # Distinguish follow-ups from auto-replies for capping purposes
            if classification == "follow_up":
                conv["follow_up_count"] = conv.get("follow_up_count", 0) + 1
            else:
                conv["auto_reply_count"] = conv.get("auto_reply_count", 0) + 1
                if classification == "interested":
                    conv["status"] = "progressing"

            conv["messages"].append(outbound)
            reply_num = conv["follow_up_count"] if classification == "follow_up" else conv["auto_reply_count"]
            logger.info(
                "Auto-reply sent to %s (classification=%s, reply #%d)",
                mask_email(sender), classification, reply_num,
            )

        except smtplib.SMTPException as exc:
            outbound["error"] = "SMTP send failed (see server logs)."
            outbound["classification"] = "auto_reply_failed"
            conv["messages"].append(outbound)
            logger.error("SMTP send failed for %s: %r", mask_email(sender), exc)
        except Exception as exc:
            outbound["error"] = "Unexpected error sending reply."
            outbound["classification"] = "auto_reply_failed"
            conv["messages"].append(outbound)
            logger.exception("Unexpected error sending auto-reply to %s", mask_email(sender))

        del conv["pending_auto_reply"]

    def _reply_already_recorded(self, convs: list[dict[str, Any]], message_id: str) -> bool:
        for conv in convs:
            for message in conv.get("messages", []):
                if (message.get("message_id") or "").strip() == message_id:
                    return True
        return False


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _new_thread(
    email: str,
    initial_body: str = "",
    initial_subject: str = "",
) -> dict[str, Any]:
    now = datetime.utcnow().isoformat()
    thread: dict[str, Any] = {
        "email":             email,
        "status":            "active",
        "auto_reply_count":  0,
        "follow_up_count":   0,
        "created_at":        now,
        "last_activity":     now,
        "last_outbound_at":  now if initial_body else None,
        "messages":          [],
    }
    if initial_body:
        thread["messages"].append({
            "direction":      "sent",
            "body":           initial_body,
            "subject":        initial_subject,
            "timestamp":      now,
            "classification": "initial_outreach",
        })
    return thread


def _extract_email(from_field: str) -> str:
    """Extract bare email address from a 'Name <email>' header value."""
    m = re.search(r"<([^>]+)>", from_field)
    return m.group(1).strip() if m else from_field.strip()


def _smtp_send(to_email: str, subject: str, body: str) -> None:
    host = os.getenv("SMTP_HOST", "")
    try:
        port = int(os.getenv("SMTP_PORT", "587"))
    except ValueError:
        port = 587
    username = os.getenv("SMTP_USERNAME", "")
    password = os.getenv("SMTP_PASSWORD", "")
    security = os.getenv("SMTP_SECURITY", "").strip().lower()
    if not security:
        use_tls_legacy = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
        security = "starttls" if use_tls_legacy else "ssl"

    if not host or not username or not password:
        raise ValueError(
            "SMTP credentials are not configured. "
            "Set SMTP_HOST, SMTP_USERNAME, and SMTP_PASSWORD in .env."
        )

    msg = EmailMessage()
    msg["From"]    = username
    msg["To"]      = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    ctx = ssl.create_default_context()
    if security == "ssl":
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as server:
            server.login(username, password)
            server.send_message(msg)
    elif security == "none":
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.ehlo()
            if username and password:
                server.login(username, password)
            server.send_message(msg)
    else:  # starttls (default)
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.ehlo()
            server.starttls(context=ctx)
            server.ehlo()
            server.login(username, password)
            server.send_message(msg)
