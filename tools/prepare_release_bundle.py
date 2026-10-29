from __future__ import annotations

import argparse
import secrets
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
_BLANK_ENV_KEYS = {
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY",
    "QWEN_API_KEY",
    "KIMI_API_KEY",
    "IMAP_USERNAME",
    "IMAP_PASSWORD",
}
_PLACEHOLDER_ENV_VALUES = {
    "SMTP_USERNAME": "you@example.com",
    "SMTP_PASSWORD": "your-app-password",
}
_DOC_FILES = [
    "README.md",
    "INSTALLATION_GUIDE.md",
    "INSTALL_AND_ACTIVATE.md",
    "BROWSER_MODE.md",
    "TROUBLESHOOTING.md",
    "LICENSE_AND_RENEWAL.md",
]
_WINDOWS_LAUNCHERS = [
    "Open Desktop App.bat",
    "Open in Browser.bat",
]
_MACOS_LAUNCHERS = [
    "Open Desktop App.command",
    "Open in Browser.command",
]


def _parse_env_text(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()
    return values


def _upsert_env_value(text: str, key: str, value: str) -> str:
    lines = text.splitlines()
    updated = False
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and stripped.split("=", 1)[0].strip() == key:
            new_lines.append(f"{key}={value}")
            updated = True
        else:
            new_lines.append(line)
    if not updated:
        if new_lines and new_lines[-1].strip():
            new_lines.append("")
        new_lines.append(f"{key}={value}")
    return "\n".join(new_lines).rstrip() + "\n"


def _copy_file(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _customer_env_template_text() -> str:
    root_env_example = PROJECT_ROOT / ".env.example"
    if root_env_example.exists():
        return root_env_example.read_text(encoding="utf-8")
    return ""


def _sanitize_customer_env(text: str, *, with_secret: bool) -> str:
    sanitized = text
    for key in sorted(_BLANK_ENV_KEYS):
        sanitized = _upsert_env_value(sanitized, key, "")
    for key, value in _PLACEHOLDER_ENV_VALUES.items():
        sanitized = _upsert_env_value(sanitized, key, value)
    sanitized = _upsert_env_value(sanitized, "APP_ENV", "production")
    sanitized = _upsert_env_value(sanitized, "ALLOW_SELF_SIGNUP", "true")
    sanitized = _upsert_env_value(
        sanitized,
        "FLASK_SECRET_KEY",
        secrets.token_hex(32) if with_secret else "",
    )
    return sanitized


def _seed_env(target_dir: Path) -> None:
    target_env_example = target_dir / ".env.example"
    target_env = target_dir / ".env"
    template = _customer_env_template_text()

    target_env_example.write_text(
        _sanitize_customer_env(template, with_secret=False),
        encoding="utf-8",
    )
    target_env.write_text(
        _sanitize_customer_env(template, with_secret=True),
        encoding="utf-8",
    )


def _prepare_layout(target_dir: Path, *, platform_name: str = "windows", seed_env: bool = True) -> None:
    for doc_name in _DOC_FILES:
        _copy_file(PROJECT_ROOT / doc_name, target_dir / doc_name)

    if platform_name == "windows":
        (target_dir / "data" / "attachments").mkdir(parents=True, exist_ok=True)
        (target_dir / "data" / "runtime").mkdir(parents=True, exist_ok=True)
        (target_dir / "logs").mkdir(parents=True, exist_ok=True)
        for launcher in _WINDOWS_LAUNCHERS:
            _copy_file(PROJECT_ROOT / launcher, target_dir / launcher)
        _copy_file(PROJECT_ROOT / "data" / "sample_contacts.csv", target_dir / "data" / "sample_contacts.csv")
        if seed_env:
            _seed_env(target_dir)
        return

    if platform_name == "macos":
        for launcher in _MACOS_LAUNCHERS:
            _copy_file(PROJECT_ROOT / launcher, target_dir / launcher)
        return

    raise ValueError(f"Unsupported platform layout: {platform_name}")


def _clean_runtime_artifacts(target_dir: Path) -> None:
    runtime_dir = target_dir / "data" / "runtime"
    attachments_dir = target_dir / "data" / "attachments"
    logs_dir = target_dir / "logs"

    for folder in (runtime_dir, attachments_dir, logs_dir):
        if not folder.exists():
            continue
        for child in folder.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a clean customer-facing release bundle.")
    parser.add_argument("target_dir", help="Path to the built app folder, e.g. dist/A1MailDynamics")
    parser.add_argument(
        "--platform",
        default="windows",
        choices=("windows", "macos"),
        help="Target release platform layout.",
    )
    parser.add_argument(
        "--clean-runtime",
        action="store_true",
        help="Remove machine-specific runtime artifacts such as lock files, logs, and system state.",
    )
    args = parser.parse_args()

    target_dir = Path(args.target_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    _prepare_layout(target_dir, platform_name=args.platform, seed_env=args.platform == "windows")
    if args.clean_runtime:
        _clean_runtime_artifacts(target_dir)
        _prepare_layout(target_dir, platform_name=args.platform, seed_env=args.platform == "windows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
