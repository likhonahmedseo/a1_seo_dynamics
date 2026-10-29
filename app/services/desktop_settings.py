from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.paths import APP_ROOT

_SHORTCUT_NAME = "A1 Mail Dynamics.lnk"


def _ps_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _startup_shortcut_path() -> Path:
    startup_dir = Path(os.getenv("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return startup_dir / _SHORTCUT_NAME


def _launch_target_and_args() -> tuple[str, str, str]:
    if getattr(sys, "frozen", False):
        exe_path = str(Path(sys.executable).resolve())
        working_dir = str(Path(sys.executable).resolve().parent)
        return exe_path, "--background", working_dir

    python_exe = str(Path(sys.executable).resolve())
    working_dir = str(APP_ROOT)
    return python_exe, "-m app.desktop --background", working_dir


def _run_powershell(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )


def _set_windows_background_launch(enabled: bool) -> None:
    shortcut_path = _startup_shortcut_path()
    if enabled:
        target_path, arguments, working_dir = _launch_target_and_args()
        script = "\n".join(
            [
                "$ErrorActionPreference = 'Stop'",
                f"$shortcutPath = {_ps_literal(str(shortcut_path))}",
                "$shortcutDir = Split-Path -Parent $shortcutPath",
                "New-Item -ItemType Directory -Force -Path $shortcutDir | Out-Null",
                "$shell = New-Object -ComObject WScript.Shell",
                "$shortcut = $shell.CreateShortcut($shortcutPath)",
                f"$shortcut.TargetPath = {_ps_literal(target_path)}",
                f"$shortcut.WorkingDirectory = {_ps_literal(working_dir)}",
                "$shortcut.Description = 'A1 Mail Dynamics - background startup'",
                f"$shortcut.Arguments = {_ps_literal(arguments)}",
                "$shortcut.WindowStyle = 7",
                "$shortcut.Save()",
            ]
        )
    else:
        script = "\n".join(
            [
                "$ErrorActionPreference = 'Stop'",
                f"$shortcutPath = {_ps_literal(str(shortcut_path))}",
                "if (Test-Path $shortcutPath) { Remove-Item -LiteralPath $shortcutPath -Force }",
            ]
        )

    result = _run_powershell(script)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "Unknown PowerShell error.").strip()
        raise RuntimeError(message)


def desktop_settings_payload() -> dict[str, Any]:
    supported = os.name == "nt"
    shortcut_path = _startup_shortcut_path() if supported else None
    target_path, arguments, _working_dir = _launch_target_and_args()
    return {
        "supported": supported,
        "platform": sys.platform,
        "background_launch_enabled": bool(shortcut_path and shortcut_path.exists()),
        "launch_target": target_path,
        "launch_arguments": arguments,
        "shortcut_path": str(shortcut_path) if shortcut_path else "",
    }


def update_background_launch(enabled: bool) -> dict[str, Any]:
    if os.name != "nt":
        raise RuntimeError("Background startup is currently supported only on Windows.")
    _set_windows_background_launch(enabled)
    payload = desktop_settings_payload()
    payload["message"] = (
        "Background startup enabled. A1 Mail Dynamics will run when you sign in."
        if enabled
        else "Background startup disabled."
    )
    return payload
