#!/bin/bash
# DevOps Butler - Build and push the Docker image to Amazon ECR.
# Run these commands after installing required CLI tools

aws ecr create-repository --repository-name flask-app
docker build -t flask-app.
docker tag flask-app:latest <AWS_ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/flask-app:latest
aws ecr get-login-password --region <REGION> | docker login --username AWS --password-stdin <AWS_ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com
docker push <AWS_ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/flask-app:latest
