"""
DevOps Butler - Unified Bedrock API Client
Supports TWO authentication methods:
  1. Bearer Token (Bedrock API Key) — uses HTTP directly
  2. IAM Credentials — uses boto3

Also includes:
  - Rate limit handling (exponential backoff + jitter)
  - Circuit breaker (after N consecutive failures)
  - Model routing (Claude Sonnet, Haiku, Nova, Titan Embeddings)
  - Structured logging with trace IDs
"""

import json
import time
import random
import logging
from typing import Optional, Dict, Any, List
from urllib.parse import quote

import boto3
import httpx
from botocore.exceptions import ClientError

from config.settings import get_settings
from config.logging_config import get_logger
from core.exceptions import (
    BedrockError,
    BedrockRateLimitError,
    BedrockTimeoutError,
    BedrockCircuitOpenError,
)

logger = get_logger("bedrock_client")


class CircuitBreaker:
    """Simple circuit breaker to stop calling after N consecutive failures."""

    def __init__(self, threshold: int = 5, reset_timeout: float = 120.0):
        self.threshold = threshold
        self.reset_timeout = reset_timeout
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.is_open = False

    def record_success(self) -> None:
        self.failure_count = 0
        self.is_open = False

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.threshold:
            self.is_open = True

    def can_proceed(self) -> bool:
        if not self.is_open:
            return True
        if time.time() - self.last_failure_time > self.reset_timeout:
            self.is_open = False
            self.failure_count = 0
            return True
        return False


class BedrockClient:
    """
    Unified AWS Bedrock client for all model invocations.
    
    Auth priority:
      1. Bearer Token (AWS_BEARER_TOKEN_BEDROCK) → direct HTTP calls
      2. IAM Credentials (AWS_ACCESS_KEY_ID) → boto3
    
    Usage:
        client = BedrockClient()
        response = client.invoke_claude_sonnet("Generate a Terraform plan for...")
        embedding = client.embed_text("flask postgresql deployment")
    """

    def __init__(self):
        self.settings = get_settings()
        self._boto3_client = None
        self._http_client = None
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        
        # Determine auth mode
        self.use_bearer_token = bool(self.settings.aws_bearer_token_bedrock)
        if self.use_bearer_token:
            logger.info("Using Bearer Token (Bedrock API Key) authentication")
        else:
            logger.info("Using IAM credentials (boto3) authentication")

    @property
    def boto3_client(self):
        """Lazy-init boto3 bedrock-runtime client (for IAM auth)."""
        if self._boto3_client is None:
            self._boto3_client = boto3.client(
                "bedrock-runtime",
                region_name=self.settings.aws_region,
                aws_access_key_id=self.settings.aws_access_key_id,
                aws_secret_access_key=self.settings.aws_secret_access_key,
            )
        return self._boto3_client

    @property
    def http_client(self):
        """Lazy-init httpx client (for Bearer Token auth)."""
        if self._http_client is None:
            self._http_client = httpx.Client(
                timeout=120.0,
                headers={
                    "Authorization": f"Bearer {self.settings.aws_bearer_token_bedrock}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
        return self._http_client

    def _get_bedrock_url(self, model_id: str) -> str:
        """Build the Bedrock REST API URL for a model."""
        region = self.settings.aws_region
        # URL-encode the model ID (colons in v1:0 must be encoded)
        encoded_id = quote(model_id, safe='')
        return f"https://bedrock-runtime.{region}.amazonaws.com/model/{encoded_id}/invoke"

    def _get_circuit_breaker(self, model_id: str) -> CircuitBreaker:
        """Get or create circuit breaker for a model."""
        if model_id not in self._circuit_breakers:
            self._circuit_breakers[model_id] = CircuitBreaker(
                threshold=self.settings.bedrock_circuit_breaker_threshold
            )
        return self._circuit_breakers[model_id]

    def _invoke_with_retry(
        self,
        model_id: str,
        body: Dict[str, Any],
        trace_id: str = "no-trace",
        max_retries: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Invoke a Bedrock model with retry + circuit breaker.
        Routes to Bearer Token HTTP or boto3 based on config.
        """
        if max_retries is None:
            max_retries = self.settings.bedrock_max_retries

        cb = self._get_circuit_breaker(model_id)
        if not cb.can_proceed():
            raise BedrockCircuitOpenError(trace_id=trace_id)

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                logger.debug(
                    f"Invoking {model_id} (attempt {attempt + 1}, "
                    f"auth={'bearer' if self.use_bearer_token else 'iam'})",
                    extra={"trace_id": trace_id}
                )

                if self.use_bearer_token:
                    result = self._invoke_bearer(model_id, body, trace_id)
                else:
                    result = self._invoke_boto3(model_id, body, trace_id)

                cb.record_success()
                return result

            except BedrockRateLimitError as e:
                cb.record_failure()
                last_error = e
                if attempt < max_retries:
                    backoff = min(
                        self.settings.bedrock_base_backoff_seconds * (2 ** attempt),
                        self.settings.bedrock_max_backoff_seconds,
                    )
                    jitter = random.uniform(0, backoff * 0.5)
                    wait = backoff + jitter
                    logger.warning(
                        f"Rate limited, retry {attempt + 1}/{max_retries} in {wait:.1f}s",
                        extra={"trace_id": trace_id}
                    )
                    time.sleep(wait)
                    continue
                raise

            except (BedrockTimeoutError, BedrockError):
                raise

            except Exception as e:
                raise BedrockError(
                    message=f"Unexpected Bedrock error: {str(e)}",
                    trace_id=trace_id,
                ) from e

        raise last_error or BedrockError("Max retries exhausted", trace_id=trace_id)

    def _invoke_bearer(
        self,
        model_id: str,
        body: Dict[str, Any],
        trace_id: str,
    ) -> Dict[str, Any]:
        """Invoke Bedrock model via HTTP with Bearer Token auth."""
        url = self._get_bedrock_url(model_id)
        
        try:
            response = self.http_client.post(url, json=body)
            
            if response.status_code == 429:
                raise BedrockRateLimitError(
                    message=f"Rate limited on {model_id} (HTTP 429)",
                    trace_id=trace_id,
                )
            elif response.status_code == 408:
                raise BedrockTimeoutError(
                    message=f"Timeout on {model_id} (HTTP 408)",
                    trace_id=trace_id,
                )
            elif response.status_code != 200:
                error_body = response.text
                raise BedrockError(
                    message=f"Bedrock HTTP {response.status_code}: {error_body[:300]}",
                    trace_id=trace_id,
                )
            
            return response.json()
            
        except httpx.TimeoutException:
            raise BedrockTimeoutError(
                message=f"HTTP timeout on {model_id}",
                trace_id=trace_id,
            )
        except httpx.HTTPError as e:
            if "429" in str(e) or "throttl" in str(e).lower():
                raise BedrockRateLimitError(
                    message=f"Rate limited on {model_id}: {str(e)}",
                    trace_id=trace_id,
                )
            raise BedrockError(
                message=f"HTTP error on {model_id}: {str(e)}",
                trace_id=trace_id,
            ) from e

    def _invoke_boto3(
        self,
        model_id: str,
        body: Dict[str, Any],
        trace_id: str,
    ) -> Dict[str, Any]:
        """Invoke Bedrock model via boto3 with IAM credentials."""
        try:
            response = self.boto3_client.invoke_model(
                modelId=model_id,
                body=json.dumps(body),
                contentType="application/json",
                accept="application/json",
            )
            return json.loads(response["body"].read())

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_msg = e.response["Error"]["Message"]

            if error_code in ("ThrottlingException", "TooManyRequestsException"):
                raise BedrockRateLimitError(
                    message=f"Rate limited on {model_id}: {error_msg}",
                    trace_id=trace_id,
                )
            elif error_code == "ModelTimeoutException":
                raise BedrockTimeoutError(
                    message=f"Timeout on {model_id}: {error_msg}",
                    trace_id=trace_id,
                )
            else:
                raise BedrockError(
                    message=f"Bedrock error ({error_code}): {error_msg}",
                    trace_id=trace_id,
                )

    # ── Claude Sonnet 4.6 (Complex Planning) ────────────────────────

    def invoke_claude_sonnet(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.3,
        trace_id: str = "no-trace",
    ) -> str:
        """
        Invoke Claude Sonnet 4.6 for complex planning tasks.
        Falls back to Nova Pro if Claude is unavailable (billing/model issues).
        """
        try:
            messages = [{"role": "user", "content": prompt}]
            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": messages,
            }
            if system_prompt:
                body["system"] = system_prompt

            result = self._invoke_with_retry(
                model_id=self.settings.bedrock_claude_sonnet_model_id,
                body=body,
                trace_id=trace_id,
            )
            return result["content"][0]["text"]

        except BedrockError as e:
            # Fallback to Nova Pro on 403 (billing) or 400 (invalid model) errors
            if "403" in str(e) or "400" in str(e) or "denied" in str(e).lower() or "invalid" in str(e).lower():
                logger.warning(
                    f"Claude Sonnet unavailable ({e.message[:80]}), falling back to Nova Pro",
                    extra={"trace_id": trace_id}
                )
                return self.invoke_nova_pro(
                    prompt, system_prompt, max_tokens, trace_id=trace_id
                )
            raise

    # ── Claude 3 Haiku (Fast & Cheap) ───────────────────────────────

    def invoke_haiku(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.2,
        trace_id: str = "no-trace",
    ) -> str:
        """
        Invoke the cheap/fast model for lightweight tasks.
        Routes to Nova Lite or Claude Haiku depending on config.
        """
        model_id = self.settings.bedrock_claude_haiku_model_id

        # Detect if this is a Nova model (different request format)
        if "nova" in model_id.lower():
            return self.invoke_nova_pro(
                prompt, system_prompt, max_tokens, trace_id=trace_id,
            )

        # Claude format
        messages = [{"role": "user", "content": prompt}]
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        if system_prompt:
            body["system"] = system_prompt

        result = self._invoke_with_retry(
            model_id=model_id,
            body=body,
            trace_id=trace_id,
        )
        return result["content"][0]["text"]

    # ── Nova Pro (Fallback) ─────────────────────────────────────────

    def invoke_nova_pro(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.3,
        trace_id: str = "no-trace",
    ) -> str:
        """
        Invoke Amazon Nova Pro as fallback when Claude is rate-limited.
        """
        messages = [{"role": "user", "content": [{"text": prompt}]}]
        body = {
            "messages": messages,
            "inferenceConfig": {
                "maxTokens": max_tokens,
                "temperature": temperature,
            },
        }
        if system_prompt:
            body["system"] = [{"text": system_prompt}]

        result = self._invoke_with_retry(
            model_id=self.settings.bedrock_nova_pro_model_id,
            body=body,
            trace_id=trace_id,
        )
        return result["output"]["message"]["content"][0]["text"]

    # ── Titan Embeddings V2 (RAG) ───────────────────────────────────

    def embed_text(
        self,
        text: str,
        trace_id: str = "no-trace",
    ) -> List[float]:
        """
        Generate embeddings using Titan Embeddings V2.
        Returns 1024-dim vector (default for v2).
        Nearly free — use liberally for RAG.
        """
        body = {
            "inputText": text,
            "dimensions": 1024,
            "normalize": True,
        }
        result = self._invoke_with_retry(
            model_id=self.settings.bedrock_titan_embed_model_id,
            body=body,
            trace_id=trace_id,
        )
        return result["embedding"]

    def embed_texts(
        self,
        texts: List[str],
        trace_id: str = "no-trace",
    ) -> List[List[float]]:
        """Embed multiple texts. Calls embed_text for each (Titan doesn't support batching)."""
        embeddings = []
        for i, text in enumerate(texts):
            logger.debug(
                f"Embedding text {i + 1}/{len(texts)}",
                extra={"trace_id": trace_id}
            )
            embeddings.append(self.embed_text(text, trace_id=trace_id))
        return embeddings

    # ── Smart Invoke (with fallback chain) ──────────────────────────

    def invoke_smart(
        self,
        prompt: str,
        system_prompt: str = "",
        complexity: str = "high",
        max_tokens: int = 4096,
        trace_id: str = "no-trace",
    ) -> str:
        """
        Smart model selection based on task complexity.
        
        complexity="high" → Claude Sonnet → Nova Pro fallback
        complexity="low"  → Claude Haiku → Nova Lite fallback
        """
        if complexity == "high":
            try:
                return self.invoke_claude_sonnet(
                    prompt, system_prompt, max_tokens, trace_id=trace_id
                )
            except (BedrockRateLimitError, BedrockCircuitOpenError) as e:
                logger.warning(
                    f"Claude Sonnet unavailable, falling back to Nova Pro: {e.message}",
                    extra={"trace_id": trace_id}
                )
                return self.invoke_nova_pro(
                    prompt, system_prompt, max_tokens, trace_id=trace_id
                )
        else:
            try:
                return self.invoke_haiku(
                    prompt, system_prompt, max_tokens=min(max_tokens, 2048),
                    trace_id=trace_id,
                )
            except (BedrockRateLimitError, BedrockCircuitOpenError) as e:
                logger.warning(
                    f"Haiku unavailable, falling back to Nova Pro: {e.message}",
                    extra={"trace_id": trace_id}
                )
                return self.invoke_nova_pro(
                    prompt, system_prompt, max_tokens, trace_id=trace_id
                )


# ── Singleton ───────────────────────────────────────────────────────────
_bedrock_client: Optional[BedrockClient] = None


def get_bedrock_client() -> BedrockClient:
    """Get or create the global Bedrock client."""
    global _bedrock_client
    if _bedrock_client is None:
        _bedrock_client = BedrockClient()
    return _bedrock_client
