"""
DevOps Butler - Master Planner Agent
The brain that decides what to deploy and how.
Uses: Decision Engine → RAG → Claude Sonnet 4.6 → Plan Validator → Cost Estimator
"""

import json
import logging
from typing import Dict, Any

from agents.base_agent import BaseAgent, trace_operation
from agents.master_planner.decision_engine import DecisionEngine
from agents.master_planner.rag import get_rag_layer
from agents.master_planner.plan_validator import PlanValidator
from agents.master_planner.prompts import (
    MASTER_PLANNER_SYSTEM,
    PLAN_GENERATION_PROMPT,
)
from core.state import ButlerState
from config.logging_config import get_logger
from config.settings import get_settings

logger = get_logger("master_planner")


class MasterPlannerAgent(BaseAgent):
    """
    Agent 2: Master Planner (The Brain)
    
    Pipeline:
        1. Decision Engine — rule-based routing of code analysis to DevOps skills
        2. RAG Query — retrieve relevant failure stories / best practices
        3. Claude Sonnet 4.6 — generate detailed deployment plan with infra code
        4. Cost Estimation — estimate monthly cost of planned resources
        5. Plan Validation — validate the plan for errors before execution
        6. User Approval — if cost > threshold, pause for user approval
    """

    def __init__(self):
        super().__init__(agent_name="master_planner")
        self.decision_engine = DecisionEngine()
        self.plan_validator = PlanValidator()

    @trace_operation("create_deployment_plan")
    def process(self, state: ButlerState) -> ButlerState:
        trace_id = state.get("trace_id", "no-trace")
        analysis = state.get("code_analysis", {})
        user_input = state.get("user_input", "")
        settings = get_settings()

        if not analysis:
            return self._add_error(state, "PLANNING_ERROR", "No code analysis available")

        # ── Step 1: Decision Engine ─────────────────────────────────
        logger.info("Running decision engine...", extra={"trace_id": trace_id})
        decision = self.decision_engine.decide(analysis, trace_id=trace_id)

        # ── Step 2: RAG Query ───────────────────────────────────────
        rag_context = self._get_rag_context(analysis, decision, trace_id)

        # ── Step 3: Generate Plan via Claude Sonnet ─────────────────
        logger.info("Generating deployment plan via Claude...", extra={"trace_id": trace_id})
        plan = self._generate_plan(analysis, decision, rag_context, user_input, trace_id)

        if not plan:
            return self._add_error(state, "PLANNING_ERROR", "Failed to generate deployment plan")

        # ── Step 4: Cost Estimation ─────────────────────────────────
        cost_result = self._estimate_costs(plan, trace_id)
        plan["estimated_cost_monthly"] = cost_result.get("total_monthly_usd", 0)
        plan["cost_breakdown"] = cost_result.get("breakdown", [])

        # ── Step 5: Validate Plan ───────────────────────────────────
        validation = self.plan_validator.validate(
            plan, budget=settings.monthly_budget_usd, trace_id=trace_id
        )
        plan["validation_result"] = validation

        if not validation["is_valid"]:
            logger.warning(
                f"Plan validation failed: {validation['errors']}",
                extra={"trace_id": trace_id}
            )
            # Try to self-correct once by regenerating
            plan = self._attempt_correction(plan, validation, trace_id)

        # ── Step 6: Check if user approval needed ───────────────────
        budget_check = self._check_budget_approval(
            plan.get("estimated_cost_monthly", 0),
            settings.monthly_budget_usd,
        )
        plan["requires_user_approval"] = budget_check["needs_approval"]

        # ── Write to state ──────────────────────────────────────────
        state["deployment_plan"] = {
            "plan_id": f"plan-{trace_id}",
            "devops_skills_needed": decision.get("skills_needed", []),
            "infrastructure": plan.get("resources", []),
            "tasks": plan.get("steps", plan.get("tasks", [])),
            "generated_files": plan.get("generated_files", {}),
            "estimated_cost_monthly": plan.get("estimated_cost_monthly", 0),
            "cost_breakdown": plan.get("cost_breakdown", []),
            "requires_user_approval": plan.get("requires_user_approval", False),
            "rag_context_used": [r.get("source", "") for r in rag_context] if isinstance(rag_context, list) else [],
            "validation_result": plan.get("validation_result", {}),
            "docker_config": plan.get("docker_config", {}),
            "kubernetes_config": plan.get("kubernetes_config", {}),
            "cicd_config": plan.get("cicd_config", {}),
        }

        if plan.get("requires_user_approval"):
            state["requires_user_input"] = True
            state["user_message"] = self._format_approval_message(plan, cost_result)

        logger.info(
            f"Plan created: strategy={plan.get('strategy', 'unknown')}, "
            f"cost=${plan.get('estimated_cost_monthly', 0):.2f}/month, "
            f"approval={'required' if plan.get('requires_user_approval') else 'auto'}",
            extra={"trace_id": trace_id}
        )

        return state

    def _get_rag_context(
        self,
        analysis: Dict[str, Any],
        decision: Dict[str, Any],
        trace_id: str,
    ) -> list:
        """Query RAG knowledge base for relevant context."""
        try:
            rag = get_rag_layer()
            
            frameworks = ", ".join(analysis.get("frameworks", ["application"]))
            databases = ", ".join(analysis.get("databases", []))
            strategy = decision.get("strategy", "deployment")

            query = (
                f"{frameworks} {strategy} deployment best practices"
                f"{' with ' + databases if databases else ''}"
            )

            results = rag.query(query, top_k=5, trace_id=trace_id)
            logger.info(
                f"RAG returned {len(results)} relevant documents",
                extra={"trace_id": trace_id}
            )
            return results

        except Exception as e:
            logger.warning(
                f"RAG query failed (proceeding without context): {e}",
                extra={"trace_id": trace_id}
            )
            return []

    def _generate_plan(
        self,
        analysis: Dict[str, Any],
        decision: Dict[str, Any],
        rag_context: list,
        user_input: str,
        trace_id: str,
    ) -> Dict[str, Any]:
        """Generate deployment plan via Claude Sonnet 4.6."""
        from generators.bedrock_client import get_bedrock_client
        settings = get_settings()

        # Format RAG context
        rag_text = ""
        if rag_context:
            for doc in rag_context:
                rag_text += f"\n### {doc.get('title', 'Document')}\n{doc.get('text', '')}\n"
        else:
            rag_text = "No specific knowledge available — use general DevOps best practices."

        # Format code analysis for prompt
        analysis_summary = json.dumps({
            "languages": analysis.get("languages", []),
            "frameworks": analysis.get("frameworks", []),
            "databases": analysis.get("databases", []),
            "services": analysis.get("services", []),
            "has_dockerfile": analysis.get("has_dockerfile"),
            "has_kubernetes": analysis.get("has_kubernetes"),
            "has_cicd": analysis.get("has_cicd"),
            "has_terraform": analysis.get("has_terraform"),
            "microservices": analysis.get("microservices_detected"),
            "entry_points": analysis.get("entry_points", [])[:5],
        }, indent=2)

        prompt = PLAN_GENERATION_PROMPT.format(
            code_analysis=analysis_summary,
            strategy=decision.get("strategy", "unknown"),
            skills_needed=", ".join(decision.get("skills_needed", [])),
            aws_services=", ".join(decision.get("aws_services", [])),
            tasks=json.dumps(decision.get("tasks", []), indent=2),
            generation_needed=json.dumps(decision.get("generation_needed", {})),
            rag_context=rag_text,
            budget=settings.monthly_budget_usd,
            user_instructions=user_input or "Deploy this application.",
        )

        try:
            client = get_bedrock_client()
            response = client.invoke_smart(
                prompt=prompt,
                system_prompt=MASTER_PLANNER_SYSTEM,
                complexity="high",
                max_tokens=4096,
                trace_id=trace_id,
            )

            # Parse JSON response
            plan = self._parse_plan_response(response, trace_id)
            return plan

        except Exception as e:
            logger.error(f"Plan generation failed: {e}", extra={"trace_id": trace_id})
            # Return a minimal fallback plan based on decision engine
            return self._create_fallback_plan(analysis, decision)

    def _parse_plan_response(self, response: str, trace_id: str) -> Dict[str, Any]:
        """Parse LLM response into structured plan dict."""
        try:
            # Try to extract JSON from response
            # Handle cases where LLM wraps JSON in markdown code blocks
            json_text = response
            if "```json" in response:
                json_text = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                json_text = response.split("```")[1].split("```")[0]

            return json.loads(json_text)
        except (json.JSONDecodeError, IndexError) as e:
            logger.warning(
                f"Failed to parse plan JSON, attempting repair: {e}",
                extra={"trace_id": trace_id}
            )
            # Try to extract any JSON-like structure
            try:
                # Find first { and last }
                start = response.index("{")
                end = response.rindex("}") + 1
                return json.loads(response[start:end])
            except (ValueError, json.JSONDecodeError):
                logger.error("Cannot parse plan response at all", extra={"trace_id": trace_id})
                return {}

    def _create_fallback_plan(
        self,
        analysis: Dict[str, Any],
        decision: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Create a minimal plan from decision engine when LLM fails."""
        return {
            "strategy": decision.get("strategy", "ecs_fargate"),
            "plan_summary": "Fallback plan based on rule engine (LLM generation failed)",
            "steps": decision.get("tasks", []),
            "resources": [],
            "generated_files": {},
            "estimated_monthly_cost_usd": 30.0,
        }

    def _estimate_costs(self, plan: Dict[str, Any], trace_id: str) -> Dict[str, Any]:
        """Estimate deployment costs."""
        from generators.cost_estimator import get_cost_estimator
        
        resources = plan.get("resources", [])
        if not resources:
            return {"total_monthly_usd": 0, "breakdown": []}
        
        estimator = get_cost_estimator()
        return estimator.estimate_plan_cost(resources, trace_id=trace_id)

    def _check_budget_approval(
        self,
        estimated_cost: float,
        budget: float,
    ) -> Dict[str, Any]:
        """Determine if user approval is needed based on cost."""
        if estimated_cost <= 0:
            return {"needs_approval": False, "reason": "No cost estimated"}
        
        ratio = estimated_cost / budget if budget > 0 else 1.0
        
        if ratio > 0.7:
            return {
                "needs_approval": True,
                "reason": f"Cost ${estimated_cost:.2f} is >{int(ratio*100)}% of budget",
            }
        return {
            "needs_approval": False,
            "reason": f"Cost ${estimated_cost:.2f} is within auto-approve threshold",
        }

    def _attempt_correction(
        self,
        plan: Dict[str, Any],
        validation: Dict[str, Any],
        trace_id: str,
    ) -> Dict[str, Any]:
        """Attempt to self-correct a failed plan validation."""
        logger.info("Attempting plan self-correction...", extra={"trace_id": trace_id})
        # For now, just log the validation errors and proceed
        # In a production system, we'd re-prompt Claude with the errors
        plan["validation_result"] = validation
        return plan

    def _format_approval_message(
        self,
        plan: Dict[str, Any],
        cost_result: Dict[str, Any],
    ) -> str:
        """Format a user-facing approval request."""
        cost = plan.get("estimated_cost_monthly", 0)
        strategy = plan.get("strategy", "unknown")
        steps = plan.get("steps", plan.get("tasks", []))

        lines = [
            "🔍 **Deployment Plan Ready — Approval Required**",
            "",
            f"**Strategy:** {strategy}",
            f"**Estimated Cost:** ${cost:.2f}/month",
            f"**Steps:** {len(steps)}",
            "",
        ]

        # Cost breakdown
        if cost_result.get("breakdown"):
            lines.append("**Cost Breakdown:**")
            for item in cost_result["breakdown"]:
                lines.append(f"  • {item.get('service', '?')}: ${item.get('cost', 0):.2f} ({item.get('details', '')})")
            lines.append("")

        lines.append("Approve this plan to proceed with deployment? (yes/no)")
        return "\n".join(lines)
