# Customer License Generator - Quick Start Guide

## 🚀 One-Click License Generation

Generate customer activation keys in seconds.

### How to Use

#### Windows
1. **Double-click** `generate_customer_license.bat`

#### macOS
1. Open Terminal in the `tools/` folder and run:
   ```bash
   chmod +x generate_customer_license.sh
   ./generate_customer_license.sh
   ```

#### Both platforms — enter customer details:
1. **Enter customer details:**
   - Customer/Company Name
   - Customer Email
   - Choose license type (1 to 4)

### License Types

#### Option 1: 7-Day Trial
- **Best for:** Testing, demos, internal use
- **Works on:** Any machine/device
- **Duration:** 7 days (auto-expires)
- **How to use:** Customer just pastes the key, no Machine ID needed

#### Option 2: 30-Day Subscription
- **Best for:** Monthly customers
- **Works on:** Only ONE specific machine/device
- **Duration:** 30 days
- **Renewal:** Generate a new 30-day key for the same Machine ID

#### Option 3: 1-Year Subscription
- **Best for:** Annual customers
- **Works on:** Only ONE specific machine/device
- **Duration:** 365 days
- **Renewal:** Generate a new 1-year key for the same Machine ID

#### Option 4: Perpetual Lifetime
- **Best for:** One-time lifetime sales
- **Works on:** Only ONE specific machine/device
- **Duration:** No expiry
- **How to get Machine ID:** Customer runs the app, signs up or logs in, goes to "License Activation" screen, copies their Machine ID
- **Example:** Customer gives you Machine ID `9DA4CDE34BD39D229DE5B29FEBCE57F1`

### Output

The script will:
1. ✓ Generate a unique activation key
2. ✓ Copy it to your clipboard automatically
3. ✓ Save it to `private\licenses\CustomerName_License.txt`
4. ✓ Display instructions for sending to customer

### Send to Customer

Once generated:
1. Send the activation key to your customer via email
2. Customer runs the packaged Windows or macOS app
3. Customer chooses **Sign Up** and enters `username`, `email`, `name/company name`, and `password` if it is the first time on that machine, or **Login** with username/email plus password if an account already exists
4. On the "License Activation" screen, they paste the key
5. License activates immediately
6. App is ready to use!

### Security

- ✓ Each license is unique and cryptographically signed
- ✓ Machine-bound licenses can't be shared across devices
- ✓ Trial, monthly, and yearly licenses expire automatically
- ✓ Private signing key is never shared with customer

### Troubleshooting

**"Private key not found"**
- Windows: `.\.venv\Scripts\python.exe tools\generate_license_keys.py --private-key private\vendor-license-private.pem`
- macOS: `.venv/bin/python3 tools/generate_license_keys.py --private-key private/vendor-license-private.pem`

**Invalid Machine ID**
- Machine IDs are 32 characters (hex)
- Ask customer to copy exactly from the app's License Activation screen

**Expired monthly or yearly license**
- Generate a fresh key for the same Machine ID
- Customer pastes the new key into the same license screen

**Trial license not working**
- Trial licenses expire after 7 days
- For extension, generate a new trial or move the customer to a paid plan

---

**For advanced usage**, see [SELLER_LICENSE_GUIDE.md](..\SELLER_LICENSE_GUIDE.md) and [SELLING_AND_DISTRIBUTION_GUIDE.md](..\SELLING_AND_DISTRIBUTION_GUIDE.md)
