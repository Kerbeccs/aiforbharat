"""
DevOps Butler - Executor Agent
LangGraph node that routes deployment tasks to appropriate sub-executors.
Handles: terminal, API, Terraform, kubectl, Docker, and browser delegation.
"""

import os
import logging
from typing import Dict, Any, List

from agents.base_agent import BaseAgent, trace_operation
from agents.executor.terminal import TerminalExecutor
from agents.executor.aws_client import get_aws_client
from agents.executor.terraform import TerraformRunner
from agents.executor.kubectl import KubectlRunner
from agents.executor.rollback import RollbackManager
from core.state import ButlerState, ExecutionResult
from config.logging_config import get_logger
from config.settings import get_settings

logger = get_logger("executor")


class ExecutorAgent(BaseAgent):
    """
    Agent 3: Executor
    
    Routes deployment tasks from the Master Planner to sub-executors:
    - Terminal: shell commands (docker build, git, etc.)
    - API: AWS API calls via boto3
    - Terraform: infrastructure provisioning
    - Kubectl: Kubernetes operations
    - Browser: delegated to Browser Agent (via state)
    
    Tracks all created resources for rollback support.
    """

    def __init__(self):
        super().__init__(agent_name="executor")
        self.terminal = TerminalExecutor()
        self.terraform = TerraformRunner()
        self.kubectl = KubectlRunner()
        self.rollback_manager = RollbackManager()

    @trace_operation("execute_tasks")
    def process(self, state: ButlerState) -> ButlerState:
        trace_id = state.get("trace_id", "no-trace")
        plan = state.get("deployment_plan", {})
        tasks = plan.get("tasks", [])

        if not tasks:
            logger.warning("No tasks to execute", extra={"trace_id": trace_id})
            return state

        logger.info(
            f"Executing {len(tasks)} tasks",
            extra={"trace_id": trace_id}
        )

        execution_results: List[ExecutionResult] = []
        browser_tasks = state.get("browser_tasks", [])
        generated_files = plan.get("generated_files", {})

        # Write any generated files first
        if generated_files:
            self._write_generated_files(
                state.get("codebase_path", "."),
                generated_files,
                trace_id,
            )

        for i, task in enumerate(tasks):
            task_type = task.get("type", "terminal")
            task_desc = task.get("description", f"Task {i + 1}")

            logger.info(
                f"Task {i + 1}/{len(tasks)}: [{task_type}] {task_desc}",
                extra={"trace_id": trace_id}
            )

            try:
                if task_type in ("terminal", "execution"):
                    result = self._execute_terminal(task, state, trace_id)
                elif task_type == "api":
                    result = self._execute_api(task, state, trace_id)
                elif task_type in ("terraform", "infrastructure"):
                    result = self._execute_terraform(task, state, trace_id)
                elif task_type in ("kubectl", "kubernetes"):
                    result = self._execute_kubectl(task, state, trace_id)
                elif task_type in ("generate", "docker", "cicd", "monitoring", "configuration"):
                    result = self._execute_generate(task, state, trace_id)
                elif task_type == "browser":
                    # Delegate to Browser Agent
                    browser_tasks.append({
                        "task_description": task_desc,
                        "status": "pending",
                        "screenshots": [],
                        "actions_taken": [],
                    })
                    result: ExecutionResult = {
                        "task_id": task.get("id", f"task-{i}"),
                        "task_type": "browser",
                        "status": "delegated",
                        "output": "Delegated to Browser Agent",
                        "duration_ms": 0,
                    }
                elif task_type == "monitoring":
                    # Skip — handled by Monitor Agent
                    result: ExecutionResult = {
                        "task_id": task.get("id", f"task-{i}"),
                        "task_type": "monitoring",
                        "status": "skipped",
                        "output": "Will be handled by Monitor Agent",
                        "duration_ms": 0,
                    }
                else:
                    result: ExecutionResult = {
                        "task_id": task.get("id", f"task-{i}"),
                        "task_type": task_type,
                        "status": "skipped",
                        "output": f"Unknown task type: {task_type}",
                        "duration_ms": 0,
                    }

                execution_results.append(result)

                # Check for failure
                if result.get("status") == "failed":
                    logger.error(
                        f"Task failed: {task_desc}",
                        extra={"trace_id": trace_id}
                    )
                    state["should_rollback"] = True
                    break

            except Exception as e:
                logger.error(
                    f"Task exception: {str(e)}",
                    extra={"trace_id": trace_id},
                    exc_info=True,
                )
                execution_results.append({
                    "task_id": task.get("id", f"task-{i}"),
                    "task_type": task_type,
                    "status": "failed",
                    "output": "",
                    "error": str(e),
                    "duration_ms": 0,
                })
                state["should_rollback"] = True
                break

        state["execution_results"] = execution_results
        state["browser_tasks"] = browser_tasks

        # If rollback needed, execute it
        if state.get("should_rollback", False):
            rollback_results = self.rollback_manager.rollback(trace_id)
            state["rollback_results"] = rollback_results
        else:
            # Clear tracked resources on success
            self.rollback_manager.clear()

        return state

    def _execute_terminal(
        self,
        task: Dict[str, Any],
        state: ButlerState,
        trace_id: str,
    ) -> ExecutionResult:
        """Execute terminal commands. Generates scripts if tools aren't installed."""
        commands = task.get("commands", [])
        cwd = os.path.abspath(state.get("codebase_path", "."))

        if not commands:
            return {
                "task_id": task.get("id", ""),
                "task_type": "terminal",
                "status": "skipped",
                "output": "No commands specified",
                "duration_ms": 0,
            }

        # Check which CLI tools are available
        tool_checks = {"aws": False, "docker": False, "kubectl": False, "terraform": False}
        for tool in tool_checks:
            check = self.terminal.execute(f"{tool} --version", trace_id=trace_id)
            tool_checks[tool] = check["success"]

        # Determine which commands can run vs need to be scripted
        runnable = []
        scripted = []
        for cmd in commands:
            first_word = cmd.strip().split()[0] if cmd.strip() else ""
            if first_word in tool_checks and not tool_checks[first_word]:
                scripted.append(cmd)
            else:
                runnable.append(cmd)

        # Run whatever we can
        results = []
        if runnable:
            results = self.terminal.execute_sequence(
                runnable, cwd=cwd, stop_on_error=False, trace_id=trace_id
            )

        # Save scripted commands to a deploy script
        if scripted:
            script_dir = os.path.join(cwd, "deploy_scripts")
            os.makedirs(script_dir, exist_ok=True)
            task_id = task.get("id", "task")
            script_path = os.path.join(script_dir, f"{task_id}_commands.sh")
            with open(script_path, "w", encoding="utf-8") as f:
                f.write("#!/bin/bash\n")
                f.write(f"# DevOps Butler - {task.get('description', 'Deployment commands')}\n")
                f.write("# Run these commands after installing required CLI tools\n\n")
                for cmd in scripted:
                    f.write(cmd + "\n")

            missing_tools = [t for t, ok in tool_checks.items() if not ok and any(c.startswith(t) for c in scripted)]
            logger.warning(
                f"CLI tools not available ({', '.join(missing_tools)}), "
                f"commands saved to {script_path}",
                extra={"trace_id": trace_id}
            )

            # Add browser task as fallback
            browser_tasks = state.get("browser_tasks", [])
            browser_tasks.append({
                "task_description": (
                    f"Log into AWS Console and perform: {task.get('description', 'deployment task')}. "
                    f"Commands that need to run: {'; '.join(scripted[:3])}"
                ),
                "status": "pending",
                "screenshots": [],
                "actions_taken": [],
            })
            state["browser_tasks"] = browser_tasks

        all_output = []
        if results:
            all_output.append("\n".join(r.get("stdout", "") for r in results))
        if scripted:
            all_output.append(f"[{len(scripted)} commands saved to deploy script + browser task added]")

        all_success = all(r["success"] for r in results) if results else True
        total_ms = sum(r.get("duration_ms", 0) for r in results)

        return {
            "task_id": task.get("id", ""),
            "task_type": "terminal",
            "status": "success" if all_success else "failed",
            "output": "\n".join(all_output),
            "duration_ms": total_ms,
        }

    def _execute_api(
        self,
        task: Dict[str, Any],
        state: ButlerState,
        trace_id: str,
    ) -> ExecutionResult:
        """Execute AWS API calls."""
        aws = get_aws_client()
        api_action = task.get("api_action", "")

        try:
            if api_action == "create_ecr_repo":
                repo_name = task.get("repo_name", "devops-butler-app")
                result = aws.create_ecr_repository(repo_name, trace_id)
                self.rollback_manager.track("ecr_repo", repo_name, trace_id=trace_id)
                return {
                    "task_id": task.get("id", ""),
                    "task_type": "api",
                    "status": "success",
                    "output": f"ECR repo created: {result.get('repository_uri', '')}",
                    "resources_created": [{"type": "ecr", "id": repo_name, "name": repo_name}],
                    "duration_ms": 0,
                }

            elif api_action == "create_s3_bucket":
                bucket = task.get("bucket_name", "")
                result = aws.create_s3_bucket(bucket, trace_id)
                self.rollback_manager.track("s3_bucket", bucket, trace_id=trace_id)
                return {
                    "task_id": task.get("id", ""),
                    "task_type": "api",
                    "status": "success",
                    "output": f"S3 bucket created: {bucket}",
                    "resources_created": [{"type": "s3", "id": bucket, "name": bucket}],
                    "duration_ms": 0,
                }

            else:
                return {
                    "task_id": task.get("id", ""),
                    "task_type": "api",
                    "status": "skipped",
                    "output": f"Unknown API action: {api_action}",
                    "duration_ms": 0,
                }

        except Exception as e:
            return {
                "task_id": task.get("id", ""),
                "task_type": "api",
                "status": "failed",
                "output": "",
                "error": str(e),
                "duration_ms": 0,
            }

    def _execute_terraform(
        self,
        task: Dict[str, Any],
        state: ButlerState,
        trace_id: str,
    ) -> ExecutionResult:
        """Execute Terraform operations — generate files via LLM, run if CLI available, browser fallback."""
        from generators.bedrock_client import get_bedrock_client
        import json as _json

        codebase = os.path.abspath(state.get("codebase_path", "."))
        tf_dir = os.path.join(codebase, "terraform")
        os.makedirs(tf_dir, exist_ok=True)
        description = task.get("description", "Create Terraform configuration")
        analysis = state.get("code_analysis", {})
        plan = state.get("deployment_plan", {})

        # Step 1: Get or generate .tf files
        tf_files = {}
        for filename, content in plan.get("generated_files", {}).items():
            if filename.endswith(".tf"):
                tf_files[filename] = content

        if not tf_files:
            # Generate via LLM
            try:
                client = get_bedrock_client()
                frameworks = ", ".join(analysis.get("frameworks", [])) or "Python"
                strategy = plan.get("strategy", "containerized")

                prompt = f"""Generate Terraform configuration for: {description}

Application: {frameworks} application using {strategy} strategy on AWS.
Region: us-east-1

Generate complete, production-ready Terraform files. Respond ONLY with JSON:
{{
  "files": {{
    "main.tf": "terraform content here",
    "variables.tf": "variables content here",
    "outputs.tf": "outputs content here"
  }}
}}

Include: AWS provider, VPC with public/private subnets, security groups, and any resources needed.
Use terraform required_providers block."""

                response = client.invoke_smart(
                    prompt=prompt,
                    system_prompt="You are a Terraform expert. Generate valid HCL configuration files. Respond ONLY with JSON.",
                    complexity="low",
                    max_tokens=4096,
                    trace_id=trace_id,
                )

                import re
                json_match = re.search(r'\{[\s\S]*\}', response)
                if json_match:
                    result = _json.loads(json_match.group())
                    tf_files = result.get("files", {})
            except Exception as e:
                logger.warning(f"Terraform file generation failed: {e}", extra={"trace_id": trace_id})

        # Write .tf files
        if tf_files:
            for filename, content in tf_files.items():
                filepath = os.path.join(tf_dir, filename)
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                logger.info(f"Wrote terraform file: {filename}", extra={"trace_id": trace_id})

        # Step 2: Check if terraform CLI is installed
        check = self.terminal.execute("terraform version", trace_id=trace_id)
        if check["success"]:
            # Run terraform
            try:
                results = self.terraform.full_lifecycle(
                    working_dir=tf_dir,
                    tf_files=None,  # Already written
                    trace_id=trace_id,
                )
                self.rollback_manager.track(
                    "terraform", tf_dir, name="infrastructure",
                    cleanup_args={"working_dir": tf_dir},
                    trace_id=trace_id,
                )
                return {
                    "task_id": task.get("id", ""),
                    "task_type": "terraform",
                    "status": "success",
                    "output": "Terraform apply completed",
                    "duration_ms": 0,
                }
            except Exception as e:
                return {
                    "task_id": task.get("id", ""),
                    "task_type": "terraform",
                    "status": "failed",
                    "output": "", "error": str(e),
                    "duration_ms": 0,
                }
        else:
            # CLI not available — add browser task for AWS Console fallback
            browser_tasks = state.get("browser_tasks", [])
            browser_tasks.append({
                "task_description": (
                    f"Log into AWS Console. Navigate to CloudFormation. "
                    f"Create a new stack using the Terraform-equivalent resources: {description}. "
                    f"Create VPC, subnets, security groups as needed."
                ),
                "status": "pending",
                "screenshots": [],
                "actions_taken": [],
            })
            state["browser_tasks"] = browser_tasks

            file_list = ", ".join(tf_files.keys()) if tf_files else "none"
            logger.warning(
                f"Terraform CLI not installed — {len(tf_files)} files generated, browser task added",
                extra={"trace_id": trace_id}
            )
            return {
                "task_id": task.get("id", ""),
                "task_type": "terraform",
                "status": "success",
                "output": f"Generated terraform files ({file_list}) in {tf_dir}. Browser agent will deploy via AWS Console.",
                "duration_ms": 0,
            }

    def _execute_kubectl(
        self,
        task: Dict[str, Any],
        state: ButlerState,
        trace_id: str,
    ) -> ExecutionResult:
        """Execute kubectl operations — generate manifests via LLM, run if CLI available, browser fallback."""
        from generators.bedrock_client import get_bedrock_client
        import json as _json

        codebase = os.path.abspath(state.get("codebase_path", "."))
        k8s_dir = os.path.join(codebase, "k8s")
        os.makedirs(k8s_dir, exist_ok=True)
        description = task.get("description", "Create Kubernetes manifests")
        analysis = state.get("code_analysis", {})
        plan = state.get("deployment_plan", {})

        # Step 1: Get or generate manifests
        manifests = task.get("manifests", {})
        if not manifests:
            try:
                client = get_bedrock_client()
                frameworks = ", ".join(analysis.get("frameworks", [])) or "Python"
                entry_points = analysis.get("entry_points", [])
                entry_point = entry_points[0] if entry_points else "app.py"

                prompt = f"""Generate Kubernetes manifests for: {description}

Application: {frameworks} app, main file: {entry_point}, port 5000

Generate complete YAML manifests. Respond ONLY with JSON:
{{
  "files": {{
    "deployment.yaml": "yaml content",
    "service.yaml": "yaml content"
  }}
}}

Include: Deployment with 2 replicas, Service with LoadBalancer, proper labels/selectors.
Use image placeholder: {{IMAGE_URI}}"""

                response = client.invoke_smart(
                    prompt=prompt,
                    system_prompt="You are a Kubernetes expert. Generate valid YAML manifests. Respond ONLY with JSON.",
                    complexity="low",
                    max_tokens=4096,
                    trace_id=trace_id,
                )

                import re
                json_match = re.search(r'\{[\s\S]*\}', response)
                if json_match:
                    result = _json.loads(json_match.group())
                    manifests = result.get("files", {})
            except Exception as e:
                logger.warning(f"K8s manifest generation failed: {e}", extra={"trace_id": trace_id})

        # Write manifest files
        written_files = []
        if manifests:
            for filename, content in manifests.items():
                filepath = os.path.join(k8s_dir, filename)
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                written_files.append(filepath)
                logger.info(f"Wrote K8s manifest: {filename}", extra={"trace_id": trace_id})

        # Step 2: Check if kubectl is installed
        check = self.terminal.execute("kubectl version --client", trace_id=trace_id)
        if check["success"]:
            try:
                for path in written_files:
                    self.kubectl.apply(path, trace_id)
                return {
                    "task_id": task.get("id", ""),
                    "task_type": "kubectl",
                    "status": "success",
                    "output": f"Applied {len(written_files)} K8s manifests",
                    "duration_ms": 0,
                }
            except Exception as e:
                return {
                    "task_id": task.get("id", ""),
                    "task_type": "kubectl",
                    "status": "failed",
                    "error": str(e), "output": "",
                    "duration_ms": 0,
                }
        else:
            # CLI not available — add browser task
            browser_tasks = state.get("browser_tasks", [])
            browser_tasks.append({
                "task_description": (
                    f"Log into AWS Console. Navigate to EKS. "
                    f"Select the cluster. Go to workloads and deploy: {description}."
                ),
                "status": "pending",
                "screenshots": [],
                "actions_taken": [],
            })
            state["browser_tasks"] = browser_tasks

            logger.warning(
                f"kubectl not installed — {len(written_files)} manifests generated, browser task added",
                extra={"trace_id": trace_id}
            )
            return {
                "task_id": task.get("id", ""),
                "task_type": "kubectl",
                "status": "success",
                "output": f"Generated {len(written_files)} K8s manifests in {k8s_dir}. Browser agent will deploy via AWS Console.",
                "duration_ms": 0,
            }

    def _execute_generate(
        self,
        task: Dict[str, Any],
        state: ButlerState,
        trace_id: str,
    ) -> ExecutionResult:
        """Generate deployment files (Dockerfiles, configs, CI/CD, etc.) using LLM."""
        from pathlib import Path
        from generators.bedrock_client import get_bedrock_client

        codebase = os.path.abspath(state.get("codebase_path", "."))
        description = task.get("description", "Generate deployment files")
        analysis = state.get("code_analysis", {})
        plan = state.get("deployment_plan", {})

        # Check if files were already generated in the plan
        generated_files = plan.get("generated_files", {})
        if generated_files:
            self._write_generated_files(codebase, generated_files, trace_id)
            return {
                "task_id": task.get("id", ""),
                "task_type": "generate",
                "status": "success",
                "output": f"Generated {len(generated_files)} files: {', '.join(generated_files.keys())}",
                "duration_ms": 0,
            }

        # Generate files via LLM
        try:
            client = get_bedrock_client()

            # Build context for file generation
            frameworks = ", ".join(analysis.get("frameworks", [])) or "Python"
            languages = ", ".join([l.get("name", "") for l in analysis.get("languages", [])]) or "Python"
            strategy = plan.get("strategy", "containerized")
            entry_points = analysis.get("entry_points", [])
            entry_point = entry_points[0] if entry_points else "app.py"

            prompt = f"""Generate the deployment files for this task: {description}

Code Analysis:
- Languages: {languages}
- Frameworks: {frameworks}
- Strategy: {strategy}
- Main file: {entry_point}

Generate the file content. Respond ONLY with JSON in this exact format:
{{
  "files": {{
    "filename1": "file content here",
    "filename2": "file content here"
  }}
}}

Rules:
- For Dockerfiles: use Python slim images, install requirements, expose correct ports
- For K8s manifests: include deployment + service YAML
- For Terraform: include provider, VPC, subnets, security groups
- For CI/CD: use GitHub Actions with build, test, deploy stages
- Make files production-ready and complete
"""
            response = client.invoke_smart(
                prompt=prompt,
                system_prompt="You are a DevOps engineer. Generate deployment configuration files. Respond ONLY with valid JSON.",
                complexity="low",
                max_tokens=4096,
                trace_id=trace_id,
            )

            # Parse response
            import re
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                import json
                result = json.loads(json_match.group())
                files = result.get("files", {})
            else:
                files = {}

            if files:
                self._write_generated_files(codebase, files, trace_id)
                return {
                    "task_id": task.get("id", ""),
                    "task_type": "generate",
                    "status": "success",
                    "output": f"Generated {len(files)} files: {', '.join(files.keys())}",
                    "resources_created": [{"type": "file", "id": f, "name": f} for f in files],
                    "duration_ms": 0,
                }
            else:
                logger.warning(
                    f"LLM did not produce files for: {description}",
                    extra={"trace_id": trace_id}
                )
                return {
                    "task_id": task.get("id", ""),
                    "task_type": "generate",
                    "status": "success",
                    "output": f"Task noted: {description} (no files generated)",
                    "duration_ms": 0,
                }

        except Exception as e:
            logger.error(f"File generation failed: {e}", extra={"trace_id": trace_id})
            return {
                "task_id": task.get("id", ""),
                "task_type": "generate",
                "status": "success",
                "output": f"Task noted: {description} (generation error: {str(e)[:80]})",
                "duration_ms": 0,
            }

    def _write_generated_files(
        self,
        codebase_path: str,
        files: Dict[str, str],
        trace_id: str,
    ) -> None:
        """Write generated files (Dockerfiles, configs, etc.) to the codebase."""
        from pathlib import Path

        for filename, content in files.items():
            filepath = os.path.join(codebase_path, filename)
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            Path(filepath).write_text(content, encoding="utf-8")
            logger.info(
                f"Wrote generated file: {filename}",
                extra={"trace_id": trace_id}
            )
