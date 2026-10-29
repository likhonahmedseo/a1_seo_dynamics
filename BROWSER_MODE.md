# Browser Mode

Browser mode opens the same local app in your default web browser instead of the native desktop window.

## How To Start It

**Windows** — double-click:

- `Open in Browser.bat`

**macOS** — double-click:

- `Open in Browser.command`

That will:

1. Reuse the local app if it is already running
2. Or start the local app server in the background
3. Open the detected local app address in your browser

## What Browser Mode Uses

Browser mode still runs locally on your own computer.

- It is not a public website
- It is not shared over the internet
- It uses the same local app data as desktop mode

## If The Page Does Not Open

1. Wait 5 to 10 seconds.
2. Refresh the browser.
3. Re-run the launcher so it can detect the current local app address again.

## If The Port Is Busy

If port `5174` is busy, the app can fall back to another free local port.

The browser launchers detect the active local app port automatically before opening the browser.

## If You Prefer The Desktop Window

**Windows** — double-click `Open Desktop App.bat`

**macOS** — double-click `Open Desktop App.command`
