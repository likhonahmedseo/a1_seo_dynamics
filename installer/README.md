# Desktop Builds

This directory contains the desktop build pipeline for Windows and macOS.

## What you get

- **Windows:** `release_dist\A1MailDynamics\A1MailDynamics.exe`
- **macOS:** `release_dist/A1MailDynamics-macos-<arch>/A1 Mail Dynamics.app`
- A native desktop window (powered by Edge WebView2 on Windows and Cocoa/WebKit on macOS)
- Background Flask + Waitress server on a local port (prefers `http://127.0.0.1:5174`) — also reachable from any browser
- Windows background-start support via a Startup-folder shortcut (no admin required)

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.11+ | Add to PATH during install |
| Node.js | 18+ | Used to build the React frontend |
| Edge WebView2 Runtime | any | Windows only; pre-installed on Windows 10/11 |

The build now generates both the Windows `.ico` and macOS `.icns` app icons automatically from `logo.png` (or `assets\app logo.png` if the root logo is absent).

## 1 · Build the desktop app

From the project root:

```cmd
installer\build.bat
```

Or on macOS:

```bash
python3 installer/build.py --platform macos
```

This will:

1. Install Python deps (`requirements.txt` + `requirements-build.txt`)
2. Install Node deps (`npm install`)
3. Build the React frontend (`npm run build` → `client/dist/`)
4. Bundle everything with PyInstaller
5. Smoke-test the packaged desktop app
6. Create the platform-specific `release_dist/` bundle and ZIP archive

Build time: ~2–4 minutes on a typical machine.

> **Tip:** Windows releases are portable folder-based builds. macOS releases keep the `.app` bundle portable, but write runtime data under `~/Library/Application Support/A1MailDynamics/`.

## 2 · First launch

Windows: double-click `A1MailDynamics.exe` or `Open Desktop App.bat`.

macOS: open `A1 Mail Dynamics.app` or `Open Desktop App.command`.

If `.env` doesn't exist yet, the app seeds `.env.example` into its writable
runtime location on first launch so you can copy it and fill in your
credentials. You can edit the AI provider, follow-ups, accounts, license, and
other settings later through the in-app **⚙️ Settings** panel.

## 3 · Auto-start with Windows

To make the app launch in the background every time you sign in:

```cmd
installer\enable_autostart.bat
```

Or directly with PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File installer\install_autostart.ps1
```

Or, if you put the .exe somewhere other than `dist\`:

```powershell
powershell -ExecutionPolicy Bypass -File installer\install_autostart.ps1 -ExePath "C:\Apps\A1MailDynamics.exe"
```

Pass `-NoMinimize` to launch with a normal window instead of background mode:

```powershell
powershell -ExecutionPolicy Bypass -File installer\install_autostart.ps1 -NoMinimize
```

### How it works

The script creates `A1 Mail Dynamics.lnk` in your user Startup folder
(`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`). Windows runs every
shortcut in this folder when you log in. **No registry changes, no scheduled
tasks, no admin rights** — nothing more invasive than a regular shortcut.

### Disable auto-start

```cmd
installer\disable_autostart.bat
```

Or directly with PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File installer\uninstall_autostart.ps1
```

## One-click setup

If you want the easiest Windows flow, run:

```cmd
installer\setup_windows_app.bat
```

That script builds `release_dist\A1MailDynamics\A1MailDynamics.exe` and then asks whether it should
enable auto-start for your Windows sign-in.

## Command-line flags (advanced)

```text
A1MailDynamics [--minimized] [--background] [--port N] [--no-window]
```

| Flag | Effect |
|------|--------|
| `--minimized` | Window starts minimized |
| `--background` | Starts the local server without opening the desktop window |
| `--port 5174` | Use a specific local port (default 5174; falls back to a random free port) |
| `--no-window` | Run headless. Browser mode will open the detected local app URL |

## Troubleshooting

**"Windows protected your PC" / SmartScreen warning**
The `.exe` isn't code-signed. Click **More info → Run anyway**. Sign with an EV
cert if you're distributing to other machines.

**macOS says the app cannot be opened**
The `.app` is not signed or notarized yet. Right-click the app, choose `Open`,
and approve it once. For broad distribution, sign and notarize it.

**Antivirus flags the .exe**
PyInstaller bundles trip some heuristic AV. The build disables UPX
specifically to reduce false positives. Submit the .exe to your AV vendor for
whitelisting if needed.

**"Could not connect to Ollama"**
Ollama runs as a separate service. Make sure `ollama serve` is running.
You can also switch to OpenAI in the app's ⚙️ AI Settings panel.

**Where are my logs / state?**
Next to the .exe — `logs/app.log`, `data/runtime/campaign_state.json`,
`data/attachments/`. Delete `data/` to wipe the campaign and start fresh.

**The window is blank / shows a connection error**
The local server takes a moment to start. If it never appears, check
`logs/app.log` for the cause. As a workaround, run with `--no-window` and
use `Open in Browser.bat`, which will try to detect the current local app URL automatically.

**The .exe looks like it did nothing**
If background startup is enabled, launching the app again reconnects to the
running local instance. Give it a few extra seconds on first launch, then try
`Open in Browser.bat` if you want to verify the local server directly.
