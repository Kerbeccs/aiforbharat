"""
DevOps Butler - LangGraph Orchestrator
Defines the state graph that wires all 5 agents together.
Flow: analyze → plan → (user_approve) → execute → (browser) → monitor → report
"""

import logging
from typing import Dict, Any, Literal

from langgraph.graph import StateGraph, END

from core.state import ButlerState
from core.trace import TraceContext
from config.logging_config import get_logger, setup_logging
from config.settings import get_settings

logger = get_logger("orchestrator")


def create_orchestrator() -> StateGraph:
    """
    Build the LangGraph state machine for DevOps Butler.
    
    Graph:
        analyze_code
            ↓
        create_plan
            ↓
        check_approval (conditional)
            ├─ approved → execute_tasks
            ├─ needs_input → wait_for_user
            └─ error → handle_error
        execute_tasks
            ↓
        check_browser_needed (conditional)
            ├─ yes → run_browser_tasks → monitor_deployment
            └─ no → monitor_deployment
        monitor_deployment
            ↓
        generate_report → END
    """
    from agents.code_analyzer.agent import CodeAnalyzerAgent
    from agents.master_planner.agent import MasterPlannerAgent
    from agents.executor.agent import ExecutorAgent
    from agents.browser_agent.agent import BrowserAgentNode
    from agents.monitor.agent import MonitorAgent

    # ── Instantiate agents ──────────────────────────────────────────
    code_analyzer = CodeAnalyzerAgent()
    master_planner = MasterPlannerAgent()
    executor = ExecutorAgent()
    browser_agent = BrowserAgentNode()
    monitor = MonitorAgent()

    # ── Build graph ─────────────────────────────────────────────────
    graph = StateGraph(ButlerState)

    # Add nodes
    graph.add_node("analyze_code", code_analyzer)
    graph.add_node("create_plan", master_planner)
    graph.add_node("execute_tasks", executor)
    graph.add_node("run_browser_tasks", browser_agent)
    graph.add_node("monitor_deployment", monitor)
    graph.add_node("generate_report", generate_report_node)
    graph.add_node("handle_error", handle_error_node)

    # ── Define edges ────────────────────────────────────────────────
    graph.set_entry_point("analyze_code")

    graph.add_edge("analyze_code", "create_plan")

    # After planning, check if user approval is needed
    graph.add_conditional_edges(
        "create_plan",
        route_after_plan,
        {
            "execute": "execute_tasks",
            "wait_for_user": END,  # Return to user for approval
            "error": "handle_error",
        },
    )

    # After execution, check if browser tasks are needed
    graph.add_conditional_edges(
        "execute_tasks",
        route_after_execution,
        {
            "browser": "run_browser_tasks",
            "monitor": "monitor_deployment",
            "rollback": "handle_error",
        },
    )

    graph.add_edge("run_browser_tasks", "monitor_deployment")
    graph.add_edge("monitor_deployment", "generate_report")
    graph.add_edge("generate_report", END)
    graph.add_edge("handle_error", END)

    return graph


def create_execution_graph() -> StateGraph:
    """
    Build a LangGraph that starts from execution (skips analyze+plan).
    Used when resuming after user approval.
    """
    from agents.executor.agent import ExecutorAgent
    from agents.browser_agent.agent import BrowserAgentNode
    from agents.monitor.agent import MonitorAgent

    executor = ExecutorAgent()
    browser_agent = BrowserAgentNode()
    monitor = MonitorAgent()

    graph = StateGraph(ButlerState)

    graph.add_node("execute_tasks", executor)
    graph.add_node("run_browser_tasks", browser_agent)
    graph.add_node("monitor_deployment", monitor)
    graph.add_node("generate_report", generate_report_node)
    graph.add_node("handle_error", handle_error_node)

    graph.set_entry_point("execute_tasks")

    graph.add_conditional_edges(
        "execute_tasks",
        route_after_execution,
        {
            "browser": "run_browser_tasks",
            "monitor": "monitor_deployment",
            "rollback": "handle_error",
        },
    )

    graph.add_edge("run_browser_tasks", "monitor_deployment")
    graph.add_edge("monitor_deployment", "generate_report")
    graph.add_edge("generate_report", END)
    graph.add_edge("handle_error", END)

    return graph


# ── Router Functions ────────────────────────────────────────────────────

def route_after_plan(state: ButlerState) -> str:
    """Decide what to do after planning."""
    errors = state.get("errors", [])
    if errors:
        return "error"

    plan = state.get("deployment_plan", {})
    if plan.get("requires_user_approval", False) and not state.get("user_approved", False):
        return "wait_for_user"

    return "execute"


def route_after_execution(state: ButlerState) -> str:
    """Decide what to do after execution."""
    if state.get("should_rollback", False):
        return "rollback"

    # Check if any tasks need browser
    browser_tasks = state.get("browser_tasks", [])
    pending_browser = [t for t in browser_tasks if t.get("status") == "pending"]
    if pending_browser:
        return "browser"

    return "monitor"


# ── Utility Nodes ───────────────────────────────────────────────────────

def generate_report_node(state: ButlerState) -> ButlerState:
    """Generate final deployment report."""
    trace_id = state.get("trace_id", "no-trace")
    logger.info("Generating final report", extra={"trace_id": trace_id})

    code_analysis = state.get("code_analysis", {})
    plan = state.get("deployment_plan", {})
    exec_results = state.get("execution_results", [])
    monitoring = state.get("monitoring_status", {})
    errors = state.get("errors", [])

    successful = [r for r in exec_results if r.get("status") == "success"]
    failed = [r for r in exec_results if r.get("status") == "failed"]

    report = {
        "trace_id": trace_id,
        "status": "success" if not failed and not errors else "partial" if successful else "failed",
        "summary": {
            "languages": [l.get("name") for l in code_analysis.get("languages", [])],
            "frameworks": code_analysis.get("frameworks", []),
            "skills_used": plan.get("devops_skills_needed", []),
            "tasks_total": len(exec_results),
            "tasks_succeeded": len(successful),
            "tasks_failed": len(failed),
            "estimated_cost": plan.get("estimated_cost_monthly", 0),
        },
        "deployment_url": state.get("deployment_url"),
        "monitoring": monitoring,
        "errors": errors,
    }

    state["final_report"] = report
    state["user_message"] = _format_report_message(report)
    
    logger.info(
        f"Report: {report['status']} — {len(successful)} succeeded, {len(failed)} failed",
        extra={"trace_id": trace_id}
    )
    return state


def handle_error_node(state: ButlerState) -> ButlerState:
    """Handle errors and prepare error report."""
    trace_id = state.get("trace_id", "no-trace")
    errors = state.get("errors", [])
    
    logger.error(
        f"Error handler invoked with {len(errors)} error(s)",
        extra={"trace_id": trace_id}
    )

    # If rollback is needed, attempt it
    if state.get("should_rollback", False):
        logger.info("Initiating rollback...", extra={"trace_id": trace_id})
        # Executor's rollback will be called separately
        state["user_message"] = (
            f"❌ Deployment failed with {len(errors)} error(s). "
            f"Rollback initiated. Check logs for trace_id: {trace_id}"
        )
    else:
        state["user_message"] = (
            f"❌ An error occurred. {len(errors)} error(s) recorded. "
            f"Trace ID: {trace_id}"
        )

    state["final_report"] = {
        "trace_id": trace_id,
        "status": "failed",
        "errors": errors,
    }
    return state


def _format_report_message(report: Dict[str, Any]) -> str:
    """Format a human-readable report message."""
    status_emoji = {"success": "✅", "partial": "⚠️", "failed": "❌"}.get(
        report["status"], "❓"
    )
    summary = report.get("summary", {})
    
    lines = [
        f"{status_emoji} Deployment {report['status'].upper()}",
        f"",
        f"📊 Summary:",
        f"  • Languages: {', '.join(summary.get('languages', ['unknown']))}",
        f"  • Frameworks: {', '.join(summary.get('frameworks', ['none']))}",
        f"  • DevOps Skills: {', '.join(summary.get('skills_used', ['none']))}",
        f"  • Tasks: {summary.get('tasks_succeeded', 0)}/{summary.get('tasks_total', 0)} succeeded",
        f"  • Est. Cost: ${summary.get('estimated_cost', 0):.2f}/month",
    ]

    if report.get("deployment_url"):
        lines.append(f"  • URL: {report['deployment_url']}")

    if report.get("errors"):
        lines.append(f"")
        lines.append(f"⚠️ {len(report['errors'])} error(s) occurred — check trace_id: {report['trace_id']}")

    return "\n".join(lines)


# ── Compile & Run ───────────────────────────────────────────────────────

def compile_graph():
    """Compile the orchestrator graph for execution."""
    graph = create_orchestrator()
    return graph.compile()


def run_butler(
    codebase_path: str,
    user_input: str = "",
    operation: str = "deploy",
) -> ButlerState:
    """
    Run the full DevOps Butler pipeline.
    
    Args:
        codebase_path: Path to the codebase to deploy
        user_input: Raw user command
        operation: Operation type (deploy, analyze, plan)
        
    Returns:
        Final ButlerState with results
    """
    # Setup
    settings = get_settings()
    setup_logging(settings.log_level)
    trace = TraceContext.create(operation)
    
    # Initial state
    initial_state: ButlerState = {
        "trace_id": trace.trace_id,
        "operation": operation,
        "user_input": user_input or f"butler {operation} {codebase_path}",
        "codebase_path": codebase_path,
        "code_analysis": {},
        "deployment_plan": {},
        "execution_results": [],
        "browser_tasks": [],
        "monitoring_status": {},
        "user_approved": False,
        "user_message": "",
        "requires_user_input": False,
        "credentials_needed": [],
        "current_agent": "orchestrator",
        "errors": [],
        "should_rollback": False,
        "rollback_results": [],
        "final_report": {},
        "deployment_url": None,
    }
    
    logger.info(
        f"Starting Butler: {operation} on {codebase_path}",
        extra={"trace_id": trace.trace_id}
    )
    
    # Compile and run graph
    app = compile_graph()
    final_state = app.invoke(initial_state)
    
    trace.finish()
    return final_state
