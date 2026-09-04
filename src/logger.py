"""Structured logging with rotation, JSON format, and console output."""

import json
import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, Optional

from src.paths import BASE_DIR

# Constants
LOG_DIR = BASE_DIR / "logs"


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""

    def __init__(self, exclude_keys: Optional[list] = None):
        super().__init__()
        self.exclude_keys = exclude_keys or [
            "exc_info",
            "exc_text",
            "stack_info",
            "args",
        ]

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
        }

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Add extra fields if present
        if hasattr(record, "extra"):
            for key, value in record.extra.items():
                if key not in self.exclude_keys:
                    log_entry[key] = value

        return json.dumps(log_entry, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Colored console formatter for human-readable logs."""

    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[41m",  # Red background
        "RESET": "\033[0m",
    }

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with colors for console."""
        levelname = record.levelname
        color = self.COLORS.get(levelname, self.COLORS["RESET"])
        reset = self.COLORS["RESET"]

        # Format message with colors
        formatted = f"{color}{record.levelname:<8}{reset} {record.getMessage()}"

        # Add module/function info for DEBUG
        if record.levelno <= logging.DEBUG:
            formatted += f" [{record.module}:{record.funcName}:{record.lineno}]"

        return formatted


def setup_logger(
    name: str = "myfactory",
    log_level: str = "INFO",
    log_to_file: bool = True,
    log_to_console: bool = True,
    max_bytes: int = 5_000_000,
    backup_count: int = 3,
) -> logging.Logger:
    """
    Setup logger with rotating file and console handlers.

    Args:
        name: Logger name
        log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_to_file: Enable file logging
        log_to_console: Enable console logging
        max_bytes: Maximum file size before rotation
        backup_count: Number of backup files to keep

    Returns:
        Configured logger instance
    """
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Clear existing handlers to avoid duplicates
    logger.handlers.clear()

    # Prevent propagation to root logger
    logger.propagate = False

    # --- File Handler (JSON format, rotating) ---
    if log_to_file:
        # Create logs directory
        LOG_DIR.mkdir(parents=True, exist_ok=True)

        # Log file path
        log_file = LOG_DIR / f"{name}_{datetime.now().strftime('%Y%m%d')}.log"

        file_handler = RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(JSONFormatter())
        logger.addHandler(file_handler)

    # --- Console Handler (human-readable, optional colors) ---
    if log_to_console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))

        # Use colored formatter if terminal supports it
        if sys.stdout.isatty():
            console_handler.setFormatter(ConsoleFormatter())
        else:
            console_handler.setFormatter(
                logging.Formatter("%(levelname)-8s %(message)s")
            )

        logger.addHandler(console_handler)

    # Log startup info
    logger.info(
        f"Logger initialized",
        extra={
            "extra": {
                "log_level": log_level,
                "log_file": str(log_file) if log_to_file else None,
            }
        },
    )

    return logger


class LoggerManager:
    """Singleton logger manager for consistent logging across modules."""

    _instances: Dict[str, logging.Logger] = {}
    _initialized = False
    _default_logger: Optional[logging.Logger] = None

    def __init__(self, log_level: str = "INFO"):
        self.log_level = log_level
        self._initialized = True

    @classmethod
    def get_logger(
        cls, name: str = "myfactory", log_level: Optional[str] = None
    ) -> logging.Logger:
        """Get or create a logger instance."""
        if name in cls._instances:
            return cls._instances[name]

        level = log_level or getattr(cls, "log_level", "INFO")
        logger = setup_logger(name, level)
        cls._instances[name] = logger

        if cls._default_logger is None:
            cls._default_logger = logger

        return logger

    @classmethod
    def get_default(cls) -> logging.Logger:
        """Get the default logger instance."""
        if cls._default_logger is None:
            cls._default_logger = cls.get_logger("myfactory")
        return cls._default_logger


class LoggerAdapter(logging.LoggerAdapter):
    """Logger adapter for adding extra context to logs."""

    def __init__(self, logger: logging.Logger, extra: Optional[Dict[str, Any]] = None):
        super().__init__(logger, extra or {})

    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
        """Add extra context to log messages."""
        if self.extra:
            msg = f"[{self.extra}] {msg}"
        return msg, kwargs


# Convenience functions
def get_logger(name: str = "myfactory") -> logging.Logger:
    """Get a logger instance."""
    return LoggerManager.get_logger(name)


def get_default_logger() -> logging.Logger:
    """Get the default logger instance."""
    return LoggerManager.get_default()


# Initialize default logger
default_logger = get_default_logger()


# === Example usage ===
if __name__ == "__main__":
    # Test logger
    logger = setup_logger("test", "DEBUG")

    logger.debug("This is a debug message")
    logger.info("This is an info message")
    logger.warning("This is a warning message")
    logger.error("This is an error message")

    # Test with extra fields
    logger.info("User action", extra={"extra": {"user_id": 123, "action": "login"}})

    # Test exception
    try:
        raise ValueError("Test exception")
    except Exception as e:
        logger.exception("An error occurred")

    print(f"\nLog file: {LOG_DIR / 'test_20260825.log'}")
