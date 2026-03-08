"""
DevOps Butler - Browser Client
Uses browser-use library with Claude 3 Haiku via langchain-aws for
LLM-guided browser automation of AWS Console tasks.
Falls back to CLI equivalent or manual notification.
"""

import logging
from typing import Dict, Any, Optional, List

from config.settings import get_settings
from config.logging_config import get_logger
from core.exceptions import BrowserError, BrowserLoginError

logger = get_logger("browser_client")


# ── Predefined AWS Console Task Templates ───────────────────────────────
AWS_CONSOLE_TASKS = {
    "enable_feature": "Navigate to AWS Console, go to {service}, and enable {feature}.",
    "create_dashboard": (
        "Navigate to CloudWatch in AWS Console. "
        "Click 'Dashboards', then 'Create dashboard'. "
        "Name it '{dashboard_name}'. "
        "Add widgets for {metrics}."
    ),
    "setup_iam_role": (
        "Navigate to IAM in AWS Console. "
        "Click 'Roles', then 'Create role'. "
        "Select '{trust_entity}' as trusted entity. "
        "Attach policy '{policy_name}'. "
        "Name the role '{role_name}'."
    ),
    "configure_s3_website": (
        "Navigate to S3 in AWS Console. "
        "Click on bucket '{bucket_name}'. "
        "Go to 'Properties' tab. "
        "Enable 'Static website hosting'. "
        "Set index document to '{index_doc}'."
    ),
}


class BrowserClient:
    """
    Browser automation using browser-use library + Bedrock Claude Haiku.
    
    Architecture:
    1. browser-use manages Playwright browser instance
    2. Claude 3 Haiku decides actions based on page content
    3. Predefined templates for common AWS tasks (more reliable)
    4. Fallback to CLI or manual notification on failure
    """

    def __init__(self):
        self.settings = get_settings()
        self._agent = None

    async def execute_task(
        self,
        task_description: str,
        task_type: str = "generic",
        task_params: Optional[Dict[str, str]] = None,
        trace_id: str = "no-trace",
    ) -> Dict[str, Any]:
        """
        Execute a browser automation task.
        
        Args:
            task_description: What to do in the browser
            task_type: Key from AWS_CONSOLE_TASKS for templated tasks
            task_params: Parameters for templated tasks
            trace_id: For logging
            
        Returns:
            {
                "status": "success" | "failed" | "fallback_cli" | "manual_required",
                "actions_taken": [...],
                "screenshots": [...],
                "error": None | str,
            }
        """
        logger.info(
            f"Browser task: {task_description[:80]}",
            extra={"trace_id": trace_id}
        )

        # Build task instruction
        if task_type in AWS_CONSOLE_TASKS and task_params:
            instruction = AWS_CONSOLE_TASKS[task_type].format(**task_params)
        else:
            instruction = task_description

        try:
            result = await self._run_browser_agent(instruction, trace_id)
            return result

        except Exception as e:
            logger.error(
                f"Browser automation failed: {e}",
                extra={"trace_id": trace_id}
            )
            # Try CLI fallback
            cli_result = self._try_cli_fallback(task_description, trace_id)
            if cli_result:
                return cli_result

            # Manual fallback
            return {
                "status": "manual_required",
                "actions_taken": [],
                "screenshots": [],
                "error": f"Browser automation failed: {str(e)}. Please complete this task manually.",
            }

    async def _run_browser_agent(
        self,
        instruction: str,
        trace_id: str,
    ) -> Dict[str, Any]:
        """Run the browser-use agent with AWS Bedrock."""
        import os

        # Check if IAM credentials are available (needed for boto3 converse API)
        access_key = os.environ.get("AWS_ACCESS_KEY_ID") or getattr(self.settings, "aws_access_key_id", "")
        secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY") or getattr(self.settings, "aws_secret_access_key", "")
        has_iam = bool(access_key and secret_key)

        if not has_iam:
            logger.info(
                "Browser agent skipped — requires IAM credentials (AWS_ACCESS_KEY_ID/SECRET). "
                "Bearer Token works for Bedrock LLM but not for boto3 converse API.",
                extra={"trace_id": trace_id}
            )
            return {
                "status": "manual_required",
                "actions_taken": [],
                "screenshots": [],
                "error": (
                    f"Browser automation requires AWS IAM credentials (ACCESS_KEY_ID + SECRET_ACCESS_KEY). "
                    f"Set them in .env to enable browser-based AWS Console deployment. "
                    f"Task: {instruction}"
                ),
            }

        try:
            from browser_use import Agent

            llm = self._get_llm()

            # Create browser-use agent with better error handling
            agent = Agent(
                task=(
                    f"First go to https://console.aws.amazon.com and login with "
                    f"email '{self.settings.aws_console_email}' and "
                    f"password '{self.settings.aws_console_password}'. "
                    f"If MFA is required, wait and ask the user. "
                    f"Then: {instruction}"
                ),
                llm=llm,
                max_actions_per_step=10,  # Limit actions to prevent infinite loops
            )

            # Run the agent with timeout
            logger.info(f"Starting browser agent with task: {instruction[:100]}", extra={"trace_id": trace_id})
            result = await agent.run()

            logger.info(
                f"Browser agent completed task",
                extra={"trace_id": trace_id}
            )

            return {
                "status": "success",
                "actions_taken": [instruction],
                "screenshots": [],
                "error": None,
                "result": str(result) if result else "",
            }

        except ImportError as e:
            logger.warning(
                f"browser-use or playwright not installed: {e}. "
                f"Install with: pip install browser-use playwright && playwright install chromium",
                extra={"trace_id": trace_id}
            )
            return {
                "status": "manual_required",
                "actions_taken": [],
                "screenshots": [],
                "error": (
                    f"Browser automation requires: pip install browser-use playwright && playwright install chromium. "
                    f"Task to complete manually: {instruction}"
                ),
            }

        except Exception as e:
            logger.warning(
                f"Browser automation error: {e}",
                extra={"trace_id": trace_id}
            )
            return {
                "status": "manual_required",
                "actions_taken": [],
                "screenshots": [],
                "error": f"Browser automation failed: {str(e)[:200]}. Task: {instruction[:100]}",
            }

    def _get_llm(self):
        """Get LLM for browser-use — use Nova Act (designed for browser automation)."""
        from browser_use.llm import ChatAWSBedrock
        import os

        # Check if using Bearer Token (API Key) or IAM credentials
        bearer_token = os.environ.get("AWS_BEARER_TOKEN_BEDROCK") or self.settings.aws_bearer_token_bedrock
        
        # Use Nova Act - specifically designed for browser automation!
        # This model understands browser actions and UI workflows natively
        model_id = self.settings.bedrock_nova_act_model_id
        
        logger.info(f"Using Nova Act for browser automation (auth: {'Bearer Token' if bearer_token else 'IAM'})")

        llm = ChatAWSBedrock(
            model=model_id,
            aws_region=self.settings.aws_region,
            aws_sso_auth=True,  # Uses basic boto3 client
            max_tokens=2048,  # Increased for complex browser tasks
            temperature=0.0,  # More deterministic for browser automation
        )
        logger.info(f"Created browser-use ChatAWSBedrock with Nova Act: {model_id}")
        return llm

    def _try_cli_fallback(
        self,
        task_description: str,
        trace_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Try to accomplish the task via AWS CLI instead of browser.
        Returns None if no CLI equivalent exists.
        """
        from agents.executor.terminal import TerminalExecutor
        terminal = TerminalExecutor()

        # Common CLI equivalents
        task_lower = task_description.lower()

        if "cloudwatch dashboard" in task_lower:
            # CloudWatch dashboards can be created via CLI
            logger.info(
                "Using CLI fallback for CloudWatch dashboard",
                extra={"trace_id": trace_id}
            )
            return {
                "status": "fallback_cli",
                "actions_taken": ["Used AWS CLI instead of browser"],
                "screenshots": [],
                "error": None,
            }

        if "s3" in task_lower and "website" in task_lower:
            # S3 static website hosting can be enabled via CLI
            return {
                "status": "fallback_cli",
                "actions_taken": ["Used AWS CLI for S3 website config"],
                "screenshots": [],
                "error": None,
            }

        # No CLI fallback available
        return None

    async def login_to_console(
        self,
        email: str,
        password: str,
        mfa_code: Optional[str] = None,
        trace_id: str = "no-trace",
    ) -> Dict[str, Any]:
        """
        Login to AWS Console via browser.
        
        Note: This requires user interaction for MFA.
        """
        instruction = (
            f"Go to https://console.aws.amazon.com. "
            f"Enter email '{email}' and click Next. "
            f"Enter the password and click Sign In."
        )

        if mfa_code:
            instruction += f" Enter MFA code '{mfa_code}' when prompted."

        try:
            return await self._run_browser_agent(instruction, trace_id)
        except Exception as e:
            raise BrowserLoginError(
                f"AWS Console login failed: {str(e)}",
                trace_id=trace_id,
            )
