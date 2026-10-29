# Install And Activate

Use the release folder as-is.

For a full installation walkthrough, read `INSTALLATION_GUIDE.md` first.

## Windows Release

Keep these items in the same `A1MailDynamics` folder:

- `A1MailDynamics.exe`
- `_internal`
- `.env`
- `.env.example`
- `data`
- `logs`
- `Open Desktop App.bat`
- `Open in Browser.bat`
- `INSTALLATION_GUIDE.md`
- `LICENSE_AND_RENEWAL.md`

## macOS Release

Keep these items in the same release folder:

- `A1 Mail Dynamics.app`
- `Open Desktop App.command`
- `Open in Browser.command`
- `INSTALLATION_GUIDE.md`
- `README.md`
- `INSTALL_AND_ACTIVATE.md`
- `LICENSE_AND_RENEWAL.md`
- `TROUBLESHOOTING.md`

## First Run

1. Extract the full release folder to a normal location such as Desktop, Documents, or Applications.
2. Start the app with either:
   - Windows: `Open Desktop App.bat` or `Open in Browser.bat`
   - macOS: `Open Desktop App.command` or `Open in Browser.command`
3. If Windows SmartScreen appears, choose `More info` and then `Run anyway`.
4. If macOS Gatekeeper blocks the app, right-click the app, choose `Open`, and approve it once.
5. On first launch, choose `Sign Up`.
6. Enter:
   - `Username`
   - `Email`
   - `Name / Company Name`
   - `Password`

## License Activation

1. After sign-up, the app opens the license activation screen.
2. Copy the `Machine ID`.
3. Send that `Machine ID` to the seller.
4. Paste the activation key the seller sends back.
5. Click `Activate License`.

## Renewing A Monthly Or Yearly License

1. Open the app and go to the license screen.
2. Copy the current `Machine ID`.
3. Send it to the seller.
4. Paste the renewed key the seller sends back.
5. Click `Activate License` again.

The new key replaces the old key on the same machine.

## After Activation

1. Open `Settings`.
2. Enter your own AI provider settings.
3. Enter your own SMTP settings.
4. Test both connections before starting a campaign.

## Important

- Desktop mode and browser mode use the same local app data on each machine.
- On Windows, your settings, license state, and campaign data stay in the app folder.
- On macOS, they stay in `~/Library/Application Support/A1MailDynamics/`.
- Browser mode will try to reconnect to the already-running local app automatically, even if that app had to move off port `5174`.
- Do not delete the runtime data unless you want to reset the app.
- For more license details, read `LICENSE_AND_RENEWAL.md`.
