# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for A1 Mail Dynamics.

Build with:  installer\\build.bat  (Windows)
         or: python installer/build.py --platform macos  (macOS)
Or manually: pyinstaller --clean --noconfirm installer\\A1SEODynamics.spec
"""
import os
import sys
from pathlib import Path

# Project root = the directory ABOVE installer/
PROJECT_ROOT = Path(os.getcwd())
if PROJECT_ROOT.name == "installer":
    PROJECT_ROOT = PROJECT_ROOT.parent

VENDORED_WEBVIEW = PROJECT_ROOT / "vendor" / "pywebview"
VENDORED_PYTHONNET = PROJECT_ROOT / "vendor" / "pythonnet"
VENDORED_CLR_LOADER = PROJECT_ROOT / "vendor" / "clr_loader"
VENDORED_BOTTLE = PROJECT_ROOT / "vendor" / "bottle"
VENDORED_PROXY_TOOLS = PROJECT_ROOT / "vendor" / "proxy_tools" / "proxy_tools-0.1.0"
PATHEX = [str(PROJECT_ROOT)]
HOOKSPATH = []

if (VENDORED_WEBVIEW / "webview").exists():
    PATHEX.append(str(VENDORED_WEBVIEW))
    HOOKSPATH.append(str(VENDORED_WEBVIEW / "webview" / "__pyinstaller"))

for vendor_path in (
    VENDORED_PYTHONNET,
    VENDORED_CLR_LOADER,
    VENDORED_BOTTLE,
    VENDORED_PROXY_TOOLS,
):
    if vendor_path.exists():
        PATHEX.append(str(vendor_path))

# Build pipeline generates both .ico and .icns from the current logo source.
ICON_ICO_PATH = PROJECT_ROOT / "assets" / "icon.ico"
ICON_ICNS_PATH = PROJECT_ROOT / "assets" / "icon.icns"
if sys.platform == "darwin" and ICON_ICNS_PATH.exists():
    icon_arg = str(ICON_ICNS_PATH)
elif ICON_ICO_PATH.exists():
    icon_arg = str(ICON_ICO_PATH)
else:
    icon_arg = None


datas = [
    # Bundled frontend (the React build output)
    (str(PROJECT_ROOT / "client" / "dist"), "client/dist"),
    # Sample CSV is served from /api/sample-csv
    (str(PROJECT_ROOT / "data" / "sample_contacts.csv"), "data"),
    # Ship the main guide so portable builds can seed it next to the .exe
    (str(PROJECT_ROOT / "README.md"), "."),
]


hiddenimports = [
    # Server / WSGI
    "waitress",
    # Desktop window
    "webview",
    # AI providers
    "openai",
    "openai._client",
    "requests",
    "requests.adapters",
    "urllib3",
    # Data
    "pandas",
    "pandas._libs.tslibs.base",
    # Web framework
    "werkzeug",
    "werkzeug.utils",
    # Config
    "dotenv",
    # Email stdlib
    "email",
    "email.utils",
    "email.message",
    "email.header",
    "email.mime.text",
    "email.mime.multipart",
    "email.mime.base",
    "email.mime.application",
    # Cryptography — required for offline license verification
    "cryptography",
    "cryptography.exceptions",
    "cryptography.hazmat",
    "cryptography.hazmat.primitives",
    "cryptography.hazmat.primitives.asymmetric",
    "cryptography.hazmat.primitives.asymmetric.ed25519",
    "cryptography.hazmat.primitives.serialization",
    "cryptography.hazmat.backends",
    "cryptography.hazmat.backends.openssl",
    # App services (the dynamic import inside generate_ai() is in drafts)
    "app.services.drafts",
    "app.services.ai",
    "app.services.auth",
    "app.services.automation",
    "app.services.contacts",
    "app.services.conversation",
    "app.services.desktop_settings",
    "app.services.email_renderer",
    "app.services.inbox",
    "app.services.licensing",
    "app.services.scheduling",
    "app.services.storage",
    "app.services.system_store",
    # pandas internals required for CSV parsing in frozen builds
    "pandas._libs.tslibs.nattype",
    "pandas._libs.tslibs.np_datetime",
    "pandas._libs.tslibs.timedeltas",
    "pandas._libs.tslibs.timestamps",
    "pandas._libs.tslibs.offsets",
]

if sys.platform == "darwin":
    hiddenimports.extend(
        [
            "webview.platforms.cocoa",
        ]
    )
elif os.name == "nt":
    hiddenimports.extend(
        [
            "webview.platforms.edgechromium",
            "webview.platforms.mshtml",
            "webview.platforms.winforms",
        ]
    )
else:
    hiddenimports.extend(
        [
            "webview.platforms.gtk",
        ]
    )


a = Analysis(
    [str(PROJECT_ROOT / "app" / "desktop.py")],
    pathex=PATHEX,
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=HOOKSPATH,
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Trim some unused heavy deps to keep the binary size sane
        "tkinter",
        "matplotlib",
        "scipy",
        "PIL.ImageTk",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    [],
    name="A1MailDynamics",
    exclude_binaries=True,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                 # UPX compression sometimes flags AV; keep off
    runtime_tmpdir=None,
    console=False,             # No background console window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_arg,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="A1MailDynamics",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="A1 Mail Dynamics.app",
        icon=icon_arg,
        bundle_identifier="com.a1technovation.a1maildynamics",
        info_plist={
            "CFBundleName": "A1 Mail Dynamics",
            "CFBundleDisplayName": "A1 Mail Dynamics",
            "CFBundleShortVersionString": "1.0.0",
            "CFBundleVersion": "1.0.0",
            "NSHighResolutionCapable": True,
        },
    )
