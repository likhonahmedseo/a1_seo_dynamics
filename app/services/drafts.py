"""
Draft email generator — produces conversion-optimised cold outreach emails.

Conversion principles applied
──────────────────────────────
1. Short body (5–9 lines) — busy people scan, not read
2. One specific CTA per email — multiple CTAs kill conversion
3. PS line — the second most-read element in any email; repeats the CTA
4. Specificity beats flattery — reference company, role, or website
5. Intrigue subjects — question / number / "quick idea" drives opens
6. No fluff openers — immediate value from line one
7. Plain language — no marketing jargon
8. Randomised templates — avoids identical body fingerprints that spam
   filters flag when thousands of the same email go out simultaneously
"""
from __future__ import annotations

import random
from textwrap import dedent

from app.models import CampaignConfig, Contact, DraftEmail
from app.services.scheduling import append_schedule_links


def generate_drafts(contacts: list[Contact], config: CampaignConfig) -> list[DraftEmail]:
    return [build_draft(contact, config) for contact in contacts]


# ── Subject line builders ─────────────────────────────────────────────────────

_SUBJECT_TEMPLATES: dict[str, list[str]] = {
    "cold_outreach": [
        "Quick idea for {company}",
        "{company} — one thing I noticed",
        "A thought on {company}'s growth",
        "Question for {first_name} at {company}",
        "Idea to help {company} get more leads",
        "Worth 15 minutes, {first_name}?",
    ],
    "follow_up": [
        "Re: my note about {company}",
        "Still relevant for {company}?",
        "Following up — quick question",
        "Did this land, {first_name}?",
        "One more thought for {company}",
    ],
    "introduction": [
        "Intro — {sender_company} x {company}",
        "Nice to meet you, {first_name}",
        "Connecting from {sender_company}",
    ],
    "partnership": [
        "Partnership idea — {company} + {sender_company}",
        "Worth a quick chat, {first_name}?",
        "Collaboration opportunity",
    ],
    "invitation": [
        "Invitation for {first_name} at {company}",
        "You're invited — a quick look?",
        "{first_name}, can I send you the details?",
    ],
    "re_engagement": [
        "Checking back in, {first_name}",
        "Still relevant for {company}?",
        "A lot has changed — worth another look?",
        "Picking up where we left off",
    ],
}


def build_subject(contact: Contact, config: CampaignConfig) -> str:
    templates = _SUBJECT_TEMPLATES.get(config.email_type, _SUBJECT_TEMPLATES["cold_outreach"])
    tpl = random.choice(templates)
    return tpl.format(
        company=contact.company.strip() or "your team",
        first_name=contact.first_name.strip() or "there",
        sender_company=config.sender_company.strip() or config.sender_name.strip() or "us",
    )


# ── Body template pools ───────────────────────────────────────────────────────

_GREETING: dict[str, list[str]] = {
    "professional": ["Hi {first_name},", "Hello {first_name},"],
    "friendly":     ["Hey {first_name},", "Hi {first_name},"],
    "direct":       ["{first_name},"],
    "warm":         ["Hi {first_name},", "Hello {first_name},"],
}

_TYPE_OPENER: dict[str, list[str]] = {
    "cold_outreach": [
        "I came across {company} and had a specific idea I wanted to share.",
        "I noticed {company} while researching the space — thought this was worth a quick note.",
        "Came across {company}{role_clause} and had a thought worth running by you.",
        "I've been looking at companies in your space and {company} stood out.",
    ],
    "follow_up": [
        "I sent you a note last week — wanted to follow up in case it got buried.",
        "Circling back quickly — I know inboxes fill up fast.",
        "Just making sure my earlier message didn't get lost in the shuffle.",
        "One more try — I promise this is the last one if it's not relevant.",
    ],
    "introduction": [
        "Quick intro: I'm {sender_name} from {sender_company}.",
        "I wanted to introduce myself — {sender_name}, {sender_company}.",
    ],
    "partnership": [
        "I think {sender_company} and {company} could do something interesting together.",
        "I've been looking at potential partners and {company} kept coming up.",
    ],
    "invitation": [
        "I wanted to personally reach out and invite you to take a look at something.",
        "I'd love to get {company} involved — here's the short version.",
    ],
    "re_engagement": [
        "It's been a while — wanted to check back in with a fresh angle.",
        "Things have moved since we last connected. Wanted to share an update.",
    ],
}

_SPECIFICITY_WITH_NOTES: list[str] = [
    "Given that {notes}, I think there's a real opening here.",
    "With {notes} in mind, the timing feels right.",
    "Noting that {notes} — this seems especially relevant right now.",
]

_SPECIFICITY_WITH_WEBSITE: list[str] = [
    "From a quick look at {website}, I can see a few areas where {company} could gain an edge.",
    "I checked out {website} and had some thoughts on where there's room to grow.",
]

_SPECIFICITY_WITH_ROLE: list[str] = [
    "For someone in your role{role_clause}, this tends to be a high-priority challenge.",
    "This is typically a pressing issue for {role} — thought you'd find it relevant.",
]

_SPECIFICITY_GENERIC: list[str] = [
    "Most teams like {company} are dealing with the same challenge right now.",
    "This comes up often for companies at {company}'s stage.",
    "I've seen this make a real difference for similar teams.",
]

_CTA_WRAPPERS: list[str] = [
    "Would you be open to {cta}?",
    "Any chance {cta} works for you?",
    "Up for {cta}?",
    "Is {cta} something that would make sense right now?",
    "Worth exploring — {cta}?",
]

_PS_LINES: list[str] = [
    "PS — happy to {cta} — I'll work around your schedule.",
    "PS — even a quick 15 minutes is enough to see if this is a fit.",
    "PS — I can send a one-pager first if that's easier.",
    "PS — no slides, no pitch deck — just a straightforward conversation.",
    "PS — if timing isn't right, I'm happy to reconnect in a month.",
]


def build_draft(contact: Contact, config: CampaignConfig) -> DraftEmail:
    first_name   = contact.first_name.strip() or "there"
    company      = contact.company.strip()    or "your team"
    role         = contact.role.strip()
    role_clause  = f" as {role}" if role else ""
    notes        = contact.notes.strip()
    website      = contact.website.strip()
    sender_name  = config.sender_name.strip() or "the team"
    sender_co    = config.sender_company.strip() or sender_name
    mission      = config.mission.strip()
    offer        = config.offer.strip()
    cta          = config.call_to_action.strip()
    tone         = config.tone.lower()

    subject  = build_subject(contact, config)

    greeting_pool = _GREETING.get(tone, _GREETING["professional"])
    greeting = random.choice(greeting_pool).format(first_name=first_name)

    opener_pool = _TYPE_OPENER.get(config.email_type, _TYPE_OPENER["cold_outreach"])
    opener = random.choice(opener_pool).format(
        company=company, role_clause=role_clause,
        sender_name=sender_name, sender_company=sender_co,
    )

    # Pick the most specific available context signal
    if notes:
        specificity = random.choice(_SPECIFICITY_WITH_NOTES).format(notes=notes)
    elif website:
        specificity = random.choice(_SPECIFICITY_WITH_WEBSITE).format(website=website, company=company)
    elif role:
        specificity = random.choice(_SPECIFICITY_WITH_ROLE).format(role_clause=role_clause, role=role)
    else:
        specificity = random.choice(_SPECIFICITY_GENERIC).format(company=company)

    value_line  = f"We {mission} — specifically, {offer}."
    cta_wrapper = random.choice(_CTA_WRAPPERS).format(cta=cta)
    sig         = build_signature(config)
    ps          = random.choice(_PS_LINES).format(cta=cta)

    body = dedent(f"""
        {greeting}

        {opener}

        {specificity}

        {value_line}

        {cta_wrapper}

        {sig}

        {ps}
    """).strip()

    body = append_schedule_links(body, config.__dict__)

    return DraftEmail(
        email=contact.email,
        first_name=contact.first_name,
        company=contact.company,
        subject=subject,
        body=body,
    )


def build_signature(config: CampaignConfig) -> str:
    lines = [
        config.sender_name.strip() or "Your Name",
        config.sender_company.strip(),
        config.signature.strip(),
    ]
    return "\n".join(line for line in lines if line)


def shorten_text(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


# ── Backward-compat helpers ───────────────────────────────────────────────────

def build_context_sentence(company_text: str, role_text: str, website_text: str, notes_text: str) -> str:
    website_clause = f" via {website_text}" if website_text else ""
    notes_clause = f" and noticed {notes_text}" if notes_text else ""
    return (
        f"From what I saw about {company_text}{role_text}{website_clause}, "
        f"it looks like there may be room to improve{notes_clause}."
    )


def build_relevance_sentence(offer_text: str, notes_text: str) -> str:
    if notes_text:
        return f"That is why I think {offer_text} could be especially relevant right now."
    return f"I think {offer_text} could be genuinely relevant for where things stand today."
