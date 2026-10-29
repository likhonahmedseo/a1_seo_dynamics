from __future__ import annotations

import json
import os
import threading
from typing import Any

from app.paths import RUNTIME_DIR

STATE_FILE = RUNTIME_DIR / "campaign_state.json"

_state_lock = threading.Lock()


_DEFAULTS: dict[str, Any] = {
    "contacts": [],
    "drafts": [],
    "form_data": {},
    "conversations": [],
    "attachments": [],
}


def _fresh_state() -> dict[str, Any]:
    return {
        "contacts": [],
        "drafts": [],
        "form_data": {},
        "conversations": [],
        "attachments": [],
    }


def load_state() -> dict[str, Any]:
    with _state_lock:
        if not STATE_FILE.exists():
            return _fresh_state()
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = _fresh_state()
        for key, default in _DEFAULTS.items():
            if key not in state:
                if isinstance(default, list):
                    state[key] = []
                elif isinstance(default, dict):
                    state[key] = {}
                else:
                    state[key] = default
        return state


def save_state(
    *,
    contacts: list[dict[str, Any]] | None = None,
    drafts: list[dict[str, Any]] | None = None,
    form_data: dict[str, Any] | None = None,
    conversations: list[dict[str, Any]] | None = None,
    attachments: list[str] | None = None,
) -> None:
    with _state_lock:
        if not STATE_FILE.exists():
            current = _fresh_state()
        else:
            try:
                current = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                current = _fresh_state()

        if contacts is not None:
            current["contacts"] = contacts
        if drafts is not None:
            current["drafts"] = drafts
        if form_data is not None:
            current["form_data"] = form_data
        if conversations is not None:
            current["conversations"] = conversations
        if attachments is not None:
            current["attachments"] = attachments

        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        temp_file = STATE_FILE.with_suffix(".tmp")
        with temp_file.open("w", encoding="utf-8") as handle:
            json.dump(current, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_file, STATE_FILE)


def reset_state() -> None:
    with _state_lock:
        if STATE_FILE.exists():
            STATE_FILE.unlink()
