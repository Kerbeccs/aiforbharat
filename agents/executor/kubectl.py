"""
DevOps Butler - Kubectl Runner
Kubernetes command execution with structured output parsing.
"""

import json
import logging
from typing import Dict, Any, Optional, List

from agents.executor.terminal import TerminalExecutor
from config.logging_config import get_logger
from core.exceptions import KubernetesError

logger = get_logger("kubectl")


class KubectlRunner:
    """Runs kubectl commands with output parsing and error handling."""

    def __init__(self):
        self.terminal = TerminalExecutor()

    def apply(self, file_path: str, trace_id: str = "no-trace") -> Dict[str, Any]:
        """Apply a Kubernetes manifest file."""
        result = self.terminal.execute(
            f"kubectl apply -f {file_path}",
            timeout=120,
            trace_id=trace_id,
        )
        if not result["success"]:
            raise KubernetesError(
                f"kubectl apply failed: {result['stderr']}",
                kubectl_command=f"apply -f {file_path}",
                trace_id=trace_id,
            )
        return result

    def apply_content(self, yaml_content: str, trace_id: str = "no-trace") -> Dict[str, Any]:
        """Apply Kubernetes manifest from string content."""
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write(yaml_content)
            temp_path = f.name
        try:
            return self.apply(temp_path, trace_id)
        finally:
            os.unlink(temp_path)

    def get(self, resource: str, namespace: str = "default", trace_id: str = "no-trace") -> Dict[str, Any]:
        """Get Kubernetes resources."""
        result = self.terminal.execute(
            f"kubectl get {resource} -n {namespace} -o json",
            timeout=30,
            trace_id=trace_id,
        )
        if result["success"] and result["stdout"]:
            try:
                return json.loads(result["stdout"])
            except json.JSONDecodeError:
                pass
        return {"raw": result["stdout"]}

    def delete(self, resource: str, name: str, namespace: str = "default", trace_id: str = "no-trace") -> Dict[str, Any]:
        """Delete a Kubernetes resource (for rollback)."""
        result = self.terminal.execute(
            f"kubectl delete {resource} {name} -n {namespace}",
            timeout=60,
            trace_id=trace_id,
        )
        return result

    def rollout_status(self, deployment: str, namespace: str = "default", trace_id: str = "no-trace") -> Dict[str, Any]:
        """Check rollout status of a deployment."""
        result = self.terminal.execute(
            f"kubectl rollout status deployment/{deployment} -n {namespace} --timeout=300s",
            timeout=310,
            trace_id=trace_id,
        )
        return result

    def create_namespace(self, namespace: str, trace_id: str = "no-trace") -> Dict[str, Any]:
        """Create a Kubernetes namespace."""
        result = self.terminal.execute(
            f"kubectl create namespace {namespace} --dry-run=client -o yaml | kubectl apply -f -",
            timeout=30,
            trace_id=trace_id,
        )
        return result

    def write_manifests(
        self,
        output_dir: str,
        manifests: Dict[str, str],
        trace_id: str = "no-trace",
    ) -> List[str]:
        """Write K8s manifest files to directory."""
        import os
        from pathlib import Path

        os.makedirs(output_dir, exist_ok=True)
        written = []
        for filename, content in manifests.items():
            filepath = os.path.join(output_dir, filename)
            Path(filepath).write_text(content, encoding="utf-8")
            written.append(filepath)
            logger.info(f"Wrote manifest: {filename}", extra={"trace_id": trace_id})
        return written
