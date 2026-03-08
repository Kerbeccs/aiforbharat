#!/bin/bash
# DevOps Butler - Build and push the Docker image to Amazon ECR.
# Run these commands after installing required CLI tools

docker build -t python-app.
docker tag python-app:latest <ECR_REPOSITORY_URI>:latest
docker push <ECR_REPOSITORY_URI>:latest
