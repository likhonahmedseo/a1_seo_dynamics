"""
Build all customer-facing distribution packages for A1 Mail Dynamics.

Windows (must run on Windows):
  python tools/build_distributions.py --windows

macOS web-mode package (cross-platform, no .app required):
  python tools/build_distributions.py --macos-web

macOS build-kit package (cross-platform, produces a self-build zip a Mac user can run):
  python tools/build_distributions.py --macos-buildkit

All packages at once (on Windows host):
  python tools/build_distributions.py --all

Each package writes to  release_dist/<bundle-name>/  and zips it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import secrets
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRODUCT_SLUG = "A1MailDynamics"
APP_NAME     = "A1 Mail Dynamics"
RELEASE_ROOT = PROJECT_ROOT / "release_dist"

# ── Env helpers ──────────────────────────────────────────────────────────────

def _parse_env(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        out[k.strip()] = v.strip()
    return out


def _upsert(text: str, key: str, value: str) -> str:
    lines = text.splitlines()
    found = False
    new: list[str] = []
    for line in lines:
        s = line.strip()
        if s and not s.startswith("#") and s.split("=", 1)[0].strip() == key:
            new.append(f"{key}={value}")
            found = True
        else:
            new.append(line)
    if not found:
        if new and new[-1].strip():
            new.append("")
        new.append(f"{key}={value}")
    return "\n".join(new).rstrip() + "\n"


def _customer_env(*, with_secret: bool = False) -> str:  # noqa: ARG001 (with_secret retained for callers)
    source = PROJECT_ROOT / ".env.example"
    text = source.read_text(encoding="utf-8") if source.exists() else ""
    for blank in (
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
        "DEEPSEEK_API_KEY", "QWEN_API_KEY", "KIMI_API_KEY",
        "IMAP_USERNAME", "IMAP_PASSWORD",
    ):
        text = _upsert(text, blank, "")
    for ph_k, ph_v in (("SMTP_USERNAME", "you@example.com"), ("SMTP_PASSWORD", "your-app-password")):
        text = _upsert(text, ph_k, ph_v)
    text = _upsert(text, "APP_ENV", "production")
    text = _upsert(text, "ALLOW_SELF_SIGNUP", "true")
    # Never pre-bake the secret key — all customers would share the same value.
    # For frozen desktop builds, app/paths.py generates a unique key per machine
    # on first launch.  For source-based web builds, start_web_production.sh/.bat
    # generates the key on first run.
    text = _upsert(text, "FLASK_SECRET_KEY", "")
    return text


# ── File helpers ─────────────────────────────────────────────────────────────

def cp(src: Path, dst: Path) -> None:
    if not src.exists():
        print(f"  [skip] {src.name} not found")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"  + {dst.relative_to(PROJECT_ROOT)}")


def mkdirs(*paths: Path) -> None:
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)
        gitkeep = p / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()


def _sha256(path: Path) -> str:
    d = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            d.update(chunk)
    return d.hexdigest()


def _write_manifest(bundle_dir: Path, archive_path: Path, platform_name: str) -> Path:
    arch = _arch_slug()
    files = [
        {"path": p.relative_to(bundle_dir).as_posix(), "size": p.stat().st_size, "sha256": _sha256(p)}
        for p in sorted(p for p in bundle_dir.rglob("*") if p.is_file())
    ]
    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "platform": platform_name,
        "architecture": arch,
        "bundle_dir": bundle_dir.name,
        "archive_name": archive_path.name,
        "archive_size": archive_path.stat().st_size,
        "archive_sha256": _sha256(archive_path),
        "file_count": len(files),
        "files": files,
    }
    m_path = RELEASE_ROOT / f"{bundle_dir.name}-manifest.json"
    m_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return m_path


def _zip_bundle(bundle_dir: Path) -> Path:
    archive_base = RELEASE_ROOT / bundle_dir.name
    archive_path = Path(
        shutil.make_archive(str(archive_base), "zip", root_dir=RELEASE_ROOT, base_dir=bundle_dir.name)
    )
    return archive_path


def _arch_slug() -> str:
    m = platform.machine().strip().lower()
    if m in {"amd64", "x86_64"}:
        return "x64"
    if m in {"arm64", "aarch64"}:
        return "arm64"
    return m or "unknown"


# ── Common doc files ─────────────────────────────────────────────────────────

_DOC_NAMES = [
    "README.md",
    "INSTALLATION_GUIDE.md",
    "INSTALL_AND_ACTIVATE.md",
    "BROWSER_MODE.md",
    "TROUBLESHOOTING.md",
    "LICENSE_AND_RENEWAL.md",
]


def _copy_docs(bundle_dir: Path) -> None:
    for name in _DOC_NAMES:
        cp(PROJECT_ROOT / name, bundle_dir / name)


# ── Source-file include list (for web/buildkit packages) ─────────────────────

_SKIP_DIRS = {
    ".venv", "node_modules", "__pycache__", ".git",
    "dist", "release_dist",
    # Dev / IDE internals — never shipped to customers
    ".claude", ".vscode", ".idea", "private", "build",
}
_SKIP_NAMES_RE = re.compile(r"(\.pyc|\.pyo|\.DS_Store|Thumbs\.db|desktop\.ini)$")
# Exact filename matches to skip
_SKIP_EXACT_NAMES = {".env"}
# Seller-only or internal files never included in customer packages
_SKIP_FILES = {
    "SELLER_LICENSE_GUIDE.md",
    "SELLING_AND_DISTRIBUTION_GUIDE.md",
    "RELEASE_CHECKLIST.md",
    "check_syntax.py",
    "verify.py",
    "license_test_input.txt",
    "test_generate.py",
    "test_generate_template.py",
    "test_openai.py",
}
_SKIP_SUBTREES = {"data/runtime", "data/attachments", "logs"}


def _iter_source_files() -> list[Path]:
    result: list[Path] = []
    for abs_path in sorted(PROJECT_ROOT.rglob("*")):
        if not abs_path.is_file():
            continue
        rel = abs_path.relative_to(PROJECT_ROOT)
        parts = rel.parts
        # Skip if ANY path component matches a skip dir (catches client/node_modules, etc.)
        if any(part in _SKIP_DIRS for part in parts):
            continue
        if rel.name in _SKIP_FILES or rel.name in _SKIP_EXACT_NAMES:
            continue
        rel_posix = rel.as_posix()
        if any(rel_posix.startswith(t + "/") or rel_posix == t for t in _SKIP_SUBTREES):
            continue
        if _SKIP_NAMES_RE.search(rel.name):
            continue
        result.append(abs_path)
    return result


# ── Windows distribution ──────────────────────────────────────────────────────

def build_windows(*, rebuild_exe: bool = False) -> Path:
    print("\n=== Windows distribution ===")

    arch      = _arch_slug()
    bundle_name = PRODUCT_SLUG
    bundle_dir  = RELEASE_ROOT / bundle_name

    # Optionally re-run PyInstaller
    if rebuild_exe:
        _rebuild_exe_windows()

    exe_dir = PROJECT_ROOT / "dist" / PRODUCT_SLUG
    if not exe_dir.exists():
        raise FileNotFoundError(
            f"Windows build not found: {exe_dir}\n"
            "Run  installer\\build.bat  first to create the .exe bundle."
        )

    # Clean previous bundle
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True)

    # Copy entire PyInstaller output
    print(f"  Copying PyInstaller build from {exe_dir.name}/...")
    shutil.copytree(exe_dir, bundle_dir, dirs_exist_ok=True)

    # Remove macOS artefacts that sometimes sneak in
    for mac_file in bundle_dir.glob("*.command"):
        mac_file.unlink(missing_ok=True)
        print(f"  - removed {mac_file.name}")

    # Seed .env / .env.example
    (bundle_dir / ".env.example").write_text(_customer_env(with_secret=False), encoding="utf-8")
    (bundle_dir / ".env").write_text(_customer_env(with_secret=True), encoding="utf-8")
    print("  + .env  (fresh secret key)")
    print("  + .env.example")

    # Ensure runtime dirs exist with .gitkeep placeholders
    mkdirs(
        bundle_dir / "data" / "runtime",
        bundle_dir / "data" / "attachments",
        bundle_dir / "logs",
    )

    # Copy sample CSV
    cp(PROJECT_ROOT / "data" / "sample_contacts.csv", bundle_dir / "data" / "sample_contacts.csv")

    # Windows launchers
    for name in ("Open Desktop App.bat", "Open in Browser.bat"):
        cp(PROJECT_ROOT / name, bundle_dir / name)

    # Doc files
    _copy_docs(bundle_dir)

    # Remove runtime artefacts left from any previous run
    _clean_runtime(bundle_dir, platform_name="windows")

    # ZIP
    archive = _zip_bundle(bundle_dir)
    manifest = _write_manifest(bundle_dir, archive, "windows")

    _print_summary("windows", arch, bundle_dir, archive, manifest)
    return archive


def _rebuild_exe_windows() -> None:
    print("  Building .exe with PyInstaller...")
    venv_python = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    python_exe  = str(venv_python) if venv_python.exists() else sys.executable

    # Build frontend first
    client_dir = PROJECT_ROOT / "client"
    npm = "npm.cmd" if os.name == "nt" else "npm"
    lockfile = client_dir / "package-lock.json"
    subprocess.run([npm, "ci", "--silent"] if lockfile.exists() else [npm, "install", "--silent"],
                   cwd=client_dir, check=True)
    subprocess.run([npm, "run", "build"], cwd=client_dir, check=True)

    subprocess.run(
        [python_exe, "-m", "PyInstaller", "--clean", "--noconfirm", "installer/A1SEODynamics.spec"],
        cwd=PROJECT_ROOT, check=True,
    )


def _clean_runtime(bundle_dir: Path, platform_name: str) -> None:
    if platform_name == "windows":
        targets = [bundle_dir / "data" / "runtime", bundle_dir / "data" / "attachments", bundle_dir / "logs"]
    else:
        targets = []
    for folder in targets:
        if not folder.exists():
            continue
        for child in folder.iterdir():
            if child.name == ".gitkeep":
                continue
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)


# ── macOS Web-Mode distribution ───────────────────────────────────────────────

def build_macos_web() -> Path:
    """
    A source-based package for macOS users.
    No .app is required — the user double-clicks start_web_production.command
    (or start_web_dev.command) and the app runs in their browser.

    Requires on the customer's Mac: Python 3.11+ and Node.js 18+.
    """
    print("\n=== macOS Web-Mode distribution ===")

    arch        = _arch_slug()
    bundle_name = f"{PRODUCT_SLUG}-macos-web"
    bundle_dir  = RELEASE_ROOT / bundle_name

    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True)

    # Web-mode: skip top-level dirs not needed at runtime
    _WEB_SKIP_DIRS = {"installer", "vendor", "tools", "assets", "nginx"}
    # Skip these individual files (Docker, Windows-only launchers, large assets, dev files)
    _WEB_SKIP_NAMES = {
        "Dockerfile", "docker-compose.yml", ".dockerignore",
        "start_app.bat", "setup_macos_app.command",
        "logo.png",          # large binary not needed for web mode
    }

    # Core application source
    for abs_path in _iter_source_files():
        rel = abs_path.relative_to(PROJECT_ROOT)
        if rel.parts[0] in _WEB_SKIP_DIRS:
            continue
        if rel.suffix in {".bat", ".spec"}:
            continue
        if rel.suffix == ".command":
            continue  # add only the web-mode .command launchers explicitly below
        if rel.name in _WEB_SKIP_NAMES:
            continue
        dst = bundle_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(abs_path, dst)

    # Add the web-mode launchers
    for name in (
        "start_web_production.sh",
        "start_web_production.command",
        "start_web_dev.sh",
        "start_web_dev.command",
    ):
        cp(PROJECT_ROOT / name, bundle_dir / name)

    # Make shell scripts executable (preserves permissions in zip on macOS)
    for sh in bundle_dir.rglob("*.sh"):
        sh.chmod(0o755)
    for cmd in bundle_dir.rglob("*.command"):
        cmd.chmod(0o755)

    # Seed .env
    (bundle_dir / ".env.example").write_text(_customer_env(with_secret=False), encoding="utf-8")
    print("  + .env.example")

    # Ensure runtime dirs
    mkdirs(
        bundle_dir / "data" / "runtime",
        bundle_dir / "data" / "attachments",
        bundle_dir / "logs",
    )

    # Doc files
    _copy_docs(bundle_dir)

    # Write a quick-start README specific to this package
    (bundle_dir / "QUICK_START_WEB.md").write_text(_macos_web_quickstart(), encoding="utf-8")
    print("  + QUICK_START_WEB.md")

    archive  = _zip_bundle(bundle_dir)
    manifest = _write_manifest(bundle_dir, archive, "macos-web")

    _print_summary("macos-web", arch, bundle_dir, archive, manifest)
    return archive


def _macos_web_quickstart() -> str:
    return """\
# A1 Mail Dynamics — macOS Web Mode Quick Start

## Requirements

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.11+ | https://www.python.org/downloads/ or `brew install python` |
| Node.js | 18+ | https://nodejs.org/ or `brew install node` |

---

## Production mode (recommended)

Double-click **`start_web_production.command`** in Finder.

That script will:
1. Create a Python virtual environment and install dependencies
2. Build the React frontend
3. Start the Waitress production server on http://127.0.0.1:5000
4. Open your browser automatically

---

## Development mode (hot-reload)

Double-click **`start_web_dev.command`** in Finder.

- Flask backend runs on http://127.0.0.1:5000
- Vite dev server with hot-reload runs on http://localhost:5173
- Both servers stop when you press Ctrl+C

---

## First login

1. Open the app in your browser.
2. Click **Sign Up** and create your account.
3. Enter your license key when prompted.
4. Go to **Settings** and add your AI provider and SMTP details.

---

## Configuration (.env)

Copy `.env.example` to `.env` before the first run:

```bash
cp .env.example .env
```

Then edit `.env` to add your AI API keys and SMTP credentials.
The app also reads and writes these settings through the in-app **Settings** panel.

---

## Where your data lives

- Runtime state: `data/runtime/`
- Attachments: `data/attachments/`
- Logs: `logs/app.log`

---

## Want the native macOS desktop window?

Build the `.app` bundle from source by running:

```bash
bash setup_macos_app.command
```

This requires Python 3.11+, Node.js 18+, and creates
`dist/A1 Mail Dynamics.app` plus a ZIP in `release_dist/`.
"""


# ── macOS Build-Kit distribution ─────────────────────────────────────────────

def build_macos_buildkit() -> Path:
    """
    A complete source kit for developers who want to produce the native
    A1 Mail Dynamics.app bundle on a Mac.

    The customer double-clicks setup_macos_app.command (or runs
    python3 installer/build.py --platform macos) on their Mac to build
    the .app and create the final release_dist package.
    """
    print("\n=== macOS Build-Kit distribution ===")

    arch        = _arch_slug()
    bundle_name = f"{PRODUCT_SLUG}-macos-buildkit"
    bundle_dir  = RELEASE_ROOT / bundle_name

    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True)

    # Everything in the source tree (excluding heavy runtime dirs)
    for abs_path in _iter_source_files():
        rel = abs_path.relative_to(PROJECT_ROOT)
        dst = bundle_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(abs_path, dst)

    # Make all shell/command scripts executable
    for sh in bundle_dir.rglob("*.sh"):
        sh.chmod(0o755)
    for cmd in bundle_dir.rglob("*.command"):
        cmd.chmod(0o755)

    # Write the top-level README for this kit
    (bundle_dir / "BUILD_KIT_README.md").write_text(_macos_buildkit_readme(), encoding="utf-8")
    print("  + BUILD_KIT_README.md")

    archive  = _zip_bundle(bundle_dir)
    manifest = _write_manifest(bundle_dir, archive, "macos-buildkit")

    _print_summary("macos-buildkit", arch, bundle_dir, archive, manifest)
    return archive


def _macos_buildkit_readme() -> str:
    return """\
# A1 Mail Dynamics — macOS Build Kit

This package contains the full application source code and a one-click build script.
Run it on a Mac to produce the native `A1 Mail Dynamics.app` bundle.

## Requirements

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.11+ | https://www.python.org/downloads/ or `brew install python` |
| Node.js | 18+ | https://nodejs.org/ or `brew install node` |

## One-click build

Double-click **`setup_macos_app.command`** in Finder.

That script will:
1. Check Python and Node.js versions
2. Install all Python dependencies (into a local `.venv/`)
3. Build the React frontend
4. Bundle the app with PyInstaller
5. Run a smoke-test to verify the build
6. Package the result into `release_dist/A1MailDynamics-macos-<arch>/`
7. Create a distributable ZIP archive

Build time: approximately 2–4 minutes.

## Terminal build

```bash
python3 installer/build.py --platform macos
```

## Output

After a successful build:

```
dist/A1 Mail Dynamics.app                         # native .app bundle
release_dist/A1MailDynamics-macos-<arch>/         # clean customer folder
release_dist/A1MailDynamics-macos-<arch>.zip      # ready to send
```

## Running without building (.app not required)

If you just want to run the app in your browser without packaging it:

```bash
bash start_web_production.sh
```

or double-click **`start_web_production.command`**.

## Alternatively: macOS auto-start

After building, enable login auto-start:

```bash
bash installer/install_autostart_macos.sh
```

or double-click **`installer/enable_autostart_macos.command`**.
"""


# ── Summary printer ──────────────────────────────────────────────────────────

def _print_summary(platform_name: str, arch: str, bundle_dir: Path, archive: Path, manifest: Path) -> None:
    size_mb = archive.stat().st_size / 1_048_576
    print()
    print(f"  Bundle  : {bundle_dir.relative_to(PROJECT_ROOT)}/")
    print(f"  ZIP     : {archive.relative_to(PROJECT_ROOT)}  ({size_mb:.1f} MB)")
    print(f"  Manifest: {manifest.relative_to(PROJECT_ROOT)}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Build A1 Mail Dynamics distribution packages.")
    parser.add_argument("--windows",        action="store_true", help="Build the Windows release package.")
    parser.add_argument("--macos-web",      action="store_true", help="Build the macOS Web-Mode package.")
    parser.add_argument("--macos-buildkit", action="store_true", help="Build the macOS Build-Kit package.")
    parser.add_argument("--all",            action="store_true", help="Build all packages.")
    parser.add_argument("--rebuild-exe",    action="store_true",
                        help="Re-run PyInstaller before packaging (Windows only).")
    args = parser.parse_args()

    if not any([args.windows, args.macos_web, args.macos_buildkit, args.all]):
        parser.print_help()
        return 0

    RELEASE_ROOT.mkdir(parents=True, exist_ok=True)
    built: list[Path] = []

    if args.all or args.windows:
        built.append(build_windows(rebuild_exe=args.rebuild_exe))

    if args.all or args.macos_web:
        built.append(build_macos_web())

    if args.all or args.macos_buildkit:
        built.append(build_macos_buildkit())

    print()
    print("=" * 60)
    print("  BUILD SUCCESSFUL")
    print("=" * 60)
    for p in built:
        print(f"  {p.relative_to(PROJECT_ROOT)}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
