from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VENV_DIR = PROJECT_ROOT / ".venv"
WINDOWS_EXE_PATH = PROJECT_ROOT / "dist" / "A1MailDynamics" / "A1MailDynamics.exe"
MACOS_APP_PATH = PROJECT_ROOT / "dist" / "A1 Mail Dynamics.app"


def _host_platform() -> str:
    if sys.platform == "darwin":
        return "macos"
    if os.name == "nt":
        return "windows"
    raise RuntimeError(f"Unsupported build host: {sys.platform}")


def _arch_slug() -> str:
    machine = platform.machine().strip().lower()
    if machine in {"amd64", "x86_64"}:
        return "x64"
    if machine in {"arm64", "aarch64"}:
        return "arm64"
    return machine or "unknown"


def _venv_python_path(platform_name: str) -> Path:
    if platform_name == "windows":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python3"


def _venv_python_fallback(platform_name: str) -> Path:
    if platform_name == "windows":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def _ensure_venv(platform_name: str) -> Path:
    python_path = _venv_python_path(platform_name)
    if python_path.exists():
        return python_path

    print("=== [1/8] Creating local virtual environment ===")
    subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], cwd=PROJECT_ROOT, check=True)
    if python_path.exists():
        return python_path

    fallback = _venv_python_fallback(platform_name)
    if fallback.exists():
        return fallback
    raise FileNotFoundError(f"Virtual environment Python not found: {python_path}")


def _run(command: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd or PROJECT_ROOT, check=True)


def _npm_command() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def _wait_for_health(url: str, timeout_s: float = 30.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=1.5) as response:
                if response.status < 500:
                    return True
        except (URLError, OSError):
            pass
        time.sleep(0.5)
    return False


def _smoke_test_executable(executable_path: Path) -> None:
    port = "5199"
    process = subprocess.Popen(
        [str(executable_path), "--no-window", "--port", port],
        cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        if not _wait_for_health(f"http://127.0.0.1:{port}/api/health"):
            raise RuntimeError("The packaged app did not become healthy in time.")
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _dist_source_dir(platform_name: str) -> Path:
    if platform_name == "windows":
        return WINDOWS_EXE_PATH.parent
    return MACOS_APP_PATH


def _smoke_test_target(platform_name: str) -> Path:
    if platform_name == "windows":
        return WINDOWS_EXE_PATH
    return MACOS_APP_PATH / "Contents" / "MacOS" / "A1MailDynamics"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the A1 Mail Dynamics desktop app.")
    parser.add_argument(
        "--platform",
        default=None,
        choices=("windows", "macos"),
        help="Target desktop platform. Defaults to the current host OS.",
    )
    args = parser.parse_args()

    host = _host_platform()
    target_platform = args.platform or host
    if target_platform != host:
        raise RuntimeError(
            f"{target_platform} builds must run on a {target_platform} machine. Current host: {host}."
        )

    print(f"=== [0/8] Target platform: {target_platform} ({_arch_slug()}) ===")
    print(f"Python: {sys.version.split()[0]}")

    python_exe = _ensure_venv(target_platform)

    print("=== [2/8] Installing build dependencies ===")
    _run([str(python_exe), "-m", "pip", "install", "--upgrade", "pip"])
    _run([str(python_exe), "-m", "pip", "install", "-r", "requirements.txt"])
    _run([str(python_exe), "-m", "pip", "install", "-r", "requirements-build.txt"])

    print("=== [3/8] Generating app icons ===")
    _run([str(python_exe), "tools/generate_app_icons.py"])

    print("=== [4/8] Building frontend (npm run build) ===")
    client_dir = PROJECT_ROOT / "client"
    npm = _npm_command()
    lockfile = client_dir / "package-lock.json"
    _run([npm, "ci", "--silent"] if lockfile.exists() else [npm, "install", "--silent"], cwd=client_dir)
    _run([npm, "run", "build"], cwd=client_dir)

    print("=== [5/8] Bundling desktop app with PyInstaller ===")
    _run([str(python_exe), "-m", "PyInstaller", "--clean", "--noconfirm", "installer/A1SEODynamics.spec"])

    print("=== [6/8] Smoke-testing packaged app ===")
    smoke_target = _smoke_test_target(target_platform)
    if not smoke_target.exists():
        raise FileNotFoundError(f"Packaged executable not found: {smoke_target}")
    _smoke_test_executable(smoke_target)

    dist_source = _dist_source_dir(target_platform)
    if target_platform == "windows":
        print("=== [7/8] Cleaning Windows bundle for customer distribution ===")
        _run([str(python_exe), "tools/prepare_release_bundle.py", str(dist_source), "--platform", "windows", "--clean-runtime"])
    else:
        print("=== [7/8] Preparing macOS release bundle ===")

    print("=== [8/8] Creating release_dist bundle and ZIP archive ===")
    _run([str(python_exe), "tools/create_release_package.py", str(dist_source), "--platform", target_platform])

    print("")
    print("BUILD SUCCESSFUL")
    if target_platform == "windows":
        print(f"Output:  {WINDOWS_EXE_PATH.relative_to(PROJECT_ROOT)}")
        print("Release: release_dist/A1MailDynamics")
        print("ZIP:     release_dist/A1MailDynamics-windows-x64.zip")
    else:
        mac_release = f"release_dist/A1MailDynamics-macos-{_arch_slug()}"
        print(f"Output:  {MACOS_APP_PATH.relative_to(PROJECT_ROOT)}")
        print(f"Release: {mac_release}")
        print(f"ZIP:     {mac_release}.zip")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
