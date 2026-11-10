"""Logging setup with structured console output."""

import logging
import sys


def setup_logging(log_level: str = "INFO") -> None:
    """Configure root logger with a structured format."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    log_format = "%(asctime)s | %(levelname)-7s | %(name)s:%(lineno)d - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    logging.basicConfig(
        level=level,
        format=log_format,
        datefmt=date_format,
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )

    # Silence noisy libraries
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
