"""
DevOps Butler - Trace Context
Generates and manages correlation trace IDs that flow through all agents.
Every operation gets a unique trace_id for end-to-end debugging.
"""

import uuid
import time
import logging
from typing import Optional, Dict, Any
from contextlib import contextmanager


class TraceContext:
    """
    Manages trace IDs for operation correlation across agents.
    
    Usage:
        trace = TraceContext.create("deploy_flask_app")
        with trace.span("code_analysis") as span:
            # All logs inside this block have the trace_id
            span.set_attribute("framework", "flask")
    """

    def __init__(self, trace_id: str, operation: str, parent_id: Optional[str] = None):
        self.trace_id = trace_id
        self.operation = operation
        self.parent_id = parent_id
        self.start_time = time.time()
        self.attributes: Dict[str, Any] = {}
        self._spans: list = []
        self._logger = logging.getLogger("butler")

    @classmethod
    def create(cls, operation: str) -> "TraceContext":
        """Create a new root trace context."""
        trace_id = f"btlr-{uuid.uuid4().hex[:12]}"
        ctx = cls(trace_id=trace_id, operation=operation)
        ctx._logger.info(
            f"Trace started: {operation}",
            extra={"trace_id": trace_id, "operation": operation}
        )
        return ctx

    def child(self, operation: str) -> "TraceContext":
        """Create a child trace context (inherits trace_id)."""
        return TraceContext(
            trace_id=self.trace_id,
            operation=operation,
            parent_id=self.trace_id,
        )

    @contextmanager
    def span(self, name: str):
        """Create a timed span within this trace."""
        span = TraceSpan(
            trace_id=self.trace_id,
            name=name,
            logger=self._logger,
        )
        self._spans.append(span)
        try:
            yield span
        except Exception as e:
            span.set_error(e)
            raise
        finally:
            span.finish()

    def set_attribute(self, key: str, value: Any) -> None:
        """Set an attribute on this trace."""
        self.attributes[key] = value

    def finish(self) -> Dict[str, Any]:
        """Finish the trace and return summary."""
        duration_ms = (time.time() - self.start_time) * 1000
        summary = {
            "trace_id": self.trace_id,
            "operation": self.operation,
            "duration_ms": round(duration_ms, 2),
            "attributes": self.attributes,
            "spans_count": len(self._spans),
            "errors": [s.error for s in self._spans if s.error],
        }
        self._logger.info(
            f"Trace completed: {self.operation} ({round(duration_ms)}ms)",
            extra={"trace_id": self.trace_id, "duration_ms": round(duration_ms, 2)}
        )
        return summary

    def to_dict(self) -> Dict[str, Any]:
        """Serialize trace context for state passing."""
        return {
            "trace_id": self.trace_id,
            "operation": self.operation,
            "parent_id": self.parent_id,
            "attributes": self.attributes,
        }


class TraceSpan:
    """A timed span within a trace."""

    def __init__(self, trace_id: str, name: str, logger: logging.Logger):
        self.trace_id = trace_id
        self.name = name
        self.start_time = time.time()
        self.error: Optional[str] = None
        self.attributes: Dict[str, Any] = {}
        self._logger = logger

        self._logger.debug(
            f"Span started: {name}",
            extra={"trace_id": trace_id, "operation": name}
        )

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def set_error(self, error: Exception) -> None:
        self.error = f"{type(error).__name__}: {str(error)}"
        self._logger.error(
            f"Span error in {self.name}: {self.error}",
            extra={"trace_id": self.trace_id, "operation": self.name}
        )

    def finish(self) -> None:
        duration_ms = (time.time() - self.start_time) * 1000
        self._logger.debug(
            f"Span completed: {self.name} ({round(duration_ms)}ms)",
            extra={
                "trace_id": self.trace_id,
                "operation": self.name,
                "duration_ms": round(duration_ms, 2),
            }
        )
