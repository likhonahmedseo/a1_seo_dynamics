from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
import secrets
import smtplib
import ssl
import sys
import threading
import time
from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from flask import Flask, Response, jsonify, request, send_file, session, stream_with_context
import requests as http_requests

from app.paths import APP_ROOT, ATTACH_DIR as _ATTACH_DIR, DATA_DIR, SAMPLE_CSV_PATH  # noqa: E402 (paths must come first)
from app.logging_config import configure_logging
from app.models import CampaignConfig, DraftEmail
from app.services.ai import generate_email_copy
from app.services.automation import (
    build_gmail_compose_url,
    send_via_gmail_browser,
    send_via_smtp,
    send_via_smtp_throttled,
    throttle_config_from_env,
    ThrottleConfig,
    THROTTLE_PRESETS,
)
from app.services.auth import (
    ROLE_ADMIN,
    ROLE_MEMBER,
    authenticate,
    bootstrap_owner,
    change_password,
    create_account,
    delete_account,
    get_account,
    has_accounts,
    list_accounts,
)
from app.services.contacts import load_contacts_from_csv
from app.services.conversation import ConversationManager
from app.services.desktop_settings import desktop_settings_payload, update_background_launch
from app.services.drafts import generate_drafts
from app.services.inbox import InboxMonitor
from app.services.licensing import activate_license, current_machine_id, get_license_status
from app.services.scheduling import normalize_schedule_url
from app.services.storage import load_state, reset_state, save_state

# ─── Logging & app setup ──────────────────────────────────────────────────────

configure_logging()
logger = logging.getLogger(__name__)

APP_ENV = os.getenv("APP_ENV", "development").lower()
IS_PROD = APP_ENV == "production"
_LOCAL_HOSTS = {"127.0.0.1", "localhost"}
_CLIENT_HEADER = "X-A1-Client"
_CLIENT_HEADER_VALUE = "desktop-ui"
_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
ALLOW_SELF_SIGNUP = os.getenv("ALLOW_SELF_SIGNUP", "true").strip().lower() not in {"0", "false", "no", "off"}

# Resolve secret key. In production we refuse defaults, placeholders, or short keys.
_WEAK_SECRETS = {
    "", "change-me", "change-me-in-production", "local-dev-secret-key",
    "secret", "changeme", "dev", "development",
}
_secret = os.getenv("FLASK_SECRET_KEY", "").strip()
if IS_PROD:
    if _secret.lower() in _WEAK_SECRETS or len(_secret) < 32:
        raise RuntimeError(
            "FLASK_SECRET_KEY must be a strong (≥32 char) random string when APP_ENV=production. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
elif not _secret or _secret.lower() in _WEAK_SECRETS:
    _secret = secrets.token_hex(32)
    logger.warning("FLASK_SECRET_KEY not set or weak — using an ephemeral random key (dev mode).")

_static_dir = APP_ROOT / "client" / "dist"
# When running as a frozen .exe, PyInstaller extracts client/dist into _MEIPASS.
if getattr(sys, "frozen", False):
    _meipass = Path(getattr(sys, "_MEIPASS", APP_ROOT))
    _static_dir = _meipass / "client" / "dist"

app = Flask(__name__, static_folder=str(_static_dir), static_url_path="/")
app.config["SECRET_KEY"]        = _secret
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024   # 25 MB cap (covers attachments)
app.config["JSON_SORT_KEYS"]    = False
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=14)

PROJECT_DIR = APP_ROOT
ATTACH_DIR  = _ATTACH_DIR.resolve()
_AUTH_OPEN_PATHS = {
    "/api/health",
    "/api/auth/status",
    "/api/auth/bootstrap",
    "/api/auth/signup",
    "/api/auth/login",
    "/api/auth/logout",
}
_LICENSE_OPEN_PATHS = {
    "/api/health",
    "/api/auth/status",
    "/api/auth/logout",
    "/api/auth/change-password",
    "/api/license/status",
    "/api/license/activate",
    "/api/license/machine-id",
}

# ─── Error helpers ────────────────────────────────────────────────────────────

def client_error(msg: str, status: int = 400, *, log_exc: BaseException | None = None):
    """User-safe error response. Always logs the real cause server-side."""
    if log_exc is not None:
        logger.error("%s — %r", msg, log_exc, exc_info=True)
    return jsonify({"error": msg}), status


@app.errorhandler(413)
def _too_large(_e):
    return jsonify({"error": "Upload too large. Max 25 MB total."}), 413


@app.errorhandler(500)
def _internal_error(e):
    logger.error("Unhandled 500: %r", e, exc_info=True)
    return jsonify({"error": "Something went wrong. Check server logs."}), 500


def _session_user() -> dict[str, Any] | None:
    username = str(session.get("username") or "").strip().lower()
    if not username:
        return None
    account = get_account(username)
    if account is None:
        session.clear()
        return None
    return {
        "username": account["username"],
        "email": account.get("email", ""),
        "name": account.get("name", account.get("display_name", account["username"])),
        "display_name": account.get("display_name", account.get("name", account["username"])),
        "role": account.get("role", "member"),
    }


def _set_user_session(user: dict[str, Any]) -> None:
    session.permanent = True
    session["username"] = user["username"]
    session["role"] = user["role"]


def _require_admin_user() -> dict[str, Any] | None:
    user = _session_user()
    if user is None:
        return None
    if user.get("role") != ROLE_ADMIN:
        return None
    return user


def _auth_status_payload() -> dict[str, Any]:
    user = _session_user()
    return {
        "setup_required": not has_accounts(),
        "signup_enabled": (not has_accounts()) or ALLOW_SELF_SIGNUP,
        "authenticated": user is not None,
        "user": user,
        "license": get_license_status(),
    }


@app.before_request
def _protect_local_api():
    if not request.path.startswith("/api/"):
        return None

    # In desktop/dev mode enforce localhost-only and require the X-A1-Client
    # header on write requests.  In production (Docker / nginx) these guards are
    # unnecessary — the network boundary is controlled by the proxy.
    if not IS_PROD:
        host = (request.host or "").split(":", 1)[0].strip().lower()
        if host and host not in _LOCAL_HOSTS:
            logger.warning("Rejected non-local host header for %s: %s", request.path, request.host)
            return jsonify({"error": "Local access only."}), 403

        if request.method in _WRITE_METHODS and request.headers.get(_CLIENT_HEADER) != _CLIENT_HEADER_VALUE:
            logger.warning("Rejected unsigned local write request for %s", request.path)
            return jsonify({"error": "Request blocked. Use the desktop app UI."}), 403

    if request.path in _AUTH_OPEN_PATHS:
        return None

    user = _session_user()
    if user is None:
        return jsonify({"error": "Please sign in to continue.", "code": "auth_required"}), 401

    if request.path in _LICENSE_OPEN_PATHS:
        return None

    license_status = get_license_status()
    if not license_status.get("active"):
        return jsonify({
            "error": "Activate a valid license to use the app.",
            "code": "license_required",
            "license": license_status,
        }), 403

    return None


@app.after_request
def _add_security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Cache-Control"] = resp.headers.get("Cache-Control", "no-store")
    return resp


@app.get("/api/health")
def health():
    return jsonify({
        "ok": True,
        "app_env": APP_ENV,
        "frozen": bool(getattr(sys, "frozen", False)),
    })


# ─── Singletons ───────────────────────────────────────────────────────────────

def _current_config() -> dict[str, Any]:
    return stored_form()

conversation_manager = ConversationManager(
    load_state_fn=load_state,
    save_state_fn=save_state,
    get_config_fn=_current_config,
)

inbox_monitor = InboxMonitor(reply_callback=conversation_manager.process_reply)

# ─── Background pending-reply monitor (with graceful shutdown) ────────────────

_shutdown = threading.Event()


_followup_tick = 0  # incremented every loop tick


def _pending_reply_loop():
    """
    Runs every 10 s: dispatches pending drafts whose send-delay window has elapsed.
    Every ~6th tick (≈1 min) it also scans for prospects who need a follow-up.
    """
    global _followup_tick
    while not _shutdown.is_set():
        try:
            conversation_manager.check_pending_replies()
        except Exception:
            logger.exception("Error checking pending replies")
        # Run the follow-up scan once a minute (every 6th 10-second tick)
        _followup_tick = (_followup_tick + 1) % 6
        if _followup_tick == 0:
            try:
                conversation_manager.check_followups()
            except Exception:
                logger.exception("Error checking follow-ups")
        # Wait up to 10s but wake immediately on shutdown
        _shutdown.wait(timeout=10)


_pending_thread = threading.Thread(
    target=_pending_reply_loop, daemon=True, name="PendingReplyMonitor"
)
_pending_thread.start()


def shutdown_app() -> None:
    """Signal background workers to stop. Idempotent."""
    if _shutdown.is_set():
        return
    logger.info("Shutting down background workers…")
    _shutdown.set()
    try:
        inbox_monitor.stop()
    except Exception:
        logger.exception("Error stopping inbox monitor during shutdown")
    _pending_thread.join(timeout=5)
    logger.info("Background workers stopped.")


# ─── State helpers ────────────────────────────────────────────────────────────

def get_form_defaults() -> dict[str, str]:
    return {
        "mission":        "",
        "sender_name":    "",
        "sender_company": "",
        "offer":          "",
        "call_to_action": "would you be open to a quick 15-minute call next week",
        "tone":           "professional",
        "signature":      "",
        "google_meet_link": "",
        "google_calendar_link": "",
        "sender_email":   "",
        "email_type":     "cold_outreach",
        "email_length":   "medium",
    }


def stored_drafts() -> list[dict[str, Any]]:
    return load_state().get("drafts", [])


def stored_contacts() -> list[dict[str, Any]]:
    return load_state().get("contacts", [])


def stored_form() -> dict[str, str]:
    defaults = get_form_defaults()
    defaults.update(load_state().get("form_data", {}))
    return defaults


_ALLOWED_TONES        = {"professional", "friendly", "direct", "warm"}
_ALLOWED_EMAIL_TYPES  = {"cold_outreach", "follow_up", "introduction", "partnership", "invitation", "re_engagement"}
_ALLOWED_EMAIL_LENGTHS = {"punchy", "short", "medium", "long"}
_EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MAX_CONTACTS_PER_CSV = 5000


def _safe(name: str, value: str, allowed: set[str], default: str) -> str:
    v = (value or "").strip().lower()
    return v if v in allowed else default


def build_config_from_form(form_data: dict[str, str]) -> CampaignConfig:
    return CampaignConfig(
        mission=form_data["mission"].strip(),
        sender_name=form_data["sender_name"].strip(),
        sender_company=form_data["sender_company"].strip(),
        offer=form_data["offer"].strip(),
        call_to_action=form_data["call_to_action"].strip(),
        tone=_safe("tone",         form_data.get("tone", ""),         _ALLOWED_TONES,         "professional"),
        signature=form_data["signature"].strip(),
        google_meet_link=normalize_schedule_url(form_data.get("google_meet_link", "")),
        google_calendar_link=normalize_schedule_url(form_data.get("google_calendar_link", "")),
        email_type=_safe("email_type",   form_data.get("email_type", ""),   _ALLOWED_EMAIL_TYPES,   "cold_outreach"),
        email_length=_safe("email_length", form_data.get("email_length", ""), _ALLOWED_EMAIL_LENGTHS, "medium"),
    )


def serialize_drafts(drafts: list[DraftEmail]) -> list[dict[str, Any]]:
    return [draft.to_dict() for draft in drafts]


def drafts_with_gmail_urls(drafts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for draft in drafts:
        draft_copy = dict(draft)
        draft_copy["gmail_url"] = build_gmail_compose_url(DraftEmail(**draft))
        enriched.append(draft_copy)
    return enriched


def _csv_safe(value: Any) -> str:
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


# ─── Auth / licensing ─────────────────────────────────────────────────────────

@app.get("/api/auth/status")
def auth_status():
    return jsonify(_auth_status_payload())


@app.post("/api/auth/bootstrap")
def auth_bootstrap():
    if has_accounts():
        return jsonify({"error": "Setup is already complete."}), 400

    data = request.get_json() or {}
    username = str(data.get("username", "") or "")
    password = str(data.get("password", "") or "")
    email = str(data.get("email", "") or "")
    name = str(data.get("name", "") or "")

    try:
        user = bootstrap_owner(username, password, email, name)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    _set_user_session(user)
    return jsonify({
        "message": "Owner account created.",
        "user": user,
        "status": _auth_status_payload(),
    })


@app.post("/api/auth/signup")
def auth_signup():
    data = request.get_json() or {}
    username = str(data.get("username", "") or "")
    password = str(data.get("password", "") or "")
    email = str(data.get("email", "") or "")
    name = str(data.get("name", "") or "")

    try:
        if has_accounts():
            if not ALLOW_SELF_SIGNUP:
                return jsonify({"error": "Sign up is disabled on this machine. Ask an admin to create your account."}), 403
            user = create_account(
                username=username,
                password=password,
                email=email,
                name=name,
                role=ROLE_MEMBER,
            )
            message = "Account created."
        else:
            user = bootstrap_owner(username, password, email, name)
            message = "Owner account created."
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    _set_user_session(user)
    return jsonify({
        "message": message,
        "user": user,
        "status": _auth_status_payload(),
    })


@app.post("/api/auth/login")
def auth_login():
    data = request.get_json() or {}
    user = authenticate(
        str(data.get("username", "") or ""),
        str(data.get("password", "") or ""),
    )
    if user is None:
        return jsonify({"error": "Invalid username/email or password."}), 401

    _set_user_session(user)
    return jsonify({
        "message": "Signed in successfully.",
        "user": user,
        "status": _auth_status_payload(),
    })


@app.post("/api/auth/logout")
def auth_logout():
    session.clear()
    return jsonify({"message": "Signed out."})


@app.post("/api/auth/change-password")
def auth_change_password():
    user = _session_user()
    if user is None:
        return jsonify({"error": "Please sign in to continue."}), 401

    data = request.get_json() or {}
    try:
        change_password(
            user["username"],
            str(data.get("current_password", "") or ""),
            str(data.get("new_password", "") or ""),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({"message": "Password updated."})


@app.get("/api/admin/accounts")
def admin_list_accounts():
    if _require_admin_user() is None:
        return jsonify({"error": "Admin access is required."}), 403
    return jsonify({"accounts": list_accounts()})


@app.post("/api/admin/accounts")
def admin_create_account():
    if _require_admin_user() is None:
        return jsonify({"error": "Admin access is required."}), 403

    data = request.get_json() or {}
    try:
        account = create_account(
            username=str(data.get("username", "") or ""),
            password=str(data.get("password", "") or ""),
            email=str(data.get("email", "") or ""),
            name=str(data.get("name", "") or ""),
            role=str(data.get("role", "member") or "member"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({"message": "Account created.", "account": account, "accounts": list_accounts()})


@app.delete("/api/admin/accounts/<path:username>")
def admin_delete_account(username: str):
    admin_user = _require_admin_user()
    if admin_user is None:
        return jsonify({"error": "Admin access is required."}), 403

    try:
        delete_account(username, actor_username=admin_user["username"])
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({"message": "Account removed.", "accounts": list_accounts()})


@app.get("/api/license/status")
def license_status():
    return jsonify(get_license_status())


@app.post("/api/license/activate")
def license_activate():
    user = _session_user()
    if user is None:
        return jsonify({"error": "Please sign in to activate a license."}), 401

    data = request.get_json() or {}
    token = str(data.get("token", "") or "")
    try:
        status = activate_license(token)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify({"message": "License activated.", "license": status})


@app.get("/api/license/machine-id")
def license_machine_id():
    """Return this machine's ID. No auth required — customers need this to request a license."""
    return jsonify({"machine_id": current_machine_id()})


# ─── Core session endpoints ───────────────────────────────────────────────────

def stored_attachments() -> list[str]:
    return load_state().get("attachments", [])


@app.get("/api/state")
def get_state():
    return jsonify({
        "form_data":   stored_form(),
        "contacts":    stored_contacts(),
        "drafts":      drafts_with_gmail_urls(stored_drafts()),
        "attachments": stored_attachments(),
    })


@app.get("/api/sample-csv")
def sample_csv():
    if not SAMPLE_CSV_PATH.exists():
        return jsonify({"error": "Sample CSV is unavailable in this build."}), 404
    return send_file(SAMPLE_CSV_PATH, as_attachment=True, download_name="sample_contacts.csv", mimetype="text/csv")


# ─── Campaign generation (template-based) ────────────────────────────────────

def _extract_form_data(form) -> dict[str, str]:
    return {
        "mission":        form.get("mission", ""),
        "sender_name":    form.get("sender_name", ""),
        "sender_company": form.get("sender_company", ""),
        "offer":          form.get("offer", ""),
        "call_to_action": form.get("call_to_action", ""),
        "tone":           form.get("tone", "professional"),
        "signature":      form.get("signature", ""),
        "google_meet_link": normalize_schedule_url(form.get("google_meet_link", "")),
        "google_calendar_link": normalize_schedule_url(form.get("google_calendar_link", "")),
        "sender_email":   form.get("sender_email", ""),
        "email_type":     form.get("email_type", "cold_outreach"),
        "email_length":   form.get("email_length", "medium"),
    }


@app.post("/api/generate")
def generate():
    uploaded_file = request.files.get("contacts_file")
    form_data = _extract_form_data(request.form)
    save_state(form_data=form_data)

    if not uploaded_file or not uploaded_file.filename:
        return jsonify({"error": "Upload a CSV file with at least an email column."}), 400

    if not form_data["mission"].strip() or not form_data["offer"].strip() or not form_data["call_to_action"].strip():
        return jsonify({"error": "Mission, offer, and call to action are required."}), 400

    try:
        contacts = load_contacts_from_csv(uploaded_file.read())
    except ValueError as exc:
        return client_error(str(exc), 400)
    except Exception as exc:
        return client_error("Could not parse the uploaded CSV. Make sure it has an 'email' column.", 400, log_exc=exc)

    if not contacts:
        return jsonify({"error": "No valid contacts found in the uploaded file."}), 400
    if len(contacts) > _MAX_CONTACTS_PER_CSV:
        return jsonify({"error": f"CSV has too many rows ({len(contacts)}). Max {_MAX_CONTACTS_PER_CSV}."}), 400

    config = build_config_from_form(form_data)
    drafts = generate_drafts(contacts, config)

    save_state(
        contacts=[c.to_dict() for c in contacts],
        drafts=serialize_drafts(drafts),
        form_data=form_data,
    )

    return jsonify({
        "message": f"Generated {len(drafts)} draft(s) for your campaign.",
        "drafts":   drafts_with_gmail_urls(serialize_drafts(drafts)),
        "contacts": [c.to_dict() for c in contacts],
        "form_data": form_data,
    })


# ─── AI-powered generation (streams progress via SSE) ────────────────────────

@app.post("/api/generate-ai")
def generate_ai():
    """
    Like /api/generate but uses the configured AI model to write each email individually.
    Streams progress events: {index, email, status, total} or {done}.
    """
    uploaded_file = request.files.get("contacts_file")
    form_data = _extract_form_data(request.form)
    save_state(form_data=form_data)

    if not uploaded_file or not uploaded_file.filename:
        return jsonify({"error": "Upload a CSV file with at least an email column."}), 400

    if not form_data["mission"].strip() or not form_data["offer"].strip():
        return jsonify({"error": "Mission and offer are required."}), 400

    try:
        contacts = load_contacts_from_csv(uploaded_file.read())
    except ValueError as exc:
        return client_error(str(exc), 400)
    except Exception as exc:
        return client_error("Could not parse the uploaded CSV.", 400, log_exc=exc)

    if not contacts:
        return jsonify({"error": "No valid contacts found."}), 400
    if len(contacts) > _MAX_CONTACTS_PER_CSV:
        return jsonify({"error": f"CSV has too many rows ({len(contacts)}). Max {_MAX_CONTACTS_PER_CSV}."}), 400

    def stream():
        total = len(contacts)
        finished_drafts: list[DraftEmail] = []

        for i, contact in enumerate(contacts):
            yield f"data: {json.dumps({'index': i, 'email': contact.email, 'status': 'generating', 'total': total})}\n\n"
            try:
                subject, body = generate_email_copy(contact.to_dict(), form_data)
                draft = DraftEmail(
                    email=contact.email,
                    first_name=contact.first_name,
                    company=contact.company,
                    subject=subject,
                    body=body,
                )
                finished_drafts.append(draft)
                yield f"data: {json.dumps({'index': i, 'email': contact.email, 'status': 'done', 'subject': subject, 'total': total})}\n\n"
            except Exception as exc:
                logger.error("AI generation failed for %s: %r", contact.email, exc, exc_info=True)
                # Fall back to template for this contact
                from app.services.drafts import build_draft
                config = build_config_from_form(form_data)
                fallback = build_draft(contact, config)
                finished_drafts.append(fallback)
                # Show a short, user-safe message; full traceback is in server logs
                err_msg = "AI generation failed — used template fallback."
                yield f"data: {json.dumps({'index': i, 'email': contact.email, 'status': 'fallback', 'error': err_msg, 'total': total})}\n\n"

        # Persist and emit final state
        serialized = serialize_drafts(finished_drafts)
        save_state(
            contacts=[c.to_dict() for c in contacts],
            drafts=serialized,
            form_data=form_data,
        )
        enriched = drafts_with_gmail_urls(serialized)
        yield f"data: {json.dumps({'done': True, 'drafts': enriched, 'contacts': [c.to_dict() for c in contacts]})}\n\n"

    return Response(stream_with_context(stream()), mimetype="text/event-stream", headers={
        "Cache-Control":    "no-cache",
        "X-Accel-Buffering": "no",
    })


# ─── Draft Editing ──────────────────────────────────────────────────────────

@app.post("/api/drafts/update")
def update_draft():
    """
    Updates a specific draft's subject and body.
    Expects JSON: {email, subject, body}
    """
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    subject = data.get("subject")
    body = data.get("body")

    if not email:
        return jsonify({"error": "Missing email for draft update."}), 400

    drafts = stored_drafts()
    found = False
    updated_draft = None

    for d in drafts:
        if d.get("email", "").strip().lower() == email:
            if subject is not None:
                d["subject"] = subject
            if body is not None:
                d["body"] = body
            found = True
            updated_draft = d
            break

    if not found:
        return jsonify({"error": f"No draft found for {email}"}), 404

    save_state(drafts=drafts)

    # Return the enriched version of the updated draft (with Gmail URL)
    return jsonify({
        "message": "Draft updated successfully.",
        "draft": drafts_with_gmail_urls([updated_draft])[0],
        "drafts": drafts_with_gmail_urls(drafts)
    })


# ─── SMTP send ────────────────────────────────────────────────────────────────

@app.post("/api/send-smtp")
def send_smtp():
    drafts = stored_drafts()
    form_data = stored_form()

    data = request.get_json() or {}
    sender_email = data.get("sender_email", form_data.get("sender_email", "")).strip()
    form_data["sender_email"] = sender_email
    save_state(form_data=form_data)

    if not drafts:
        return jsonify({"error": "Generate drafts before sending."}), 400
    if not sender_email or not _EMAIL_REGEX.match(sender_email):
        return jsonify({"error": "Provide a valid sender email before sending through SMTP."}), 400

    attachment_paths = [ATTACH_DIR / fn for fn in stored_attachments()]
    draft_objects = [DraftEmail(**d) for d in drafts]
    try:
        updated = send_via_smtp(draft_objects, sender_email=sender_email, attachment_paths=attachment_paths)
    except ValueError as exc:
        # Configuration errors are safe to surface
        return client_error(str(exc), 400)
    except Exception as exc:
        return client_error("SMTP send failed. Check server logs for details.", 502, log_exc=exc)

    serialized = serialize_drafts(updated)
    save_state(drafts=serialized)

    # Initialise conversation threads for newly sent emails
    conversation_manager.init_from_drafts(serialized)

    sent    = sum(d.status == "sent"   for d in updated)
    failed  = sum(d.status == "failed" for d in updated)
    return jsonify({
        "message": f"SMTP finished. Sent: {sent}. Failed: {failed}.",
        "drafts":  drafts_with_gmail_urls(serialized),
    })


# ─── Throttled SMTP send (SSE streaming) ─────────────────────────────────────

@app.post("/api/send-smtp-throttled")
def send_smtp_throttled():
    """
    Sends all campaign drafts via SMTP with human-like throttling to avoid
    spam filters.  Streams real-time progress as Server-Sent Events so the
    UI can show a live progress bar with ETA.

    Request body (JSON):
      sender_email   str   — required
      sender_name    str   — optional (falls back to SMTP_USERNAME)
      preset         str   — "careful" | "normal" | "fast"  (optional)
    """
    drafts_data = stored_drafts()
    if not drafts_data:
        return jsonify({"error": "Generate drafts before sending."}), 400

    data = request.get_json(silent=True) or {}
    form_data = stored_form()

    sender_email = (data.get("sender_email") or form_data.get("sender_email", "")).strip()
    sender_name  = (data.get("sender_name")  or form_data.get("sender_name", "")).strip()

    if not sender_email or not _EMAIL_REGEX.match(sender_email):
        return jsonify({"error": "Provide a valid sender email."}), 400

    # Apply preset if supplied
    preset = str(data.get("preset", "normal")).strip().lower()
    throttle = THROTTLE_PRESETS.get(preset, None)
    if throttle is None:
        throttle = throttle_config_from_env()

    form_data["sender_email"] = sender_email
    save_state(form_data=form_data)

    attachment_paths = [ATTACH_DIR / fn for fn in stored_attachments()]
    draft_objects = [DraftEmail(**d) for d in drafts_data]

    def generate():
        for event in send_via_smtp_throttled(
            draft_objects,
            sender_email=sender_email,
            sender_name=sender_name or sender_email.split("@")[0],
            attachment_paths=attachment_paths,
            throttle=throttle,
        ):
            yield f"data: {json.dumps(event)}\n\n"
            if event.get("done"):
                serialized = serialize_drafts(draft_objects)
                save_state(drafts=serialized)
                conversation_manager.init_from_drafts(serialized)
            if event.get("fatal") or event.get("done"):
                break

    return Response(generate(), mimetype="text/event-stream", headers={
        "Cache-Control":    "no-cache",
        "X-Accel-Buffering": "no",
    })


# ─── Sending settings (throttle presets) ─────────────────────────────────────

@app.get("/api/settings/sending")
def get_sending_settings():
    """Return current throttle configuration and available presets."""
    cfg = throttle_config_from_env()
    preset = os.getenv("SMTP_THROTTLE_PRESET", "normal").strip().lower()
    return jsonify({
        "preset": preset,
        "presets": {name: {
            "delay_min": p.delay_min, "delay_max": p.delay_max,
            "batch_size": p.batch_size,
            "batch_pause_min": p.batch_pause_min, "batch_pause_max": p.batch_pause_max,
            "daily_limit": p.daily_limit,
        } for name, p in THROTTLE_PRESETS.items()},
        "current": {
            "delay_min": cfg.delay_min, "delay_max": cfg.delay_max,
            "batch_size": cfg.batch_size,
            "batch_pause_min": cfg.batch_pause_min, "batch_pause_max": cfg.batch_pause_max,
            "daily_limit": cfg.daily_limit,
        },
    })


@app.post("/api/settings/sending")
def save_sending_settings():
    """Save throttle preset and optional overrides to .env."""
    data = request.get_json() or {}
    preset = str(data.get("preset", "normal")).strip().lower()
    if preset not in THROTTLE_PRESETS:
        return jsonify({"error": f"Unknown preset '{preset}'. Use: {list(THROTTLE_PRESETS)}."}), 400

    updates: dict[str, str] = {"SMTP_THROTTLE_PRESET": preset}

    # Optional fine-grained overrides
    int_fields   = {"SMTP_BATCH_SIZE": "batch_size", "SMTP_DAILY_LIMIT": "daily_limit"}
    float_fields = {
        "SMTP_DELAY_MIN": "delay_min", "SMTP_DELAY_MAX": "delay_max",
        "SMTP_BATCH_PAUSE_MIN": "batch_pause_min", "SMTP_BATCH_PAUSE_MAX": "batch_pause_max",
    }
    for env_key, data_key in int_fields.items():
        if data_key in data:
            try:
                updates[env_key] = str(int(data[data_key]))
            except (TypeError, ValueError):
                return jsonify({"error": f"{data_key} must be an integer."}), 400
    for env_key, data_key in float_fields.items():
        if data_key in data:
            try:
                updates[env_key] = str(float(data[data_key]))
            except (TypeError, ValueError):
                return jsonify({"error": f"{data_key} must be a number."}), 400

    _update_env_file(PROJECT_DIR / ".env", updates)
    for k, v in updates.items():
        os.environ[k] = v

    return jsonify({
        "message": f"Sending settings saved (preset: {preset}).",
        "preset": preset,
        "current": throttle_config_from_env().__dict__,
    })


# ─── Gmail browser automation (SSE) ──────────────────────────────────────────

@app.post("/api/send-gmail")
def send_gmail():
    drafts_data = stored_drafts()
    if not drafts_data:
        return jsonify({"error": "No drafts found. Generate drafts first."}), 400

    payload = request.get_json(silent=True) or {}
    raw_limit = payload.get("limit")
    limit = raw_limit if isinstance(raw_limit, int) and raw_limit > 0 else None

    draft_objects = [DraftEmail(**d) for d in drafts_data]

    def generate():
        for event in send_via_gmail_browser(draft_objects, limit=limit):
            yield f"data: {json.dumps(event)}\n\n"
            if event.get("fatal") or event.get("done"):
                break
        serialized = serialize_drafts(draft_objects)
        save_state(drafts=serialized)
        # Bootstrap conversation threads for sent emails
        conversation_manager.init_from_drafts(serialized)

    return Response(generate(), mimetype="text/event-stream", headers={
        "Cache-Control":    "no-cache",
        "X-Accel-Buffering": "no",
    })


# ─── Download endpoints ───────────────────────────────────────────────────────

@app.get("/api/download/csv")
def download_csv():
    drafts = stored_drafts()
    if not drafts:
        return jsonify({"error": "Generate drafts before exporting."}), 400

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(drafts[0].keys()))
    writer.writeheader()
    writer.writerows([{k: _csv_safe(v) for k, v in row.items()} for row in drafts])

    return send_file(
        io.BytesIO(output.getvalue().encode("utf-8")),
        as_attachment=True,
        download_name="campaign_drafts.csv",
        mimetype="text/csv",
    )


@app.get("/api/download/json")
def download_json():
    drafts = stored_drafts()
    if not drafts:
        return jsonify({"error": "Generate drafts before exporting."}), 400

    return send_file(
        io.BytesIO(json.dumps(drafts, indent=2).encode("utf-8")),
        as_attachment=True,
        download_name="campaign_drafts.json",
        mimetype="application/json",
    )


# ─── Inbox monitor endpoints ──────────────────────────────────────────────────

@app.post("/api/inbox/start")
def inbox_start():
    try:
        inbox_monitor.start()
        return jsonify({"message": "Inbox monitor started.", "status": inbox_monitor.status()})
    except ValueError as exc:
        return client_error(str(exc), 400)
    except Exception as exc:
        return client_error("Failed to start inbox monitor. Check server logs.", 500, log_exc=exc)


@app.post("/api/inbox/stop")
def inbox_stop():
    inbox_monitor.stop()
    return jsonify({"message": "Inbox monitor stopped.", "status": inbox_monitor.status()})


@app.get("/api/inbox/status")
def inbox_status():
    return jsonify(inbox_monitor.status())


# ─── Conversation endpoints ───────────────────────────────────────────────────

@app.get("/api/conversations")
def list_conversations():
    convs = conversation_manager.get_all()
    # Sort by last_activity descending
    convs_sorted = sorted(convs, key=lambda c: c.get("last_activity", ""), reverse=True)
    return jsonify({"conversations": convs_sorted, "total": len(convs_sorted)})


@app.get("/api/conversations/<path:addr>")
def get_conversation(addr: str):
    conv = conversation_manager.get_by_email(addr)
    if conv is None:
        return jsonify({"error": f"No conversation found for {addr}"}), 404
    return jsonify(conv)


@app.post("/api/conversations/<path:addr>/approve")
def approve_reply(addr: str):
    data = request.get_json() or {}
    edited_body = data.get("body")
    try:
        conversation_manager.approve_pending_reply(addr, edited_body)
        return jsonify({"message": "Reply approved and sent."})
    except ValueError as exc:
        return client_error(str(exc), 404)
    except Exception as exc:
        return client_error("Failed to approve reply. Check server logs.", 500, log_exc=exc)


@app.post("/api/conversations/<path:addr>/cancel")
def cancel_reply(addr: str):
    try:
        conversation_manager.cancel_pending_reply(addr)
        return jsonify({"message": "Pending reply cancelled."})
    except ValueError as exc:
        return client_error(str(exc), 404)
    except Exception as exc:
        return client_error("Failed to cancel reply. Check server logs.", 500, log_exc=exc)


# ─── Attachments ─────────────────────────────────────────────────────────────

_ALLOWED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".txt", ".csv", ".png", ".jpg", ".jpeg", ".gif", ".zip",
}
_MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024  # 20 MB per file


def _resolve_attachment(filename: str) -> Path | None:
    """
    Resolve a user-supplied filename to a path inside ATTACH_DIR.
    Returns None if the resolved path escapes the directory.
    """
    from werkzeug.utils import secure_filename
    safe = secure_filename(filename or "")
    if not safe:
        return None
    candidate = (ATTACH_DIR / safe).resolve()
    try:
        candidate.relative_to(ATTACH_DIR)
    except ValueError:
        return None
    return candidate


@app.post("/api/attachments/upload")
def upload_attachment():
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "No file provided."}), 400

    target = _resolve_attachment(file.filename)
    if target is None:
        return jsonify({"error": "Invalid filename."}), 400

    ext = target.suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        return jsonify({"error": f"File type '{ext}' not allowed."}), 400

    data = file.read()
    if len(data) > _MAX_ATTACHMENT_BYTES:
        return jsonify({"error": "File exceeds 20 MB limit."}), 400

    target.write_bytes(data)

    attachments = stored_attachments()
    if target.name not in attachments:
        attachments.append(target.name)
    save_state(attachments=attachments)
    return jsonify({"message": f"{target.name} uploaded.", "filename": target.name, "attachments": attachments})


@app.get("/api/attachments")
def list_attachments():
    return jsonify({"attachments": stored_attachments()})


@app.delete("/api/attachments/<path:filename>")
def delete_attachment(filename: str):
    target = _resolve_attachment(filename)
    if target is None:
        return jsonify({"error": "Invalid filename."}), 400
    if target.exists():
        target.unlink(missing_ok=True)
    attachments = [a for a in stored_attachments() if a != target.name]
    save_state(attachments=attachments)
    return jsonify({"message": f"{target.name} removed.", "attachments": attachments})


# ─── AI Settings ─────────────────────────────────────────────────────────────

def _update_env_file(env_path: Path, updates: dict[str, str]) -> None:
    """Update or insert specific keys in a .env file."""
    text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    lines = text.splitlines()
    updated_keys: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in updates:
            new_lines.append(f"{key}={updates[key]}")
            updated_keys.add(key)
        else:
            new_lines.append(line)
    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}")
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def _mask_secret(raw_value: str) -> str:
    raw_value = raw_value.strip()
    return (raw_value[:8] + "…" + raw_value[-4:]) if len(raw_value) > 14 else ("set" if raw_value else "")


@app.get("/api/settings/ai")
def get_ai_settings():
    openai_key    = os.getenv("OPENAI_API_KEY", "")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    deepseek_key  = os.getenv("DEEPSEEK_API_KEY", "")
    qwen_key      = os.getenv("QWEN_API_KEY", "")
    kimi_key      = os.getenv("KIMI_API_KEY", "")
    return jsonify({
        "provider":           os.getenv("AI_PROVIDER", "ollama"),
        "ollama_base_url":    os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        "ollama_model":       os.getenv("OLLAMA_MODEL", "llama3.2"),
        "openai_key_set":     bool(openai_key),
        "openai_key_hint":    _mask_secret(openai_key),
        "openai_model":       os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "claude_key_set":     bool(anthropic_key),
        "claude_key_hint":    _mask_secret(anthropic_key),
        "claude_model":       os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022"),
        "deepseek_key_set":   bool(deepseek_key),
        "deepseek_key_hint":  _mask_secret(deepseek_key),
        "deepseek_model":     os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        "qwen_key_set":       bool(qwen_key),
        "qwen_key_hint":      _mask_secret(qwen_key),
        "qwen_model":         os.getenv("QWEN_MODEL", "qwen-plus"),
        "kimi_key_set":       bool(kimi_key),
        "kimi_key_hint":      _mask_secret(kimi_key),
        "kimi_model":         os.getenv("KIMI_MODEL", "moonshot-v1-8k"),
    })


@app.post("/api/settings/ai")
def save_ai_settings():
    data     = request.get_json() or {}
    provider = data.get("provider", "ollama").strip().lower()

    updates: dict[str, str] = {"AI_PROVIDER": provider}

    if provider == "ollama":
        base_url = data.get("ollama_base_url", "").strip().rstrip("/")
        model    = data.get("ollama_model", "").strip()
        if not base_url:
            return jsonify({"error": "Ollama server URL is required."}), 400
        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return jsonify({"error": "Ollama URL must start with http:// or https:// and include a host."}), 400
        if not model or len(model) > 100:
            return jsonify({"error": "Provide a valid model name (max 100 chars)."}), 400
        updates["OLLAMA_BASE_URL"] = base_url
        updates["OLLAMA_MODEL"]    = model
        os.environ["OLLAMA_BASE_URL"] = base_url
        os.environ["OLLAMA_MODEL"]    = model

    elif provider == "openai":
        api_key = data.get("openai_api_key", "").strip()
        model   = data.get("openai_model", "gpt-4o-mini").strip()
        # Only update the key if a real new value was sent (not a masked placeholder)
        if api_key and "…" not in api_key:
            if not api_key.startswith("sk-") or len(api_key) < 20:
                return jsonify({"error": "OpenAI API key looks invalid (should start with 'sk-')."}), 400
            updates["OPENAI_API_KEY"] = api_key
            os.environ["OPENAI_API_KEY"] = api_key
        elif not os.getenv("OPENAI_API_KEY"):
            return jsonify({"error": "OpenAI API key is required."}), 400
        if not model or len(model) > 100:
            return jsonify({"error": "Provide a valid model name."}), 400
        updates["OPENAI_MODEL"] = model
        os.environ["OPENAI_MODEL"] = model

    elif provider == "claude":
        api_key = data.get("claude_api_key", "").strip()
        model   = data.get("claude_model", "claude-3-5-haiku-20241022").strip()
        if api_key and "…" not in api_key:
            if not api_key.startswith("sk-ant-") or len(api_key) < 20:
                return jsonify({"error": "Claude API key looks invalid (should start with 'sk-ant-')."}), 400
            updates["ANTHROPIC_API_KEY"] = api_key
            os.environ["ANTHROPIC_API_KEY"] = api_key
        elif not os.getenv("ANTHROPIC_API_KEY"):
            return jsonify({"error": "Claude API key is required."}), 400
        if not model or len(model) > 100:
            return jsonify({"error": "Provide a valid Claude model name."}), 400
        updates["ANTHROPIC_MODEL"] = model
        os.environ["ANTHROPIC_MODEL"] = model

    elif provider == "deepseek":
        api_key = data.get("deepseek_api_key", "").strip()
        model   = data.get("deepseek_model", "deepseek-chat").strip()
        if api_key and "…" not in api_key:
            if len(api_key) < 10:
                return jsonify({"error": "DeepSeek API key looks invalid."}), 400
            updates["DEEPSEEK_API_KEY"] = api_key
            os.environ["DEEPSEEK_API_KEY"] = api_key
        elif not os.getenv("DEEPSEEK_API_KEY"):
            return jsonify({"error": "DeepSeek API key is required."}), 400
        if not model or len(model) > 100:
            return jsonify({"error": "Provide a valid DeepSeek model name."}), 400
        updates["DEEPSEEK_MODEL"] = model
        os.environ["DEEPSEEK_MODEL"] = model

    elif provider == "qwen":
        api_key = data.get("qwen_api_key", "").strip()
        model   = data.get("qwen_model", "qwen-plus").strip()
        if api_key and "…" not in api_key:
            if len(api_key) < 10:
                return jsonify({"error": "Qwen API key looks invalid."}), 400
            updates["QWEN_API_KEY"] = api_key
            os.environ["QWEN_API_KEY"] = api_key
        elif not os.getenv("QWEN_API_KEY"):
            return jsonify({"error": "Qwen API key is required."}), 400
        if not model or len(model) > 100:
            return jsonify({"error": "Provide a valid Qwen model name."}), 400
        updates["QWEN_MODEL"] = model
        os.environ["QWEN_MODEL"] = model

    elif provider == "kimi":
        api_key = data.get("kimi_api_key", "").strip()
        model   = data.get("kimi_model", "moonshot-v1-8k").strip()
        if api_key and "…" not in api_key:
            if len(api_key) < 10:
                return jsonify({"error": "Kimi API key looks invalid."}), 400
            updates["KIMI_API_KEY"] = api_key
            os.environ["KIMI_API_KEY"] = api_key
        elif not os.getenv("KIMI_API_KEY"):
            return jsonify({"error": "Kimi API key is required."}), 400
        if not model or len(model) > 100:
            return jsonify({"error": "Provide a valid Kimi model name."}), 400
        updates["KIMI_MODEL"] = model
        os.environ["KIMI_MODEL"] = model

    else:
        return jsonify({"error": f"Unknown provider '{provider}'."}), 400

    os.environ["AI_PROVIDER"] = provider
    _update_env_file(PROJECT_DIR / ".env", updates)
    return jsonify({"message": "AI settings saved.", "provider": provider})


def _smtp_settings_payload() -> dict[str, Any]:
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    security = os.getenv("SMTP_SECURITY", "").strip().lower()
    if not security:
        use_tls_legacy = os.getenv("SMTP_USE_TLS", "true").strip().lower() == "true"
        security = "starttls" if use_tls_legacy else "ssl"
    return {
        "host": os.getenv("SMTP_HOST", ""),
        "port": int(os.getenv("SMTP_PORT", "587") or 587),
        "username": os.getenv("SMTP_USERNAME", ""),
        "security": security,
        "password_set": bool(smtp_password),
        "password_hint": _mask_secret(smtp_password),
    }


def _validated_smtp_settings(data: dict[str, Any], *, allow_keep_password: bool) -> tuple[dict[str, str], str]:
    host = str(data.get("host", "") or "").strip()
    username = str(data.get("username", "") or "").strip()
    password = str(data.get("password", "") or "")
    security = str(data.get("security", "starttls") or "starttls").strip().lower()
    raw_port = data.get("port", 587)

    if not host:
        raise ValueError("SMTP host is required.")

    try:
        port = int(raw_port)
    except (TypeError, ValueError) as exc:
        raise ValueError("SMTP port must be a valid number.") from exc

    if not (1 <= port <= 65535):
        raise ValueError("SMTP port must be between 1 and 65535.")

    if not username:
        raise ValueError("SMTP username is required.")

    if security not in ("starttls", "ssl", "none"):
        raise ValueError("Security must be 'starttls', 'ssl', or 'none'.")

    if password and "…" in password:
        password = ""

    current_password = os.getenv("SMTP_PASSWORD", "")
    if not password and not (allow_keep_password and current_password):
        raise ValueError("SMTP password is required.")

    resolved_password = password or current_password
    updates = {
        "SMTP_HOST": host,
        "SMTP_PORT": str(port),
        "SMTP_USERNAME": username,
        "SMTP_PASSWORD": resolved_password,
        "SMTP_SECURITY": security,
        "SMTP_USE_TLS": "true" if security == "starttls" else "false",
    }
    return updates, resolved_password


def _smtp_probe(settings: dict[str, str]) -> None:
    host     = settings["SMTP_HOST"]
    port     = int(settings["SMTP_PORT"])
    username = settings["SMTP_USERNAME"]
    password = settings["SMTP_PASSWORD"]
    security = settings.get("SMTP_SECURITY", "").strip().lower()
    if not security:
        use_tls_legacy = settings.get("SMTP_USE_TLS", "true").strip().lower() == "true"
        security = "starttls" if use_tls_legacy else "ssl"

    ctx = ssl.create_default_context()

    if security == "ssl":
        server = smtplib.SMTP_SSL(host, port, context=ctx, timeout=10)
        try:
            server.login(username, password)
        finally:
            try:
                server.quit()
            except Exception:
                server.close()
    elif security == "none":
        server = smtplib.SMTP(host, port, timeout=10)
        try:
            server.ehlo()
            if username and password:
                server.login(username, password)
        finally:
            try:
                server.quit()
            except Exception:
                server.close()
    else:  # starttls
        server = smtplib.SMTP(host, port, timeout=10)
        try:
            server.ehlo()
            server.starttls(context=ctx)
            server.ehlo()
            server.login(username, password)
        finally:
            try:
                server.quit()
            except Exception:
                server.close()


def _sanitize_smtp_settings_error(exc: BaseException) -> str:
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "SMTP authentication failed. Check the username or password."
    if isinstance(exc, smtplib.SMTPConnectError):
        return "Could not connect to the SMTP server."
    if isinstance(exc, smtplib.SMTPNotSupportedError):
        return "This SMTP server does not support the selected security mode."
    if isinstance(exc, (TimeoutError, OSError)):
        return "Network error while reaching the SMTP server."
    return "SMTP connection test failed. Check the server details and credentials."


@app.get("/api/settings/smtp")
def get_smtp_settings():
    return jsonify(_smtp_settings_payload())


@app.post("/api/settings/smtp")
def save_smtp_settings():
    data = request.get_json() or {}
    try:
        updates, _resolved_password = _validated_smtp_settings(data, allow_keep_password=True)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    _update_env_file(PROJECT_DIR / ".env", updates)
    for key, value in updates.items():
        os.environ[key] = value

    return jsonify({
        "message": "SMTP settings saved.",
        "settings": _smtp_settings_payload(),
    })


@app.post("/api/settings/smtp/test")
def test_smtp_settings():
    data = request.get_json() or {}
    try:
        updates, _resolved_password = _validated_smtp_settings(data, allow_keep_password=True)
        _smtp_probe(updates)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.warning("SMTP settings test failed: %r", exc, exc_info=True)
        return jsonify({"ok": False, "error": _sanitize_smtp_settings_error(exc)}), 400

    return jsonify({
        "ok": True,
        "message": "Connected successfully to the SMTP server.",
    })


@app.get("/api/settings/ai/models")
def list_ollama_models():
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    try:
        resp = http_requests.get(f"{base_url}/api/tags", timeout=5)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        return jsonify({"models": models, "ok": True})
    except Exception as exc:
        return jsonify({"models": [], "ok": False, "error": str(exc)})


@app.get("/api/settings/followup")
def get_followup_settings():
    return jsonify({
        "enabled":     os.getenv("FOLLOWUP_ENABLED", "false").strip().lower() == "true",
        "delay_hours": int(os.getenv("FOLLOWUP_DELAY_HOURS", "24") or 24),
        "max_count":   int(os.getenv("FOLLOWUP_MAX_COUNT", "2") or 2),
    })


@app.post("/api/settings/followup")
def save_followup_settings():
    data = request.get_json() or {}
    enabled = bool(data.get("enabled"))
    try:
        delay_hours = int(data.get("delay_hours", 24))
        max_count   = int(data.get("max_count", 2))
    except (TypeError, ValueError):
        return jsonify({"error": "delay_hours and max_count must be integers."}), 400

    if not (1 <= delay_hours <= 168):
        return jsonify({"error": "delay_hours must be between 1 and 168 (1 week)."}), 400
    if not (1 <= max_count <= 5):
        return jsonify({"error": "max_count must be between 1 and 5."}), 400

    updates = {
        "FOLLOWUP_ENABLED":     "true" if enabled else "false",
        "FOLLOWUP_DELAY_HOURS": str(delay_hours),
        "FOLLOWUP_MAX_COUNT":   str(max_count),
    }
    _update_env_file(PROJECT_DIR / ".env", updates)
    for k, v in updates.items():
        os.environ[k] = v
    logger.info("Follow-up settings updated: enabled=%s delay=%dh max=%d", enabled, delay_hours, max_count)
    return jsonify({"message": "Follow-up settings saved.", "enabled": enabled, "delay_hours": delay_hours, "max_count": max_count})


@app.get("/api/settings/desktop")
def get_desktop_settings():
    return jsonify(desktop_settings_payload())


@app.post("/api/settings/desktop")
def save_desktop_settings():
    data = request.get_json() or {}
    enabled = bool(data.get("background_launch_enabled"))
    try:
        payload = update_background_launch(enabled)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.error("Failed to update desktop settings: %r", exc, exc_info=True)
        return jsonify({"error": "Could not update the Windows startup shortcut."}), 500
    return jsonify(payload)


@app.get("/api/settings/ai/test")
def test_ai_connection():
    provider = os.getenv("AI_PROVIDER", "ollama")
    if provider == "ollama":
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        try:
            resp = http_requests.get(f"{base_url}/api/tags", timeout=5)
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            return jsonify({"ok": True, "models": models, "provider": "ollama"})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc), "provider": "ollama"})
    if provider == "openai":
        # OpenAI — just confirm the key is set
        key = os.getenv("OPENAI_API_KEY", "")
        if not key:
            return jsonify({"ok": False, "error": "OPENAI_API_KEY is not set.", "provider": "openai"})
        return jsonify({"ok": True, "provider": "openai", "models": [os.getenv("OPENAI_MODEL", "gpt-4o-mini")]})

    if provider == "claude":
        key = os.getenv("ANTHROPIC_API_KEY", "")
        model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022")
        if not key:
            return jsonify({"ok": False, "error": "ANTHROPIC_API_KEY is not set.", "provider": "claude"})
        try:
            resp = http_requests.get(
                f"https://api.anthropic.com/v1/models/{model}",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            return jsonify({"ok": True, "provider": "claude", "models": [data.get("id", model)]})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc), "provider": "claude"})

    if provider == "deepseek":
        key = os.getenv("DEEPSEEK_API_KEY", "")
        if not key:
            return jsonify({"ok": False, "error": "DEEPSEEK_API_KEY is not set.", "provider": "deepseek"})
        return jsonify({"ok": True, "provider": "deepseek", "models": [os.getenv("DEEPSEEK_MODEL", "deepseek-chat")]})

    if provider == "qwen":
        key = os.getenv("QWEN_API_KEY", "")
        if not key:
            return jsonify({"ok": False, "error": "QWEN_API_KEY is not set.", "provider": "qwen"})
        return jsonify({"ok": True, "provider": "qwen", "models": [os.getenv("QWEN_MODEL", "qwen-plus")]})

    if provider == "kimi":
        key = os.getenv("KIMI_API_KEY", "")
        if not key:
            return jsonify({"ok": False, "error": "KIMI_API_KEY is not set.", "provider": "kimi"})
        return jsonify({"ok": True, "provider": "kimi", "models": [os.getenv("KIMI_MODEL", "moonshot-v1-8k")]})

    return jsonify({"ok": False, "error": f"Unknown provider '{provider}'.", "provider": provider}), 400


# ─── Reset ────────────────────────────────────────────────────────────────────

@app.post("/api/reset")
def reset():
    inbox_monitor.stop()
    # Remove uploaded attachments for this campaign
    for fn in stored_attachments():
        p = ATTACH_DIR / fn
        if p.exists():
            p.unlink(missing_ok=True)
    reset_state()
    return jsonify({"message": "Campaign state cleared."})


# ─── Frontend SPA serving ─────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    # If the requested route doesn't match and not an API call, serve the SPA
    if not request.path.startswith("/api/"):
        return app.send_static_file("index.html")
    return jsonify({"error": "Not found"}), 404

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_spa(path):
    if path and os.path.exists(os.path.join(app.static_folder, path)):
        return app.send_static_file(path)
    return app.send_static_file("index.html")
