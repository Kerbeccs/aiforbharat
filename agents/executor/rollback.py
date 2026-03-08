"""
DevOps Butler - Rollback Mechanism
Tracks all created resources and can destroy them in reverse order.
"""

import time
import logging
from typing import Dict, List, Any, Optional

from config.logging_config import get_logger
from core.exceptions import RollbackError

logger = get_logger("rollback")


class RollbackManager:
    """
    Tracks resources created during deployment and supports rollback.
    Resources are tagged with trace_id for identification.
    Rollback destroys resources in reverse creation order.
    """

    def __init__(self):
        self._created_resources: List[Dict[str, Any]] = []

    def track(
        self,
        resource_type: str,
        resource_id: str,
        name: str = "",
        cleanup_method: str = "",
        cleanup_args: Optional[Dict] = None,
        trace_id: str = "no-trace",
    ) -> None:
        """
        Track a created resource for potential rollback.
        
        Args:
            resource_type: e.g., "ecr_repo", "s3_bucket", "terraform", "k8s_deployment"
            resource_id: Unique identifier (ARN, name, etc.)
            name: Human-readable name
            cleanup_method: Method name to call for cleanup
            cleanup_args: Arguments for cleanup method
        """
        self._created_resources.append({
            "resource_type": resource_type,
            "resource_id": resource_id,
            "name": name or resource_id,
            "cleanup_method": cleanup_method,
            "cleanup_args": cleanup_args or {},
            "created_at": time.time(),
            "trace_id": trace_id,
        })
        logger.info(
            f"Tracking resource: {resource_type}/{name or resource_id}",
            extra={"trace_id": trace_id}
        )

    def rollback(self, trace_id: str = "no-trace") -> List[Dict[str, Any]]:
        """
        Roll back all tracked resources in reverse creation order.
        
        Returns:
            List of rollback results [{resource, status, error}]
        """
        if not self._created_resources:
            logger.info("No resources to roll back", extra={"trace_id": trace_id})
            return []

        logger.warning(
            f"Starting rollback of {len(self._created_resources)} resources",
            extra={"trace_id": trace_id}
        )

        results = []
        # Reverse order (most recently created first)
        for resource in reversed(self._created_resources):
            result = self._rollback_resource(resource, trace_id)
            results.append(result)

        successful = sum(1 for r in results if r["status"] == "rolled_back")
        failed = sum(1 for r in results if r["status"] == "rollback_failed")

        logger.info(
            f"Rollback complete: {successful} succeeded, {failed} failed",
            extra={"trace_id": trace_id}
        )

        # Clear tracked resources
        self._created_resources.clear()

        return results

    def _rollback_resource(
        self,
        resource: Dict[str, Any],
        trace_id: str,
    ) -> Dict[str, Any]:
        """Roll back a single resource."""
        resource_type = resource["resource_type"]
        resource_id = resource["resource_id"]
        name = resource.get("name", resource_id)

        logger.info(
            f"Rolling back: {resource_type}/{name}",
            extra={"trace_id": trace_id}
        )

        try:
            if resource_type == "ecr_repo":
                from agents.executor.aws_client import get_aws_client
                get_aws_client().delete_ecr_repository(resource_id, trace_id)

            elif resource_type == "s3_bucket":
                from agents.executor.aws_client import get_aws_client
                get_aws_client().delete_s3_bucket(resource_id, trace_id)

            elif resource_type == "terraform":
                from agents.executor.terraform import TerraformRunner
                tf = TerraformRunner()
                working_dir = resource.get("cleanup_args", {}).get("working_dir", "")
                if working_dir:
                    tf.destroy(working_dir, trace_id)

            elif resource_type in ("k8s_deployment", "k8s_service", "k8s_namespace"):
                from agents.executor.kubectl import KubectlRunner
                kubectl = KubectlRunner()
                cleanup_args = resource.get("cleanup_args", {})
                k8s_type = cleanup_args.get("type", "deployment")
                k8s_name = cleanup_args.get("name", resource_id)
                namespace = cleanup_args.get("namespace", "default")
                kubectl.delete(k8s_type, k8s_name, namespace, trace_id)

            elif resource_type == "docker_image":
                from agents.executor.terminal import TerminalExecutor
                terminal = TerminalExecutor()
                terminal.execute(f"docker rmi {resource_id}", trace_id=trace_id)

            elif resource_type == "ecs_cluster":
                from agents.executor.aws_client import get_aws_client
                ecs = get_aws_client()._get_client("ecs")
                ecs.delete_cluster(cluster=resource_id)

            else:
                logger.warning(
                    f"Unknown resource type for rollback: {resource_type}",
                    extra={"trace_id": trace_id}
                )
                return {
                    "resource": f"{resource_type}/{name}",
                    "status": "rollback_skipped",
                    "error": f"Unknown resource type: {resource_type}",
                }

            return {
                "resource": f"{resource_type}/{name}",
                "status": "rolled_back",
                "error": None,
            }

        except Exception as e:
            logger.error(
                f"Rollback failed for {resource_type}/{name}: {e}",
                extra={"trace_id": trace_id}
            )
            return {
                "resource": f"{resource_type}/{name}",
                "status": "rollback_failed",
                "error": str(e),
            }

    def get_tracked_resources(self) -> List[Dict[str, Any]]:
        """Get list of all tracked resources."""
        return list(self._created_resources)

    def clear(self) -> None:
        """Clear all tracked resources (after successful deployment)."""
        self._created_resources.clear()
