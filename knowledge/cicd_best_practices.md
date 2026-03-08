# CI/CD Pipeline Best Practices

## GitHub Actions for AWS Deployment
1. Store AWS credentials as GitHub Secrets
2. Use OIDC federation instead of static keys when possible
3. Run tests before build
4. Use Docker layer caching
5. Tag images with git SHA

## Common Failure: Docker Build Context Too Large
**Cause:** Entire repo (including node_modules, .git) copied as build context.
**Fix:** Create `.dockerignore` with:
```
node_modules
.git
.env
*.md
tests/
```

## Common Failure: ECR Login Expired
**Cause:** ECR auth tokens expire after 12 hours.
**Fix:** Always run `aws ecr get-login-password` in CI before docker push.

## Pipeline Template (GitHub Actions)
```yaml
name: Deploy
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1
      - uses: aws-actions/amazon-ecr-login@v2
      - run: docker build -t $ECR_REPO:$GITHUB_SHA .
      - run: docker push $ECR_REPO:$GITHUB_SHA
```
