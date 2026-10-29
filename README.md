# A1 Mail Dynamics

A1 Mail Dynamics is a local-first desktop outreach app for building CSV-based campaigns, generating personalized emails with AI, reviewing drafts, sending through SMTP or Gmail compose links, and monitoring replies from a packaged Windows or macOS desktop build.

## What’s Included

- React desktop UI hosted by a local Flask + Waitress server
- Native desktop wrapper with `pywebview`
- AI draft generation with Ollama, OpenAI, or Claude
- CSV import, draft preview/editing, export, attachments, and SMTP send
- Inbox monitoring, reply classification, and queued AI follow-ups
- Local user accounts with owner/admin/member access
- Offline machine-bound license activation with signed tokens
- PyInstaller desktop bundles for:
  - Windows: `dist\A1MailDynamics\A1MailDynamics.exe`
  - macOS: `dist/A1 Mail Dynamics.app`

## Run In Development

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app\main.py
```

Then open `http://127.0.0.1:5000`.

For the desktop shell during development:

```powershell
python -m app.desktop
```

That opens the native window and serves the app locally on port `5174` by default.

## Build The Desktop App

From the project root:

Windows:

```cmd
installer\build.bat
```

macOS:

```bash
python3 installer/build.py --platform macos
```

Output:

```text
dist\A1MailDynamics\A1MailDynamics.exe
dist/A1 Mail Dynamics.app
```

The build script:

1. Creates or reuses `.venv`
2. Installs Python runtime + build dependencies
3. Builds the React frontend from `client\`
4. Bundles the desktop app with PyInstaller for the current host platform
5. Smoke-tests the packaged app against a local health endpoint

## Distribution Bundle

The customer-ready folders are:

```text
release_dist\A1MailDynamics\
release_dist/A1MailDynamics-macos-arm64/
release_dist/A1MailDynamics-macos-x64/
```

Distribute the full folder, not only the executable or `.app`.

The build also creates:

```text
release_dist\A1MailDynamics-windows-x64.zip
release_dist\A1MailDynamics-release.json
release_dist/A1MailDynamics-macos-<arch>.zip
release_dist/A1MailDynamics-macos-<arch>-release.json
```

Recommended customer-facing files in that folder:

- Windows:
  - `A1MailDynamics.exe`
  - `Open Desktop App.bat`
  - `Open in Browser.bat`
- macOS:
  - `A1 Mail Dynamics.app`
  - `Open Desktop App.command`
  - `Open in Browser.command`
- `README.md`
- `INSTALLATION_GUIDE.md`
- `INSTALL_AND_ACTIVATE.md`
- `LICENSE_AND_RENEWAL.md`
- `BROWSER_MODE.md`
- `TROUBLESHOOTING.md`

Windows bundles also include `.env`, `.env.example`, `data\`, `logs\`, and `_internal\`.

Each build refreshes the app icon from `logo.png` (falling back to `assets\app logo.png`), rebuilds the web bundle, smoke-tests the packaged app, and then recreates the platform-specific `release_dist` bundle.

## Configure The App

Copy `.env.example` to `.env` and fill in the providers you want to use.

In packaged desktop builds:

- Windows seeds `.env` and `.env.example` inside the app folder beside the `.exe`
- macOS seeds runtime data under `~/Library/Application Support/A1MailDynamics/`

Common settings:

```env
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=you@example.com
SMTP_PASSWORD=your-app-password
SMTP_USE_TLS=true
```

Production hardening:

```env
APP_ENV=production
FLASK_SECRET_KEY=use-a-random-64-char-secret
ALLOW_SELF_SIGNUP=true
```

Set `ALLOW_SELF_SIGNUP=false` on shared installs if you want admins to create all additional local users from the Settings screen instead of allowing self-service signup at startup.

Customers should enter their own `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OLLAMA_*`, and SMTP credentials. The app does not require your API keys to operate on their machine.

Generate a strong secret with:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

## CSV Format

Only `email` is required. Recommended columns:

```csv
email,first_name,last_name,company,role,website,notes
jane@example.com,Jane,Doe,Acme,Marketing Lead,https://acme.com,Interested in lead gen
```

## Packaged Desktop Behavior

- Windows keeps `.env`, `data\`, and `logs\` next to the `.exe` for a portable folder-based release
- macOS stores writable runtime data in `~/Library/Application Support/A1MailDynamics/` so the `.app` bundle can stay clean and signable
- On first launch, the app seeds `.env.example` and the sample CSV into its writable runtime location
- Packaged builds auto-seed `APP_ENV=production` plus a strong persistent `FLASK_SECRET_KEY` if `.env` does not already provide one
- Browser mode can reconnect to the already-running local app automatically, even if the app had to fall back from port `5174` to another free local port
- Windows background startup can be controlled from `Settings -> Desktop`, and a second launch will reconnect to the running local instance instead of silently failing
- Runtime state is saved in `data/runtime/campaign_state.json`
- Logs are written to `logs/app.log`
- Attachments are stored in `data/attachments/`

## Offline Licensing Setup

The desktop app now supports local accounts and offline signed license activation.

Startup account flow:

- First launch shows both `Sign Up` and `Login`
- `Sign Up` collects `username`, `email`, `name/company name`, and `password`
- `Sign Up` creates the first owner account when the machine has no users yet
- After setup, `Sign Up` creates a local member account unless `ALLOW_SELF_SIGNUP=false`
- `Login` accepts either the local username or the saved email address
- Signed-in users without an active license are taken straight to the activation screen

1. Generate a vendor signing keypair:

```powershell
.\.venv\Scripts\python.exe tools\generate_license_keys.py --private-key private\vendor-license-private.pem
```

This updates [app/license_public_key.py](app/license_public_key.py) with the public key that will be bundled into the app. Keep the generated private key secret.

2. Get the customer machine ID from the app's activation screen.

If this is a fresh machine, the customer signs up first by creating the local owner account. If the app was already set up on that machine, they log in before opening the license activation screen.

3. Generate a signed license token for that machine:

```powershell
.\.venv\Scripts\python.exe tools\generate_license_token.py `
  --private-key private\vendor-license-private.pem `
  --customer-name "Customer Name" `
  --customer-email "customer@example.com" `
  --machine-id "MACHINE_ID_FROM_APP"
```

4. Send that token to the customer. They sign up or log in, then paste it into the app's activation screen.

If you want a non-machine-bound token for internal demos, pass `--machine-id "*"` instead.

Recommended commercial plans:

- `7-Day Trial`
- `30-Day Subscription`
- `1-Year Subscription`
- `Perpetual Lifetime`

Monthly and yearly renewals work by issuing a fresh key for the same `Machine ID`. The customer pastes the new key into the same license activation screen.

Seller-side helper files:

- [SELLER_LICENSE_GUIDE.md](SELLER_LICENSE_GUIDE.md)
- [SELLING_AND_DISTRIBUTION_GUIDE.md](SELLING_AND_DISTRIBUTION_GUIDE.md)
- [LICENSE_AND_RENEWAL.md](LICENSE_AND_RENEWAL.md)
- [tools/generate_license_keys.bat](tools/generate_license_keys.bat)
- [tools/generate_customer_license.bat](tools/generate_customer_license.bat)

## Commercial Release Checklist

This repo can now produce a cleaner production build, but software that is ready to sell still needs release work outside the codebase:

1. Code-sign `A1MailDynamics.exe` on Windows and sign/notarize `A1 Mail Dynamics.app` on macOS.
2. Replace test/demo credentials and verify `.env` is not shipped with secrets.
3. Decide your license, EULA, refund policy, and privacy policy.
4. Review third-party license obligations for bundled dependencies.
5. Test on a clean Windows machine and a clean Mac with and without Ollama installed.
6. Package an installer or signed DMG if you want non-technical customers to install it easily.

## Support Files

- Build guide: [installer/README.md](installer/README.md)
- Installation guide: [INSTALLATION_GUIDE.md](INSTALLATION_GUIDE.md)
- Release checklist: [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md)
- Desktop entrypoint: [app/desktop.py](app/desktop.py)
- Web server: [app/web.py](app/web.py)
# a1_seo_dynamics
