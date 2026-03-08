"""
DevOps Butler - Code Analyzer Agent
LangGraph node that orchestrates code parsing and detection.
Uses Haiku for natural language summary of the analysis.
"""

import logging
from typing import Dict, Any

from agents.base_agent import BaseAgent, trace_operation
from agents.code_analyzer.parsers import CodeParser
from agents.code_analyzer.detectors import CodeDetector
from core.state import ButlerState
from config.logging_config import get_logger

logger = get_logger("code_analyzer")


class CodeAnalyzerAgent(BaseAgent):
    """
    Agent 1: Code Analyzer
    
    Parses the user's codebase to understand:
    - Languages and frameworks used
    - Databases and services
    - Microservice vs monolith architecture
    - Existing infrastructure (Docker, K8s, CI/CD, Terraform)
    - Entry points and dependencies
    
    Output is written to state["code_analysis"] as structured JSON.
    """

    def __init__(self):
        super().__init__(agent_name="code_analyzer")

    @trace_operation("analyze_code")
    def process(self, state: ButlerState) -> ButlerState:
        """
        Run code analysis on the codebase.
        
        Steps:
            1. Scan all files recursively
            2. Parse key source files for structure
            3. Detect frameworks, databases, services
            4. Generate natural language summary via Haiku
            5. Write results to state
        """
        trace_id = state.get("trace_id", "no-trace")
        codebase_path = state.get("codebase_path", "")

        if not codebase_path:
            return self._add_error(state, "ANALYSIS_ERROR", "No codebase path provided")

        # ── Step 1: Scan files ──────────────────────────────────────
        logger.info(f"Scanning codebase: {codebase_path}", extra={"trace_id": trace_id})
        parser = CodeParser(codebase_path, trace_id=trace_id)
        scan_result = parser.scan_files()

        # ── Step 2: Parse key source files ──────────────────────────
        parsed_files = []
        source_extensions = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go"}
        
        source_files = [
            f for f in scan_result.get("files", [])
            if f.get("extension", "") in source_extensions
        ]

        # Parse up to 50 source files (prioritize smaller ones first for speed)
        source_files.sort(key=lambda f: f.get("size", 0))
        for file_info in source_files[:50]:
            parsed = parser.parse_file_content(file_info["path"])
            if "error" not in parsed:
                parsed_files.append(parsed)

        logger.info(
            f"Parsed {len(parsed_files)} source files",
            extra={"trace_id": trace_id}
        )

        # ── Step 3: Detect frameworks, databases, services ──────────
        detector = CodeDetector(codebase_path, trace_id=trace_id)
        detection = detector.detect_all(scan_result, parsed_files)

        # ── Step 4: Generate summary via Haiku ──────────────────────
        summary = self._generate_summary(scan_result, detection, trace_id)

        # ── Step 5: Write to state ──────────────────────────────────
        state["code_analysis"] = {
            "languages": scan_result.get("languages", []),
            "frameworks": detection.get("frameworks", []),
            "services": detection.get("services", []),
            "databases": detection.get("databases", []),
            "dependencies": detection.get("dependencies", {}),
            "dependency_files": detection.get("dependency_files", []),
            "has_dockerfile": detection.get("has_dockerfile", False),
            "has_docker_compose": detection.get("has_docker_compose", False),
            "has_kubernetes": detection.get("has_kubernetes", False),
            "has_cicd": detection.get("has_cicd", False),
            "has_terraform": detection.get("has_terraform", False),
            "microservices_detected": detection.get("microservices_detected", False),
            "entry_points": detection.get("entry_points", []),
            "project_structure": {
                "total_files": scan_result.get("total_files", 0),
                "total_dirs": scan_result.get("total_dirs", 0),
                "directories": scan_result.get("directories", []),
            },
            "raw_summary": summary,
        }

        logger.info(
            f"Analysis complete: {len(detection.get('frameworks', []))} frameworks, "
            f"{len(detection.get('databases', []))} databases",
            extra={"trace_id": trace_id}
        )

        return state

    def _generate_summary(
        self,
        scan_result: Dict[str, Any],
        detection: Dict[str, Any],
        trace_id: str,
    ) -> str:
        """Generate a natural language summary using Claude Haiku."""
        try:
            from generators.bedrock_client import get_bedrock_client

            languages = scan_result.get("languages", [])
            lang_str = ", ".join(
                f"{l['name']} ({l['percentage']}%)" for l in languages[:5]
            )

            prompt = (
                f"Summarize this codebase analysis in 2-3 sentences:\n"
                f"- Languages: {lang_str}\n"
                f"- Frameworks: {', '.join(detection.get('frameworks', ['none']))}\n"
                f"- Databases: {', '.join(detection.get('databases', ['none']))}\n"
                f"- Architecture: {'Microservices' if detection.get('microservices_detected') else 'Monolith'}\n"
                f"- Services: {len(detection.get('services', []))}\n"
                f"- Has Docker: {detection.get('has_dockerfile', False)}\n"
                f"- Has K8s: {detection.get('has_kubernetes', False)}\n"
                f"- Has CI/CD: {detection.get('has_cicd', False)}\n"
                f"- Has Terraform: {detection.get('has_terraform', False)}\n"
                f"- Total files: {scan_result.get('total_files', 0)}\n"
            )

            return get_bedrock_client().invoke_haiku(
                prompt=prompt,
                system_prompt=(
                    "You are a code analysis expert. Provide a brief, technical summary "
                    "of the codebase. Focus on architecture, key technologies, and "
                    "deployment readiness. Be concise."
                ),
                max_tokens=256,
                trace_id=trace_id,
            )
        except Exception as e:
            logger.warning(
                f"Summary generation failed, using fallback: {e}",
                extra={"trace_id": trace_id}
            )
            # Fallback: generate summary without LLM
            frameworks = detection.get("frameworks", [])
            databases = detection.get("databases", [])
            arch = "microservices" if detection.get("microservices_detected") else "monolith"
            return (
                f"A {arch} application using "
                f"{', '.join(frameworks) if frameworks else 'unknown frameworks'}. "
                f"{'Uses ' + ', '.join(databases) + '. ' if databases else ''}"
                f"{scan_result.get('total_files', 0)} files analyzed."
            )
