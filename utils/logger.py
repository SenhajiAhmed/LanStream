import logging
import os
import sys

from config import APP_LOG_FILE


def setup_logger(name: str = "EGY-Stream", level: int = logging.INFO) -> logging.Logger:
    """Configures and returns a styled logger instance with both console and file output."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(level)

        # 1. Console Handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-7s | %(message)s",
            datefmt="%H:%M:%S"
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

        # 2. File Handler (saves all app logs to output/app.log)
        try:
            os.makedirs(os.path.dirname(APP_LOG_FILE), exist_ok=True)
            file_handler = logging.FileHandler(APP_LOG_FILE, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)  # Always log details to file
            file_formatter = logging.Formatter(
                fmt="%(asctime)s | %(levelname)-7s | [%(name)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
        except Exception:
            pass

    return logger
