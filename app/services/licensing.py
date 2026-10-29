from __future__ import annotations

import base64
import hashlib
import json
import platform
import uuid
from datetime import UTC, datetime
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.license_public_key import LICENSE_PUBLIC_KEY_PEM
from app.services.system_store import load_system_state, save_system_state

PRODUCT_ID = "A1MailDynamics"


def _b64url_decode(value: str) -> bytes:
    padding = "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _load_public_key() -> Ed25519PublicKey:
    pem = (LICENSE_PUBLIC_KEY_PEM or "").strip()
    if "PLACEHOLDER_VENDOR_PUBLIC_KEY" in pem or "BEGIN PUBLIC KEY" not in pem:
        raise RuntimeError("Vendor license public key is not configured.")
    key = serialization.load_pem_public_key(pem.encode("utf-8"))
    if not isinstance(key, Ed25519PublicKey):
        raise RuntimeError("Vendor license public key must be an Ed25519 public key.")
    return key


def current_machine_id() -> str:
    host = platform.node().strip().lower()
    system = platform.system().strip().lower()
    release = platform.release().strip().lower()
    mac = f"{uuid.getnode():012x}"
    raw = f"{PRODUCT_ID}|{host}|{system}|{release}|{mac}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()
    return digest[:32]


def verify_license_token(token: str) -> dict[str, Any]:
    normalized = "".join((token or "").strip().split())
    if "." not in normalized:
        raise ValueError("License token format is invalid.")

    payload_b64, signature_b64 = normalized.split(".", 1)
    try:
        payload_bytes = _b64url_decode(payload_b64)
        signature = _b64url_decode(signature_b64)
    except Exception as exc:
        raise ValueError("License token could not be decoded.") from exc

    try:
        _load_public_key().verify(signature, payload_bytes)
    except InvalidSignature as exc:
        raise ValueError("License signature is invalid.") from exc

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception as exc:
        raise ValueError("License payload is invalid.") from exc

    if payload.get("product") != PRODUCT_ID:
        raise ValueError("This license is not for A1 Mail Dynamics.")

    machine_id = str(payload.get("machine_id") or "").strip().upper()
    current_id = current_machine_id()
    if machine_id and machine_id != "*" and machine_id != current_id:
        raise ValueError(
            f"This license is bound to machine {machine_id} but this machine's ID is {current_id}. "
            "Ask the vendor to generate a new license for your Machine ID, or request a universal (*) license."
        )

    expires_at = str(payload.get("expires_at") or "").strip()
    if expires_at:
        try:
            expires = _parse_iso_datetime(expires_at)
        except ValueError as exc:
            raise ValueError("License expiry format is invalid.") from exc
        if expires < datetime.now(UTC):
            raise ValueError("This license has expired.")

    return {
        "token": normalized,
        "payload": payload,
        "machine_id": current_id,
        "active": True,
    }


def activate_license(token: str) -> dict[str, Any]:
    verified = verify_license_token(token)
    payload = verified["payload"]
    license_state = {
        "token": verified["token"],
        "activated_at": datetime.utcnow().isoformat(),
        "customer_name": payload.get("customer_name", ""),
        "customer_email": payload.get("customer_email", ""),
        "license_type": payload.get("license_type", "lifetime"),
        "machine_id": verified["machine_id"],
        "expires_at": payload.get("expires_at", ""),
        "issued_at": payload.get("issued_at", ""),
        "product": payload.get("product", PRODUCT_ID),
        "notes": payload.get("notes", ""),
    }
    save_system_state(license_data=license_state)
    return get_license_status()


def get_license_status() -> dict[str, Any]:
    current_id = current_machine_id()
    state = load_system_state().get("license", {})
    token = str(state.get("token") or "").strip()

    if not token:
        return {
            "configured": is_public_key_configured(),
            "active": False,
            "machine_id": current_id,
            "reason": "No license has been activated on this machine.",
            "customer_name": "",
            "customer_email": "",
            "license_type": "",
            "expires_at": "",
        }

    try:
        verified = verify_license_token(token)
        payload = verified["payload"]
        return {
            "configured": is_public_key_configured(),
            "active": True,
            "machine_id": current_id,
            "reason": "",
            "customer_name": payload.get("customer_name", ""),
            "customer_email": payload.get("customer_email", ""),
            "license_type": payload.get("license_type", "lifetime"),
            "expires_at": payload.get("expires_at", ""),
            "issued_at": payload.get("issued_at", ""),
            "notes": payload.get("notes", ""),
        }
    except Exception as exc:
        return {
            "configured": is_public_key_configured(),
            "active": False,
            "machine_id": current_id,
            "reason": str(exc),
            "customer_name": state.get("customer_name", ""),
            "customer_email": state.get("customer_email", ""),
            "license_type": state.get("license_type", ""),
            "expires_at": state.get("expires_at", ""),
        }


def is_public_key_configured() -> bool:
    try:
        _load_public_key()
    except Exception:
        return False
    return True


def _parse_iso_datetime(raw: str) -> datetime:
    candidate = raw.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    parsed = datetime.fromisoformat(candidate)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
