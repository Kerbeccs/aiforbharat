#!/bin/bash
# DevOps Butler - Build and push the Docker image to Amazon ECR.
# Run these commands after installing required CLI tools

aws ecr create-repository --repository-name app
docker build -t app.
aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin <ECR_REPO_URI>
docker tag app:latest <ECR_REPO_URI>:latest
docker push <ECR_REPO_URI>:latest
