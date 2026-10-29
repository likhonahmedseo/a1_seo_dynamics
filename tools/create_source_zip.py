"""
Create a clean source-distribution ZIP of A1 Mail Dynamics.

Excludes:  .venv/, __pycache__/, node_modules/, dist/, release_dist/,
           .git/, *.pyc, *.DS_Store, Thumbs.db, logs/, data/runtime/,
           data/attachments/

Usage:
    python tools/create_source_zip.py [--output release_dist]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRODUCT_SLUG = "A1MailDynamics"

_SKIP_DIRS = {
    ".venv", "node_modules", "__pycache__", ".git",
    "dist", "release_dist",
}
_SKIP_PATTERNS = re.compile(
    r"(\.pyc|\.pyo|\.DS_Store|Thumbs\.db|\.env\.bak|desktop\.ini)$"
)
_SKIP_SUBTREES = {
    "data/runtime",
    "data/attachments",
    "logs",
}


def _should_skip(rel: Path) -> bool:
    parts = rel.parts
    # Skip excluded top-level directories
    if parts and parts[0] in _SKIP_DIRS:
        return True
    # Skip excluded subtrees (e.g. data/runtime)
    rel_posix = rel.as_posix()
    for subtree in _SKIP_SUBTREES:
        if rel_posix.startswith(subtree + "/") or rel_posix == subtree:
            return True
    # Skip by pattern
    if _SKIP_PATTERNS.search(rel.name):
        return True
    return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _version() -> str:
    # Try to read from pyproject.toml or a __version__ file; fall back to date
    version_file = PROJECT_ROOT / "VERSION"
    if version_file.exists():
        return version_file.read_text().strip()
    return datetime.now(UTC).strftime("%Y%m%d")


def _arch_slug() -> str:
    machine = platform.machine().strip().lower()
    if machine in {"amd64", "x86_64"}:
        return "x64"
    if machine in {"arm64", "aarch64"}:
        return "arm64"
    return machine or "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description="Package A1 Mail Dynamics source into a ZIP.")
    parser.add_argument(
        "--output",
        default="release_dist",
        help="Directory to write the ZIP and manifest into (default: release_dist).",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Override the ZIP base name (default: A1MailDynamics-source-<version>).",
    )
    args = parser.parse_args()

    version = _version()
    base_name = args.name or f"{PRODUCT_SLUG}-source-{version}"
    output_dir = (PROJECT_ROOT / args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    zip_path = output_dir / f"{base_name}.zip"
    manifest_path = output_dir / f"{base_name}-manifest.json"

    print(f"Packaging {PRODUCT_SLUG} source -> {zip_path.relative_to(PROJECT_ROOT)}")

    included: list[dict] = []
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for abs_path in sorted(PROJECT_ROOT.rglob("*")):
            if not abs_path.is_file():
                continue
            rel = abs_path.relative_to(PROJECT_ROOT)
            if _should_skip(rel):
                continue
            arc_name = f"{base_name}/{rel.as_posix()}"
            zf.write(abs_path, arc_name)
            included.append({
                "path": rel.as_posix(),
                "size": abs_path.stat().st_size,
                "sha256": _sha256(abs_path),
            })
            print(f"  + {rel.as_posix()}")

    zip_size = zip_path.stat().st_size
    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "product": PRODUCT_SLUG,
        "version": version,
        "archive_name": zip_path.name,
        "archive_size": zip_size,
        "archive_sha256": _sha256(zip_path),
        "file_count": len(included),
        "files": included,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print()
    print(f"ZIP archive : {zip_path}")
    print(f"Manifest    : {manifest_path}")
    print(f"Files packed: {len(included)}")
    print(f"Archive size: {zip_size / 1_048_576:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
