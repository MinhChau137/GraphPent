"""Structured logging với structlog – production ready."""

import logging
import structlog
from rich.console import Console
from rich.traceback import install as install_rich_traceback


# Bật rich traceback đẹp cho development
install_rich_traceback(show_locals=True)

def setup_logger(log_level: str = "INFO"):
    """Cấu hình structlog một lần duy nhất."""
    resolved_level = getattr(logging, log_level.upper(), logging.INFO)

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.UnicodeDecoder(),
    ]

    if log_level.upper() == "DEBUG":
        processors.append(structlog.processors.ExceptionPrettyPrinter())
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        logger_factory=structlog.PrintLoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(resolved_level),
        cache_logger_on_first_use=True,
    )

    # Console handler đẹp cho development
    console = Console(stderr=True)
    structlog.get_logger().info("Logger initialized", env=log_level)

    return structlog.get_logger()

# Khởi tạo logger global
logger = setup_logger()