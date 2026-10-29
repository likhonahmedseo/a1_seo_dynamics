from __future__ import annotations

import json
import os
import threading
from typing import Any

from app.paths import RUNTIME_DIR

SYSTEM_STATE_FILE = RUNTIME_DIR / "system_state.json"

_system_lock = threading.Lock()

_DEFAULTS: dict[str, Any] = {
    "accounts": [],
    "license": {},
}


def _fresh_state() -> dict[str, Any]:
    return {
        "accounts": [],
        "license": {},
    }


def load_system_state() -> dict[str, Any]:
    with _system_lock:
        if not SYSTEM_STATE_FILE.exists():
            return _fresh_state()
        try:
            state = json.loads(SYSTEM_STATE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = _fresh_state()
        for key, default in _DEFAULTS.items():
            if key not in state:
                state[key] = [] if isinstance(default, list) else dict(default)
        return state


def save_system_state(
    *,
    accounts: list[dict[str, Any]] | None = None,
    license_data: dict[str, Any] | None = None,
) -> None:
    with _system_lock:
        if not SYSTEM_STATE_FILE.exists():
            current = _fresh_state()
        else:
            try:
                current = json.loads(SYSTEM_STATE_FILE.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                current = _fresh_state()

        if accounts is not None:
            current["accounts"] = accounts
        if license_data is not None:
            current["license"] = license_data

        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        temp_file = SYSTEM_STATE_FILE.with_suffix(".tmp")
        with temp_file.open("w", encoding="utf-8") as handle:
            json.dump(current, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_file, SYSTEM_STATE_FILE)
