# ECS Fargate Deployment Best Practices

## When to Use ECS Fargate
- Single-service applications
- Containers that don't need Kubernetes complexity
- Cost-effective for 1-3 services
- When you want AWS-managed infrastructure

## Common Failure: Task Definition Memory
**Problem:** Tasks OOM-killed because container memory exceeds task memory.
**Solution:** Set task memory = container memory + 256MB buffer.
**Example:** If your app needs 512MB, set task memory to 768MB.

## Common Failure: Health Check Timeout
**Problem:** ALB health check fails because app takes too long to start.
**Solution:** Set health check grace period to 120s and increase deregistration delay.

## Dockerfile Best Practices
- Use multi-stage builds to reduce image size
- Pin base image versions (never use :latest)
- Copy dependency files before code for layer caching
- Use non-root user for security

## Cost Optimization
- Use Fargate Spot for non-critical workloads (70% savings)
- Right-size task CPU/memory
- Use ALB without NAT Gateway when possible
