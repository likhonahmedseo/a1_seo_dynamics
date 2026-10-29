from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
from datetime import UTC, datetime
from pathlib import Path

from prepare_release_bundle import _clean_runtime_artifacts, _prepare_layout


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRODUCT_SLUG = "A1MailDynamics"
MACOS_APP_NAME = "A1 Mail Dynamics.app"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _collect_file_metadata(root: Path) -> list[dict[str, object]]:
    files: list[dict[str, object]] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    return files


def _normalized_arch(platform_name: str) -> str:
    machine = platform.machine().strip().lower()
    if platform_name == "windows":
        if machine in {"amd64", "x86_64"}:
            return "x64"
        if machine in {"arm64", "aarch64"}:
            return "arm64"
        return machine or "unknown"

    if machine in {"amd64", "x86_64"}:
        return "x64"
    if machine in {"arm64", "aarch64"}:
        return "arm64"
    return machine or "unknown"


def _bundle_dir_name(platform_name: str, arch: str) -> str:
    if platform_name == "windows":
        return PRODUCT_SLUG
    return f"{PRODUCT_SLUG}-macos-{arch}"


def _archive_base_name(platform_name: str, arch: str) -> str:
    if platform_name == "windows":
        return f"{PRODUCT_SLUG}-windows-{arch}"
    return f"{PRODUCT_SLUG}-macos-{arch}"


def _manifest_name(platform_name: str, arch: str) -> str:
    if platform_name == "windows":
        return f"{PRODUCT_SLUG}-release.json"
    return f"{PRODUCT_SLUG}-macos-{arch}-release.json"


def _chmod_macos_launchers(bundle_dir: Path) -> None:
    for launcher_name in ("Open Desktop App.command", "Open in Browser.command"):
        launcher_path = bundle_dir / launcher_name
        if launcher_path.exists():
            launcher_path.chmod(0o755)


def _stage_windows_release(source_dir: Path, bundle_dir: Path) -> None:
    shutil.copytree(source_dir, bundle_dir)
    _clean_runtime_artifacts(bundle_dir)
    _prepare_layout(bundle_dir, platform_name="windows", seed_env=True)


def _stage_macos_release(source_dir: Path, bundle_dir: Path) -> None:
    app_target = bundle_dir / MACOS_APP_NAME
    bundle_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, app_target)
    _prepare_layout(bundle_dir, platform_name="macos", seed_env=False)
    _chmod_macos_launchers(bundle_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a clean release_dist bundle and ZIP archive.")
    parser.add_argument("source_dir", help="Path to the built app folder or .app bundle.")
    parser.add_argument(
        "--platform",
        default="windows",
        choices=("windows", "macos"),
        help="Target release platform.",
    )
    parser.add_argument(
        "--release-root",
        default="release_dist",
        help="Directory that will receive the copied app folder and ZIP archive.",
    )
    args = parser.parse_args()

    source_dir = Path(args.source_dir).resolve()
    if not source_dir.exists():
        raise FileNotFoundError(f"Source bundle not found: {source_dir}")

    arch = _normalized_arch(args.platform)
    release_root = (PROJECT_ROOT / args.release_root).resolve()
    bundle_name = _bundle_dir_name(args.platform, arch)
    archive_base_name = _archive_base_name(args.platform, arch)
    manifest_name = _manifest_name(args.platform, arch)

    bundle_dir = release_root / bundle_name
    archive_base = release_root / archive_base_name
    manifest_path = release_root / manifest_name

    release_root.mkdir(parents=True, exist_ok=True)
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)

    if args.platform == "windows":
        _stage_windows_release(source_dir, bundle_dir)
    else:
        _stage_macos_release(source_dir, bundle_dir)

    archive_path = shutil.make_archive(str(archive_base), "zip", root_dir=release_root, base_dir=bundle_dir.name)
    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "platform": args.platform,
        "architecture": arch,
        "bundle_dir": bundle_dir.name,
        "archive_name": Path(archive_path).name,
        "files": _collect_file_metadata(bundle_dir),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"Release bundle ready: {bundle_dir}")
    print(f"Release archive ready: {archive_path}")
    print(f"Release manifest ready: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
