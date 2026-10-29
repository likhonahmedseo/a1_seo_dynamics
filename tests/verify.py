"""
Deep verification script — checks imports, env vars, SMTP/IMAP connectivity, OpenAI key.
Run: python verify.py
"""
import os, sys

# ── Load .env first ────────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv(override=True)

results = []

def ok(label):   results.append(('OK', label))
def warn(label): results.append(('WARN', label))
def err(label):  results.append(('ERR', label))

# ── 1. Python imports ──────────────────────────────────────────────────────────
imports_to_check = [
    ('Flask',    'flask',                       'Flask framework'),
    ('Pandas',   'pandas',                      'CSV parsing'),
    ('OpenAI',   'openai',                      'AI email generation'),
    ('Playwright','playwright.sync_api',        'Gmail browser automation'),
    ('dotenv',   'dotenv',                      'Env file loading'),
]

for name, module, desc in imports_to_check:
    try:
        __import__(module)
        ok(f'{name} ({desc}) — importable')
    except ImportError as e:
        err(f'{name} ({desc}) — NOT installed: {e}')


# ── 2. App module imports ──────────────────────────────────────────────────────
app_modules = [
    'app.models',
    'app.services.storage',
    'app.services.contacts',
    'app.services.drafts',
    'app.services.ai',
    'app.services.automation',
    'app.services.inbox',
    'app.services.conversation',
]

for mod in app_modules:
    try:
        __import__(mod)
        ok(f'Import {mod}')
    except Exception as e:
        err(f'Import {mod}: {e}')


# ── 3. Full Flask app import ───────────────────────────────────────────────────
try:
    from app.web import app as flask_app
    ok('Flask app (app.web) loads cleanly')
except Exception as e:
    err(f'Flask app failed to load: {e}')


# ── 4. Environment variables ───────────────────────────────────────────────────
env_checks = {
    'OPENAI_API_KEY':  ('AI generation & auto-replies',   True),
    'SMTP_HOST':       ('SMTP sending',                    True),
    'SMTP_USERNAME':   ('SMTP sending / IMAP login',       True),
    'SMTP_PASSWORD':   ('SMTP sending / IMAP login',       True),
    'IMAP_HOST':       ('Inbox monitoring',                True),
}

for var, (desc, required) in env_checks.items():
    value = os.getenv(var, '')
    if value:
        masked = value[:6] + '…' + value[-4:] if len(value) > 12 else '***'
        ok(f'ENV {var} = {masked}  ({desc})')
    elif required:
        err(f'ENV {var} is MISSING — needed for {desc}')
    else:
        warn(f'ENV {var} not set — {desc} disabled')


# ── 5. SMTP connectivity test ─────────────────────────────────────────────────
import smtplib, ssl as ssl_mod
host     = os.getenv('SMTP_HOST', 'smtp.gmail.com')
port     = int(os.getenv('SMTP_PORT', '587'))
username = os.getenv('SMTP_USERNAME', '')
password = os.getenv('SMTP_PASSWORD', '')

if username and password:
    try:
        ctx = ssl_mod.create_default_context()
        with smtplib.SMTP(host, port, timeout=8) as s:
            s.starttls(context=ctx)
            s.login(username, password)
        ok(f'SMTP login to {host}:{port} — SUCCESS')
    except smtplib.SMTPAuthenticationError:
        err(f'SMTP auth failed — check SMTP_USERNAME / SMTP_PASSWORD in .env')
    except Exception as e:
        err(f'SMTP connection failed: {e}')
else:
    warn('SMTP credentials missing — skipping connectivity test')


# ── 6. IMAP connectivity test ─────────────────────────────────────────────────
import imaplib
imap_host = os.getenv('IMAP_HOST', 'imap.gmail.com')
imap_port = int(os.getenv('IMAP_PORT', '993'))

if username and password:
    try:
        with imaplib.IMAP4_SSL(imap_host, imap_port) as imap:
            imap.login(username, password)
            imap.select('INBOX')
        ok(f'IMAP login to {imap_host}:{imap_port} — SUCCESS')
    except imaplib.IMAP4.error:
        err(f'IMAP auth failed — ensure IMAP is enabled in Gmail Settings and the App Password is correct')
    except Exception as e:
        err(f'IMAP connection failed: {e}')
else:
    warn('IMAP credentials missing — skipping connectivity test')


# ── 7. OpenAI API key validity (lightweight) ──────────────────────────────────
api_key = os.getenv('OPENAI_API_KEY', '')
if api_key and api_key.startswith('sk-'):
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        # Minimal call — just list models to confirm key works
        models = client.models.list()
        ok(f'OpenAI API key valid — {len(list(models))} models accessible')
    except Exception as e:
        err(f'OpenAI API key check failed: {e}')
elif api_key:
    warn(f'OPENAI_API_KEY present but does not start with sk- (may be a project key — ok)')
else:
    err('OPENAI_API_KEY is missing — AI features will not work')


# ── 8. Playwright Chrome check ────────────────────────────────────────────────
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        # Just check that the chrome channel is available
        browser = p.chromium.launch(channel='chrome', headless=True)
        version = browser.version
        browser.close()
    ok(f'Playwright Chrome available (version {version})')
except Exception as e:
    err(f'Playwright Chrome not ready: {e}\n       Run: python -m playwright install chrome')


# ── 9. Data directories ────────────────────────────────────────────────────────
from pathlib import Path
runtime_dir = Path('data/runtime')
runtime_dir.mkdir(parents=True, exist_ok=True)
ok(f'data/runtime directory exists (or was created)')


# ── Print report ───────────────────────────────────────────────────────────────
print('\n' + '='*58)
print('  FULL SYSTEM VERIFICATION REPORT')
print('='*58)

ok_count   = sum(1 for s,_ in results if s=='OK')
warn_count = sum(1 for s,_ in results if s=='WARN')
err_count  = sum(1 for s,_ in results if s=='ERR')

for status, msg in results:
    icon = {'OK':'[OK]  ','WARN':'[WARN]','ERR':'[ERR] '}[status]
    print(f'  {icon} {msg}')

print('='*58)
print(f'  Result: {ok_count} OK   {warn_count} Warnings   {err_count} Errors')
print('='*58)

if err_count:
    sys.exit(1)
