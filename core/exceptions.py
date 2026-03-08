"""
DevOps Butler - Custom Exception Hierarchy
Every exception carries an error_code and trace_id for debugging.
"""

from typing import Optional, Dict, Any


class ButlerError(Exception):
    """Base exception for all DevOps Butler errors."""

    def __init__(
        self,
        message: str,
        error_code: str = "BUTLER_ERROR",
        trace_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.error_code = error_code
        self.trace_id = trace_id
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": self.error_code,
            "message": self.message,
            "trace_id": self.trace_id,
            "details": self.details,
        }


# ── Bedrock / LLM Errors ────────────────────────────────────────────────

class BedrockError(ButlerError):
    """Base error for all Bedrock API issues."""
    def __init__(self, message: str, **kwargs):
        super().__init__(message, error_code="BEDROCK_ERROR", **kwargs)


class BedrockRateLimitError(BedrockError):
    """Bedrock API rate limit exceeded (throttling)."""
    def __init__(self, message: str = "Bedrock API rate limit exceeded", **kwargs):
        super().__init__(message, **kwargs)
        self.error_code = "BEDROCK_RATE_LIMIT"


class BedrockTimeoutError(BedrockError):
    """Bedrock API call timed out."""
    def __init__(self, message: str = "Bedrock API call timed out", **kwargs):
        super().__init__(message, **kwargs)
        self.error_code = "BEDROCK_TIMEOUT"


class BedrockCircuitOpenError(BedrockError):
    """Circuit breaker is open — too many consecutive failures."""
    def __init__(self, message: str = "Bedrock circuit breaker open — service unavailable", **kwargs):
        super().__init__(message, **kwargs)
        self.error_code = "BEDROCK_CIRCUIT_OPEN"


# ── Code Analysis Errors ────────────────────────────────────────────────

class AnalysisError(ButlerError):
    """Error during code analysis."""
    def __init__(self, message: str, **kwargs):
        super().__init__(message, error_code="ANALYSIS_ERROR", **kwargs)


class ParsingError(AnalysisError):
    """Tree-sitter or file parsing error."""
    def __init__(self, message: str, file_path: str = "", **kwargs):
        super().__init__(message, **kwargs)
        self.error_code = "PARSING_ERROR"
        self.details["file_path"] = file_path


# ── Planning Errors ─────────────────────────────────────────────────────

class PlanningError(ButlerError):
    """Error during deployment planning."""
    def __init__(self, message: str, **kwargs):
        super().__init__(message, error_code="PLANNING_ERROR", **kwargs)


class PlanValidationError(PlanningError):
    """Generated plan failed validation."""
    def __init__(self, message: str, validation_errors: list = None, **kwargs):
        super().__init__(message, **kwargs)
        self.error_code = "PLAN_VALIDATION_ERROR"
        self.details["validation_errors"] = validation_errors or []


class BudgetExceededError(PlanningError):
    """Estimated cost exceeds budget."""
    def __init__(self, estimated: float, budget: float, **kwargs):
        message = f"Estimated cost ${estimated:.2f}/month exceeds budget ${budget:.2f}/month"
        super().__init__(message, **kwargs)
        self.error_code = "BUDGET_EXCEEDED"
        self.details["estimated_cost"] = estimated
        self.details["budget"] = budget


# ── Execution Errors ────────────────────────────────────────────────────

class ExecutionError(ButlerError):
    """Error during task execution."""
    def __init__(self, message: str, **kwargs):
        super().__init__(message, error_code="EXECUTION_ERROR", **kwargs)


class TerminalError(ExecutionError):
    """Shell command execution failed."""
    def __init__(self, message: str, command: str = "", exit_code: int = -1, **kwargs):
        super().__init__(message, **kwargs)
        self.error_code = "TERMINAL_ERROR"
        self.details["command"] = command
        self.details["exit_code"] = exit_code


class TerraformError(ExecutionError):
    """Terraform operation failed."""
    def __init__(self, message: str, tf_command: str = "", **kwargs):
        super().__init__(message, **kwargs)
        self.error_code = "TERRAFORM_ERROR"
        self.details["tf_command"] = tf_command


class KubernetesError(ExecutionError):
    """Kubernetes operation failed."""
    def __init__(self, message: str, kubectl_command: str = "", **kwargs):
        super().__init__(message, **kwargs)
        self.error_code = "KUBERNETES_ERROR"
        self.details["kubectl_command"] = kubectl_command


class RollbackError(ExecutionError):
    """Rollback operation failed."""
    def __init__(self, message: str, original_error: str = "", **kwargs):
        super().__init__(message, **kwargs)
        self.error_code = "ROLLBACK_ERROR"
        self.details["original_error"] = original_error


# ── Browser Errors ──────────────────────────────────────────────────────

class BrowserError(ButlerError):
    """Error during browser automation."""
    def __init__(self, message: str, **kwargs):
        super().__init__(message, error_code="BROWSER_ERROR", **kwargs)


class BrowserLoginError(BrowserError):
    """Failed to login to AWS Console."""
    def __init__(self, message: str = "AWS Console login failed", **kwargs):
        super().__init__(message, **kwargs)
        self.error_code = "BROWSER_LOGIN_ERROR"


class BrowserNavigationError(BrowserError):
    """Failed to navigate to target page."""
    def __init__(self, message: str, target_url: str = "", **kwargs):
        super().__init__(message, **kwargs)
        self.error_code = "BROWSER_NAV_ERROR"
        self.details["target_url"] = target_url


# ── Monitoring Errors ───────────────────────────────────────────────────

class MonitoringError(ButlerError):
    """Error during health monitoring."""
    def __init__(self, message: str, **kwargs):
        super().__init__(message, error_code="MONITORING_ERROR", **kwargs)


# ── HuggingFace Errors ──────────────────────────────────────────────────

class HuggingFaceError(ButlerError):
    """Error calling HuggingFace Inference API."""
    def __init__(self, message: str, **kwargs):
        super().__init__(message, error_code="HUGGINGFACE_ERROR", **kwargs)


class HuggingFaceRateLimitError(HuggingFaceError):
    """HuggingFace API rate limit."""
    def __init__(self, message: str = "HuggingFace rate limit reached", **kwargs):
        super().__init__(message, **kwargs)
        self.error_code = "HF_RATE_LIMIT"
