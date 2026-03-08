"""
DevOps Butler - Structured Logging Configuration
Every log line includes: trace_id, agent_name, timestamp, level.
JSON-formatted for easy parsing and debugging.
"""

import logging
import logging.handlers
import json
import os
from datetime import datetime, timezone
from typing import Optional


class TraceIDFilter(logging.Filter):
    """Injects trace_id and agent_name into every log record."""

    def __init__(self, default_agent: str = "system"):
        super().__init__()
        self.default_agent = default_agent
        self._trace_id: Optional[str] = None
        self._agent_name: str = default_agent

    def set_trace_id(self, trace_id: str) -> None:
        self._trace_id = trace_id

    def set_agent_name(self, agent_name: str) -> None:
        self._agent_name = agent_name

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = getattr(record, "trace_id", self._trace_id or "no-trace")
        record.agent_name = getattr(record, "agent_name", self._agent_name)
        return True


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "agent": getattr(record, "agent_name", "system"),
            "trace_id": getattr(record, "trace_id", "no-trace"),
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Include exception info if present
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Include any extra fields
        for key in ("error_code", "operation", "duration_ms", "resource_type"):
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val

        return json.dumps(log_entry, default=str)


class ConsoleFormatter(logging.Formatter):
    """Human-readable colored console output."""

    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.RESET)
        trace = getattr(record, "trace_id", "no-trace")
        agent = getattr(record, "agent_name", "system")

        # Truncate trace_id to first 8 chars for readability
        trace_short = trace[:8] if trace != "no-trace" else "--------"

        return (
            f"{color}[{record.levelname:<8}]{self.RESET} "
            f"\033[90m[{trace_short}]\033[0m "
            f"\033[94m[{agent:<16}]\033[0m "
            f"{record.getMessage()}"
        )


def setup_logging(
    log_level: str = "INFO",
    log_dir: Optional[str] = None,
    enable_file_logging: bool = True,
) -> logging.Logger:
    """
    Configure the root logger for DevOps Butler.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Directory for log files. Defaults to ~/.butler/logs/
        enable_file_logging: Whether to write logs to file
        
    Returns:
        Configured root logger
    """
    logger = logging.getLogger("butler")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    logger.handlers.clear()

    # ── Trace ID filter (shared across all handlers) ────────────────
    trace_filter = TraceIDFilter()
    logger.addFilter(trace_filter)

    # ── Console handler (human-readable) ────────────────────────────
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(ConsoleFormatter())
    logger.addHandler(console_handler)

    # ── File handler (JSON, rotating) ───────────────────────────────
    if enable_file_logging:
        if log_dir is None:
            log_dir = os.path.expanduser("~/.butler/logs")
        os.makedirs(log_dir, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, "butler.log"),
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(JSONFormatter())
        logger.addHandler(file_handler)

    # Store trace_filter on logger for access by agents
    logger._trace_filter = trace_filter  # type: ignore

    return logger


def get_logger(agent_name: str = "system") -> logging.Logger:
    """Get a child logger for a specific agent."""
    logger = logging.getLogger(f"butler.{agent_name}")
    return logger
