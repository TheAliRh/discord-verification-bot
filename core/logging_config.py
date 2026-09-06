"""
Central logging configuration for the whole bot.

Call setup_logging() once, at startup, before anything else runs. Every
other module just does `logger = logging.getLogger(__name__)` at the top
and logs normally - this file is the only place that decides format,
level, and where logs go (console + a rotating file).

This is deliberately separate from core/service.py's log_event(), which
posts human-readable audit messages to a Discord channel for server
admins to read. This module is for the bot's OWN operational logs -
startup, errors, warnings - the kind of thing you'd read in a terminal
or a log file, not something a Discord server's members or even admins
need to see.
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_FILE = LOG_DIR / "bot.log"


def setup_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()  # avoid duplicate handlers if this ever runs twice in one process
    root_logger.addHandler(console_handler)

    # File logging is a nice-to-have, not a requirement - if the logs/
    # directory can't be created (read-only disk, permissions issue), fall
    # back to console-only rather than crashing the whole bot before any
    # error-reporting infrastructure even exists to catch it.
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except OSError as e:
        root_logger.warning(
            "Could not set up file logging at %s (%s) - continuing with console only",
            LOG_FILE,
            e,
        )

    # discord.py's own logger is very chatty at INFO/DEBUG (gateway
    # heartbeats, session events) - keep it quiet unless the whole bot
    # is explicitly running in debug mode.
    if level > logging.DEBUG:
        logging.getLogger("discord").setLevel(logging.WARNING)
        logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
