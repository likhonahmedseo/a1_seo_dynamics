"""
Print the Machine ID for the current machine.

Run this on any machine to get the ID needed to generate a machine-bound license:

    python tools/get_machine_id.py

Or from inside a frozen build folder:

    .\_internal\python.exe tools\get_machine_id.py

Send the printed Machine ID to the vendor so they can generate a license
bound to this specific machine. For a license that works on any machine,
ask the vendor to issue a universal (*) license instead.
"""
from __future__ import annotations

import hashlib
import platform
import uuid

PRODUCT_ID = "A1MailDynamics"


def current_machine_id() -> str:
    host = platform.node().strip().lower()
    system = platform.system().strip().lower()
    release = platform.release().strip().lower()
    mac = f"{uuid.getnode():012x}"
    raw = f"{PRODUCT_ID}|{host}|{system}|{release}|{mac}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()
    return digest[:32]


if __name__ == "__main__":
    machine_id = current_machine_id()
    print()
    print("=" * 60)
    print("  A1 Mail Dynamics — Machine ID")
    print("=" * 60)
    print()
    print(f"  Machine ID:  {machine_id}")
    print()
    print("  Share this ID with your vendor to receive a machine-bound")
    print("  license. For a universal license (any machine), ask for")
    print("  a license with machine_id = *.")
    print()
    print("  System info used to compute this ID:")
    print(f"    Hostname : {platform.node()}")
    print(f"    OS       : {platform.system()} {platform.release()}")
    print(f"    MAC addr : {uuid.getnode():012x}")
    print()
    print("=" * 60)

    try:
        import subprocess
        subprocess.run("clip", input=machine_id.encode(), check=False)
        print("  Machine ID copied to clipboard.")
    except Exception:
        pass
    print()
