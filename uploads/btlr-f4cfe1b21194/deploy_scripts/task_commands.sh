#!/bin/bash
# DevOps Butler - Build the Docker image and push it to the ECR repository.
# Run these commands after installing required CLI tools

aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <aws_account_id>.dkr.ecr.us-east-1.amazonaws.com
docker build -t flask-app.
docker tag flask-app:latest <aws_account_id>.dkr.ecr.us-east-1.amazonaws.com/flask-app-repo:latest
docker push <aws_account_id>.dkr.ecr.us-east-1.amazonaws.com/flask-app-repo:latest
