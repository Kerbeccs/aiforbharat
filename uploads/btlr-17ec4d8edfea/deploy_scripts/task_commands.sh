#!/bin/bash
# DevOps Butler - Build and push Docker image to Amazon ECR.
# Run these commands after installing required CLI tools

aws ecr create-repository --repository-name flask-app
docker build -t flask-app.
docker tag flask-app:latest <ECR_REPOSITORY_URL>:latest
docker push <ECR_REPOSITORY_URL>:latest
