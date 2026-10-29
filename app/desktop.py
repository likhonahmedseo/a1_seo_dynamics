"""
Desktop launcher — runs the Flask app in a background thread and opens
a native window via pywebview.

Usage:
    python -m app.desktop                  # opens the window normally
    python -m app.desktop --minimized      # starts hidden (used by autostart)
    python -m app.desktop --background     # starts server only in the background
    python -m app.desktop --port 5174      # change local port

When packaged with PyInstaller, the same module is the entry point of the
Windows `A1MailDynamics.exe` and the macOS `A1 Mail Dynamics.app` bundle.
See installer/A1SEODynamics.spec.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import queue
import socket
import sys
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

# IMPORTANT: app.paths must be imported first so .env is loaded before any
# module reads os.getenv at import time.
import app.paths  # noqa: F401
from app.logging_config import configure_logging
from app.paths import LOG_DIR, RUNTIME_DIR
from app.runtime_lock import SingleInstanceLock
from app.web import app, shutdown_app


ACTIVE_SERVER_FILE = RUNTIME_DIR / "active_server.json"


def _write_boot_trace(message: str) -> None:
    """Best-effort early startup trace for frozen builds and packaging smoke tests."""
    try:
        log_dir = Path(LOG_DIR)
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / "bootstrap.log").open("a", encoding="utf-8") as handle:
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            handle.write(f"{stamp} {message}\n")
    except Exception:
        pass


def _publish_active_server(url: str, port: int, *, mode: str) -> None:
    try:
        ACTIVE_SERVER_FILE.parent.mkdir(parents=True, exist_ok=True)
        ACTIVE_SERVER_FILE.write_text(
            json.dumps(
                {
                    "url": url,
                    "port": port,
                    "pid": os.getpid(),
                    "mode": mode,
                    "updated_at": datetime.now().isoformat(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass


def _clear_active_server() -> None:
    try:
        if ACTIVE_SERVER_FILE.exists():
            ACTIVE_SERVER_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def _active_server_candidates(preferred_port: int) -> list[str]:
    candidates: list[str] = []
    if ACTIVE_SERVER_FILE.exists():
        try:
            state = json.loads(ACTIVE_SERVER_FILE.read_text(encoding="utf-8"))
            url = str(state.get("url") or "").strip()
            if url:
                candidates.append(url)
        except Exception:
            pass
    candidates.append(f"http://127.0.0.1:{preferred_port}")
    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            deduped.append(candidate)
    return deduped


def _first_healthy_url(candidates: list[str], timeout_s: float = 0.75) -> str | None:
    for candidate in candidates:
        try:
            with urlopen(f"{candidate}/api/health", timeout=timeout_s) as resp:
                if resp.status < 500:
                    return candidate
        except (URLError, OSError):
            continue
    return None


def _wait_for_existing_instance(preferred_port: int, timeout_s: float = 12.0) -> str | None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        healthy_url = _first_healthy_url(_active_server_candidates(preferred_port))
        if healthy_url:
            return healthy_url
        time.sleep(0.35)
    return None


def _open_existing_instance(url: str) -> None:
    try:
        if os.name == "nt":
            os.startfile(url)  # type: ignore[attr-defined]
            return
    except Exception:
        pass
    try:
        webbrowser.open(url, new=0, autoraise=True)
    except Exception:
        pass


def _is_port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) != 0


def _pick_port(host: str, preferred: int) -> int:
    """Use the preferred port if available, otherwise let the OS pick one."""
    if _is_port_free(host, preferred):
        return preferred
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def _run_server(host: str, port: int, errors: "queue.Queue[BaseException]") -> None:
    """Run waitress (or Flask dev fallback) in this thread."""
    log = logging.getLogger("app.desktop.server")
    _write_boot_trace(f"server-thread start host={host} port={port}")
    try:
        from waitress import serve
        _write_boot_trace("waitress import ok")
        log.info("Starting Waitress on %s:%d", host, port)
        serve(
            app,
            host=host,
            port=port,
            threads=8,
            channel_timeout=600,
            cleanup_interval=30,
            ident="A1-Mail-Dynamics",
            asyncore_use_poll=True,
        )
    except ImportError:
        if getattr(sys, "frozen", False) or os.getenv("APP_ENV", "").strip().lower() == "production":
            _write_boot_trace("waitress missing in production/frozen build")
            raise RuntimeError("Waitress is required for production desktop builds.") from None
        log.warning("Waitress unavailable — falling back to Flask dev server.")
        _write_boot_trace("falling back to flask dev server")
        app.run(host=host, port=port, debug=False, threaded=True, use_reloader=False)
    except BaseException as exc:
        _write_boot_trace(f"server-thread crash: {exc!r}")
        log.exception("Desktop server thread crashed before becoming healthy.")
        errors.put(exc)


def _wait_for_server(url: str, errors: "queue.Queue[BaseException]", timeout_s: float = 8.0) -> bool:
    """Poll until the server responds, or give up after timeout."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            exc = errors.get_nowait()
        except queue.Empty:
            exc = None
        if exc is not None:
            raise RuntimeError("Embedded server failed to start.") from exc
        try:
            with urlopen(url, timeout=0.5) as resp:
                if resp.status < 500:
                    return True
        except (URLError, OSError):
            pass
        time.sleep(0.15)
    return False


def _startup_timeout() -> float:
    if getattr(sys, "frozen", False):
        return 30.0
    return 12.0


def main() -> int:
    _write_boot_trace("main enter")
    configure_logging()
    log = logging.getLogger(__name__)
    _write_boot_trace("logging configured")

    parser = argparse.ArgumentParser(description="A1 Mail Dynamics — desktop app")
    parser.add_argument("--minimized", action="store_true",
                        help="Start with the window minimized (used by autostart).")
    parser.add_argument("--port", type=int, default=5174,
                        help="Preferred local port (default: 5174).")
    parser.add_argument("--no-window", action="store_true",
                        help="Run headless (server only). Open http://localhost:<port> in any browser.")
    parser.add_argument("--background", action="store_true",
                        help="Run in the background with no desktop window (used by sign-in startup).")
    args = parser.parse_args()
    headless_mode = args.no_window or args.background
    _write_boot_trace(
        f"args parsed no_window={args.no_window} background={args.background} "
        f"minimized={args.minimized} port={args.port}"
    )

    instance_lock = SingleInstanceLock("desktop.lock")
    if not instance_lock.acquire():
        _write_boot_trace("instance lock acquire failed")
        existing_url = _wait_for_existing_instance(args.port)
        if existing_url:
            _write_boot_trace(f"existing instance healthy at {existing_url}")
            log.info("Another instance is already running at %s", existing_url)
            if not headless_mode:
                _open_existing_instance(existing_url)
            return 0
        log.warning("Another desktop instance is already running, but no healthy server was detected.")
        return 3
    _write_boot_trace("instance lock acquired")

    try:
        host = "127.0.0.1"
        port = _pick_port(host, args.port)
        url  = f"http://{host}:{port}"
        _write_boot_trace(f"resolved url {url}")
        server_errors: "queue.Queue[BaseException]" = queue.Queue()

        server_thread = threading.Thread(
            target=_run_server, args=(host, port, server_errors),
            daemon=True, name="FlaskServer",
        )
        server_thread.start()
        _write_boot_trace("server thread started")

        if not _wait_for_server(f"{url}/api/health", server_errors, timeout_s=_startup_timeout()):
            _write_boot_trace("health wait timed out")
            log.error("Server did not become ready within timeout — exiting.")
            shutdown_app()
            return 1

        _write_boot_trace("health check passed")
        log.info("Server ready at %s", url)
        if args.background:
            published_mode = "background"
        elif args.no_window:
            published_mode = "browser"
        else:
            published_mode = "desktop"
        _publish_active_server(url, port, mode=published_mode)

        if headless_mode:
            # Headless — keep the foreground thread alive until Ctrl+C
            try:
                while True:
                    time.sleep(60)
            except KeyboardInterrupt:
                pass
            finally:
                _clear_active_server()
                shutdown_app()
            return 0

        # Native desktop window
        try:
            import webview  # type: ignore
        except ImportError:
            log.error("pywebview is not installed. Install with: pip install pywebview")
            log.error("Or use --no-window mode and open %s in your browser.", url)
            shutdown_app()
            return 2

        window = webview.create_window(
            title="A1 Mail Dynamics",
            url=url,
            width=1280,
            height=820,
            min_size=(960, 640),
            confirm_close=False,
            text_select=True,
        )

        if args.minimized:
            # Minimize once shown — works on Windows EdgeChromium / GTK / Cocoa
            def _on_shown():
                try:
                    window.minimize()
                except Exception:
                    pass
            window.events.shown += _on_shown

        try:
            webview.start()
        finally:
            log.info("Window closed — shutting down.")
            _clear_active_server()
            shutdown_app()
        return 0
    finally:
        _clear_active_server()
        instance_lock.release()


if __name__ == "__main__":
    sys.exit(main())
