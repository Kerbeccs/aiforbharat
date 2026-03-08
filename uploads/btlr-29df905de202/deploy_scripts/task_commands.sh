#!/bin/bash
# DevOps Butler - Build the Docker image locally and push it to the ECR repository.
# Run these commands after installing required CLI tools

docker build -t my-app:latest.
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <ecr-repo-url>
docker tag my-app:latest <ecr-repo-url>/my-app:latest
docker push <ecr-repo-url>/my-app:latest
