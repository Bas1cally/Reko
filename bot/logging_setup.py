"""Zentrales Logging-Setup: Konsole + rotierende Datei (bot/bot.log)."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from . import config

_CONFIGURED = False


def get_logger(name: str = "bot") -> logging.Logger:
    """Liefert einen konfigurierten Logger (idempotent)."""
    global _CONFIGURED
    root = logging.getLogger("bot")
    if not _CONFIGURED:
        root.setLevel(getattr(logging, config.LOG_LEVEL, logging.INFO))
        fmt = logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        root.addHandler(console)
        try:
            fileh = RotatingFileHandler(
                config.LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
            )
            fileh.setFormatter(fmt)
            root.addHandler(fileh)
        except OSError:
            pass  # Datei-Logging optional (z.B. read-only FS)
        root.propagate = False
        _CONFIGURED = True
    return logging.getLogger(name if name.startswith("bot") else f"bot.{name}")
