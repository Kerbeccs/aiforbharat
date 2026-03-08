"""
DevOps Butler - Terraform Runner
Manages Terraform lifecycle: init → validate → plan → apply.
"""

import os
import json
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

from agents.executor.terminal import TerminalExecutor
from config.logging_config import get_logger
from core.exceptions import TerraformError

logger = get_logger("terraform")


class TerraformRunner:
    """Runs Terraform commands with output parsing and error handling."""

    def __init__(self):
        self.terminal = TerminalExecutor()

    def init(self, working_dir: str, trace_id: str = "no-trace") -> Dict[str, Any]:
        """Run terraform init."""
        result = self.terminal.execute(
            "terraform init -no-color",
            cwd=working_dir,
            timeout=120,
            trace_id=trace_id,
        )
        if not result["success"]:
            raise TerraformError(
                f"terraform init failed: {result['stderr']}",
                tf_command="init",
                trace_id=trace_id,
            )
        return result

    def validate(self, working_dir: str, trace_id: str = "no-trace") -> Dict[str, Any]:
        """Run terraform validate."""
        result = self.terminal.execute(
            "terraform validate -no-color",
            cwd=working_dir,
            timeout=60,
            trace_id=trace_id,
        )
        return result

    def plan(self, working_dir: str, trace_id: str = "no-trace") -> Dict[str, Any]:
        """Run terraform plan and capture planned changes."""
        result = self.terminal.execute(
            "terraform plan -no-color -out=tfplan",
            cwd=working_dir,
            timeout=180,
            trace_id=trace_id,
        )
        if not result["success"]:
            raise TerraformError(
                f"terraform plan failed: {result['stderr']}",
                tf_command="plan",
                trace_id=trace_id,
            )
        return result

    def apply(self, working_dir: str, auto_approve: bool = True, trace_id: str = "no-trace") -> Dict[str, Any]:
        """Run terraform apply."""
        cmd = "terraform apply -no-color"
        if auto_approve:
            cmd += " -auto-approve"
        
        # Use saved plan if available
        plan_file = os.path.join(working_dir, "tfplan")
        if os.path.exists(plan_file):
            cmd = f"terraform apply -no-color -auto-approve tfplan"

        result = self.terminal.execute(
            cmd,
            cwd=working_dir,
            timeout=600,  # 10 minutes for apply
            trace_id=trace_id,
        )
        if not result["success"]:
            raise TerraformError(
                f"terraform apply failed: {result['stderr']}",
                tf_command="apply",
                trace_id=trace_id,
            )
        return result

    def destroy(self, working_dir: str, trace_id: str = "no-trace") -> Dict[str, Any]:
        """Run terraform destroy (for rollback)."""
        result = self.terminal.execute(
            "terraform destroy -no-color -auto-approve",
            cwd=working_dir,
            timeout=600,
            trace_id=trace_id,
        )
        return result

    def output(self, working_dir: str, trace_id: str = "no-trace") -> Dict[str, Any]:
        """Get terraform outputs as JSON."""
        result = self.terminal.execute(
            "terraform output -json -no-color",
            cwd=working_dir,
            timeout=30,
            trace_id=trace_id,
        )
        if result["success"] and result["stdout"]:
            try:
                return json.loads(result["stdout"])
            except json.JSONDecodeError:
                pass
        return {}

    def write_tf_files(
        self,
        working_dir: str,
        files: Dict[str, str],
        trace_id: str = "no-trace",
    ) -> None:
        """Write Terraform files to the working directory."""
        os.makedirs(working_dir, exist_ok=True)
        for filename, content in files.items():
            filepath = os.path.join(working_dir, filename)
            Path(filepath).write_text(content, encoding="utf-8")
            logger.info(f"Wrote {filename}", extra={"trace_id": trace_id})

    def full_lifecycle(
        self,
        working_dir: str,
        tf_files: Optional[Dict[str, str]] = None,
        trace_id: str = "no-trace",
    ) -> Dict[str, Any]:
        """Run the full Terraform lifecycle: write → init → validate → plan → apply."""
        results = {}

        if tf_files:
            self.write_tf_files(working_dir, tf_files, trace_id)

        results["init"] = self.init(working_dir, trace_id)
        results["validate"] = self.validate(working_dir, trace_id)
        results["plan"] = self.plan(working_dir, trace_id)
        results["apply"] = self.apply(working_dir, trace_id=trace_id)
        results["output"] = self.output(working_dir, trace_id)

        return results
