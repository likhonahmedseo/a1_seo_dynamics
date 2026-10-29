from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _sha256_for(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a portable release ZIP and checksum from a built bundle.")
    parser.add_argument("target_dir", help="Path to the built app folder, e.g. dist/A1MailDynamics")
    parser.add_argument(
        "--release-root",
        default=str(PROJECT_ROOT / "release_dist"),
        help="Output directory for final release artifacts (default: release_dist)",
    )
    parser.add_argument(
        "--archive-name",
        default="A1MailDynamics-windows-portable",
        help="Base filename for the ZIP and checksum outputs",
    )
    args = parser.parse_args()

    target_dir = Path(args.target_dir).resolve()
    if not target_dir.exists():
        raise FileNotFoundError(f"Built app folder not found: {target_dir}")

    release_root = Path(args.release_root).resolve()
    release_root.mkdir(parents=True, exist_ok=True)

    archive_base = release_root / args.archive_name
    zip_path = Path(shutil.make_archive(str(archive_base), "zip", root_dir=target_dir.parent, base_dir=target_dir.name))
    sha256 = _sha256_for(zip_path)

    checksum_path = release_root / f"{args.archive_name}.sha256.txt"
    checksum_path.write_text(f"{sha256} *{zip_path.name}\n", encoding="utf-8")

    latest_info = release_root / "LATEST_RELEASE.txt"
    latest_info.write_text(
        "\n".join(
            [
                f"Bundle folder: {target_dir}",
                f"ZIP artifact: {zip_path}",
                f"SHA256 file: {checksum_path}",
                f"SHA256: {sha256}",
                "",
                "Distribute either the full built folder above or the ZIP artifact.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Created release archive: {zip_path}")
    print(f"Wrote checksum file: {checksum_path}")
    print(f"Wrote release summary: {latest_info}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
