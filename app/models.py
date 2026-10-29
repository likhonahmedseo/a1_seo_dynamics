from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class Contact:
    email: str
    first_name: str = ""
    last_name: str = ""
    company: str = ""
    role: str = ""
    website: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CampaignConfig:
    mission: str
    sender_name: str
    sender_company: str
    offer: str
    call_to_action: str
    tone: str = "professional"
    signature: str = ""
    google_meet_link: str = ""
    google_calendar_link: str = ""
    email_type: str = "cold_outreach"   # cold_outreach | follow_up | introduction | partnership | invitation | re_engagement
    email_length: str = "medium"        # short | medium | long


@dataclass
class DraftEmail:
    email: str
    subject: str
    body: str
    first_name: str = ""
    company: str = ""
    status: str = "draft"
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)
