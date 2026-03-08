"""
DevOps Butler - FastAPI Web Server
REST API + WebSocket for real-time deployment progress.
"""

import asyncio
import json
import uuid
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

from config.settings import get_settings
from config.logging_config import get_logger, setup_logging
from core.trace import TraceContext

logger = get_logger("server")

app = FastAPI(
    title="DevOps Butler",
    description="AI-powered DevOps automation system",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store for active deployments
active_deployments: Dict[str, Dict[str, Any]] = {}

# ── Static UI Files ─────────────────────────────────────────────────────
STATIC_DIR = Path(__file__).resolve().parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main UI."""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return index_path.read_text(encoding="utf-8")
    return HTMLResponse("<h1>DevOps Butler</h1><p>UI not found. Run from project root.</p>")


# ── REST API Endpoints ──────────────────────────────────────────────────

@app.post("/api/deploy")
async def start_deployment(
    user_input: str = Form("deploy"),
    codebase_path: str = Form(""),
    file: Optional[UploadFile] = File(None),
):
    """
    Start a new deployment.
    
    Accepts either:
    - A local codebase path
    - An uploaded code file/zip
    """
    trace = TraceContext.create("deploy")
    deployment_id = trace.trace_id

    # Handle file upload
    if file:
        upload_dir = Path("uploads").resolve() / deployment_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        filepath = upload_dir / file.filename
        content = await file.read()
        filepath.write_bytes(content)
        codebase_path = str(upload_dir)
        logger.info(f"Uploaded file: {file.filename}", extra={"trace_id": deployment_id})

    if not codebase_path:
        raise HTTPException(status_code=400, detail="No codebase path or file provided")

    active_deployments[deployment_id] = {
        "status": "started",
        "codebase_path": codebase_path,
        "user_input": user_input,
        "trace_id": deployment_id,
        "progress": [],
    }

    # Run deployment in background
    asyncio.create_task(_run_deployment_async(deployment_id, codebase_path, user_input))

    return {
        "deployment_id": deployment_id,
        "status": "started",
        "message": "Deployment initiated. Connect to WebSocket for live updates.",
    }


@app.get("/api/deploy/{deployment_id}")
async def get_deployment_status(deployment_id: str):
    """Get the current status of a deployment."""
    if deployment_id not in active_deployments:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return active_deployments[deployment_id]


@app.post("/api/deploy/{deployment_id}/approve")
async def approve_deployment(deployment_id: str):
    """Approve a pending deployment plan."""
    if deployment_id not in active_deployments:
        raise HTTPException(status_code=404, detail="Deployment not found")
    active_deployments[deployment_id]["user_approved"] = True
    return {"message": "Plan approved", "deployment_id": deployment_id}


@app.get("/api/health")
async def health_check():
    """System health check."""
    return {
        "status": "healthy",
        "service": "DevOps Butler",
        "version": "1.0.0",
    }


@app.get("/api/deploy/{deployment_id}/files")
async def list_generated_files(deployment_id: str):
    """List all generated files for a deployment."""
    upload_dir = Path("uploads").resolve() / deployment_id
    if not upload_dir.exists():
        raise HTTPException(status_code=404, detail="Deployment not found")

    files = []
    for f in upload_dir.rglob("*"):
        if f.is_file():
            rel = f.relative_to(upload_dir)
            files.append({
                "path": str(rel),
                "size": f.stat().st_size,
                "content": f.read_text(encoding="utf-8", errors="replace")[:5000],
            })
    return {"deployment_id": deployment_id, "files": files}


# ── WebSocket for Real-time Updates ────────────────────────────────────

class ConnectionManager:
    """Manage WebSocket connections per deployment."""
    
    def __init__(self):
        self.connections: Dict[str, list] = {}

    async def connect(self, websocket: WebSocket, deployment_id: str):
        await websocket.accept()
        if deployment_id not in self.connections:
            self.connections[deployment_id] = []
        self.connections[deployment_id].append(websocket)

    def disconnect(self, websocket: WebSocket, deployment_id: str):
        if deployment_id in self.connections:
            self.connections[deployment_id].remove(websocket)

    async def send_update(self, deployment_id: str, data: Dict[str, Any]):
        if deployment_id in self.connections:
            for ws in self.connections[deployment_id]:
                try:
                    await ws.send_json(data)
                except Exception:
                    pass


ws_manager = ConnectionManager()


@app.websocket("/ws/{deployment_id}")
async def websocket_endpoint(websocket: WebSocket, deployment_id: str):
    """WebSocket endpoint for live deployment updates."""
    await ws_manager.connect(websocket, deployment_id)
    try:
        while True:
            # Keep connection alive, handle user messages
            data = await websocket.receive_text()
            msg = json.loads(data)
            
            if msg.get("type") == "approve":
                if deployment_id in active_deployments:
                    active_deployments[deployment_id]["user_approved"] = True
                    await ws_manager.send_update(deployment_id, {
                        "type": "status",
                        "message": "Plan approved by user",
                    })
            elif msg.get("type") == "message":
                if deployment_id in active_deployments:
                    active_deployments[deployment_id]["user_message"] = msg.get("text", "")

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, deployment_id)


# ── Background Deployment Runner ────────────────────────────────────────

async def _run_deployment_async(deployment_id: str, codebase_path: str, user_input: str):
    """Run the full Butler pipeline in background with approval support."""
    try:
        await ws_manager.send_update(deployment_id, {
            "type": "status",
            "agent": "orchestrator",
            "message": "Starting deployment...",
        })

        from core.orchestrator import run_butler, compile_graph, create_execution_graph
        from core.trace import TraceContext
        from config.logging_config import setup_logging

        settings = get_settings()
        setup_logging(settings.log_level)
        trace = TraceContext.create("deploy")

        # Build initial state
        initial_state = {
            "trace_id": trace.trace_id,
            "operation": "deploy",
            "user_input": user_input or f"butler deploy {codebase_path}",
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
            f"Starting Butler: deploy on {codebase_path}",
            extra={"trace_id": trace.trace_id}
        )

        # Run the pipeline (first pass — may stop at approval)
        loop = asyncio.get_event_loop()
        app = compile_graph()
        result = await loop.run_in_executor(None, app.invoke, initial_state)

        # Check if pipeline stopped for user approval
        plan = result.get("deployment_plan", {})
        needs_approval = (
            plan.get("requires_user_approval", False) and
            not result.get("user_approved", False) and
            not result.get("final_report", {}).get("status")  # Not already finished
        )

        if needs_approval:
            # Send plan to UI for approval
            await ws_manager.send_update(deployment_id, {
                "type": "approval_required",
                "plan": {
                    "strategy": plan.get("strategy", "unknown"),
                    "estimated_cost": plan.get("estimated_cost_monthly", 0),
                    "tasks": len(plan.get("tasks", [])),
                    "skills": plan.get("devops_skills_needed", []),
                    "services": plan.get("aws_services", []),
                },
                "message": (
                    f"📋 Plan ready: {plan.get('strategy', 'unknown')} strategy, "
                    f"${plan.get('estimated_cost_monthly', 0):.2f}/month, "
                    f"{len(plan.get('tasks', []))} tasks. Approve to continue."
                ),
            })

            # Store intermediate state for resumption
            active_deployments[deployment_id].update({
                "status": "awaiting_approval",
                "intermediate_state": result,
                "trace": trace,
            })

            # Wait for user approval (poll every 2 seconds)
            approved = False
            for _ in range(300):  # Max 10 minutes wait
                await asyncio.sleep(2)
                if active_deployments.get(deployment_id, {}).get("user_approved", False):
                    approved = True
                    break

            if not approved:
                active_deployments[deployment_id]["status"] = "timed_out"
                await ws_manager.send_update(deployment_id, {
                    "type": "error",
                    "message": "Approval timed out after 10 minutes.",
                })
                trace.finish()
                return

            # Resume execution with approval
            logger.info("User approved plan, resuming execution", extra={"trace_id": trace.trace_id})
            await ws_manager.send_update(deployment_id, {
                "type": "status",
                "agent": "orchestrator",
                "message": "Plan approved! Executing deployment...",
            })

            # Re-run from execution only (skip analyze+plan)
            result["user_approved"] = True
            result["final_report"] = {}
            exec_graph = create_execution_graph()
            exec_app = exec_graph.compile()
            result = await loop.run_in_executor(None, exec_app.invoke, result)

        # Final result
        active_deployments[deployment_id].update({
            "status": "completed",
            "result": result.get("final_report", {}),
        })

        await ws_manager.send_update(deployment_id, {
            "type": "complete",
            "report": result.get("final_report", {}),
            "message": result.get("user_message", "Deployment complete"),
        })

        trace.finish()

    except Exception as e:
        logger.error(f"Deployment failed: {e}", extra={"trace_id": deployment_id}, exc_info=True)
        active_deployments[deployment_id]["status"] = "failed"
        active_deployments[deployment_id]["error"] = str(e)

        await ws_manager.send_update(deployment_id, {
            "type": "error",
            "message": f"Deployment failed: {str(e)}",
        })


# ── Entry Point ─────────────────────────────────────────────────────────

def start_server(host: str = "0.0.0.0", port: int = 8000):
    """Start the FastAPI server."""
    import uvicorn
    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info(f"Starting DevOps Butler server on {host}:{port}")
    uvicorn.run(app, host=host, port=port)
