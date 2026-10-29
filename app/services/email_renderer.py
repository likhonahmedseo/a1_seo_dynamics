"""
Email renderer — converts a plain-text draft into a properly structured
deliverability-optimised email message (multipart/alternative with text + HTML).

Deliverability features baked in
─────────────────────────────────
• Multipart/alternative   — every provider scores this positively
• Message-ID              — required; missing → spam
• List-Unsubscribe        — required by Gmail / Yahoo for bulk senders (Feb 2024 mandate)
• Reply-To                — keeps conversation out of junk
• From display name       — "Jane Smith <jane@agency.com>" vs bare address
• X-Mailer                — identifies the sending app
• Date                    — explicit (some servers penalise missing Date)
• Plain-text body         — always present; HTML-only → spam
• Minimal CSS HTML        — no heavy tracking pixels; inbox-friendly template
• Preheader / preview text — first line recipients see in mobile inbox lists
• One clear CTA           — conversion best practice
"""
from __future__ import annotations

import email.utils
import hashlib
import html
import os
import re
import textwrap
import time
from email.message import EmailMessage
from typing import Optional


# ── HTML template ─────────────────────────────────────────────────────────────

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{subject}</title>
  <!--[if mso]><xml><o:OfficeDocumentSettings><o:AllowPNG/><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml><![endif]-->
  <style>
    body{{margin:0;padding:0;background:#f9f9f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;font-size:16px;line-height:1.65;color:#1a1a1a}}
    .wrapper{{width:100%;background:#f9f9f9;padding:32px 12px}}
    .card{{max-width:600px;margin:0 auto;background:#ffffff;border-radius:8px;padding:40px 44px 36px;box-shadow:0 1px 4px rgba(0,0,0,.06)}}
    p{{margin:0 0 18px;font-size:16px;line-height:1.65;color:#1a1a1a}}
    .signature{{margin-top:28px;padding-top:20px;border-top:1px solid #ececec;font-size:14px;color:#555}}
    .unsubscribe{{margin-top:28px;font-size:12px;color:#aaa;text-align:center}}
    .unsubscribe a{{color:#aaa}}
    @media(max-width:600px){{.card{{padding:28px 20px}}}}
  </style>
</head>
<body>
  <!-- Preheader (hidden preview text) -->
  <span style="display:none;max-height:0;overflow:hidden;mso-hide:all">{preheader}&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;</span>
  <div class="wrapper">
    <div class="card">
      {body_html}
      <div class="unsubscribe">
        <a href="mailto:{reply_to}?subject=Unsubscribe">Unsubscribe</a>
      </div>
    </div>
  </div>
</body>
</html>"""


def _plain_to_html(text: str) -> str:
    """Convert plain-text email body to simple inbox-safe HTML paragraphs."""
    paragraphs: list[str] = []
    for block in re.split(r"\n{2,}", text.strip()):
        block = block.strip()
        if not block:
            continue
        # Convert single newlines inside a block to <br>
        lines = [html.escape(line) for line in block.splitlines()]
        paragraphs.append("<p>" + "<br>\n".join(lines) + "</p>")
    return "\n".join(paragraphs)


def _extract_preheader(text: str, max_len: int = 100) -> str:
    """Use the first sentence of the body as the email preview / preheader text."""
    first_line = text.strip().splitlines()[0] if text.strip() else ""
    # Drop greeting line (e.g. "Hi John,") — use the second paragraph instead
    if first_line.lower().startswith(("hi ", "hello ", "dear ", "hey ")):
        paragraphs = [p.strip() for p in re.split(r"\n{2,}", text.strip()) if p.strip()]
        first_line = paragraphs[1].splitlines()[0] if len(paragraphs) > 1 else first_line
    first_line = first_line.strip()
    if len(first_line) > max_len:
        first_line = first_line[: max_len - 1] + "…"
    return first_line


def _make_message_id(sender_email: str) -> str:
    """Generate a unique Message-ID header value."""
    domain = sender_email.split("@")[-1] if "@" in sender_email else "localhost"
    unique = hashlib.sha1(f"{time.time_ns()}".encode()).hexdigest()[:20]
    return f"<{unique}@{domain}>"


def _unsubscribe_header(sender_email: str, recipient_email: str) -> str:
    """One-click unsubscribe header (mailto form — no URL needed)."""
    encoded = recipient_email.replace("+", "%2B")
    return f"<mailto:{sender_email}?subject=Unsubscribe%20{encoded}>"


def build_email_message(
    *,
    subject: str,
    body_text: str,
    sender_email: str,
    sender_name: str,
    recipient_email: str,
    reply_to: Optional[str] = None,
    attachments: Optional[list[tuple[bytes, str, str, str]]] = None,
) -> EmailMessage:
    """
    Build a fully-formed, deliverability-optimised EmailMessage.

    Parameters
    ----------
    subject        Email subject line.
    body_text      Plain-text body (will also be rendered as HTML).
    sender_email   Sending address.
    sender_name    Display name shown in the From field.
    recipient_email  Destination address.
    reply_to       Address to receive replies (defaults to sender_email).
    attachments    List of (bytes, maintype, subtype, filename) tuples.
    """
    reply_to = reply_to or sender_email

    # ── Headers ───────────────────────────────────────────────────────────────
    msg = EmailMessage()
    msg["Message-ID"]       = _make_message_id(sender_email)
    msg["Date"]             = email.utils.formatdate(localtime=True)
    msg["From"]             = email.utils.formataddr((sender_name, sender_email))
    msg["Reply-To"]         = reply_to
    msg["To"]               = recipient_email
    msg["Subject"]          = subject
    msg["List-Unsubscribe"] = _unsubscribe_header(reply_to, recipient_email)
    msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    msg["X-Mailer"]         = "A1 Mail Dynamics"
    msg["Precedence"]       = "bulk"        # tells spam checkers this is bulk mail
    msg["MIME-Version"]     = "1.0"

    # ── Body (multipart/alternative: plain + HTML) ────────────────────────────
    preheader = _extract_preheader(body_text)
    html_body = _HTML_TEMPLATE.format(
        subject=html.escape(subject),
        preheader=html.escape(preheader),
        body_html=_plain_to_html(body_text),
        reply_to=reply_to,
    )

    msg.set_content(body_text)                        # text/plain (fallback)
    msg.add_alternative(html_body, subtype="html")    # text/html  (preferred)

    # ── Attachments ───────────────────────────────────────────────────────────
    for data, maintype, subtype, filename in (attachments or []):
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)

    return msg
