from __future__ import annotations

import argparse
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate vendor Ed25519 license keys.")
    parser.add_argument(
        "--private-key",
        default="private/vendor-license-private.pem",
        help="Where to write the vendor private key PEM.",
    )
    parser.add_argument(
        "--public-module",
        default="app/license_public_key.py",
        help="Python module to update with the public key PEM.",
    )
    args = parser.parse_args()

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    private_path = Path(args.private_key)
    private_path.parent.mkdir(parents=True, exist_ok=True)
    private_path.write_text(private_pem, encoding="utf-8")

    public_module_path = Path(args.public_module)
    public_module_path.parent.mkdir(parents=True, exist_ok=True)
    public_module_path.write_text(
        '"""Vendor public key used to verify offline license tokens."""\n\n'
        f'LICENSE_PUBLIC_KEY_PEM = """\n{public_pem.strip()}\n""".strip()\n',
        encoding="utf-8",
    )

    print(f"Private key written to {private_path}")
    print(f"Public key module updated at {public_module_path}")
    print("Keep the private key secret. Ship only the generated desktop app.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
