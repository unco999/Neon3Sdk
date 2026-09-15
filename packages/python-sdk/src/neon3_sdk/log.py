"""Structured logging for the Neon3 SDK.

Usage::

    import logging
    from neon3_sdk.log import get_logger, configure

    configure(level=logging.DEBUG)  # or NEON3_LOG_LEVEL=debug env var
    log = get_logger("render")

Every RPC call logs one line at INFO: target, method, request_id, elapsed_ms,
ok/err. Set level to DEBUG for frame-level detail.
"""

from __future__ import annotations

import logging
import os
import sys

_ROOT_NAME = "neon3_sdk"

_configured = False


def configure(level: int | str = logging.INFO) -> None:
    """Configure the neon3_sdk logger. Idempotent."""
    global _configured
    if _configured:
        return
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)
    logger = logging.getLogger(_ROOT_NAME)
    logger.setLevel(level)
    if not logger.handlers:
        handler = logging.StreamHandler(stream=sys.stderr)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
        ))
        logger.addHandler(handler)
    logger.propagate = False
    _configured = True


def get_logger(name: str = "") -> logging.Logger:
    """Return a child logger under ``neon3_sdk``.

    Honors the ``NEON3_LOG_LEVEL`` env var (``debug``/``info``/``warning``/
    ``error``) on first call.
    """
    if not _configured:
        env_level = os.environ.get("NEON3_LOG_LEVEL", "warning")
        configure(env_level)
    if name:
        return logging.getLogger(f"{_ROOT_NAME}.{name}")
    return logging.getLogger(_ROOT_NAME)
