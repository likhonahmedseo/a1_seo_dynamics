# A1 Mail Dynamics Release Checklist

Use this before shipping the Windows or macOS release bundle to customers.

## Product

1. Confirm branding, company name, support email, and website are correct in the UI.
2. Confirm default sender fields are blank on a fresh install.
3. Verify the sample CSV and onboarding text match the actual product workflow.
4. Verify owner setup, login, and license activation screens work on first launch.

## Security

1. Build with `APP_ENV=production` if you are testing from source.
2. For the packaged build, confirm first launch created a `.env` with a strong `FLASK_SECRET_KEY`.
3. Remove any real API keys, SMTP passwords, or mailbox credentials from the shipped folder.
4. Review runtime data for test data before distribution.
5. Keep `private\vendor-license-private.pem` out of the distributed package and out of source control.

## Functional QA

1. Launch the app from the platform release bundle.
2. Create the first owner account on a clean machine.
3. Activate the app with a valid signed license token.
4. Generate template drafts from a sample CSV.
5. Generate AI drafts with the configured provider.
6. Save and re-open the app to confirm state persistence works.
7. Test SMTP save, SMTP connection test, and a real send.
8. Test attachment upload and removal.
9. Test inbox monitor start/stop and conversation refresh.

## Packaging

1. Rebuild with `installer\build.bat` on Windows or `python3 installer/build.py --platform macos` on a Mac, and make sure the final smoke test passes.
2. Confirm the matching `release_dist` folder is the folder you plan to distribute.
3. Confirm the matching ZIP archive opens correctly and matches the folder contents.
4. Sign the Windows executable and sign/notarize the macOS app if you plan to sell or broadly distribute it.
5. If you want Windows auto-start, test `installer\enable_autostart.bat` and `installer\disable_autostart.bat`.

## Commercial Readiness

1. Add a license or EULA.
2. Add a privacy policy if customer data or API keys are used.
3. Prepare customer setup instructions for AI and SMTP providers.
4. Decide how you will handle updates, support, and bug reports.
