"""
DevOps Butler - Decision Engine
Rule-based routing that maps code analysis results to required DevOps skills.
Determines which tools, services, and agents are needed for deployment.
"""

import logging
from typing import Dict, List, Any, Set

from core.state import CodeAnalysis
from config.logging_config import get_logger

logger = get_logger("decision_engine")


# ═══════════════════════════════════════════════════════════════════════
# DEPLOYMENT STRATEGY RULES
# ═══════════════════════════════════════════════════════════════════════

class DecisionEngine:
    """
    Rule-based engine that analyzes code analysis results and determines:
    - Which DevOps skills are needed (Docker, K8s, Terraform, CI/CD, etc.)
    - Deployment strategy (single container, ECS, EKS, serverless, etc.)
    - Required AWS services
    - What needs to be generated (Dockerfiles, manifests, Terraform)
    """

    def decide(
        self,
        analysis: CodeAnalysis,
        trace_id: str = "no-trace",
    ) -> Dict[str, Any]:
        """
        Main decision method. Takes code analysis, returns deployment decisions.
        """
        skills_needed: Set[str] = set()
        aws_services: Set[str] = set()
        tasks: List[Dict[str, Any]] = []
        generation_needed: Dict[str, bool] = {}
        strategy = "single_container"  # default

        frameworks = analysis.get("frameworks", [])
        databases = analysis.get("databases", [])
        is_microservice = analysis.get("microservices_detected", False)
        services = analysis.get("services", [])
        has_dockerfile = analysis.get("has_dockerfile", False)
        has_docker_compose = analysis.get("has_docker_compose", False)
        has_kubernetes = analysis.get("has_kubernetes", False)
        has_cicd = analysis.get("has_cicd", False)
        has_terraform = analysis.get("has_terraform", False)

        # ── Rule 1: Docker is almost always needed ──────────────────
        skills_needed.add("docker")
        if not has_dockerfile:
            generation_needed["dockerfile"] = True
            tasks.append({
                "id": "gen_dockerfile",
                "type": "generate",
                "description": "Generate Dockerfile(s)",
                "priority": 1,
            })

        # ── Rule 2: Microservices → Kubernetes ──────────────────────
        if is_microservice or len(services) > 1:
            strategy = "kubernetes_eks"
            skills_needed.update(["kubernetes", "container_orchestration"])
            aws_services.update(["EKS", "ECR", "ALB"])

            if not has_kubernetes:
                generation_needed["kubernetes_manifests"] = True
                tasks.append({
                    "id": "gen_k8s",
                    "type": "generate",
                    "description": "Generate Kubernetes manifests",
                    "priority": 2,
                })

            if not has_docker_compose:
                generation_needed["docker_compose"] = True

        # ── Rule 3: Single service → ECS or EC2 ────────────────────
        elif len(services) <= 1:
            # Check if it's a simple app
            is_frontend_only = all(
                fw in ("react", "vue", "angular", "nextjs")
                for fw in frameworks
            ) and frameworks
            
            if is_frontend_only:
                strategy = "s3_cloudfront"
                aws_services.update(["S3", "CloudFront"])
                skills_needed.add("static_hosting")
            else:
                strategy = "ecs_fargate"
                aws_services.update(["ECS", "ECR", "ALB"])
                skills_needed.add("container_orchestration")

        # ── Rule 4: Database → RDS/DynamoDB ─────────────────────────
        if databases:
            skills_needed.add("database_management")
            for db in databases:
                if db in ("postgresql", "mysql", "sqlite"):
                    aws_services.add("RDS")
                    tasks.append({
                        "id": f"setup_{db}",
                        "type": "infrastructure",
                        "description": f"Set up {db.upper()} on RDS",
                        "priority": 3,
                    })
                elif db == "mongodb":
                    aws_services.add("DocumentDB")
                elif db == "redis":
                    aws_services.add("ElastiCache")
                elif db == "dynamodb":
                    aws_services.add("DynamoDB")
                elif db == "elasticsearch":
                    aws_services.add("OpenSearch")

        # ── Rule 5: Infrastructure as Code ──────────────────────────
        if not has_terraform and aws_services:
            skills_needed.add("infrastructure_as_code")
            generation_needed["terraform"] = True
            tasks.append({
                "id": "gen_terraform",
                "type": "generate",
                "description": "Generate Terraform configuration",
                "priority": 2,
            })

        # ── Rule 6: CI/CD Pipeline ──────────────────────────────────
        if not has_cicd:
            skills_needed.add("cicd")
            generation_needed["cicd_pipeline"] = True
            tasks.append({
                "id": "gen_cicd",
                "type": "generate",
                "description": "Generate CI/CD pipeline (GitHub Actions)",
                "priority": 4,
            })

        # ── Rule 7: Networking ──────────────────────────────────────
        if strategy in ("kubernetes_eks", "ecs_fargate"):
            skills_needed.update(["networking", "security"])
            aws_services.update(["VPC", "SecurityGroup"])
            tasks.append({
                "id": "setup_networking",
                "type": "infrastructure",
                "description": "Configure VPC, subnets, and security groups",
                "priority": 1,
            })

        # ── Rule 8: Container Registry ──────────────────────────────
        if "docker" in skills_needed and strategy != "s3_cloudfront":
            aws_services.add("ECR")
            tasks.append({
                "id": "push_to_ecr",
                "type": "execution",
                "description": "Build and push Docker image(s) to ECR",
                "priority": 5,
            })

        # ── Rule 9: Monitoring (always) ─────────────────────────────
        skills_needed.add("monitoring")
        aws_services.add("CloudWatch")
        tasks.append({
            "id": "setup_monitoring",
            "type": "monitoring",
            "description": "Configure CloudWatch monitoring and alerts",
            "priority": 8,
        })

        # ── Sort tasks by priority ──────────────────────────────────
        tasks.sort(key=lambda t: t.get("priority", 99))

        result = {
            "strategy": strategy,
            "skills_needed": sorted(skills_needed),
            "aws_services": sorted(aws_services),
            "tasks": tasks,
            "generation_needed": generation_needed,
            "estimated_complexity": self._estimate_complexity(
                skills_needed, aws_services, is_microservice
            ),
        }

        logger.info(
            f"Decision: strategy={strategy}, "
            f"skills={len(skills_needed)}, services={len(aws_services)}, "
            f"tasks={len(tasks)}",
            extra={"trace_id": trace_id}
        )

        return result

    def _estimate_complexity(
        self,
        skills: Set[str],
        services: Set[str],
        is_microservice: bool,
    ) -> str:
        """Estimate deployment complexity."""
        score = len(skills) + len(services)
        if is_microservice:
            score += 5
        if "kubernetes" in skills:
            score += 3

        if score <= 5:
            return "low"
        elif score <= 10:
            return "medium"
        elif score <= 15:
            return "high"
        else:
            return "very_high"
