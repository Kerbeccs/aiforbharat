"""
DevOps Butler - Central Configuration
Loads all settings from environment variables via .env file.
"""

import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Central configuration for DevOps Butler.
    All values loaded from .env file or environment variables.
    """

    # ── AWS Credentials ──────────────────────────────────────────────
    aws_access_key_id: str = Field(default="", description="AWS Access Key ID")
    aws_secret_access_key: str = Field(default="", description="AWS Secret Access Key")
    aws_region: str = Field(default="us-east-1", description="AWS Region")

    # ── Bedrock API Key (Bearer Token) ──────────────────────────────
    # If set, this is used INSTEAD of IAM credentials for Bedrock calls
    aws_bearer_token_bedrock: str = Field(
        default="",
        description="Bedrock API Key (Bearer Token) — alternative to IAM credentials"
    )

    # ── Bedrock Model IDs ────────────────────────────────────────────
    bedrock_claude_sonnet_model_id: str = Field(
        default="anthropic.claude-sonnet-4-6-20250514-v1:0",
        description="Claude Sonnet 4.6 for complex planning"
    )
    bedrock_claude_haiku_model_id: str = Field(
        default="anthropic.claude-3-haiku-20240307-v1:0",
        description="Claude 3 Haiku for fast cheap tasks"
    )
    bedrock_nova_pro_model_id: str = Field(
        default="amazon.nova-pro-v1:0",
        description="Nova Pro fallback model"
    )
    bedrock_nova_lite_model_id: str = Field(
        default="amazon.nova-lite-v1:0",
        description="Nova Lite for lightweight tasks"
    )
    bedrock_nova_act_model_id: str = Field(
        default="amazon.nova-act-v1:0",
        description="Nova Act for browser automation (specifically designed for UI tasks)"
    )
    bedrock_titan_embed_model_id: str = Field(
        default="amazon.titan-embed-text-v2:0",
        description="Titan Embeddings V2 for RAG vectors"
    )

    # ── HuggingFace ──────────────────────────────────────────────────
    hf_token: str = Field(default="", description="HuggingFace API token (free tier)")
    hf_codegemma_model: str = Field(
        default="google/codegemma-7b",
        description="CodeGemma model for Dockerfile generation"
    )

    # ── GitHub ───────────────────────────────────────────────────────
    github_token: Optional[str] = Field(default=None, description="GitHub PAT for CI/CD")

    # ── AWS Console (Browser Agent) ──────────────────────────────────
    aws_console_email: Optional[str] = Field(default=None)
    aws_console_password: Optional[str] = Field(default=None)
    enable_browser_automation: bool = Field(
        default=False,
        description="Enable browser automation with Nova Act"
    )

    # ── Budget ───────────────────────────────────────────────────────
    monthly_budget_usd: float = Field(default=100.0, description="Monthly budget cap in USD")

    # ── Notifications ────────────────────────────────────────────────
    slack_webhook_url: Optional[str] = Field(default=None)

    # ── Application ──────────────────────────────────────────────────
    log_level: str = Field(default="INFO")
    butler_home: str = Field(default="~/.butler")

    # ── Rate Limiting ────────────────────────────────────────────────
    bedrock_max_retries: int = Field(default=5, description="Max retries on Bedrock rate limit")
    bedrock_base_backoff_seconds: float = Field(default=1.0, description="Base backoff in seconds")
    bedrock_max_backoff_seconds: float = Field(default=60.0, description="Max backoff cap")
    bedrock_circuit_breaker_threshold: int = Field(
        default=5, description="Consecutive failures before circuit opens"
    )

    # ── Web UI ───────────────────────────────────────────────────────
    web_host: str = Field(default="0.0.0.0")
    web_port: int = Field(default=8000)

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }

    def get_butler_home_path(self) -> str:
        """Expand ~ in butler_home to absolute path."""
        return os.path.expanduser(self.butler_home)


# ── Singleton instance ──────────────────────────────────────────────────
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create the global settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
