from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from tjr.storage.app_paths import log_path


def get_log_path() -> Path:
    return log_path()


def configure_logging() -> Path:
    log_path = get_log_path()
    log_dir = log_path.parent
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return log_path

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    return log_path


def reset_log_file() -> Path:
    log_path = get_log_path()
    logger = logging.getLogger()

    for handler in logger.handlers:
        if isinstance(handler, RotatingFileHandler) and Path(handler.baseFilename) == log_path:
            handler.acquire()
            try:
                if handler.stream is not None:
                    handler.stream.seek(0)
                    handler.stream.truncate()
                    handler.stream.flush()
                    return log_path
            finally:
                handler.release()

    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("", encoding="utf-8")
    return log_path
