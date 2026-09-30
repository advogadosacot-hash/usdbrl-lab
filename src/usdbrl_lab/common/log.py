"""Logging com timestamps em UTC. Mensagens em português (decisão P8)."""

from __future__ import annotations

import logging
import time

_FORMAT = "%(asctime)sZ %(levelname)s %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%dT%H:%M:%S"


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(_FORMAT, _DATEFMT)
        formatter.converter = time.gmtime
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(level)
        logger.propagate = False
    return logger
