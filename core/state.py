"""
DevOps Butler - LangGraph Shared State Schema
This is the single source of truth passed between all agents.
Uses TypedDict for LangGraph compatibility.
"""

from typing import TypedDict, Optional, Any
from dataclasses import dataclass, field


class CodeAnalysis(TypedDict, total=False):
    """Output from Code Analyzer Agent."""
    languages: list[dict]           # [{"name": "python", "percentage": 80.0, "files": 12}]
    frameworks: list[str]           # ["flask", "react", "sqlalchemy"]
    services: list[dict]            # [{"name": "backend", "entry_point": "app.py", "type": "api"}]
    databases: list[str]            # ["postgresql", "redis"]
    dependencies: dict              # {"python": ["flask", "sqlalchemy"], "node": ["react", "axios"]}
    dependency_files: list[str]     # ["requirements.txt", "package.json"]
    has_dockerfile: bool
    has_docker_compose: bool
    has_kubernetes: bool
    has_cicd: bool                  # .github/workflows, Jenkinsfile, etc.
    has_terraform: bool
    microservices_detected: bool
    entry_points: list[dict]        # [{"file": "app.py", "type": "flask", "line": 42}]
    project_structure: dict         # {"total_files": 50, "directories": [...]}
    raw_summary: str                # LLM-generated natural language summary


class DeploymentPlan(TypedDict, total=False):
    """Output from Master Planner Agent."""
    plan_id: str                    # Unique plan identifier
    devops_skills_needed: list[str] # ["docker", "kubernetes", "terraform", "cicd"]
    infrastructure: dict            # Terraform/CloudFormation specs
    docker_config: dict             # Dockerfiles, compose files
    kubernetes_config: dict         # K8s manifests
    cicd_config: dict               # Pipeline definitions
    estimated_cost_monthly: float   # Estimated monthly cost in USD
    cost_breakdown: list[dict]      # [{"service": "EC2", "cost": 25.0}]
    requires_user_approval: bool    # True if cost > auto_approve threshold
    tasks: list[dict]               # Ordered list of execution tasks
    generated_files: dict           # {"Dockerfile": "...", "main.tf": "..."}
    rag_context_used: list[str]     # References to knowledge docs used
    validation_result: dict         # From plan_validator


class ExecutionResult(TypedDict, total=False):
    """Output from Executor Agent."""
    task_id: str
    task_type: str                  # "terminal", "api", "terraform", "kubectl", "browser"
    status: str                     # "success", "failed", "skipped", "rolled_back"
    output: str                     # Command output / API response
    error: Optional[str]
    duration_ms: float
    resources_created: list[dict]   # [{"type": "ec2", "id": "i-xxx", "name": "..."}]


class BrowserTask(TypedDict, total=False):
    """Output from Browser Agent."""
    task_description: str
    status: str                     # "success", "failed", "fallback_cli", "manual_required"
    screenshots: list[str]          # Paths to captured screenshots
    actions_taken: list[str]        # ["navigated to EC2", "clicked Launch", ...]
    error: Optional[str]


class MonitoringStatus(TypedDict, total=False):
    """Output from Monitor Agent."""
    health_checks: list[dict]       # [{"resource": "ec2-xxx", "status": "healthy"}]
    current_cost: float             # Current month spend
    cost_forecast: float            # Predicted month-end cost
    alerts: list[dict]              # [{"severity": "warning", "message": "..."}]
    recommendations: list[str]


class ButlerState(TypedDict, total=False):
    """
    The master state object passed through the LangGraph pipeline.
    Every agent reads from and writes to this state.
    """
    # ── Trace & Meta ────────────────────────────────────────────────
    trace_id: str                   # Correlation ID for this run
    operation: str                  # e.g., "deploy", "analyze", "plan"
    user_input: str                 # Raw user command
    codebase_path: str              # Path to the codebase being deployed
    
    # ── Agent Outputs ───────────────────────────────────────────────
    code_analysis: CodeAnalysis
    deployment_plan: DeploymentPlan
    execution_results: list[ExecutionResult]
    browser_tasks: list[BrowserTask]
    monitoring_status: MonitoringStatus
    
    # ── User Interaction ────────────────────────────────────────────
    user_approved: bool             # Whether user approved the plan
    user_message: str               # Message to show user
    requires_user_input: bool       # Whether we need user interaction
    credentials_needed: list[str]   # ["aws_console_password", "mfa_code"]
    
    # ── Flow Control ────────────────────────────────────────────────
    current_agent: str              # Which agent is currently running
    errors: list[dict]              # Accumulated errors [{error_code, message, agent}]
    should_rollback: bool           # Whether to trigger rollback
    rollback_results: list[dict]    # Results of rollback operations
    
    # ── Final Report ────────────────────────────────────────────────
    final_report: dict              # Summary shown to user at end
    deployment_url: Optional[str]   # URL of deployed application (if applicable)
