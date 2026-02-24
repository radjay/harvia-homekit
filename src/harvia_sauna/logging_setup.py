"""Centralised logging configuration for Harvia Sauna.

Call ``setup_logging()`` once at CLI entry to wire up console + file handlers.
Modules simply use ``logging.getLogger("harvia_sauna")`` etc. — the handlers
are only attached here, so importing a module has no side-effects.
"""

import logging
import os

LOG_DIR = "/tmp/harvia-homekit"
API_LOG_FILE = os.path.join(LOG_DIR, "api.log")
WS_LOG_FILE = os.path.join(LOG_DIR, "websocket.log")


def setup_logging(*, debug: bool = False, file_logs: bool = True):
    """Configure all loggers used by the package.

    Parameters
    ----------
    debug : bool
        If ``True``, set the main logger to DEBUG and pyhap to INFO.
    file_logs : bool
        If ``True`` (the default when running the service), create file
        handlers for the API and WebSocket loggers.  One-shot CLI
        commands can pass ``False`` to skip creating log files.
    """
    level = logging.DEBUG if debug else logging.INFO
    fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    logging.basicConfig(level=level, format=fmt)

    # Silence noisy libraries
    for name in ("boto3", "botocore", "urllib3"):
        logging.getLogger(name).setLevel(logging.WARNING)
    logging.getLogger("pyhap").setLevel(logging.INFO if debug else logging.WARNING)

    if not file_logs:
        return

    os.makedirs(LOG_DIR, exist_ok=True)
    file_fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    # --- API logger ---
    api_logger = logging.getLogger("harvia_api")
    api_logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(API_LOG_FILE)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(file_fmt)
    api_logger.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setLevel(logging.INFO)
    sh.setFormatter(file_fmt)
    api_logger.addHandler(sh)

    # --- WebSocket logger ---
    ws_logger = logging.getLogger("harvia_websocket")
    ws_logger.setLevel(logging.DEBUG)
    fh2 = logging.FileHandler(WS_LOG_FILE)
    fh2.setLevel(logging.DEBUG)
    fh2.setFormatter(file_fmt)
    ws_logger.addHandler(fh2)
    sh2 = logging.StreamHandler()
    sh2.setLevel(logging.INFO)
    sh2.setFormatter(file_fmt)
    ws_logger.addHandler(sh2)
