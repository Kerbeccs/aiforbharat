#!/bin/bash
# DevOps Butler - Build the Docker image and push it to the ECR repository.
# Run these commands after installing required CLI tools

aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin <aws_account_id>.dkr.ecr.us-west-2.amazonaws.com
docker build -t my-app:latest.
docker tag my-app:latest <aws_account_id>.dkr.ecr.us-west-2.amazonaws.com/my-app-repo:latest
docker push <aws_account_id>.dkr.ecr.us-west-2.amazonaws.com/my-app-repo:latest
