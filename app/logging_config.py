"""Centralised logging setup with rotating file handler."""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

from app.paths import LOG_DIR

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

_configured = False


def configure_logging() -> None:
    """Idempotent. Configures root logger once with stdout + rotating file handler."""
    global _configured
    if _configured:
        return
    _configured = True

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    log_dir = LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)

    root = logging.getLogger()
    root.setLevel(level)

    # Clear stale handlers (e.g. from Flask reloader) so we don't double-log
    for h in list(root.handlers):
        root.removeHandler(h)

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    root.addHandler(stream)

    file_handler = RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=5 * 1024 * 1024,   # 5 MB per file
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # Quiet noisy third-party loggers
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def mask_email(addr: str) -> str:
    """Lightly anonymise an email for logging (e.g. j***@example.com)."""
    if not addr or "@" not in addr:
        return addr or "<unknown>"
    local, _, domain = addr.partition("@")
    if len(local) <= 1:
        masked = "*"
    else:
        masked = local[0] + "***"
    return f"{masked}@{domain}"
