"""
DevOps Butler - Cost Estimator
Uses AWS Pricing API to estimate monthly infrastructure costs before deployment.
Helps Master Planner validate plans against budget.
"""

import logging
from typing import Dict, List, Any, Optional

import boto3
from botocore.exceptions import ClientError

from config.settings import get_settings
from config.logging_config import get_logger

logger = get_logger("cost_estimator")

# ── Static cost estimates (fallback when Pricing API is unavailable) ────
# Based on us-east-1 on-demand pricing as of 2024
STATIC_COST_ESTIMATES: Dict[str, Dict[str, float]] = {
    "ec2": {
        "t2.micro": 8.35,
        "t2.small": 16.70,
        "t2.medium": 33.41,
        "t3.micro": 7.49,
        "t3.small": 14.98,
        "t3.medium": 29.95,
        "t3.large": 59.90,
        "m5.large": 69.12,
        "m5.xlarge": 138.24,
    },
    "rds": {
        "db.t3.micro": 12.41,
        "db.t3.small": 24.82,
        "db.t3.medium": 49.64,
        "db.r5.large": 172.80,
    },
    "eks": {
        "cluster": 73.00,  # $0.10/hr for control plane
        "node_t3.medium": 29.95,
        "node_t3.large": 59.90,
    },
    "s3": {
        "storage_per_gb": 0.023,
        "requests_per_1000": 0.005,
    },
    "ecr": {
        "storage_per_gb": 0.10,
    },
    "cloudfront": {
        "per_gb_transfer": 0.085,
    },
    "rds_storage": {
        "per_gb": 0.115,
    },
    "elasticache": {
        "cache.t3.micro": 11.52,
        "cache.t3.small": 23.04,
    },
    "alb": {
        "base": 16.20,  # $0.0225/hr
        "per_lcu": 5.84,
    },
    "nat_gateway": {
        "base": 32.40,  # $0.045/hr
        "per_gb": 0.045,
    },
}


class CostEstimator:
    """
    Estimates monthly AWS infrastructure costs.
    Uses static lookup tables (fast, free)
    with optional Pricing API validation.
    """

    def __init__(self):
        self.settings = get_settings()
        self._pricing_client = None

    @property
    def pricing_client(self):
        """Lazy-init AWS Pricing API client (us-east-1 only)."""
        if self._pricing_client is None:
            try:
                self._pricing_client = boto3.client(
                    "pricing",
                    region_name="us-east-1",  # Pricing API only available here
                    aws_access_key_id=self.settings.aws_access_key_id,
                    aws_secret_access_key=self.settings.aws_secret_access_key,
                )
            except Exception as e:
                logger.warning(f"Pricing API unavailable, using static estimates: {e}")
        return self._pricing_client

    def estimate_plan_cost(
        self,
        plan_resources: List[Dict[str, Any]],
        trace_id: str = "no-trace",
    ) -> Dict[str, Any]:
        """
        Estimate total monthly cost for a deployment plan.
        
        Args:
            plan_resources: List of resources like:
                [
                    {"type": "ec2", "instance_type": "t3.medium", "count": 2},
                    {"type": "rds", "instance_type": "db.t3.micro", "storage_gb": 20},
                    {"type": "eks", "node_count": 2, "node_type": "t3.medium"},
                    {"type": "s3", "storage_gb": 10},
                    {"type": "alb", "count": 1},
                ]
                
        Returns:
            {
                "total_monthly_usd": 150.00,
                "breakdown": [{"service": "EC2", "details": "2x t3.medium", "cost": 59.90}],
                "within_budget": True,
                "budget_remaining": 50.00,
            }
        """
        logger.info(
            f"Estimating cost for {len(plan_resources)} resources",
            extra={"trace_id": trace_id}
        )

        breakdown = []
        total = 0.0

        for resource in plan_resources:
            r_type = resource.get("type", "").lower()
            cost_info = self._estimate_resource(resource, trace_id)
            breakdown.append(cost_info)
            total += cost_info["cost"]

        budget = self.settings.monthly_budget_usd
        result = {
            "total_monthly_usd": round(total, 2),
            "breakdown": breakdown,
            "within_budget": total <= budget,
            "budget_remaining": round(budget - total, 2),
            "budget_limit": budget,
        }

        logger.info(
            f"Cost estimate: ${total:.2f}/month (budget: ${budget:.2f})",
            extra={"trace_id": trace_id}
        )
        return result

    def _estimate_resource(
        self,
        resource: Dict[str, Any],
        trace_id: str,
    ) -> Dict[str, Any]:
        """Estimate cost for a single resource."""
        r_type = resource.get("type", "").lower()
        count = resource.get("count", 1)

        if r_type == "ec2":
            instance_type = resource.get("instance_type", "t3.medium")
            unit_cost = STATIC_COST_ESTIMATES.get("ec2", {}).get(instance_type, 30.0)
            cost = unit_cost * count
            return {
                "service": "EC2",
                "details": f"{count}x {instance_type}",
                "cost": round(cost, 2),
            }

        elif r_type == "rds":
            instance_type = resource.get("instance_type", "db.t3.micro")
            storage_gb = resource.get("storage_gb", 20)
            instance_cost = STATIC_COST_ESTIMATES.get("rds", {}).get(instance_type, 25.0)
            storage_cost = storage_gb * STATIC_COST_ESTIMATES["rds_storage"]["per_gb"]
            cost = (instance_cost + storage_cost) * count
            return {
                "service": "RDS",
                "details": f"{count}x {instance_type} + {storage_gb}GB",
                "cost": round(cost, 2),
            }

        elif r_type == "eks":
            node_count = resource.get("node_count", 2)
            node_type = resource.get("node_type", "t3.medium")
            cluster_cost = STATIC_COST_ESTIMATES["eks"]["cluster"]
            node_key = f"node_{node_type}"
            node_unit = STATIC_COST_ESTIMATES.get("eks", {}).get(node_key, 30.0)
            cost = cluster_cost + (node_unit * node_count)
            return {
                "service": "EKS",
                "details": f"Cluster + {node_count}x {node_type} nodes",
                "cost": round(cost, 2),
            }

        elif r_type == "s3":
            storage_gb = resource.get("storage_gb", 10)
            cost = storage_gb * STATIC_COST_ESTIMATES["s3"]["storage_per_gb"]
            return {
                "service": "S3",
                "details": f"{storage_gb}GB storage",
                "cost": round(cost, 2),
            }

        elif r_type == "alb":
            cost = STATIC_COST_ESTIMATES["alb"]["base"] * count
            return {
                "service": "ALB",
                "details": f"{count}x Application Load Balancer",
                "cost": round(cost, 2),
            }

        elif r_type == "ecr":
            storage_gb = resource.get("storage_gb", 5)
            cost = storage_gb * STATIC_COST_ESTIMATES["ecr"]["storage_per_gb"]
            return {
                "service": "ECR",
                "details": f"{storage_gb}GB container images",
                "cost": round(cost, 2),
            }

        elif r_type == "cloudfront":
            transfer_gb = resource.get("transfer_gb", 50)
            cost = transfer_gb * STATIC_COST_ESTIMATES["cloudfront"]["per_gb_transfer"]
            return {
                "service": "CloudFront",
                "details": f"{transfer_gb}GB/month transfer",
                "cost": round(cost, 2),
            }

        elif r_type == "elasticache":
            instance_type = resource.get("instance_type", "cache.t3.micro")
            unit_cost = STATIC_COST_ESTIMATES.get("elasticache", {}).get(instance_type, 12.0)
            cost = unit_cost * count
            return {
                "service": "ElastiCache",
                "details": f"{count}x {instance_type}",
                "cost": round(cost, 2),
            }

        elif r_type == "nat_gateway":
            transfer_gb = resource.get("transfer_gb", 30)
            base = STATIC_COST_ESTIMATES["nat_gateway"]["base"]
            transfer = transfer_gb * STATIC_COST_ESTIMATES["nat_gateway"]["per_gb"]
            cost = (base + transfer) * count
            return {
                "service": "NAT Gateway",
                "details": f"{count}x gateway + {transfer_gb}GB",
                "cost": round(cost, 2),
            }

        else:
            logger.warning(
                f"Unknown resource type: {r_type}, using $10 estimate",
                extra={"trace_id": trace_id}
            )
            return {
                "service": r_type.upper(),
                "details": f"{count}x {r_type}",
                "cost": 10.0 * count,
            }

    def check_budget(
        self,
        estimated_cost: float,
        trace_id: str = "no-trace",
    ) -> Dict[str, Any]:
        """
        Check if estimated cost is within budget.
        Returns whether auto-approval is safe or user approval needed.
        """
        budget = self.settings.monthly_budget_usd
        ratio = estimated_cost / budget if budget > 0 else float("inf")

        if ratio <= 0.3:
            decision = "auto_approve"
            message = f"Cost ${estimated_cost:.2f} is well within budget (${budget:.2f})"
        elif ratio <= 0.7:
            decision = "auto_approve"
            message = f"Cost ${estimated_cost:.2f} is within budget (${budget:.2f})"
        elif ratio <= 1.0:
            decision = "user_approve"
            message = f"Cost ${estimated_cost:.2f} is close to budget limit (${budget:.2f})"
        else:
            decision = "reject"
            message = f"Cost ${estimated_cost:.2f} EXCEEDS budget (${budget:.2f})"

        logger.info(f"Budget check: {decision} — {message}", extra={"trace_id": trace_id})

        return {
            "decision": decision,
            "message": message,
            "estimated_cost": estimated_cost,
            "budget": budget,
            "ratio": round(ratio, 2),
        }


# ── Singleton ───────────────────────────────────────────────────────────
_estimator: Optional[CostEstimator] = None


def get_cost_estimator() -> CostEstimator:
    global _estimator
    if _estimator is None:
        _estimator = CostEstimator()
    return _estimator
