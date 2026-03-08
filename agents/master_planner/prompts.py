"""
DevOps Butler - LLM Prompt Templates
Structured prompts for Claude Sonnet 4.6 planning tasks.
"""

# ═══════════════════════════════════════════════════════════════════════
# SYSTEM PROMPTS
# ═══════════════════════════════════════════════════════════════════════

MASTER_PLANNER_SYSTEM = """You are DevOps Butler's Master Planner — an expert DevOps engineer AI.

Your job is to create a complete, executable deployment plan for the user's application.

RULES:
1. Always prefer cost-efficient solutions (user has $100/month budget).
2. Use the simplest architecture that works (don't over-engineer).
3. Generate actual, runnable infrastructure code (Terraform, K8s manifests, Dockerfiles).
4. Consider security best practices (no hardcoded secrets, use IAM roles, least privilege).
5. Include rollback strategy for every step.
6. Estimate costs accurately.

DEPLOYMENT STRATEGIES (choose the simplest that fits):
- Single container on ECS Fargate: for simple apps (1 service, no K8s needed)
- EKS with K8s: for microservices (2+ services) or apps needing orchestration
- S3 + CloudFront: for static frontends (React, Vue, Angular builds)
- EC2 + Docker: for apps needing persistent storage or custom setups
- Lambda: for event-driven, stateless functions

RESPONSE FORMAT:
Always respond with valid JSON matching this schema:
{
    "strategy": "ecs_fargate | kubernetes_eks | s3_cloudfront | ec2_docker | lambda",
    "plan_summary": "Brief description of the deployment plan",
    "steps": [
        {
            "step_id": 1,
            "name": "Step name",
            "description": "What this step does",
            "type": "terraform | docker | kubectl | terminal | api | browser",
            "commands": ["command1", "command2"],
            "generated_files": {"filename": "file content"},
            "rollback": "How to undo this step",
            "estimated_time_minutes": 5
        }
    ],
    "resources": [
        {"type": "ec2|rds|eks|s3|alb|ecr|...", "instance_type": "t3.medium", "count": 1}
    ],
    "environment_variables": {"KEY": "description of what to set"},
    "security_considerations": ["..."],
    "estimated_monthly_cost_usd": 50.00
}
"""

# ═══════════════════════════════════════════════════════════════════════
# PLAN GENERATION PROMPT
# ═══════════════════════════════════════════════════════════════════════

PLAN_GENERATION_PROMPT = """Create a deployment plan for this application:

## Code Analysis
{code_analysis}

## Decision Engine Output
- Strategy: {strategy}
- Skills Needed: {skills_needed}
- AWS Services: {aws_services}
- Tasks Required: {tasks}
- Generation Needed: {generation_needed}

## Knowledge Context (from past deployments & best practices)
{rag_context}

## Budget
Maximum monthly cost: ${budget}/month

## User Instructions
{user_instructions}

Generate a complete, step-by-step deployment plan with all infrastructure code included.
Respond ONLY with valid JSON as specified in your system prompt.
"""

# ═══════════════════════════════════════════════════════════════════════
# DOCKERFILE GENERATION PROMPT (for Bedrock fallback)
# ═══════════════════════════════════════════════════════════════════════

DOCKERFILE_PROMPT = """Generate a production-ready Dockerfile for this application:

Framework: {framework}
Language: {language}
Dependencies: {dependencies}
Entry Point: {entry_point}

Requirements:
- Use multi-stage build if appropriate
- Use slim/alpine base images
- Set proper WORKDIR
- Copy dependency files first for layer caching
- Don't run as root if possible
- Expose the correct port

Output ONLY the Dockerfile content. No explanations.
"""

# ═══════════════════════════════════════════════════════════════════════
# TERRAFORM GENERATION PROMPT
# ═══════════════════════════════════════════════════════════════════════

TERRAFORM_PROMPT = """Generate Terraform configuration for deploying this infrastructure:

## Requirements
{requirements}

## AWS Services Needed
{aws_services}

## Strategy
{strategy}

## Region
{region}

Generate production-ready Terraform files. Include:
- provider.tf (AWS provider config)
- main.tf (primary resources)
- variables.tf (input variables with defaults)
- outputs.tf (important outputs like URLs, IPs)

Use these conventions:
- Tags: Project = "devops-butler", Environment = "production", ManagedBy = "terraform"
- Use data sources for existing resources (default VPC, etc.)
- Include security groups with least-privilege rules

Output as JSON: {{"provider.tf": "content", "main.tf": "content", ...}}
"""

# ═══════════════════════════════════════════════════════════════════════
# KUBERNETES MANIFEST PROMPT
# ═══════════════════════════════════════════════════════════════════════

K8S_MANIFEST_PROMPT = """Generate Kubernetes manifests for this application:

## Services
{services}

## Container Images
{images}

## Requirements
{requirements}

Generate:
- deployment.yaml for each service
- service.yaml for each service
- ingress.yaml if needed
- configmap.yaml for environment variables

Use these conventions:
- Namespace: devops-butler
- Resource limits: set appropriate CPU/memory
- Health checks (liveness + readiness probes)
- Rolling update strategy

Output as JSON: {{"deployment.yaml": "content", "service.yaml": "content", ...}}
"""

# ═══════════════════════════════════════════════════════════════════════
# CI/CD PIPELINE PROMPT
# ═══════════════════════════════════════════════════════════════════════

CICD_PROMPT = """Generate a GitHub Actions CI/CD pipeline for this application:

## Application
{application_details}

## Deployment Target
{deployment_target}

## Steps Required
1. Checkout code
2. Run tests (if test framework detected)
3. Build Docker image
4. Push to ECR
5. Deploy to {deployment_target}

Output ONLY the YAML content for .github/workflows/deploy.yml
"""
