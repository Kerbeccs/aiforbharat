# Kubernetes Deployment Common Issues

## Failure: ImagePullBackOff
**Cause:** Pod can't pull the Docker image from registry.
**Fix:**
1. Verify image exists in ECR: `aws ecr describe-images --repository-name <name>`
2. Check IAM permissions for EKS node group
3. Create image pull secret: `kubectl create secret docker-registry`

## Failure: CrashLoopBackOff
**Cause:** Container starts, crashes, restarts in a loop.
**Fix:**
1. Check logs: `kubectl logs <pod-name> --previous`
2. Verify environment variables are set
3. Check health probe configuration
4. Ensure startup command is correct

## Failure: Pending Pods (No Nodes Available)
**Cause:** No nodes with enough resources to schedule the pod.
**Fix:**
1. Check node resources: `kubectl describe nodes`
2. Reduce resource requests
3. Add more nodes or enable cluster autoscaler

## Resource Limits Best Practice
Set requests = what your app normally uses, limits = peak usage.
```yaml
resources:
  requests:
    cpu: "250m"
    memory: "256Mi"
  limits:
    cpu: "500m"
    memory: "512Mi"
```

## Security Best Practices
- Never run containers as root
- Use read-only filesystem where possible
- Limit capabilities
- Use network policies
