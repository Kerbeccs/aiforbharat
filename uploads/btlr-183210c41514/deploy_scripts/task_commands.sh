#!/bin/bash
# DevOps Butler - Build the Docker image locally and push it to the ECR repository.
# Run these commands after installing required CLI tools

aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin <ecr-repo-url>
docker build -t my-app.
docker tag my-app:latest <ecr-repo-url>/my-app:latest
docker push <ecr-repo-url>/my-app:latest
