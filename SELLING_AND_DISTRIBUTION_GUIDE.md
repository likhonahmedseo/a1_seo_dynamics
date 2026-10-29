# Selling And Distribution Guide

This guide is the full seller workflow for A1 Mail Dynamics across both Windows and macOS.

## What You Are Selling

You are selling the desktop software license.

Your customers provide their own:

- OpenAI, Anthropic, or Ollama usage
- SMTP or IMAP credentials
- email sending infrastructure

You should never ship your private signing key or your personal API keys inside the customer release.

## Supported Customer Platforms

- Windows customers receive the Windows release folder or ZIP
- macOS customers receive the macOS release folder or ZIP built on a Mac

## Release Artifacts

Windows release output:

- `release_dist\A1MailDynamics\`
- `release_dist\A1MailDynamics-windows-x64.zip`

macOS release output:

- `release_dist/A1MailDynamics-macos-<arch>/`
- `release_dist/A1MailDynamics-macos-<arch>.zip`

## Build The Sellable App

Windows:

```powershell
installer\build.bat
```

macOS:

```bash
python3 installer/build.py --platform macos
```

Important:

- the Windows build must be produced on Windows
- the macOS build must be produced on a Mac
- if you want broad Mac distribution, you should sign and notarize the `.app`

## Generate Your Vendor Keys

Run once:

```powershell
.\.venv\Scripts\python.exe tools\generate_license_keys.py --private-key private\vendor-license-private.pem
```

This creates:

- `private\vendor-license-private.pem`
- an updated `app\license_public_key.py`

Rules:

- keep `private\vendor-license-private.pem` secret
- do not ship the private key to customers
- the customer build should contain only the public verification key

## License Plans You Can Sell

- `7-Day Trial`
  - best for demos and evaluation
  - not tied to one machine in the quick generator flow
  - expires automatically after 7 days
- `30-Day Subscription`
  - tied to one machine
  - expires after 30 days
  - renew by reissuing a new key for the same `Machine ID`
- `1-Year Subscription`
  - tied to one machine
  - expires after 1 year
  - renew by reissuing a new key for the same `Machine ID`
- `Perpetual Lifetime`
  - tied to one machine
  - no expiry

## Customer Activation Flow

On first use, the customer:

1. opens the app
2. signs up or logs in
3. reaches the `License Activation` screen
4. copies the `Machine ID`
5. sends the `Machine ID` to you if the plan is machine-bound

You then:

1. generate the license key
2. send the activation key to the customer
3. the customer pastes the key into the app

## One-Click License Generation

Use:

```powershell
tools\generate_customer_license.bat
```

The generator now supports:

- `7-Day Trial`
- `30-Day Subscription`
- `1-Year Subscription`
- `Perpetual Lifetime`

The script will:

- ask for customer name and email
- ask for the plan
- ask for the `Machine ID` when needed
- generate the signed key
- copy it to the clipboard
- save a copy under `private\licenses\`

## Manual License Generation

Examples:

7-day trial:

```powershell
.\.venv\Scripts\python.exe tools\generate_license_token.py `
  --private-key private\vendor-license-private.pem `
  --customer-name "Customer Name" `
  --customer-email "customer@example.com" `
  --machine-id "*" `
  --license-type "7-Day Trial" `
  --duration-days 7
```

30-day subscription:

```powershell
.\.venv\Scripts\python.exe tools\generate_license_token.py `
  --private-key private\vendor-license-private.pem `
  --customer-name "Customer Name" `
  --customer-email "customer@example.com" `
  --machine-id "CUSTOMER_MACHINE_ID" `
  --license-type "30-Day Subscription" `
  --duration-days 30
```

1-year subscription:

```powershell
.\.venv\Scripts\python.exe tools\generate_license_token.py `
  --private-key private\vendor-license-private.pem `
  --customer-name "Customer Name" `
  --customer-email "customer@example.com" `
  --machine-id "CUSTOMER_MACHINE_ID" `
  --license-type "1-Year Subscription" `
  --duration-days 365
```

Perpetual lifetime:

```powershell
.\.venv\Scripts\python.exe tools\generate_license_token.py `
  --private-key private\vendor-license-private.pem `
  --customer-name "Customer Name" `
  --customer-email "customer@example.com" `
  --machine-id "CUSTOMER_MACHINE_ID" `
  --license-type "Perpetual Lifetime"
```

## Renewal Workflow

For a monthly or yearly customer:

1. ask the customer to copy their current `Machine ID`
2. confirm it matches the original machine, or use the new machine ID if they changed devices
3. generate a fresh license for that machine
4. send the new key
5. the customer pastes it into the same license activation screen

The renewal process is the same for:

- `30-Day Subscription`
- `1-Year Subscription`

## What To Send To Customers

Windows customers:

- `release_dist\A1MailDynamics\` or `release_dist\A1MailDynamics-windows-x64.zip`

macOS customers:

- `release_dist/A1MailDynamics-macos-<arch>/` or its ZIP

Also send:

- the activation key
- `INSTALLATION_GUIDE.md`
- any support email or onboarding note you want included

## Recommended Commercial Process

Before selling:

1. build fresh release artifacts
2. test on a clean Windows machine
3. test on a clean Mac
4. confirm no personal API keys or test data are in the package
5. sign the Windows executable if possible
6. sign and notarize the macOS app if possible
7. prepare refund, support, and update policies

## Related Docs

- [README.md](README.md)
- [INSTALLATION_GUIDE.md](INSTALLATION_GUIDE.md)
- [INSTALL_AND_ACTIVATE.md](INSTALL_AND_ACTIVATE.md)
- [LICENSE_AND_RENEWAL.md](LICENSE_AND_RENEWAL.md)
- [SELLER_LICENSE_GUIDE.md](SELLER_LICENSE_GUIDE.md)
- [tools/LICENSE_GENERATOR_README.md](tools/LICENSE_GENERATOR_README.md)
