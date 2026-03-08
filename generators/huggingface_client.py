"""
DevOps Butler - HuggingFace Inference API Client
Uses CodeGemma for Dockerfile/YAML generation (FREE tier).
Fallback chain: HuggingFace → Bedrock Nova Pro → Local Templates
"""

import os
import logging
from typing import Optional, Dict, Any

import httpx

from config.settings import get_settings
from config.logging_config import get_logger
from core.exceptions import HuggingFaceError, HuggingFaceRateLimitError

logger = get_logger("huggingface_client")

# ── Local Template Fallbacks ────────────────────────────────────────────

DOCKERFILE_TEMPLATES: Dict[str, str] = {
    "flask": """FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
""",
    "django": """FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "config.wsgi:application"]
""",
    "fastapi": """FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
""",
    "express": """FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
EXPOSE 3000
CMD ["node", "index.js"]
""",
    "react": """FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/build /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
""",
    "nextjs": """FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine
WORKDIR /app
COPY --from=build /app/.next ./.next
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/package.json ./
EXPOSE 3000
CMD ["npm", "start"]
""",
    "springboot": """FROM eclipse-temurin:17-jdk-alpine AS build
WORKDIR /app
COPY . .
RUN ./mvnw package -DskipTests

FROM eclipse-temurin:17-jre-alpine
WORKDIR /app
COPY --from=build /app/target/*.jar app.jar
EXPOSE 8080
CMD ["java", "-jar", "app.jar"]
""",
    "go": """FROM golang:1.22-alpine AS build
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o main .

FROM alpine:latest
WORKDIR /app
COPY --from=build /app/main .
EXPOSE 8080
CMD ["./main"]
""",
    "generic_python": """FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py"]
""",
    "generic_node": """FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
CMD ["node", "index.js"]
""",
}

DOCKER_COMPOSE_TEMPLATE = """version: '3.8'

services:
  {service_name}:
    build: .
    ports:
      - "{host_port}:{container_port}"
    environment:
      - NODE_ENV=production
    restart: unless-stopped
"""

NGINX_CONF_TEMPLATE = """server {{
    listen 80;
    server_name {domain};

    location / {{
        proxy_pass http://app:{port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}
"""


class HuggingFaceClient:
    """
    HuggingFace Inference API client for CodeGemma.
    FREE tier with rate limits: ~100 requests/hour.
    
    Fallback chain:
        1. HuggingFace CodeGemma (free)
        2. Bedrock Nova Pro (paid, but more reliable)
        3. Local templates (100% reliable, no AI)
    """

    HF_API_URL = "https://api-inference.huggingface.co/models"

    def __init__(self):
        self.settings = get_settings()
        self._http_client = None

    @property
    def http_client(self) -> httpx.Client:
        if self._http_client is None:
            self._http_client = httpx.Client(
                timeout=60.0,
                headers={"Authorization": f"Bearer {self.settings.hf_token}"},
            )
        return self._http_client

    def generate_dockerfile(
        self,
        framework: str,
        app_details: str = "",
        trace_id: str = "no-trace",
    ) -> str:
        """
        Generate a Dockerfile for the given framework.
        
        Falls back through: HuggingFace → Bedrock → Local template
        """
        # ── Try HuggingFace first (FREE) ────────────────────────────
        if self.settings.hf_token:
            try:
                return self._generate_via_hf(framework, app_details, trace_id)
            except (HuggingFaceError, HuggingFaceRateLimitError) as e:
                logger.warning(
                    f"HuggingFace failed, trying Bedrock fallback: {e.message}",
                    extra={"trace_id": trace_id}
                )

        # ── Try Bedrock Nova Pro (paid fallback) ────────────────────
        try:
            return self._generate_via_bedrock(framework, app_details, trace_id)
        except Exception as e:
            logger.warning(
                f"Bedrock fallback failed, using local template: {str(e)}",
                extra={"trace_id": trace_id}
            )

        # ── Local template (100% reliable) ──────────────────────────
        return self._get_local_template(framework, trace_id)

    def _generate_via_hf(
        self,
        framework: str,
        app_details: str,
        trace_id: str,
    ) -> str:
        """Generate via HuggingFace CodeGemma API."""
        prompt = (
            f"Generate a production-ready Dockerfile for a {framework} application. "
            f"Details: {app_details}. "
            f"Only output the Dockerfile content, no explanations."
        )

        try:
            response = self.http_client.post(
                f"{self.HF_API_URL}/{self.settings.hf_codegemma_model}",
                json={
                    "inputs": prompt,
                    "parameters": {
                        "max_new_tokens": 512,
                        "temperature": 0.2,
                        "return_full_text": False,
                    },
                },
            )

            if response.status_code == 429:
                raise HuggingFaceRateLimitError(trace_id=trace_id)
            
            if response.status_code == 503:
                raise HuggingFaceError(
                    message="Model is loading, try again later",
                    trace_id=trace_id,
                )

            if response.status_code != 200:
                raise HuggingFaceError(
                    message=f"HF API error {response.status_code}: {response.text}",
                    trace_id=trace_id,
                )

            result = response.json()
            if isinstance(result, list) and len(result) > 0:
                text = result[0].get("generated_text", "")
            elif isinstance(result, dict):
                text = result.get("generated_text", "")
            else:
                text = str(result)

            # Clean up — extract just the Dockerfile content
            text = self._extract_dockerfile(text)
            if text:
                logger.info(
                    f"Generated Dockerfile via HuggingFace for {framework}",
                    extra={"trace_id": trace_id}
                )
                return text

            raise HuggingFaceError(
                message="Empty response from HuggingFace",
                trace_id=trace_id,
            )

        except httpx.TimeoutException:
            raise HuggingFaceError(
                message="HuggingFace request timed out",
                trace_id=trace_id,
            )

    def _generate_via_bedrock(
        self,
        framework: str,
        app_details: str,
        trace_id: str,
    ) -> str:
        """Generate via Bedrock Nova Pro as paid fallback."""
        from generators.bedrock_client import get_bedrock_client

        prompt = (
            f"Generate a production-ready Dockerfile for a {framework} application.\n"
            f"Details: {app_details}\n\n"
            f"Output ONLY the Dockerfile content — no explanations, no markdown.\n"
            f"Start with FROM and end with CMD or ENTRYPOINT."
        )

        response = get_bedrock_client().invoke_nova_pro(
            prompt=prompt,
            system_prompt="You are a DevOps expert. Generate only Dockerfile content.",
            max_tokens=512,
            trace_id=trace_id,
        )
        return self._extract_dockerfile(response)

    def _get_local_template(self, framework: str, trace_id: str) -> str:
        """Get a pre-built local template — 100% reliable fallback."""
        framework_lower = framework.lower()
        
        # Try exact match
        if framework_lower in DOCKERFILE_TEMPLATES:
            logger.info(
                f"Using local Dockerfile template for {framework}",
                extra={"trace_id": trace_id}
            )
            return DOCKERFILE_TEMPLATES[framework_lower]

        # Try fuzzy match
        for key, template in DOCKERFILE_TEMPLATES.items():
            if key in framework_lower or framework_lower in key:
                return template

        # Generic fallback based on likely language
        if any(kw in framework_lower for kw in ("python", "py", "pip")):
            return DOCKERFILE_TEMPLATES["generic_python"]
        elif any(kw in framework_lower for kw in ("node", "npm", "javascript", "js")):
            return DOCKERFILE_TEMPLATES["generic_node"]

        return DOCKERFILE_TEMPLATES["generic_python"]

    def _extract_dockerfile(self, text: str) -> str:
        """Extract Dockerfile content from LLM output."""
        lines = text.strip().split("\n")
        
        # Find the FROM line
        start_idx = None
        for i, line in enumerate(lines):
            if line.strip().startswith("FROM "):
                start_idx = i
                break

        if start_idx is not None:
            return "\n".join(lines[start_idx:]).strip()
        
        # If no FROM found, return cleaned text
        return text.strip()

    def generate_yaml(
        self,
        file_type: str,
        context: str,
        trace_id: str = "no-trace",
    ) -> str:
        """
        Generate YAML config files (K8s manifests, docker-compose, etc.)
        Same fallback chain as generate_dockerfile.
        """
        prompt = (
            f"Generate a {file_type} YAML file.\n"
            f"Context: {context}\n\n"
            f"Output ONLY valid YAML content — no explanations, no markdown."
        )

        # Try HuggingFace
        if self.settings.hf_token:
            try:
                response = self.http_client.post(
                    f"{self.HF_API_URL}/{self.settings.hf_codegemma_model}",
                    json={
                        "inputs": prompt,
                        "parameters": {
                            "max_new_tokens": 1024,
                            "temperature": 0.2,
                            "return_full_text": False,
                        },
                    },
                )
                if response.status_code == 200:
                    result = response.json()
                    if isinstance(result, list) and len(result) > 0:
                        text = result[0].get("generated_text", "")
                        if text.strip():
                            logger.info(
                                f"Generated {file_type} YAML via HuggingFace",
                                extra={"trace_id": trace_id}
                            )
                            return text.strip()
            except Exception as e:
                logger.warning(f"HF YAML generation failed: {e}", extra={"trace_id": trace_id})

        # Bedrock fallback
        try:
            from generators.bedrock_client import get_bedrock_client
            return get_bedrock_client().invoke_smart(
                prompt=prompt,
                system_prompt="You are a DevOps expert. Generate only valid YAML.",
                complexity="low",
                max_tokens=1024,
                trace_id=trace_id,
            )
        except Exception as e:
            logger.error(f"All YAML generation methods failed: {e}", extra={"trace_id": trace_id})
            raise HuggingFaceError(
                message=f"Failed to generate {file_type} YAML",
                trace_id=trace_id,
            )

    def close(self) -> None:
        """Close HTTP client."""
        if self._http_client:
            self._http_client.close()


# ── Singleton ───────────────────────────────────────────────────────────
_hf_client: Optional[HuggingFaceClient] = None


def get_huggingface_client() -> HuggingFaceClient:
    global _hf_client
    if _hf_client is None:
        _hf_client = HuggingFaceClient()
    return _hf_client
