"""
DevOps Butler - Health & Cost Monitoring
CloudWatch health checks and Cost Explorer budget tracking.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional

import boto3
from botocore.exceptions import ClientError

from config.settings import get_settings
from config.logging_config import get_logger
from core.exceptions import MonitoringError

logger = get_logger("health_monitor")


def _boto3_kwargs(settings) -> dict:
    """Build boto3 kwargs, only including credentials if set."""
    kwargs = {"region_name": settings.aws_region}
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    return kwargs


class HealthMonitor:
    """CloudWatch-based health monitoring for deployed resources."""

    def __init__(self):
        self.settings = get_settings()
        self._cloudwatch = None

    @property
    def cloudwatch(self):
        if self._cloudwatch is None:
            self._cloudwatch = boto3.client("cloudwatch", **_boto3_kwargs(self.settings))
        return self._cloudwatch

    def check_ec2_health(
        self,
        instance_id: str,
        trace_id: str = "no-trace",
    ) -> Dict[str, Any]:
        """Check EC2 instance health via CloudWatch."""
        try:
            ec2 = boto3.client("ec2", **_boto3_kwargs(self.settings))
            response = ec2.describe_instance_status(InstanceIds=[instance_id])
            statuses = response.get("InstanceStatuses", [])

            if statuses:
                status = statuses[0]
                return {
                    "resource": f"ec2/{instance_id}",
                    "status": "healthy" if status["InstanceState"]["Name"] == "running" else "unhealthy",
                    "instance_state": status["InstanceState"]["Name"],
                    "system_status": status["SystemStatus"]["Status"],
                    "instance_status": status["InstanceStatus"]["Status"],
                }
            return {
                "resource": f"ec2/{instance_id}",
                "status": "unknown",
                "message": "No status information available",
            }
        except ClientError as e:
            logger.warning(f"EC2 health check failed: {e}", extra={"trace_id": trace_id})
            return {"resource": f"ec2/{instance_id}", "status": "error", "error": str(e)}

    def check_ecs_health(
        self,
        cluster: str,
        service: str,
        trace_id: str = "no-trace",
    ) -> Dict[str, Any]:
        """Check ECS service health."""
        try:
            ecs = boto3.client("ecs", **_boto3_kwargs(self.settings))
            response = ecs.describe_services(cluster=cluster, services=[service])
            services = response.get("services", [])

            if services:
                svc = services[0]
                running = svc.get("runningCount", 0)
                desired = svc.get("desiredCount", 0)
                return {
                    "resource": f"ecs/{cluster}/{service}",
                    "status": "healthy" if running >= desired else "degraded",
                    "running_count": running,
                    "desired_count": desired,
                }
            return {"resource": f"ecs/{cluster}/{service}", "status": "not_found"}
        except ClientError as e:
            return {"resource": f"ecs/{cluster}/{service}", "status": "error", "error": str(e)}

    def get_resource_metrics(
        self,
        namespace: str,
        metric_name: str,
        dimensions: List[Dict[str, str]],
        period_minutes: int = 60,
        trace_id: str = "no-trace",
    ) -> Dict[str, Any]:
        """Get CloudWatch metrics for a resource."""
        try:
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(minutes=period_minutes)

            response = self.cloudwatch.get_metric_statistics(
                Namespace=namespace,
                MetricName=metric_name,
                Dimensions=dimensions,
                StartTime=start_time,
                EndTime=end_time,
                Period=300,
                Statistics=["Average", "Maximum"],
            )

            datapoints = response.get("Datapoints", [])
            if datapoints:
                latest = sorted(datapoints, key=lambda x: x["Timestamp"])[-1]
                return {
                    "metric": metric_name,
                    "average": latest.get("Average", 0),
                    "maximum": latest.get("Maximum", 0),
                    "timestamp": str(latest.get("Timestamp")),
                }
            return {"metric": metric_name, "message": "No data"}
        except ClientError as e:
            return {"metric": metric_name, "error": str(e)}


class CostMonitor:
    """AWS Cost Explorer integration for budget tracking."""

    def __init__(self):
        self.settings = get_settings()
        self._cost_explorer = None

    @property
    def cost_explorer(self):
        if self._cost_explorer is None:
            kwargs = _boto3_kwargs(self.settings)
            kwargs["region_name"] = "us-east-1"  # Cost Explorer is global
            self._cost_explorer = boto3.client("ce", **kwargs)
        return self._cost_explorer

    def get_current_month_cost(
        self,
        trace_id: str = "no-trace",
    ) -> Dict[str, Any]:
        """Get current month's AWS spending."""
        try:
            now = datetime.now(timezone.utc)
            start = now.replace(day=1).strftime("%Y-%m-%d")
            end = now.strftime("%Y-%m-%d")

            response = self.cost_explorer.get_cost_and_usage(
                TimePeriod={"Start": start, "End": end},
                Granularity="MONTHLY",
                Metrics=["UnblendedCost"],
            )

            results = response.get("ResultsByTime", [])
            if results:
                amount = float(results[0]["Total"]["UnblendedCost"]["Amount"])
                return {
                    "current_cost": round(amount, 2),
                    "period": f"{start} to {end}",
                    "budget": self.settings.monthly_budget_usd,
                    "budget_remaining": round(self.settings.monthly_budget_usd - amount, 2),
                    "utilization_pct": round(amount / self.settings.monthly_budget_usd * 100, 1),
                }
            return {"current_cost": 0, "message": "No cost data available"}

        except ClientError as e:
            logger.warning(f"Cost Explorer query failed: {e}", extra={"trace_id": trace_id})
            return {"current_cost": -1, "error": str(e)}

    def get_cost_by_service(
        self,
        trace_id: str = "no-trace",
    ) -> List[Dict[str, Any]]:
        """Get cost breakdown by AWS service."""
        try:
            now = datetime.now(timezone.utc)
            start = now.replace(day=1).strftime("%Y-%m-%d")
            end = now.strftime("%Y-%m-%d")

            response = self.cost_explorer.get_cost_and_usage(
                TimePeriod={"Start": start, "End": end},
                Granularity="MONTHLY",
                Metrics=["UnblendedCost"],
                GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
            )

            results = response.get("ResultsByTime", [])
            services = []
            if results:
                for group in results[0].get("Groups", []):
                    service_name = group["Keys"][0]
                    cost = float(group["Metrics"]["UnblendedCost"]["Amount"])
                    if cost > 0.01:
                        services.append({
                            "service": service_name,
                            "cost": round(cost, 2),
                        })
            return sorted(services, key=lambda x: x["cost"], reverse=True)

        except ClientError as e:
            logger.warning(f"Cost breakdown query failed: {e}", extra={"trace_id": trace_id})
            return []
