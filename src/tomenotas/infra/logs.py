"""Structured logging for the daemon (Fase 5).

Every module uses logging.getLogger("tomenotas.<module>"); this function
wires the "tomenotas" root logger to a rotating file at
~/.local/share/tomenotas/daemon.log to make debugging easier.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def setup_logging(log_file: Path) -> logging.Logger:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("tomenotas")
    logger.setLevel(logging.INFO)
    # Idempotent per file: repeating for the same destination does not
    # duplicate the handler; a new destination replaces the previous one.
    for existing in list(logger.handlers):
        if (isinstance(existing, RotatingFileHandler)
                and Path(existing.baseFilename) == log_file):
            return logger
        logger.removeHandler(existing)
        existing.close()
    handler = RotatingFileHandler(
        log_file, maxBytes=1_000_000, backupCount=2, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(FORMAT))
    logger.addHandler(handler)
    return logger
