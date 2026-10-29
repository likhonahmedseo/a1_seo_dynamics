from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from werkzeug.security import check_password_hash, generate_password_hash

from app.services.system_store import load_system_state, save_system_state

ROLE_ADMIN = "admin"
ROLE_MEMBER = "member"
_VALID_ROLES = {ROLE_ADMIN, ROLE_MEMBER}
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _norm_username(username: str) -> str:
    return (username or "").strip().lower()


def _norm_email(email: str) -> str:
    return (email or "").strip().lower()


def _account_name(account: dict[str, Any]) -> str:
    return (account.get("name") or account.get("display_name") or account.get("username") or "").strip()


def _normalize_account(account: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(account)
    normalized["username"] = _norm_username(account.get("username", ""))
    normalized["email"] = _norm_email(account.get("email", ""))
    normalized["name"] = _account_name(account)
    normalized["display_name"] = normalized["name"]
    normalized["role"] = (account.get("role") or ROLE_MEMBER).strip().lower()
    return normalized


def _public_account(account: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_account(account)
    return {
        "username": normalized["username"],
        "email": normalized.get("email", ""),
        "name": normalized.get("name", ""),
        "display_name": normalized.get("display_name", ""),
        "role": normalized.get("role", ROLE_MEMBER),
        "created_at": normalized.get("created_at"),
        "last_login_at": normalized.get("last_login_at"),
    }


def _load_accounts() -> list[dict[str, Any]]:
    state = load_system_state()
    accounts = state.get("accounts", [])
    normalized_accounts = [_normalize_account(account) for account in accounts]
    if normalized_accounts != accounts:
        save_system_state(accounts=normalized_accounts)
    return normalized_accounts


def _validate_account_fields(*, username: str, email: str, password: str, role: str) -> tuple[str, str, str]:
    normalized = _norm_username(username)
    normalized_email = _norm_email(email)
    normalized_role = (role or ROLE_MEMBER).strip().lower()
    if not normalized:
        raise ValueError("Username is required.")
    if not normalized_email:
        raise ValueError("Email is required.")
    if not _EMAIL_RE.match(normalized_email):
        raise ValueError("Enter a valid email address.")
    if len(password or "") < 8:
        raise ValueError("Password must be at least 8 characters.")
    if normalized_role not in _VALID_ROLES:
        raise ValueError("Role must be admin or member.")
    return normalized, normalized_email, normalized_role


def has_accounts() -> bool:
    return bool(_load_accounts())


def list_accounts() -> list[dict[str, Any]]:
    return [_public_account(account) for account in _load_accounts()]


def get_account(username: str) -> dict[str, Any] | None:
    normalized = _norm_username(username)
    for account in _load_accounts():
        if account.get("username") == normalized:
            return account
    return None


def bootstrap_owner(username: str, password: str, email: str, name: str) -> dict[str, Any]:
    accounts = _load_accounts()
    if accounts:
        raise ValueError("An owner account already exists.")

    normalized, normalized_email, _ = _validate_account_fields(
        username=username,
        email=email,
        password=password,
        role=ROLE_ADMIN,
    )

    account = {
        "username": normalized,
        "email": normalized_email,
        "name": (name or "").strip() or normalized,
        "display_name": (name or "").strip() or normalized,
        "password_hash": generate_password_hash(password),
        "role": ROLE_ADMIN,
        "created_at": _now_iso(),
        "last_login_at": None,
    }
    save_system_state(accounts=[account])
    return _public_account(account)


def authenticate(username: str, password: str) -> dict[str, Any] | None:
    normalized = _norm_username(username)
    normalized_email = _norm_email(username)
    accounts = _load_accounts()
    for account in accounts:
        if account.get("username") != normalized and account.get("email") != normalized_email:
            continue
        if not check_password_hash(account.get("password_hash", ""), password or ""):
            return None
        account["last_login_at"] = _now_iso()
        save_system_state(accounts=accounts)
        return _public_account(account)
    return None


def create_account(
    *,
    username: str,
    password: str,
    email: str,
    name: str,
    role: str,
) -> dict[str, Any]:
    normalized, normalized_email, role = _validate_account_fields(
        username=username,
        email=email,
        password=password,
        role=role,
    )

    accounts = _load_accounts()
    if any(account.get("username") == normalized for account in accounts):
        raise ValueError("That username already exists.")
    if any(account.get("email") == normalized_email for account in accounts):
        raise ValueError("That email is already in use.")

    account = {
        "username": normalized,
        "email": normalized_email,
        "name": (name or "").strip() or normalized,
        "display_name": (name or "").strip() or normalized,
        "password_hash": generate_password_hash(password),
        "role": role,
        "created_at": _now_iso(),
        "last_login_at": None,
    }
    accounts.append(account)
    save_system_state(accounts=accounts)
    return _public_account(account)


def delete_account(username: str, *, actor_username: str) -> None:
    normalized = _norm_username(username)
    actor = _norm_username(actor_username)
    accounts = _load_accounts()
    if not any(account.get("username") == normalized for account in accounts):
        raise ValueError("Account not found.")
    if normalized == actor:
        raise ValueError("You cannot delete the account you are signed in with.")

    remaining = [account for account in accounts if account.get("username") != normalized]
    admin_count = sum(1 for account in remaining if account.get("role") == ROLE_ADMIN)
    if admin_count == 0:
        raise ValueError("At least one admin account must remain.")
    save_system_state(accounts=remaining)


def change_password(username: str, current_password: str, new_password: str) -> None:
    normalized = _norm_username(username)
    if len(new_password or "") < 8:
        raise ValueError("New password must be at least 8 characters.")

    accounts = _load_accounts()
    for account in accounts:
        if account.get("username") != normalized:
            continue
        if not check_password_hash(account.get("password_hash", ""), current_password or ""):
            raise ValueError("Current password is incorrect.")
        account["password_hash"] = generate_password_hash(new_password)
        save_system_state(accounts=accounts)
        return
    raise ValueError("Account not found.")
