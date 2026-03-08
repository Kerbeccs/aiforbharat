"""
DevOps Butler - AWS Client
Boto3 operations for common AWS services: ECR, ECS, EC2, S3, etc.

NOTE: If IAM credentials are not set, this client will attempt to use
the default credential chain (env vars, instance profile, etc.).
Operations that require IAM will fail gracefully if no credentials are available.
"""

import json
import time
import logging
from typing import Dict, Any, Optional, List

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from config.settings import get_settings
from config.logging_config import get_logger
from core.exceptions import ExecutionError

logger = get_logger("aws_client")


class AWSClient:
    """
    Wrapper around boto3 for common AWS operations.
    Handles missing credentials gracefully — operations that need IAM
    will return clear error messages instead of crashing.
    """

    def __init__(self):
        self.settings = get_settings()
        self._clients: Dict[str, Any] = {}
        self._credentials_available: Optional[bool] = None

    def _get_client(self, service: str):
        """Get or create boto3 client for a service."""
        if service not in self._clients:
            kwargs = {"region_name": self.settings.aws_region}

            # Only pass explicit credentials if they are set
            if self.settings.aws_access_key_id and self.settings.aws_secret_access_key:
                kwargs["aws_access_key_id"] = self.settings.aws_access_key_id
                kwargs["aws_secret_access_key"] = self.settings.aws_secret_access_key

            # Otherwise boto3 will try the default credential chain
            # (env vars, ~/.aws/credentials, instance profile, etc.)
            self._clients[service] = boto3.client(service, **kwargs)
        return self._clients[service]

    def has_credentials(self) -> bool:
        """Check if AWS credentials are available (IAM or default chain)."""
        if self._credentials_available is not None:
            return self._credentials_available

        try:
            sts = self._get_client("sts")
            sts.get_caller_identity()
            self._credentials_available = True
            logger.info("AWS IAM credentials verified")
            return True
        except (ClientError, NoCredentialsError, Exception) as e:
            logger.warning(f"AWS IAM credentials not available: {e}")
            self._credentials_available = False
            return False

    def _require_credentials(self, operation: str, trace_id: str = "no-trace"):
        """Check credentials before an operation, raise clear error if missing."""
        if not self.has_credentials():
            raise ExecutionError(
                f"AWS IAM credentials required for {operation}. "
                f"Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in .env, "
                f"or use the Browser Agent to perform this operation via AWS Console.",
                trace_id=trace_id,
            )

    # ── ECR (Container Registry) ────────────────────────────────────

    def create_ecr_repository(
        self,
        repo_name: str,
        trace_id: str = "no-trace",
    ) -> Dict[str, Any]:
        """Create an ECR repository for Docker images."""
        self._require_credentials("ECR create_repository", trace_id)
        ecr = self._get_client("ecr")
        try:
            response = ecr.create_repository(
                repositoryName=repo_name,
                imageTagMutability="MUTABLE",
                imageScanningConfiguration={"scanOnPush": True},
                tags=[
                    {"Key": "Project", "Value": "devops-butler"},
                    {"Key": "ManagedBy", "Value": "butler"},
                    {"Key": "TraceId", "Value": trace_id},
                ],
            )
            repo = response["repository"]
            logger.info(
                f"Created ECR repo: {repo['repositoryUri']}",
                extra={"trace_id": trace_id}
            )
            return {
                "repository_uri": repo["repositoryUri"],
                "registry_id": repo["registryId"],
                "repository_name": repo_name,
            }
        except ClientError as e:
            if e.response["Error"]["Code"] == "RepositoryAlreadyExistsException":
                desc = ecr.describe_repositories(repositoryNames=[repo_name])
                repo = desc["repositories"][0]
                logger.info(f"ECR repo already exists: {repo['repositoryUri']}", extra={"trace_id": trace_id})
                return {
                    "repository_uri": repo["repositoryUri"],
                    "registry_id": repo["registryId"],
                    "repository_name": repo_name,
                }
            raise ExecutionError(
                f"ECR create failed: {str(e)}",
                trace_id=trace_id,
            )

    def get_ecr_login_command(self, trace_id: str = "no-trace") -> str:
        """Get the docker login command for ECR."""
        self._require_credentials("ECR get-login-password", trace_id)
        ecr = self._get_client("ecr")
        response = ecr.get_authorization_token()
        auth = response["authorizationData"][0]
        endpoint = auth["proxyEndpoint"]
        return f"aws ecr get-login-password --region {self.settings.aws_region} | docker login --username AWS --password-stdin {endpoint}"

    # ── S3 ──────────────────────────────────────────────────────────

    def create_s3_bucket(
        self,
        bucket_name: str,
        trace_id: str = "no-trace",
    ) -> Dict[str, Any]:
        """Create an S3 bucket."""
        self._require_credentials("S3 create_bucket", trace_id)
        s3 = self._get_client("s3")
        try:
            create_args = {"Bucket": bucket_name}
            if self.settings.aws_region != "us-east-1":
                create_args["CreateBucketConfiguration"] = {
                    "LocationConstraint": self.settings.aws_region
                }
            s3.create_bucket(**create_args)

            s3.put_bucket_tagging(
                Bucket=bucket_name,
                Tagging={
                    "TagSet": [
                        {"Key": "Project", "Value": "devops-butler"},
                        {"Key": "TraceId", "Value": trace_id},
                    ]
                },
            )
            logger.info(f"Created S3 bucket: {bucket_name}", extra={"trace_id": trace_id})
            return {"bucket_name": bucket_name, "region": self.settings.aws_region}
        except ClientError as e:
            if "BucketAlreadyOwnedByYou" in str(e):
                return {"bucket_name": bucket_name, "region": self.settings.aws_region}
            raise ExecutionError(f"S3 create failed: {str(e)}", trace_id=trace_id)

    def upload_to_s3(
        self,
        bucket: str,
        key: str,
        file_path: str = "",
        content: str = "",
        trace_id: str = "no-trace",
    ) -> Dict[str, Any]:
        """Upload a file or content to S3."""
        self._require_credentials("S3 upload", trace_id)
        s3 = self._get_client("s3")
        try:
            if file_path:
                s3.upload_file(file_path, bucket, key)
            elif content:
                s3.put_object(Bucket=bucket, Key=key, Body=content.encode("utf-8"))

            logger.info(f"Uploaded to s3://{bucket}/{key}", extra={"trace_id": trace_id})
            return {"bucket": bucket, "key": key, "url": f"s3://{bucket}/{key}"}
        except ClientError as e:
            raise ExecutionError(f"S3 upload failed: {str(e)}", trace_id=trace_id)

    # ── ECS (Container Service) ─────────────────────────────────────

    def create_ecs_cluster(
        self,
        cluster_name: str,
        trace_id: str = "no-trace",
    ) -> Dict[str, Any]:
        """Create an ECS cluster."""
        self._require_credentials("ECS create_cluster", trace_id)
        ecs = self._get_client("ecs")
        try:
            response = ecs.create_cluster(
                clusterName=cluster_name,
                tags=[
                    {"key": "Project", "value": "devops-butler"},
                    {"key": "TraceId", "value": trace_id},
                ],
            )
            logger.info(f"Created ECS cluster: {cluster_name}", extra={"trace_id": trace_id})
            return {
                "cluster_name": cluster_name,
                "cluster_arn": response["cluster"]["clusterArn"],
            }
        except ClientError as e:
            raise ExecutionError(f"ECS cluster create failed: {str(e)}", trace_id=trace_id)

    # ── Resource Listing (for rollback) ─────────────────────────────

    def list_resources_by_tag(
        self,
        tag_key: str = "TraceId",
        tag_value: str = "",
        trace_id: str = "no-trace",
    ) -> List[Dict[str, str]]:
        """List all resources with a specific tag (for rollback tracking)."""
        try:
            if not self.has_credentials():
                return []
            tagging = self._get_client("resourcegroupstaggingapi")
            response = tagging.get_resources(
                TagFilters=[{"Key": tag_key, "Values": [tag_value]}],
            )
            resources = []
            for item in response.get("ResourceTagMappingList", []):
                resources.append({
                    "arn": item["ResourceARN"],
                    "tags": {t["Key"]: t["Value"] for t in item.get("Tags", [])},
                })
            return resources
        except Exception as e:
            logger.warning(f"Failed to list tagged resources: {e}", extra={"trace_id": trace_id})
            return []

    # ── Cleanup ─────────────────────────────────────────────────────

    def delete_ecr_repository(self, repo_name: str, trace_id: str = "no-trace") -> None:
        """Delete an ECR repository (for rollback)."""
        if not self.has_credentials():
            logger.warning("Cannot rollback ECR: no IAM credentials", extra={"trace_id": trace_id})
            return
        ecr = self._get_client("ecr")
        try:
            ecr.delete_repository(repositoryName=repo_name, force=True)
            logger.info(f"Deleted ECR repo: {repo_name}", extra={"trace_id": trace_id})
        except ClientError as e:
            logger.warning(f"ECR delete failed: {e}", extra={"trace_id": trace_id})

    def delete_s3_bucket(self, bucket_name: str, trace_id: str = "no-trace") -> None:
        """Delete an S3 bucket (for rollback). Must be empty or force delete."""
        if not self.has_credentials():
            logger.warning("Cannot rollback S3: no IAM credentials", extra={"trace_id": trace_id})
            return
        s3 = self._get_client("s3")
        try:
            # Delete all objects first
            kwargs = {"region_name": self.settings.aws_region}
            if self.settings.aws_access_key_id and self.settings.aws_secret_access_key:
                kwargs["aws_access_key_id"] = self.settings.aws_access_key_id
                kwargs["aws_secret_access_key"] = self.settings.aws_secret_access_key

            s3r = boto3.resource("s3", **kwargs)
            bucket = s3r.Bucket(bucket_name)
            bucket.objects.all().delete()
            bucket.delete()
            logger.info(f"Deleted S3 bucket: {bucket_name}", extra={"trace_id": trace_id})
        except ClientError as e:
            logger.warning(f"S3 delete failed: {e}", extra={"trace_id": trace_id})


# ── Singleton ───────────────────────────────────────────────────────────
_aws_client: Optional[AWSClient] = None


def get_aws_client() -> AWSClient:
    global _aws_client
    if _aws_client is None:
        _aws_client = AWSClient()
    return _aws_client
