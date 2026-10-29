from __future__ import annotations

import logging
import os
import re
from typing import Literal

# .env is loaded once by app.paths (imported transitively) — no per-module load needed.
import app.paths  # noqa: F401
import requests
from app.services.scheduling import (
    append_cold_outreach_booking_link,
    append_schedule_links,
    build_cold_outreach_booking_context,
    build_schedule_context,
)

ReplyClass = Literal["interested", "question", "objection", "not_interested", "out_of_office", "other"]

logger = logging.getLogger(__name__)
_ANTHROPIC_VERSION = "2023-06-01"

# ── Email meta-maps ────────────────────────────────────────────────────────────

_LENGTH_WORDS: dict[str, str] = {
    "punchy": "30–50 words — extremely tight, one specific value point and one CTA, ideal for cold outreach",
    "short":  "60–90 words",
    "medium": "160–220 words",
    "long":   "280–360 words",
}

_TYPE_INSTRUCTION: dict[str, str] = {
    "cold_outreach": (
        "This is a COLD OUTREACH email — the recipient has never heard from you. "
        "Lead with value immediately. Do not reference any prior contact."
    ),
    "follow_up": (
        "This is a FOLLOW-UP to a previous outreach they may not have replied to. "
        "Briefly acknowledge the prior reach-out and add a fresh angle or new piece of value."
    ),
    "introduction": (
        "This is an INTRODUCTION email. Focus on who you are, what you do, "
        "and why connecting benefits both sides."
    ),
    "partnership": (
        "This is a PARTNERSHIP PROPOSAL. Frame it as a mutually beneficial collaboration "
        "— make the win-win crystal clear."
    ),
    "invitation": (
        "This is an INVITATION to an event, webinar, or meeting. "
        "Make the value of attending immediately obvious and include a clear date/CTA."
    ),
    "re_engagement": (
        "This is a RE-ENGAGEMENT email to someone who went cold. "
        "Be brief, low-pressure, and offer something new or different from before."
    ),
}


# ── Provider resolution ────────────────────────────────────────────────────────

def _get_provider_config(purpose: str = "standard") -> dict[str, str]:
    """
    Return provider configuration for whichever AI provider is active.

    Supported providers (set via AI_PROVIDER env var):
      ollama    — local Ollama server (OLLAMA_BASE_URL + OLLAMA_MODEL)
      openai    — OpenAI API (OPENAI_API_KEY + OPENAI_MODEL)
      claude    — Anthropic Claude (ANTHROPIC_API_KEY + ANTHROPIC_MODEL)
      deepseek  — DeepSeek API (DEEPSEEK_API_KEY + DEEPSEEK_MODEL)
      qwen      — Alibaba Qwen / DashScope (QWEN_API_KEY + QWEN_MODEL)
      kimi      — Moonshot Kimi API (KIMI_API_KEY + KIMI_MODEL)

    purpose: "standard" | "smart" — used only for default model selection.
    """
    provider = os.getenv("AI_PROVIDER", "").strip().lower()
    ollama_url = os.getenv("OLLAMA_BASE_URL", "").strip().rstrip("/")
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()

    use_ollama = provider == "ollama" or (not provider and bool(ollama_url) and not openai_key and not anthropic_key)
    use_openai = provider == "openai" or (not provider and bool(openai_key))
    use_claude = provider == "claude" or (not provider and not openai_key and bool(anthropic_key))

    if use_ollama:
        if not ollama_url:
            raise RuntimeError(
                "AI_PROVIDER is 'ollama' but OLLAMA_BASE_URL is not set. "
                "Configure it in Settings or your .env file."
            )
        model = os.getenv("OLLAMA_MODEL", "llama3.2")
        return {
            "provider": "ollama",
            "base_url": f"{ollama_url}/v1",
            "api_key": "ollama",
            "model": model,
        }

    if use_openai:
        if not openai_key:
            raise RuntimeError(
                "AI_PROVIDER is 'openai' but OPENAI_API_KEY is not set. "
                "Add your key in Settings or your .env file."
            )
        default_model = "gpt-4o" if purpose == "smart" else "gpt-4o-mini"
        model = os.getenv("OPENAI_MODEL", default_model)
        return {
            "provider": "openai",
            "api_key": openai_key,
            "model": model,
        }

    if use_claude:
        if not anthropic_key:
            raise RuntimeError(
                "AI_PROVIDER is 'claude' but ANTHROPIC_API_KEY is not set. "
                "Add your key in Settings or your .env file."
            )
        default_model = "claude-sonnet-4-20250514" if purpose == "smart" else "claude-3-5-haiku-20241022"
        model = os.getenv("ANTHROPIC_MODEL", default_model)
        return {
            "provider": "claude",
            "api_key": anthropic_key,
            "model": model,
        }

    if provider == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "AI_PROVIDER is 'deepseek' but DEEPSEEK_API_KEY is not set. "
                "Add your key in Settings or your .env file."
            )
        default_model = "deepseek-chat" if purpose == "standard" else "deepseek-reasoner"
        model = os.getenv("DEEPSEEK_MODEL", default_model)
        return {
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com/v1",
            "api_key": api_key,
            "model": model,
        }

    if provider == "qwen":
        api_key = os.getenv("QWEN_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "AI_PROVIDER is 'qwen' but QWEN_API_KEY is not set. "
                "Add your key in Settings or your .env file."
            )
        model = os.getenv("QWEN_MODEL", "qwen-plus")
        return {
            "provider": "qwen",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key": api_key,
            "model": model,
        }

    if provider == "kimi":
        api_key = os.getenv("KIMI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "AI_PROVIDER is 'kimi' but KIMI_API_KEY is not set. "
                "Add your key in Settings or your .env file."
            )
        model = os.getenv("KIMI_MODEL", "moonshot-v1-8k")
        return {
            "provider": "kimi",
            "base_url": "https://api.moonshot.cn/v1",
            "api_key": api_key,
            "model": model,
        }

    raise RuntimeError(
        "No AI provider configured.\n"
        "• Ollama:    set AI_PROVIDER=ollama and OLLAMA_BASE_URL in Settings\n"
        "• OpenAI:    set AI_PROVIDER=openai and OPENAI_API_KEY in Settings\n"
        "• Claude:    set AI_PROVIDER=claude and ANTHROPIC_API_KEY in Settings\n"
        "• DeepSeek:  set AI_PROVIDER=deepseek and DEEPSEEK_API_KEY in Settings\n"
        "• Qwen:      set AI_PROVIDER=qwen and QWEN_API_KEY in Settings\n"
        "• Kimi:      set AI_PROVIDER=kimi and KIMI_API_KEY in Settings"
    )


def _chat(
    messages: list[dict],
    purpose: str = "standard",
    temperature: float = 0.7,
    max_tokens: int = 900,
) -> str:
    """Call the active AI provider and return the assistant text."""
    try:
        config = _get_provider_config(purpose)
        provider = config["provider"]

        # All OpenAI-compatible providers (ollama, openai, deepseek, qwen, kimi)
        if provider in {"ollama", "openai", "deepseek", "qwen", "kimi"}:
            from openai import OpenAI

            client_kwargs = {"api_key": config["api_key"]}
            if "base_url" in config:
                client_kwargs["base_url"] = config["base_url"]

            client = OpenAI(**client_kwargs)
            response = client.chat.completions.create(
                model=config["model"],
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content
            return content.strip() if content else ""

        system_parts: list[str] = []
        anthropic_messages: list[dict[str, str]] = []
        for message in messages:
            role = str(message.get("role", "")).strip().lower()
            content = str(message.get("content", "") or "").strip()
            if not content:
                continue
            if role == "system":
                system_parts.append(content)
            elif role in {"user", "assistant"}:
                anthropic_messages.append({"role": role, "content": content})

        if not anthropic_messages:
            raise RuntimeError("No user/assistant messages were supplied for Claude.")

        payload: dict[str, object] = {
            "model": config["model"],
            "max_tokens": max_tokens,
            "messages": anthropic_messages,
            "temperature": temperature,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)

        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": config["api_key"],
                "anthropic-version": _ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            json=payload,
            timeout=45,
        )
        response.raise_for_status()
        data = response.json()
        text = "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        )
        return text.strip()
    except Exception as e:
        logger.error(f"AI chat completion failed: {e}", exc_info=True)
        return ""


# ── Outbound email generation ──────────────────────────────────────────────────

def generate_email_copy(contact_dict: dict, config_dict: dict) -> tuple[str, str]:
    """
    Generate a fully personalized outbound email for one contact.
    Returns (subject, body).
    """
    email_type   = config_dict.get("email_type",   "cold_outreach")
    email_length = config_dict.get("email_length", "medium")
    word_target  = _LENGTH_WORDS.get(email_length, "150–200 words")
    type_note    = _TYPE_INSTRUCTION.get(email_type, _TYPE_INSTRUCTION["cold_outreach"])

    contact_lines = [
        f"- Email: {contact_dict.get('email', '')}",
        f"- First name: {contact_dict.get('first_name', '') or 'Unknown'}",
        f"- Last name: {contact_dict.get('last_name', '')}",
        f"- Company: {contact_dict.get('company', '') or 'their company'}",
        f"- Role: {contact_dict.get('role', '')}",
        f"- Website: {contact_dict.get('website', '')}",
        f"- Notes: {contact_dict.get('notes', '')}",
    ]
    contact_info = "\n".join(contact_lines)
    schedule_context = build_schedule_context(config_dict)

    signature = "\n".join(filter(None, [
        config_dict.get("sender_name", ""),
        config_dict.get("sender_company", ""),
        config_dict.get("signature", ""),
    ]))

    system_prompt = (
        f"You are a world-class B2B copywriter writing emails on behalf of "
        f"{config_dict.get('sender_name', 'the sender')} from "
        f"{config_dict.get('sender_company', 'the company')}.\n\n"
        f"Writing style: {config_dict.get('tone', 'professional')}, concise, and genuine. "
        "Never use generic openers like 'I hope this finds you well' or 'I wanted to reach out'. "
        "Every sentence must earn its place.\n\n"
        f"Email type context: {type_note}\n\n"
        f"Signature block:\n{signature}"
    )

    user_prompt = (
        f"Write an email using the context below.\n\n"
        f"Mission / value proposition: {config_dict.get('mission', '')}\n"
        f"Offer: {config_dict.get('offer', '')}\n"
        f"Call to action: {config_dict.get('call_to_action', '')}\n\n"
        f"Contact:\n{contact_info}\n\n"
        + (f"{schedule_context}\n\n" if schedule_context else "")
    ) + (
        "Respond in EXACTLY this format (no extra text):\n"
        "SUBJECT: <subject line>\n"
        "BODY:\n<email body>\n\n"
        "Rules:\n"
        f"- Body length: {word_target} — be precise\n"
        "- Subject: compelling and specific, under 60 chars\n"
        "- Use the strongest available context from company, role, website, and notes\n"
        "- Make the email feel informed and a little detailed, not generic or shallow\n"
        "- Explain why the offer is relevant to this specific contact or business\n"
        "- If notes or website context exist, naturally reference at least one of them\n"
        "- Do not invent facts that are not in the provided context\n"
        "- End with the signature block\n"
        "- No fluff openers"
    )

    raw = _chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.7,
        max_tokens=900,
    )
    
    if not raw:
        return "Error: Could not generate subject", "Error: AI generation failed. Please check your AI provider settings and connection in the logs."

    subject, body = _parse_subject_body(raw)
    return subject, append_schedule_links(body, config_dict)


# ── Reply classification ───────────────────────────────────────────────────────

def classify_reply(reply_text: str) -> ReplyClass:
    """Classify the intent of an incoming reply into one of the known categories."""
    categories = (
        "interested      — wants to learn more, book a call, or is open to discussion\n"
        "question        — has a specific question before deciding\n"
        "objection       — concern about price, timing, relevance, etc.\n"
        "not_interested  — clearly doesn't want to continue, says no / remove me\n"
        "out_of_office   — automated out-of-office or vacation reply\n"
        "other           — doesn't fit any of the above"
    )

    raw = _chat(
        messages=[
            {
                "role": "system",
                "content": (
                    "Classify the email reply below into exactly one category. "
                    "Respond with ONLY the category name, nothing else.\n\n"
                    f"Categories:\n{categories}"
                ),
            },
            {
                "role": "user",
                "content": f"Reply to classify:\n---\n{reply_text[:1500]}\n---",
            },
        ],
        temperature=0.0,
        max_tokens=10,
    )

    if not raw:
        return "other"
        
    parts = raw.lower().replace(" ", "_").strip().split()
    result = parts[0] if parts else "other"
    valid: set[ReplyClass] = {
        "interested", "question", "objection", "not_interested", "out_of_office", "other"
    }
    return result if result in valid else "other"  # type: ignore[return-value]


# ── Auto-reply generation ──────────────────────────────────────────────────────

def generate_auto_reply(
    thread_messages: list[dict],
    latest_reply: str,
    classification: ReplyClass,
    config_dict: dict,
) -> str:
    """
    Generate a human-sounding auto-reply given the full conversation thread.
    Returns the email body text, or "SKIP" if no reply should be sent.
    """
    if classification == "out_of_office":
        return "SKIP"

    instruction_map: dict[str, str] = {
        "interested": (
            "They're interested! Move the conversation forward. "
            "Invite them to book an online meeting using the provided booking link when available, "
            "or suggest a specific day/time for a call. "
            "Be warm and enthusiastic but not pushy."
        ),
        "question": (
            "They have a question. Answer it clearly and helpfully. "
            "Then make it easy for them to take the next step, including a booking link when relevant."
        ),
        "objection": (
            "They have a concern or objection. Acknowledge it genuinely, "
            "address it with empathy, and offer a low-commitment next step."
        ),
        "other": "Respond naturally and helpfully to keep the conversation going.",
    }
    instruction = instruction_map.get(classification, instruction_map["other"])

    thread_formatted = "\n\n---\n".join(
        f"[{'YOU' if m['direction'] == 'sent' else 'THEM'}]\n{m['body']}"
        for m in thread_messages[-6:]
    )

    signature = "\n".join(filter(None, [
        config_dict.get("sender_name", ""),
        config_dict.get("sender_company", ""),
        config_dict.get("signature", ""),
    ]))
    schedule_context = build_schedule_context(config_dict)
    cold_outreach_booking_context = ""
    if classification in {"interested", "question"}:
        cold_outreach_booking_context = build_cold_outreach_booking_context(config_dict)

    system_prompt = (
        f"You ARE {config_dict.get('sender_name', 'the sender')} from "
        f"{config_dict.get('sender_company', 'the company')}. "
        f"Writing style: {config_dict.get('tone', 'professional')}, concise, completely human. "
        "Never sound like a bot or use hollow phrases.\n\n"
        f"Your signature:\n{signature}"
    )

    user_prompt = (
        f"Full thread so far:\n{thread_formatted}\n\n"
        f"Their latest reply:\n{latest_reply}\n\n"
        f"Classification: {classification}\n"
        f"What to do: {instruction}\n\n"
        + (f"{schedule_context}\n\n" if schedule_context else "")
        + (f"{cold_outreach_booking_context}\n\n" if cold_outreach_booking_context else "")
    ) + (
        "Write ONLY the reply body text. No subject line. "
        "Under 150 words. Sound completely human. End with your signature."
    )

    raw = _chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        purpose="smart",
        temperature=0.75,
        max_tokens=500,
    )

    if not raw:
        return "SKIP"

    if classification in {"interested", "question"}:
        if str(config_dict.get("email_type", "") or "").strip().lower() == "cold_outreach":
            return append_cold_outreach_booking_link(raw, config_dict)
        return append_schedule_links(raw, config_dict)
    return raw


# ── Follow-up generation ──────────────────────────────────────────────────────

def generate_follow_up(
    thread_messages: list[dict],
    config_dict: dict,
    follow_up_number: int = 1,
) -> tuple[str, str]:
    """
    Generate a polite follow-up email after a prospect went silent.
    Returns (subject, body). The thread is provided so the model can reference
    the previous message and avoid repetition.
    """
    # Pick out the last outbound message (the one we're following up on)
    last_sent = next(
        (m for m in reversed(thread_messages) if m.get("direction") == "sent"),
        None,
    )
    last_subject = (last_sent or {}).get("subject", "").strip()
    last_body    = (last_sent or {}).get("body", "").strip()

    nudge_style_map = {
        1: "First gentle nudge. Reference the prior email briefly, add one new angle, keep it shorter than the original.",
        2: "Second follow-up. Be even briefer. Acknowledge they may be busy. Offer a clear, low-friction next step.",
        3: "Final follow-up — the 'breakup' email. Honest and short: ask if they'd prefer you stop following up.",
    }
    nudge = nudge_style_map.get(follow_up_number, nudge_style_map[2])

    signature = "\n".join(filter(None, [
        config_dict.get("sender_name", ""),
        config_dict.get("sender_company", ""),
        config_dict.get("signature", ""),
    ]))
    schedule_context = build_schedule_context(config_dict)

    system_prompt = (
        f"You are {config_dict.get('sender_name', 'the sender')} from "
        f"{config_dict.get('sender_company', 'the company')}. "
        f"Tone: {config_dict.get('tone', 'professional')}, concise, completely human. "
        "You are following up on a previous outreach. NEVER apologise for following up. "
        "NEVER use phrases like 'just bumping this up' or 'circling back'. "
        "Lead with value, not guilt.\n\n"
        f"Signature:\n{signature}"
    )

    user_prompt = (
        f"Previous email subject: {last_subject}\n\n"
        f"Previous email body:\n{last_body}\n\n"
        f"This is follow-up #{follow_up_number}.\n"
        f"Style: {nudge}\n\n"
        + (f"{schedule_context}\n\n" if schedule_context else "")
    ) + (
        "Respond in EXACTLY this format (no extra text):\n"
        "SUBJECT: <subject — typically 'Re: <previous subject>'>\n"
        "BODY:\n<follow-up body, under 100 words>\n\n"
        "End the body with the signature block."
    )

    raw = _chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.7,
        max_tokens=500,
    )
    
    if not raw:
        return "Error: Could not generate follow-up", "Error: AI generation failed. Please check your AI provider settings and connection in the logs."

    subject, body = _parse_subject_body(raw)
    return subject, append_schedule_links(body, config_dict)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_subject_body(raw: str) -> tuple[str, str]:
    """Parse SUBJECT: … BODY: … from the model response."""
    subject = ""
    body_lines: list[str] = []
    in_body = False

    for line in raw.split("\n"):
        if line.upper().startswith("SUBJECT:"):
            subject = line[len("SUBJECT:"):].strip()
        elif line.upper().startswith("BODY:"):
            in_body = True
        elif in_body:
            body_lines.append(line)

    body = "\n".join(body_lines).strip()

    if not subject or not body:
        parts = raw.split("\n\n", 1)
        subject = re.sub(r'(?i)^SUBJECT:\s*', '', parts[0]).strip()
        body = parts[1].strip() if len(parts) > 1 else raw

    return subject, body
