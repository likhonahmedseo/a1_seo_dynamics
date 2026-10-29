# Installation Guide

This guide explains how to install and start A1 Mail Dynamics on Windows and macOS.

## Before You Start

Make sure you received the full release folder or ZIP file from the seller.

You should not run only one file by itself.

## Windows Installation

### What You Should Receive

The Windows package should include:

- `A1MailDynamics.exe`
- `_internal`
- `.env`
- `.env.example`
- `data`
- `logs`
- `Open Desktop App.bat`
- `Open in Browser.bat`
- `INSTALL_AND_ACTIVATE.md`
- `LICENSE_AND_RENEWAL.md`
- `TROUBLESHOOTING.md`

### Install Steps

1. Extract the ZIP file if the seller sent a ZIP.
2. Move the full `A1MailDynamics` folder to a normal location such as:
   - `Desktop`
   - `Documents`
   - `C:\Apps\A1MailDynamics`
3. Do not place the app inside a temporary ZIP preview window.
4. Keep all files together in the same folder.

### First Launch

Start the app with either:

- `Open Desktop App.bat` for the native desktop app
- `Open in Browser.bat` for browser mode

Inside the app, you can later open `Settings -> Desktop` to turn Windows background startup on or off.

If Windows SmartScreen appears:

1. Click `More info`
2. Click `Run anyway`

## macOS Installation

### What You Should Receive

The macOS package should include:

- `A1 Mail Dynamics.app`
- `Open Desktop App.command`
- `Open in Browser.command`
- `INSTALL_AND_ACTIVATE.md`
- `LICENSE_AND_RENEWAL.md`
- `TROUBLESHOOTING.md`

### Install Steps

1. Extract the ZIP file if the seller sent a ZIP.
2. Move the full release folder to a normal location such as:
   - `Applications`
   - `Desktop`
   - `Documents`
3. Keep `A1 Mail Dynamics.app` beside the `.command` launchers.

### First Launch

Start the app with either:

- `Open Desktop App.command` for the native desktop app
- `Open in Browser.command` for browser mode

If you want to launch from Terminal, use:

```bash
./Open\ Desktop\ App.command
./Open\ in\ Browser.command
```

If macOS blocks the app:

1. Right-click `A1 Mail Dynamics.app`
2. Click `Open`
3. Confirm the warning once

For wide distribution, the seller should sign and notarize the app.

## After Installation

After the app opens:

1. Create your account with `Sign Up`, or log in if an account already exists.
2. Open the license screen.
3. Copy the `Machine ID`.
4. Send the `Machine ID` to the seller if your plan is machine-bound.
5. Paste the activation key the seller sends back.
6. Open `Settings` and enter your own AI and SMTP details.

## Where Your Data Lives

Windows:

- app folder stores `.env`, `data`, and `logs`

macOS:

- runtime data lives in `~/Library/Application Support/A1MailDynamics/`

## Important Rules

- Do not delete the `data` or runtime files unless you want to reset the app.
- Keep the release files together.
- Monthly and yearly licenses are renewed by pasting a new key for the same `Machine ID`.
- Your AI keys and SMTP credentials are separate from the desktop software license.
- If Windows background startup is enabled, opening the `.exe` again reconnects to the running local app instead of starting a second copy.

## Related Files

- `INSTALL_AND_ACTIVATE.md`
- `LICENSE_AND_RENEWAL.md`
- `TROUBLESHOOTING.md`
