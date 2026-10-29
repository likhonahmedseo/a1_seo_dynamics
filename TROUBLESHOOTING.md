# Troubleshooting

## The App Does Not Start

Windows: check that these are all still in the same folder:

- `A1MailDynamics.exe`
- `_internal`
- `.env`
- `data`
- `logs`

If `_internal` is missing, the app will not run.

macOS: check that `A1 Mail Dynamics.app` is still in the same release folder as the `.command` launchers.

## Windows Shows A Warning

If Windows SmartScreen appears:

1. Click `More info`
2. Click `Run anyway`

This can happen with unsigned apps.

## macOS Shows A Security Warning

If macOS blocks the app:

1. Right-click `A1 Mail Dynamics.app`
2. Click `Open`
3. Confirm the prompt

For broad distribution, sign and notarize the app.

## Browser Mode Opens But Page Is Blank

1. Wait a few seconds.
2. Refresh the page.
3. If needed, close the app and start `Open in Browser.bat` again.
4. If browser mode still fails, start `Open Desktop App.bat` first and then retry browser mode.

## The App Says Another Instance Is Running

If Windows background startup is enabled, this usually means the app is already running correctly.

If needed:

1. Wait a few seconds for the local server to finish starting
2. Run `Open in Browser.bat` to reconnect to the running instance
3. If you want normal launch behavior again, turn off `Settings -> Desktop -> Run in background at sign-in`
4. Then close the app and start it again

## License Activation Fails

Check that:

- You copied the full activation key
- The key matches this machine's `Machine ID`
- The seller generated the key for the correct machine

If the key is still rejected, ask the seller to regenerate it.

## My Monthly Or Yearly License Expired

1. Open the license screen in the app.
2. Copy the current `Machine ID`.
3. Ask the seller for a renewed key for that machine.
4. Paste the new key into the activation screen.

You do not need to reinstall the app to renew.

## SMTP Or AI Features Do Not Work

Open `Settings` and verify:

- AI provider details
- API keys or Ollama URL
- SMTP host, port, username, and password

Run the built-in connection tests before sending campaigns.

## Where Your Local Data Lives

- Windows settings, license state, and app state: `data\runtime`
- Windows logs: `logs`
- Windows attachments: `data\attachments`
- macOS runtime data: `~/Library/Application Support/A1MailDynamics/`

## Full Reset

Only do this if you want to clear local app state.

Delete:

- `data\runtime\system_state.json`

You may also clear other files in `data\runtime` if directed by support.
