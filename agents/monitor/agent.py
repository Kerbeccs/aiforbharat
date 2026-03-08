"""
DevOps Butler - Monitor Agent
LangGraph node for post-deployment health checks and cost monitoring.
"""

import logging
from typing import Dict, Any

from agents.base_agent import BaseAgent, trace_operation
from agents.monitor.health import HealthMonitor, CostMonitor
from core.state import ButlerState
from config.logging_config import get_logger

logger = get_logger("monitor")


class MonitorAgent(BaseAgent):
    """
    Agent 5: Monitor
    
    Post-deployment responsibilities:
    1. Health checks on all deployed resources
    2. Cost tracking against budget
    3. Alert generation for issues
    4. Recommendations for optimization
    """

    def __init__(self):
        super().__init__(agent_name="monitor")
        self.health = HealthMonitor()
        self.cost = CostMonitor()

    @trace_operation("monitor_deployment")
    def process(self, state: ButlerState) -> ButlerState:
        trace_id = state.get("trace_id", "no-trace")
        exec_results = state.get("execution_results", [])

        logger.info("Starting post-deployment monitoring", extra={"trace_id": trace_id})

        health_checks = []
        alerts = []
        recommendations = []

        # ── Health Checks ───────────────────────────────────────────
        for result in exec_results:
            if result.get("status") == "success":
                resources = result.get("resources_created", [])
                for resource in resources:
                    check = self._check_resource_health(resource, trace_id)
                    if check:
                        health_checks.append(check)
                        if check.get("status") == "unhealthy":
                            alerts.append({
                                "severity": "critical",
                                "resource": check.get("resource"),
                                "message": f"Resource is unhealthy: {check.get('resource')}",
                            })
                        elif check.get("status") == "degraded":
                            alerts.append({
                                "severity": "warning",
                                "resource": check.get("resource"),
                                "message": f"Resource is degraded: {check.get('resource')}",
                            })

        # ── Cost Monitoring ─────────────────────────────────────────
        cost_info = self._check_costs(trace_id)
        current_cost = cost_info.get("current_cost", 0)
        budget = cost_info.get("budget", 100)

        if current_cost > 0:
            if current_cost > budget * 0.9:
                alerts.append({
                    "severity": "critical",
                    "resource": "budget",
                    "message": f"Cost ${current_cost:.2f} is {int(current_cost/budget*100)}% of budget",
                })
            elif current_cost > budget * 0.7:
                alerts.append({
                    "severity": "warning",
                    "resource": "budget",
                    "message": f"Cost ${current_cost:.2f} is approaching budget limit",
                })

        # ── Recommendations ─────────────────────────────────────────
        plan = state.get("deployment_plan", {})
        est_cost = plan.get("estimated_cost_monthly", 0)
        if est_cost > 50:
            recommendations.append(
                "Consider using Spot Instances for non-critical workloads to reduce costs by up to 90%."
            )
        if any(r.get("type") in ("ec2", "rds") for r in plan.get("infrastructure", [])):
            recommendations.append(
                "Enable auto-scaling to handle traffic spikes without over-provisioning."
            )

        # ── Write to state ──────────────────────────────────────────
        state["monitoring_status"] = {
            "health_checks": health_checks,
            "current_cost": current_cost,
            "cost_forecast": current_cost * 1.1,  # Simple 10% buffer forecast
            "alerts": alerts,
            "recommendations": recommendations,
        }

        logger.info(
            f"Monitoring complete: {len(health_checks)} checks, "
            f"{len(alerts)} alerts, cost=${current_cost:.2f}",
            extra={"trace_id": trace_id}
        )

        return state

    def _check_resource_health(
        self,
        resource: Dict[str, Any],
        trace_id: str,
    ) -> Dict[str, Any]:
        """Check health of a single deployed resource."""
        r_type = resource.get("type", "").lower()
        r_id = resource.get("id", "")

        try:
            if r_type == "ec2":
                return self.health.check_ec2_health(r_id, trace_id)
            elif r_type == "ecs":
                cluster = resource.get("cluster", "")
                service = resource.get("service", r_id)
                return self.health.check_ecs_health(cluster, service, trace_id)
            else:
                return {
                    "resource": f"{r_type}/{r_id}",
                    "status": "monitored",
                    "message": f"Basic monitoring active for {r_type}",
                }
        except Exception as e:
            logger.warning(
                f"Health check failed for {r_type}/{r_id}: {e}",
                extra={"trace_id": trace_id}
            )
            return {
                "resource": f"{r_type}/{r_id}",
                "status": "check_failed",
                "error": str(e),
            }

    def _check_costs(self, trace_id: str) -> Dict[str, Any]:
        """Get current cost information."""
        try:
            return self.cost.get_current_month_cost(trace_id)
        except Exception as e:
            logger.warning(f"Cost check failed: {e}", extra={"trace_id": trace_id})
            return {"current_cost": 0, "error": str(e), "budget": self.cost.settings.monthly_budget_usd}
