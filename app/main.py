from __future__ import annotations

import logging
import os
import signal
import sys

from app.runtime_lock import SingleInstanceLock

def _install_signal_handlers(shutdown_fn) -> None:
    """Install SIGINT/SIGTERM handlers for graceful shutdown (where supported)."""
    log = logging.getLogger(__name__)

    def _handler(signum, _frame):
        log.info("Received signal %s — shutting down.", signum)
        try:
            shutdown_fn()
        finally:
            sys.exit(0)

    for sig_name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            try:
                signal.signal(sig, _handler)
            except (ValueError, OSError):
                # Some platforms (e.g. Windows under certain consoles) reject
                # specific signals. Skip silently.
                pass


def main() -> None:
    from app.web import app, shutdown_app
    log = logging.getLogger(__name__)

    host = os.getenv("HOST", "127.0.0.1")
    try:
        port = int(os.getenv("PORT", "5000"))
    except ValueError:
        port = 5000

    _install_signal_handlers(shutdown_app)
    instance_lock = SingleInstanceLock("server.lock")
    if not instance_lock.acquire():
        log.error("Another server instance is already running.")
        sys.exit(3)

    banner = f"""
{'='*55}
  A1 Mail Dynamics  —  AI Marketing Agent
  http://{host}:{port}
{'='*55}
"""
    print(banner)

    try:
        from waitress import serve
        log.info("Starting production server (Waitress) on %s:%s", host, port)
        serve(
            app,
            host=host,
            port=port,
            threads=int(os.getenv("WAITRESS_THREADS", "8")),
            channel_timeout=600,         # allow long SSE streams
            cleanup_interval=30,
            ident="A1-Mail-Dynamics",
            asyncore_use_poll=True,
        )
    except ImportError:
        if getattr(sys, "frozen", False) or os.getenv("APP_ENV", "").strip().lower() == "production":
            raise RuntimeError("Waitress is required for production server mode.") from None
        log.warning("Waitress not found — falling back to Flask dev server. "
                    "Run: pip install waitress  for production stability.")
        app.run(debug=False, host=host, port=port, threaded=True, use_reloader=False)
    except KeyboardInterrupt:
        pass
    finally:
        shutdown_app()
        instance_lock.release()


if __name__ == "__main__":
    main()
