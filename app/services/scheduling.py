from __future__ import annotations

import os
import re
from typing import Mapping

def _cold_outreach_booking_url() -> str:
    return os.getenv("COLD_OUTREACH_BOOKING_URL", "").strip()


def normalize_schedule_url(value: str) -> str:
    """Trim a scheduling URL and add https:// when the user omitted a scheme."""
    url = (value or "").strip()
    if not url:
        return ""
    if re.match(r"^[a-z][a-z0-9+.-]*://", url, re.IGNORECASE):
        return url
    if url.startswith("//"):
        return f"https:{url}"
    return f"https://{url}"


def build_schedule_context(config: Mapping[str, object]) -> str:
    """Return plain-text scheduling options for AI prompts."""
    links = _schedule_links(config)
    if not links:
        return ""
    lines = ["Scheduling options available to include when relevant:"]
    lines.extend(f"- {label}: {url}" for label, url in links)
    return "\n".join(lines)


def append_schedule_links(body: str, config: Mapping[str, object], heading: str = "Book a time:") -> str:
    """Append Meet/Calendar links to an email body if they are configured and missing."""
    text = (body or "").strip()
    links = [(label, url) for label, url in _schedule_links(config) if url not in text]
    if not links:
        return text

    block_lines = [heading]
    block_lines.extend(f"{label}: {url}" for label, url in links)
    block = "\n".join(block_lines)
    return f"{text}\n\n{block}".strip() if text else block


def build_cold_outreach_booking_context(config: Mapping[str, object]) -> str:
    """Return the required online-booking handoff for cold outreach reply prompts."""
    url = _cold_outreach_booking_url()
    if not _is_cold_outreach(config) or not url:
        return ""
    return "\n".join([
        "When the cold outreach converts and they want to talk, invite them to book an online meeting here:",
        f"- Online meeting: {url}",
    ])


def append_cold_outreach_booking_link(
    body: str,
    config: Mapping[str, object],
    heading: str = "Book an online meeting:",
) -> str:
    """Append the configured booking link for cold outreach replies."""
    text = (body or "").strip()
    url = _cold_outreach_booking_url()
    if not _is_cold_outreach(config) or not url or url in text:
        return text

    block = "\n".join([
        heading,
        f"Online meeting: {url}",
    ])
    return f"{text}\n\n{block}".strip() if text else block


def _schedule_links(config: Mapping[str, object]) -> list[tuple[str, str]]:
    meet_link = normalize_schedule_url(str(config.get("google_meet_link", "") or ""))
    calendar_link = normalize_schedule_url(str(config.get("google_calendar_link", "") or ""))

    links: list[tuple[str, str]] = []
    if meet_link:
        links.append(("Google Meet", meet_link))
    if calendar_link:
        links.append(("Google Calendar", calendar_link))
    return links


def _is_cold_outreach(config: Mapping[str, object]) -> bool:
    return str(config.get("email_type", "") or "").strip().lower() == "cold_outreach"
