"""
DevOps Butler - Browser Agent
LangGraph node that handles AWS Console browser automation tasks.
"""

import asyncio
import logging
from typing import Dict, Any

from agents.base_agent import BaseAgent, trace_operation
from agents.browser_agent.browser_client import BrowserClient
from core.state import ButlerState
from config.logging_config import get_logger

logger = get_logger("browser_agent")


class BrowserAgentNode(BaseAgent):
    """
    Agent 4: Browser Agent
    
    Handles tasks that require AWS Console interaction:
    - Enabling new features with no CLI
    - Configuring CloudWatch dashboards
    - Setting up IAM roles visually
    - Any console-only operation
    
    Uses browser-use library with Claude 3 Haiku for decision-making.
    Falls back to CLI or manual notification on failure.
    """

    def __init__(self):
        super().__init__(agent_name="browser_agent")
        self.client = BrowserClient()

    @trace_operation("browser_tasks")
    def process(self, state: ButlerState) -> ButlerState:
        trace_id = state.get("trace_id", "no-trace")
        browser_tasks = state.get("browser_tasks", [])

        pending = [t for t in browser_tasks if t.get("status") == "pending"]
        if not pending:
            logger.info("No browser tasks to execute", extra={"trace_id": trace_id})
            return state

        logger.info(
            f"Executing {len(pending)} browser task(s)",
            extra={"trace_id": trace_id}
        )

        # Create a new event loop for this thread (LangGraph runs in thread pool)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            for task in pending:
                try:
                    result = loop.run_until_complete(
                        self.client.execute_task(
                            task_description=task.get("task_description", ""),
                            trace_id=trace_id,
                        )
                    )

                    task["status"] = result.get("status", "failed")
                    task["actions_taken"] = result.get("actions_taken", [])
                    task["screenshots"] = result.get("screenshots", [])
                    task["error"] = result.get("error")

                except Exception as e:
                    logger.warning(
                        f"Browser task failed: {e}",
                        extra={"trace_id": trace_id}
                    )
                    task["status"] = "manual_required"
                    task["error"] = str(e)

                logger.info(
                    f"Browser task result: {task['status']}",
                    extra={"trace_id": trace_id}
                )
        finally:
            loop.close()

        state["browser_tasks"] = browser_tasks
        return state
