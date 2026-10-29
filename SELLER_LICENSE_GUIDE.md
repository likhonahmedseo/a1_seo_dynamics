# Seller License Guide

This app is designed so your customers use their own API keys and mail credentials.

- Customer pays for their own OpenAI, Anthropic, Ollama, SMTP, or IMAP usage
- You sell the desktop software license
- The customer `.exe` contains only the public verification key
- Your private signing key must stay with you and must never be shipped

## 1. Generate Vendor Keys

Run once:

```powershell
.\.venv\Scripts\python.exe tools\generate_license_keys.py --private-key private\vendor-license-private.pem
```

This creates:

- `private\vendor-license-private.pem`
- an updated `app\license_public_key.py`

Keep `private\vendor-license-private.pem` secret.

## 2. Build The Customer EXE

```powershell
installer\build.bat
```

For macOS, build on a Mac:

```bash
python3 installer/build.py --platform macos
```

Or manually:

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm installer\A1SEODynamics.spec
```

## 3. Get The Customer Machine ID

On first launch, the customer:

1. Opens `A1MailDynamics.exe`
2. Chooses **Sign Up** and enters `username`, `email`, `name/company name`, and `password` if this is the first run
3. Or chooses **Login** with username/email plus password if an account already exists on that machine
4. Reaches the license activation screen
5. Copies the machine ID shown there

## 4. Generate A Customer License (One-Click)

**Easy way (recommended):**

```powershell
tools\generate_customer_license.bat
```

This opens an interactive form where you enter:
1. **Customer/Company Name**
2. **Customer Email**
3. **License Type:**
   - **Option 1:** `7-Day Trial`
   - **Option 2:** `30-Day Subscription`
   - **Option 3:** `1-Year Subscription`
   - **Option 4:** `Perpetual Lifetime`

You will enter the **Machine ID** for the monthly, yearly, and perpetual plans.

The script will:
- Generate the activation key
- Copy it to your clipboard
- Save it to `private\licenses\`

Renewal rule:

- `30-Day Subscription`: issue a new 30-day key for the same `Machine ID`
- `1-Year Subscription`: issue a new 1-year key for the same `Machine ID`
- the customer pastes the new key into the same activation screen

**Manual way (advanced):**

```powershell
.\.venv\Scripts\python.exe tools\generate_license_token.py `
  --private-key private\vendor-license-private.pem `
  --customer-name "A1 Technovation" `
  --customer-email "a1technovation@gmail.com" `
  --machine-id "9DA4CDE34BD39D229DE5B29FEBCE57F1" `
  --license-type "30-Day Subscription" `
  --duration-days 30
```

**Send to customer:** Copy the activation key and send it to the customer. They sign up or log in, then paste it into the activation screen.

## 5. Recommended License Plans

- `7-Day Trial`: good for demos and evaluation
- `30-Day Subscription`: monthly renewable, machine-bound
- `1-Year Subscription`: yearly renewable, machine-bound
- `Perpetual Lifetime`: one-time sale, machine-bound

## 6. Important Rule

Do not bundle the private key into the customer `.exe`.

If the private key is shipped with the app, anyone can mint unlimited fake licenses and bypass your sales model.

For the full seller workflow, see [SELLING_AND_DISTRIBUTION_GUIDE.md](SELLING_AND_DISTRIBUTION_GUIDE.md).
