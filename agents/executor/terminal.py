"""
DevOps Butler - Terminal Executor
Subprocess wrapper with streaming output, timeouts, and structured results.
"""

import subprocess
import shlex
import time
import logging
import platform
from typing import Dict, Any, Optional, List

from config.logging_config import get_logger
from core.exceptions import TerminalError

logger = get_logger("terminal")

IS_WINDOWS = platform.system() == "Windows"


class TerminalExecutor:
    """
    Safe subprocess wrapper for executing shell commands.
    Features: timeout, output capture, error detection, platform handling.
    """

    def execute(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 300,
        env: Optional[Dict[str, str]] = None,
        trace_id: str = "no-trace",
    ) -> Dict[str, Any]:
        """
        Execute a shell command and capture results.
        
        Args:
            command: Shell command to execute
            cwd: Working directory
            timeout: Max execution time in seconds
            env: Additional environment variables
            trace_id: For logging
            
        Returns:
            {
                "command": str,
                "exit_code": int,
                "stdout": str,
                "stderr": str,
                "success": bool,
                "duration_ms": float,
            }
        """
        logger.info(
            f"Executing: {command[:100]}{'...' if len(command) > 100 else ''}",
            extra={"trace_id": trace_id}
        )

        start_time = time.time()

        try:
            # Build environment
            import os
            run_env = os.environ.copy()
            if env:
                run_env.update(env)

            # Execute
            if IS_WINDOWS:
                result = subprocess.run(
                    command,
                    shell=True,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=run_env,
                )
            else:
                result = subprocess.run(
                    command,
                    shell=True,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=run_env,
                    executable="/bin/bash",
                )

            duration_ms = (time.time() - start_time) * 1000
            success = result.returncode == 0

            output = {
                "command": command,
                "exit_code": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "success": success,
                "duration_ms": round(duration_ms, 2),
            }

            level = logging.INFO if success else logging.WARNING
            logger.log(
                level,
                f"Command {'succeeded' if success else 'failed'} (exit {result.returncode}, {round(duration_ms)}ms)",
                extra={"trace_id": trace_id}
            )

            return output

        except subprocess.TimeoutExpired:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                f"Command timed out after {timeout}s: {command[:80]}",
                extra={"trace_id": trace_id}
            )
            return {
                "command": command,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Command timed out after {timeout} seconds",
                "success": False,
                "duration_ms": round(duration_ms, 2),
            }

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                f"Command execution error: {str(e)}",
                extra={"trace_id": trace_id}
            )
            return {
                "command": command,
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "success": False,
                "duration_ms": round(duration_ms, 2),
            }

    def execute_sequence(
        self,
        commands: List[str],
        cwd: Optional[str] = None,
        stop_on_error: bool = True,
        trace_id: str = "no-trace",
    ) -> List[Dict[str, Any]]:
        """
        Execute a sequence of commands.
        
        Args:
            commands: List of commands to execute in order
            cwd: Working directory
            stop_on_error: If True, stop on first failure
            trace_id: For logging
        """
        results = []
        for i, cmd in enumerate(commands):
            logger.info(
                f"Step {i + 1}/{len(commands)}: {cmd[:80]}",
                extra={"trace_id": trace_id}
            )
            result = self.execute(cmd, cwd=cwd, trace_id=trace_id)
            results.append(result)

            if not result["success"] and stop_on_error:
                logger.error(
                    f"Stopping sequence at step {i + 1} due to error",
                    extra={"trace_id": trace_id}
                )
                break

        return results
