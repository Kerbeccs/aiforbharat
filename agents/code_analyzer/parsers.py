"""
DevOps Butler - Code Parsers
Uses Tree-sitter for multi-language parsing + regex-based fallback.
Extracts: imports, function signatures, class definitions, entry points.
"""

import os
import re
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Set

from config.logging_config import get_logger

logger = get_logger("code_parser")

# ── File extension → language mapping ───────────────────────────────────
LANGUAGE_MAP: Dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rb": "ruby",
    ".rs": "rust",
    ".php": "php",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".c": "c",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".r": "r",
    ".sh": "bash",
    ".bash": "bash",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".json": "json",
    ".xml": "xml",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".sql": "sql",
    ".tf": "terraform",
    ".hcl": "terraform",
}

# Files / directories to skip
SKIP_DIRS: Set[str] = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
    ".env", "dist", "build", ".next", ".nuxt", "target", "bin", "obj",
    ".terraform", ".idea", ".vscode", "coverage", ".pytest_cache",
    ".mypy_cache", "egg-info",
}

SKIP_FILES: Set[str] = {
    ".gitignore", ".dockerignore", "LICENSE", "LICENCE",
    ".DS_Store", "Thumbs.db",
}

# Max file size to parse (500KB)
MAX_FILE_SIZE = 500 * 1024


class CodeParser:
    """
    Parses a codebase recursively to extract structure information.
    Uses regex-based parsing (more reliable cross-platform than tree-sitter binaries).
    """

    def __init__(self, codebase_path: str, trace_id: str = "no-trace"):
        self.codebase_path = Path(codebase_path).resolve()
        self.trace_id = trace_id

        if not self.codebase_path.exists():
            raise FileNotFoundError(f"Codebase path not found: {codebase_path}")

    def scan_files(self) -> Dict[str, Any]:
        """
        Recursively scan all files in the codebase.
        
        Returns:
            {
                "total_files": 42,
                "total_dirs": 8,
                "files": [{"path": "app.py", "language": "python", "size": 1234}],
                "languages": {"python": 12, "javascript": 8},
                "directories": ["src/", "tests/", "config/"],
            }
        """
        files = []
        language_counts: Dict[str, int] = {}
        language_bytes: Dict[str, int] = {}
        directories: Set[str] = set()
        total_files = 0
        total_dirs = 0

        for root, dirs, filenames in os.walk(self.codebase_path):
            # Filter out skip directories
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
            
            rel_root = os.path.relpath(root, self.codebase_path)
            if rel_root != ".":
                directories.add(rel_root)
                total_dirs += 1

            for filename in filenames:
                if filename in SKIP_FILES:
                    continue

                filepath = os.path.join(root, filename)
                rel_path = os.path.relpath(filepath, self.codebase_path)
                
                try:
                    file_size = os.path.getsize(filepath)
                except OSError:
                    continue

                if file_size > MAX_FILE_SIZE:
                    continue

                ext = Path(filename).suffix.lower()
                language = LANGUAGE_MAP.get(ext, "other")

                file_info = {
                    "path": rel_path.replace("\\", "/"),
                    "name": filename,
                    "language": language,
                    "size": file_size,
                    "extension": ext,
                }
                files.append(file_info)
                total_files += 1

                if language != "other":
                    language_counts[language] = language_counts.get(language, 0) + 1
                    language_bytes[language] = language_bytes.get(language, 0) + file_size

        # Calculate language percentages
        total_bytes = sum(language_bytes.values()) or 1
        languages = []
        for lang, count in sorted(language_counts.items(), key=lambda x: x[1], reverse=True):
            languages.append({
                "name": lang,
                "files": count,
                "bytes": language_bytes.get(lang, 0),
                "percentage": round(language_bytes.get(lang, 0) / total_bytes * 100, 1),
            })

        logger.info(
            f"Scanned {total_files} files, {total_dirs} dirs, "
            f"{len(languages)} languages detected",
            extra={"trace_id": self.trace_id}
        )

        return {
            "total_files": total_files,
            "total_dirs": total_dirs,
            "files": files,
            "languages": languages,
            "directories": sorted(directories),
        }

    def parse_file_content(self, filepath: str) -> Dict[str, Any]:
        """
        Parse a single file and extract structural information.
        Uses regex-based extraction.
        """
        full_path = self.codebase_path / filepath
        if not full_path.exists():
            return {"error": f"File not found: {filepath}"}

        try:
            content = full_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return {"error": f"Cannot read {filepath}: {e}"}

        ext = Path(filepath).suffix.lower()
        language = LANGUAGE_MAP.get(ext, "other")

        result = {
            "path": filepath,
            "language": language,
            "lines": content.count("\n") + 1,
            "imports": [],
            "functions": [],
            "classes": [],
            "entry_points": [],
        }

        if language == "python":
            result.update(self._parse_python(content))
        elif language in ("javascript", "typescript"):
            result.update(self._parse_javascript(content))
        elif language == "java":
            result.update(self._parse_java(content))
        elif language == "go":
            result.update(self._parse_go(content))

        return result

    def _parse_python(self, content: str) -> Dict[str, Any]:
        """Extract Python structures."""
        imports = []
        functions = []
        classes = []
        entry_points = []

        for line in content.split("\n"):
            line_stripped = line.strip()

            # Imports
            if line_stripped.startswith("import ") or line_stripped.startswith("from "):
                imports.append(line_stripped)

            # Functions
            match = re.match(r"^def\s+(\w+)\s*\(", line_stripped)
            if match:
                functions.append(match.group(1))

            # Classes
            match = re.match(r"^class\s+(\w+)", line_stripped)
            if match:
                classes.append(match.group(1))

            # Entry points
            if "if __name__" in line_stripped and "__main__" in line_stripped:
                entry_points.append({"type": "python_main", "line": line_stripped})
            if ".run(" in line_stripped and ("app" in line_stripped.lower() or "flask" in line_stripped.lower()):
                entry_points.append({"type": "flask_run", "line": line_stripped})
            if "uvicorn.run" in line_stripped:
                entry_points.append({"type": "fastapi_run", "line": line_stripped})

        return {
            "imports": imports,
            "functions": functions,
            "classes": classes,
            "entry_points": entry_points,
        }

    def _parse_javascript(self, content: str) -> Dict[str, Any]:
        """Extract JavaScript/TypeScript structures."""
        imports = []
        functions = []
        classes = []
        entry_points = []

        for line in content.split("\n"):
            line_stripped = line.strip()

            # Imports
            if line_stripped.startswith("import ") or "require(" in line_stripped:
                imports.append(line_stripped)

            # Functions
            match = re.match(r"(?:export\s+)?(?:async\s+)?function\s+(\w+)", line_stripped)
            if match:
                functions.append(match.group(1))
            # Arrow functions
            match = re.match(r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\([^)]*\)|[^=])\s*=>", line_stripped)
            if match:
                functions.append(match.group(1))

            # Classes
            match = re.match(r"(?:export\s+)?class\s+(\w+)", line_stripped)
            if match:
                classes.append(match.group(1))

            # Entry points
            if ".listen(" in line_stripped:
                entry_points.append({"type": "server_listen", "line": line_stripped})
            if "createServer" in line_stripped:
                entry_points.append({"type": "http_server", "line": line_stripped})

        return {
            "imports": imports,
            "functions": functions,
            "classes": classes,
            "entry_points": entry_points,
        }

    def _parse_java(self, content: str) -> Dict[str, Any]:
        """Extract Java structures."""
        imports = [line.strip() for line in content.split("\n") if line.strip().startswith("import ")]
        classes = re.findall(r"(?:public\s+)?class\s+(\w+)", content)
        functions = re.findall(r"(?:public|private|protected)\s+\w+\s+(\w+)\s*\(", content)
        entry_points = []
        if "public static void main" in content:
            entry_points.append({"type": "java_main", "line": "public static void main"})

        return {"imports": imports, "functions": functions, "classes": classes, "entry_points": entry_points}

    def _parse_go(self, content: str) -> Dict[str, Any]:
        """Extract Go structures."""
        imports = re.findall(r'"([^"]+)"', content)
        functions = re.findall(r"func\s+(\w+)\s*\(", content)
        entry_points = []
        if "func main()" in content:
            entry_points.append({"type": "go_main", "line": "func main()"})

        return {"imports": imports, "functions": functions, "classes": [], "entry_points": entry_points}

    def get_file_content(self, filepath: str, max_lines: int = 200) -> str:
        """Read file content (truncated for LLM context)."""
        full_path = self.codebase_path / filepath
        try:
            lines = full_path.read_text(encoding="utf-8", errors="replace").split("\n")
            if len(lines) > max_lines:
                return "\n".join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} more lines)"
            return "\n".join(lines)
        except Exception:
            return ""
