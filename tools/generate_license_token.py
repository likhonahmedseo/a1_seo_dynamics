from __future__ import annotations

import argparse
import base64
import json
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an offline A1 Mail Dynamics license token.")
    parser.add_argument("--private-key", required=True, help="Path to the vendor private key PEM.")
    parser.add_argument("--customer-name", required=True, help="Customer or company name.")
    parser.add_argument("--customer-email", default="", help="Customer email address.")
    parser.add_argument("--machine-id", default="*", help="Target machine id, or * for any machine.")
    parser.add_argument("--expires-at", default="", help="ISO8601 expiry, e.g. 2027-12-31T23:59:59Z")
    parser.add_argument(
        "--duration-days",
        type=int,
        default=0,
        help="Set expiry to the end of day UTC after N days. Cannot be combined with --expires-at.",
    )
    parser.add_argument("--license-type", default="lifetime", help="License type label.")
    parser.add_argument("--notes", default="", help="Optional internal note included in the payload.")
    args = parser.parse_args()

    if args.expires_at and args.duration_days:
        raise SystemExit("Use either --expires-at or --duration-days, not both.")
    if args.duration_days < 0:
        raise SystemExit("--duration-days must be zero or greater.")

    private_key_path = Path(args.private_key)
    private_key = serialization.load_pem_private_key(
        private_key_path.read_bytes(),
        password=None,
    )
    if not isinstance(private_key, Ed25519PrivateKey):
        raise SystemExit("Private key must be an Ed25519 private key.")

    issued_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    expires_at = args.expires_at.strip()
    if args.duration_days:
        expiry = datetime.now(UTC).replace(hour=23, minute=59, second=59, microsecond=0)
        from datetime import timedelta
        expiry = expiry + timedelta(days=args.duration_days)
        expires_at = expiry.isoformat().replace("+00:00", "Z")

    payload = {
        "product": "A1MailDynamics",
        "customer_name": args.customer_name.strip(),
        "customer_email": args.customer_email.strip(),
        "machine_id": args.machine_id.strip().upper() or "*",
        "license_type": args.license_type.strip() or "lifetime",
        "issued_at": issued_at,
        "expires_at": expires_at,
        "notes": args.notes.strip(),
    }

    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = private_key.sign(payload_bytes)
    token = f"{_b64url(payload_bytes)}.{_b64url(signature)}"
    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
