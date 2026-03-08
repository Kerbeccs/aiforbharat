"""
DevOps Butler - CLI Entry Point
Main executable for running Butler from the command line.
"""

import sys
import os
import json
import argparse
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import get_settings
from config.logging_config import setup_logging, get_logger

logger = get_logger("cli")


def main():
    parser = argparse.ArgumentParser(
        prog="butler",
        description="🤖 DevOps Butler — AI-powered deployment automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  butler deploy ./my-app
  butler deploy ./my-app --instructions "Use Kubernetes with PostgreSQL"
  butler analyze ./my-app
  butler serve --port 8000

Environment Variables:
  AWS_ACCESS_KEY_ID        AWS credentials
  AWS_SECRET_ACCESS_KEY    AWS credentials
  AWS_DEFAULT_REGION       AWS region (default: us-east-1)
  HF_TOKEN                 HuggingFace API token
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # ── deploy ──────────────────────────────────────────────
    deploy_parser = subparsers.add_parser("deploy", help="Deploy an application")
    deploy_parser.add_argument("path", help="Path to the codebase")
    deploy_parser.add_argument(
        "--instructions", "-i",
        default="",
        help="Deployment instructions (e.g., 'Use K8s with CI/CD')",
    )
    deploy_parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Auto-approve deployment plan (skip budget check)",
    )

    # ── analyze ─────────────────────────────────────────────
    analyze_parser = subparsers.add_parser("analyze", help="Analyze a codebase (no deployment)")
    analyze_parser.add_argument("path", help="Path to the codebase")

    # ── serve ───────────────────────────────────────────────
    serve_parser = subparsers.add_parser("serve", help="Start the web UI server")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to listen on")

    # ── version ─────────────────────────────────────────────
    subparsers.add_parser("version", help="Show version")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Setup
    settings = get_settings()
    setup_logging(settings.log_level)

    if args.command == "version":
        print("DevOps Butler v1.0.0")
        return

    if args.command == "serve":
        from ui.server import start_server
        start_server(args.host, args.port)
        return

    if args.command == "deploy":
        run_deploy(args.path, args.instructions, args.auto_approve)
        return

    if args.command == "analyze":
        run_analyze(args.path)
        return


def run_deploy(path: str, instructions: str, auto_approve: bool):
    """Run full deployment pipeline."""
    path = os.path.abspath(path)
    if not os.path.exists(path):
        print(f"❌ Path not found: {path}")
        sys.exit(1)

    print("🤖 DevOps Butler — Starting Deployment")
    print(f"📁 Codebase: {path}")
    if instructions:
        print(f"📝 Instructions: {instructions}")
    print("─" * 60)

    from core.orchestrator import run_butler

    result = run_butler(
        codebase_path=path,
        user_input=instructions,
        operation="deploy",
    )

    # Print results
    report = result.get("final_report", {})
    message = result.get("user_message", "")

    if message:
        print()
        print(message)

    if report.get("status") == "success":
        print("\n✅ Deployment completed successfully!")
    elif report.get("status") == "partial":
        print("\n⚠️ Deployment partially completed. Check logs.")
    else:
        print("\n❌ Deployment failed. Check logs and errors.")

    sys.exit(0 if report.get("status") == "success" else 1)


def run_analyze(path: str):
    """Run code analysis only."""
    path = os.path.abspath(path)
    if not os.path.exists(path):
        print(f"❌ Path not found: {path}")
        sys.exit(1)

    print("🔍 DevOps Butler — Code Analysis")
    print(f"📁 Codebase: {path}")
    print("─" * 60)

    from agents.code_analyzer.parsers import CodeParser
    from agents.code_analyzer.detectors import CodeDetector

    # Scan
    parser = CodeParser(path)
    scan = parser.scan_files()

    # Parse source files
    parsed = []
    for f in scan.get("files", []):
        if f.get("extension") in {".py", ".js", ".ts", ".java", ".go"}:
            p = parser.parse_file_content(f["path"])
            if "error" not in p:
                parsed.append(p)

    # Detect
    detector = CodeDetector(path)
    detection = detector.detect_all(scan, parsed)

    # Display results
    print(f"\n📊 Files: {scan['total_files']} | Dirs: {scan['total_dirs']}")
    print(f"\n📝 Languages:")
    for lang in scan.get("languages", []):
        print(f"   {lang['name']:15} {lang['files']:3} files ({lang['percentage']}%)")

    print(f"\n🛠️  Frameworks: {', '.join(detection.get('frameworks', ['none']))}")
    print(f"🗄️  Databases: {', '.join(detection.get('databases', ['none']))}")
    print(f"🏗️  Architecture: {'Microservices' if detection.get('microservices_detected') else 'Monolith'}")
    
    infra = []
    if detection.get("has_dockerfile"): infra.append("Docker")
    if detection.get("has_docker_compose"): infra.append("Compose")
    if detection.get("has_kubernetes"): infra.append("Kubernetes")
    if detection.get("has_cicd"): infra.append("CI/CD")
    if detection.get("has_terraform"): infra.append("Terraform")
    print(f"📦 Infrastructure: {', '.join(infra) if infra else 'none'}")

    entry_points = detection.get("entry_points", [])
    if entry_points:
        print(f"\n🎯 Entry Points:")
        for ep in entry_points[:5]:
            print(f"   {ep.get('file', '?')}: {ep.get('type', 'unknown')}")

    print(f"\n{'─' * 60}")
    print("✅ Analysis complete")


if __name__ == "__main__":
    main()
