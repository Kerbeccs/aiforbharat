"""
DevOps Butler - Framework & Service Detectors
Identifies frameworks, databases, microservices, and infrastructure from code analysis.
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Set, Optional

from config.logging_config import get_logger

logger = get_logger("detectors")


# ═══════════════════════════════════════════════════════════════════════
# FRAMEWORK DETECTION RULES
# ═══════════════════════════════════════════════════════════════════════

FRAMEWORK_RULES: Dict[str, Dict[str, Any]] = {
    # Python frameworks
    "flask": {
        "language": "python",
        "indicators": {
            "imports": ["flask", "Flask"],
            "files": [],
            "deps": ["flask"],
        },
    },
    "django": {
        "language": "python",
        "indicators": {
            "imports": ["django"],
            "files": ["manage.py", "wsgi.py", "asgi.py", "settings.py"],
            "deps": ["django"],
        },
    },
    "fastapi": {
        "language": "python",
        "indicators": {
            "imports": ["fastapi", "FastAPI"],
            "files": [],
            "deps": ["fastapi"],
        },
    },
    "streamlit": {
        "language": "python",
        "indicators": {
            "imports": ["streamlit"],
            "files": [],
            "deps": ["streamlit"],
        },
    },
    # JavaScript/TypeScript frameworks
    "react": {
        "language": "javascript",
        "indicators": {
            "imports": ["react", "React"],
            "files": [],
            "deps": ["react", "react-dom"],
        },
    },
    "nextjs": {
        "language": "javascript",
        "indicators": {
            "imports": ["next"],
            "files": ["next.config.js", "next.config.mjs", "next.config.ts"],
            "deps": ["next"],
        },
    },
    "express": {
        "language": "javascript",
        "indicators": {
            "imports": ["express"],
            "files": [],
            "deps": ["express"],
        },
    },
    "nestjs": {
        "language": "typescript",
        "indicators": {
            "imports": ["@nestjs"],
            "files": ["nest-cli.json"],
            "deps": ["@nestjs/core"],
        },
    },
    "vue": {
        "language": "javascript",
        "indicators": {
            "imports": ["vue"],
            "files": ["vue.config.js"],
            "deps": ["vue"],
        },
    },
    "angular": {
        "language": "typescript",
        "indicators": {
            "imports": ["@angular"],
            "files": ["angular.json"],
            "deps": ["@angular/core"],
        },
    },
    # Java frameworks
    "springboot": {
        "language": "java",
        "indicators": {
            "imports": ["org.springframework"],
            "files": ["pom.xml", "build.gradle"],
            "deps": ["spring-boot"],
        },
    },
    # Go frameworks
    "gin": {
        "language": "go",
        "indicators": {
            "imports": ["github.com/gin-gonic/gin"],
            "files": [],
            "deps": ["gin"],
        },
    },
}

# ═══════════════════════════════════════════════════════════════════════
# DATABASE DETECTION
# ═══════════════════════════════════════════════════════════════════════

DATABASE_INDICATORS: Dict[str, List[str]] = {
    "postgresql": [
        "psycopg2", "asyncpg", "pg", "postgres", "postgresql",
        "sqlalchemy.*postgres", "DATABASE_URL.*postgres",
    ],
    "mysql": [
        "pymysql", "mysqlclient", "mysql2", "mysql",
        "sqlalchemy.*mysql", "DATABASE_URL.*mysql",
    ],
    "mongodb": [
        "pymongo", "mongoose", "mongodb", "mongoclient", "mongo",
    ],
    "redis": [
        "redis", "ioredis", "aioredis", "redis-py",
    ],
    "sqlite": [
        "sqlite3", "sqlite", "better-sqlite3",
    ],
    "dynamodb": [
        "dynamodb", "boto3.*dynamodb", "aws-sdk.*dynamodb",
    ],
    "elasticsearch": [
        "elasticsearch", "elastic", "opensearch",
    ],
}

# ═══════════════════════════════════════════════════════════════════════
# DEPENDENCY FILE PARSERS
# ═══════════════════════════════════════════════════════════════════════

def parse_requirements_txt(content: str) -> List[str]:
    """Parse Python requirements.txt."""
    deps = []
    for line in content.split("\n"):
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("-"):
            # Extract package name (before ==, >=, <=, ~=, !=)
            pkg = re.split(r"[><=!~\[]", line)[0].strip()
            if pkg:
                deps.append(pkg.lower())
    return deps


def parse_package_json(content: str) -> List[str]:
    """Parse Node.js package.json."""
    try:
        data = json.loads(content)
        deps = list(data.get("dependencies", {}).keys())
        deps += list(data.get("devDependencies", {}).keys())
        return [d.lower() for d in deps]
    except json.JSONDecodeError:
        return []


def parse_go_mod(content: str) -> List[str]:
    """Parse Go go.mod."""
    deps = []
    for line in content.split("\n"):
        line = line.strip()
        if line and not line.startswith("module") and not line.startswith("go "):
            parts = line.split()
            if parts and not parts[0] in ("require", "(", ")"):
                deps.append(parts[0])
    return deps


def parse_pom_xml(content: str) -> List[str]:
    """Parse Java pom.xml (simplified)."""
    artifacts = re.findall(r"<artifactId>([^<]+)</artifactId>", content)
    return [a.lower() for a in artifacts]


DEP_FILE_PARSERS = {
    "requirements.txt": parse_requirements_txt,
    "Pipfile": parse_requirements_txt,  # Simplified
    "setup.py": lambda c: [],  # TODO: complex parsing
    "pyproject.toml": lambda c: [],  # TODO: complex parsing
    "package.json": parse_package_json,
    "go.mod": parse_go_mod,
    "pom.xml": parse_pom_xml,
    "build.gradle": lambda c: [],  # TODO: complex parsing
    "Gemfile": lambda c: [],
    "Cargo.toml": lambda c: [],
}


class CodeDetector:
    """
    Detects frameworks, databases, microservices, and infrastructure
    from a parsed codebase.
    """

    def __init__(self, codebase_path: str, trace_id: str = "no-trace"):
        self.codebase_path = Path(codebase_path).resolve()
        self.trace_id = trace_id

    def detect_all(
        self,
        scan_result: Dict[str, Any],
        parsed_files: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Run all detectors and return combined results.
        
        Args:
            scan_result: Output from CodeParser.scan_files()
            parsed_files: List of outputs from CodeParser.parse_file_content()
        """
        # Collect all imports and file names
        all_imports = set()
        all_files = set()
        all_content: Dict[str, str] = {}

        for pf in parsed_files:
            for imp in pf.get("imports", []):
                all_imports.add(imp.lower())
            all_files.add(pf.get("path", ""))

        for f in scan_result.get("files", []):
            all_files.add(f.get("name", ""))
            all_files.add(f.get("path", ""))

        # Parse dependency files
        dependencies = self._detect_dependencies(scan_result)
        all_dep_names = set()
        for dep_list in dependencies.values():
            all_dep_names.update(dep_list)

        # Run detectors
        frameworks = self._detect_frameworks(all_imports, all_files, all_dep_names)
        databases = self._detect_databases(all_imports, all_dep_names, all_content)
        microservices = self._detect_microservices(scan_result, parsed_files)
        infrastructure = self._detect_infrastructure(all_files)
        entry_points = self._collect_entry_points(parsed_files)

        result = {
            "frameworks": frameworks,
            "databases": databases,
            "dependencies": dependencies,
            "dependency_files": list(dependencies.keys()),
            "microservices_detected": microservices["is_microservice"],
            "services": microservices["services"],
            "entry_points": entry_points,
            "has_dockerfile": infrastructure["has_dockerfile"],
            "has_docker_compose": infrastructure["has_docker_compose"],
            "has_kubernetes": infrastructure["has_kubernetes"],
            "has_cicd": infrastructure["has_cicd"],
            "has_terraform": infrastructure["has_terraform"],
            "infrastructure_files": infrastructure["files"],
        }

        logger.info(
            f"Detection complete: {len(frameworks)} frameworks, "
            f"{len(databases)} databases, "
            f"{'microservices' if microservices['is_microservice'] else 'monolith'} detected",
            extra={"trace_id": self.trace_id}
        )

        return result

    def _detect_frameworks(
        self,
        imports: Set[str],
        files: Set[str],
        deps: Set[str],
    ) -> List[str]:
        """Detect frameworks from imports, files, and dependencies."""
        detected = []
        imports_str = " ".join(imports)
        files_str = " ".join(files)

        for framework, rules in FRAMEWORK_RULES.items():
            indicators = rules["indicators"]
            score = 0

            # Check imports
            for imp_pattern in indicators.get("imports", []):
                if imp_pattern.lower() in imports_str:
                    score += 2

            # Check files
            for file_pattern in indicators.get("files", []):
                if file_pattern.lower() in files_str.lower():
                    score += 3

            # Check dependencies
            for dep_pattern in indicators.get("deps", []):
                if dep_pattern.lower() in deps:
                    score += 3

            if score >= 2:
                detected.append(framework)

        return detected

    def _detect_databases(
        self,
        imports: Set[str],
        deps: Set[str],
        content: Dict[str, str],
    ) -> List[str]:
        """Detect database usage from imports and dependencies."""
        detected = []
        search_str = " ".join(imports) + " " + " ".join(deps)

        for db, indicators in DATABASE_INDICATORS.items():
            for indicator in indicators:
                if re.search(indicator, search_str, re.IGNORECASE):
                    if db not in detected:
                        detected.append(db)
                    break

        return detected

    def _detect_dependencies(self, scan_result: Dict[str, Any]) -> Dict[str, List[str]]:
        """Parse dependency files and return deps by file."""
        dependencies = {}

        for file_info in scan_result.get("files", []):
            filename = file_info.get("name", "")
            if filename in DEP_FILE_PARSERS:
                filepath = self.codebase_path / file_info["path"]
                try:
                    content = filepath.read_text(encoding="utf-8", errors="replace")
                    deps = DEP_FILE_PARSERS[filename](content)
                    if deps:
                        dependencies[filename] = deps
                except Exception as e:
                    logger.warning(
                        f"Failed to parse {filename}: {e}",
                        extra={"trace_id": self.trace_id}
                    )

        return dependencies

    def _detect_microservices(
        self,
        scan_result: Dict[str, Any],
        parsed_files: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Detect if codebase is microservices architecture.
        Indicators: multiple entry points, docker-compose, multiple Dockerfiles,
        multiple package.json/requirements.txt in subdirectories.
        """
        entry_points = []
        for pf in parsed_files:
            entry_points.extend(pf.get("entry_points", []))

        # Count Dockerfiles
        dockerfiles = [
            f for f in scan_result.get("files", [])
            if "dockerfile" in f.get("name", "").lower()
        ]

        # Count dependency files in different directories
        dep_dirs = set()
        for f in scan_result.get("files", []):
            if f.get("name", "") in DEP_FILE_PARSERS:
                dep_dir = os.path.dirname(f.get("path", ""))
                dep_dirs.add(dep_dir)

        is_microservice = (
            len(entry_points) > 1
            or len(dockerfiles) > 1
            or len(dep_dirs) > 1
        )

        # Build service list
        services = []
        if is_microservice:
            for ep in entry_points:
                services.append({
                    "name": Path(ep.get("file", "service")).stem,
                    "entry_point": ep.get("file", ""),
                    "type": ep.get("type", "unknown"),
                })
        else:
            # Single service
            main_entry = entry_points[0] if entry_points else {}
            services.append({
                "name": "main",
                "entry_point": main_entry.get("file", ""),
                "type": main_entry.get("type", "monolith"),
            })

        return {
            "is_microservice": is_microservice,
            "services": services,
            "service_count": len(services),
        }

    def _detect_infrastructure(self, files: Set[str]) -> Dict[str, Any]:
        """Detect existing infrastructure files."""
        files_lower = {f.lower() for f in files}
        files_str = " ".join(files_lower)

        infra_files = []

        has_dockerfile = any("dockerfile" in f for f in files_lower)
        if has_dockerfile:
            infra_files.append("Dockerfile")

        has_docker_compose = any("docker-compose" in f or "compose.yml" in f or "compose.yaml" in f for f in files_lower)
        if has_docker_compose:
            infra_files.append("docker-compose.yml")

        has_kubernetes = any(
            f.endswith((".yaml", ".yml")) and any(kw in f for kw in ("k8s", "kubernetes", "deployment", "service.y"))
            for f in files_lower
        ) or any("kustomization" in f for f in files_lower)

        has_cicd = any(
            ".github/workflows" in f or
            "jenkinsfile" in f or
            ".gitlab-ci" in f or
            ".circleci" in f or
            ".travis.yml" in f or
            "azure-pipelines" in f
            for f in files_lower
        )

        has_terraform = any(f.endswith(".tf") for f in files_lower)

        return {
            "has_dockerfile": has_dockerfile,
            "has_docker_compose": has_docker_compose,
            "has_kubernetes": has_kubernetes,
            "has_cicd": has_cicd,
            "has_terraform": has_terraform,
            "files": infra_files,
        }

    def _collect_entry_points(self, parsed_files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Collect all entry points from parsed files."""
        entry_points = []
        for pf in parsed_files:
            for ep in pf.get("entry_points", []):
                ep_copy = dict(ep)
                ep_copy["file"] = pf.get("path", "")
                entry_points.append(ep_copy)
        return entry_points
