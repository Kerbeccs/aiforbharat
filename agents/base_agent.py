"""
DevOps Butler - Abstract Base Agent
All 5 agents inherit from this class.
Provides: structured logging, retry with backoff, trace propagation, error wrapping.
"""

import time
import logging
import functools
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Callable

from core.state import ButlerState
from core.trace import TraceContext
from core.exceptions import ButlerError, BedrockRateLimitError
from config.logging_config import get_logger


def trace_operation(operation_name: str):
    """
    Decorator that wraps agent methods with trace spans and error logging.
    
    Usage:
        @trace_operation("analyze_code")
        def analyze(self, state: ButlerState) -> ButlerState:
            ...
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(self, state: ButlerState, *args, **kwargs):
            trace_id = state.get("trace_id", "no-trace")
            self.logger.info(
                f"Starting {operation_name}",
                extra={"trace_id": trace_id, "agent_name": self.agent_name}
            )
            start_time = time.time()
            
            try:
                result = func(self, state, *args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000
                self.logger.info(
                    f"Completed {operation_name} ({round(duration_ms)}ms)",
                    extra={
                        "trace_id": trace_id,
                        "agent_name": self.agent_name,
                        "duration_ms": round(duration_ms, 2),
                    }
                )
                return result
            except ButlerError:
                raise  # Already has error_code and trace_id
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                self.logger.error(
                    f"Failed {operation_name}: {type(e).__name__}: {str(e)}",
                    extra={
                        "trace_id": trace_id,
                        "agent_name": self.agent_name,
                        "duration_ms": round(duration_ms, 2),
                    },
                    exc_info=True,
                )
                # Wrap in ButlerError for consistent handling
                raise ButlerError(
                    message=f"{operation_name} failed: {str(e)}",
                    error_code=f"{self.agent_name.upper()}_ERROR",
                    trace_id=trace_id,
                ) from e
        return wrapper
    return decorator


class BaseAgent(ABC):
    """
    Abstract base class for all DevOps Butler agents.
    
    Subclasses must implement:
        - process(state: ButlerState) -> ButlerState
        
    Provides:
        - self.logger: agent-specific logger with trace ID injection
        - self.retry_with_backoff(): retry wrapper for API calls
        - self._add_error(): helper to append errors to state
    """

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.logger = get_logger(agent_name)

    @abstractmethod
    def process(self, state: ButlerState) -> ButlerState:
        """
        Process the state and return updated state.
        This is the LangGraph node function.
        """
        ...

    def __call__(self, state: ButlerState) -> ButlerState:
        """Make the agent callable as a LangGraph node."""
        state["current_agent"] = self.agent_name
        try:
            return self.process(state)
        except ButlerError as e:
            self.logger.error(
                f"Agent error: {e.error_code} - {e.message}",
                extra={"trace_id": state.get("trace_id", "no-trace")}
            )
            return self._add_error(state, e.error_code, e.message)
        except Exception as e:
            self.logger.error(
                f"Unexpected error: {str(e)}",
                extra={"trace_id": state.get("trace_id", "no-trace")},
                exc_info=True,
            )
            return self._add_error(state, "UNEXPECTED_ERROR", str(e))

    def retry_with_backoff(
        self,
        func: Callable,
        max_retries: int = 5,
        base_backoff: float = 1.0,
        max_backoff: float = 60.0,
        retry_on: tuple = (BedrockRateLimitError,),
        trace_id: str = "no-trace",
    ) -> Any:
        """
        Retry a function with exponential backoff + jitter.
        
        Args:
            func: Callable to retry (no arguments — use functools.partial)
            max_retries: Maximum retry attempts
            base_backoff: Initial backoff in seconds
            max_backoff: Maximum backoff cap
            retry_on: Tuple of exception types to retry on
            trace_id: For logging
            
        Returns:
            Result of successful func() call
            
        Raises:
            Last exception if all retries exhausted
        """
        import random
        
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                return func()
            except retry_on as e:
                last_error = e
                if attempt == max_retries:
                    self.logger.error(
                        f"All {max_retries} retries exhausted: {str(e)}",
                        extra={"trace_id": trace_id, "agent_name": self.agent_name}
                    )
                    raise
                
                # Exponential backoff with jitter
                backoff = min(base_backoff * (2 ** attempt), max_backoff)
                jitter = random.uniform(0, backoff * 0.5)
                wait_time = backoff + jitter
                
                self.logger.warning(
                    f"Retry {attempt + 1}/{max_retries} in {wait_time:.1f}s: {str(e)}",
                    extra={"trace_id": trace_id, "agent_name": self.agent_name}
                )
                time.sleep(wait_time)

    def _add_error(
        self,
        state: ButlerState,
        error_code: str,
        message: str,
    ) -> ButlerState:
        """Append an error to state's error list."""
        errors = state.get("errors", [])
        errors.append({
            "error_code": error_code,
            "message": message,
            "agent": self.agent_name,
            "trace_id": state.get("trace_id", "no-trace"),
            "timestamp": time.time(),
        })
        state["errors"] = errors
        return state
