# CI/CD Pipeline — Quick Start Guide

Quick reference for common CI/CD operations.

## TL;DR

```bash
# Push to main → builds images automatically
git push origin main

# Push to develop → deploys to staging automatically
git push origin develop

# Manual production deploy → requires GitHub approval
gh workflow run deploy-production-enhanced.yml \
  -f image_tag=sha-abc123d \
  -f deployment_strategy=canary
```

## Workflows at a Glance

| Workflow | Trigger | Purpose | Approval |
|----------|---------|---------|----------|
| `ci.yml` | Push/PR main, staging, develop | Lint, test, security scan | None |
| `build-images.yml` | Push main | Build and push to ECR | None |
| `deploy-staging-enhanced.yml` | Push develop | Deploy to staging | None |
| `deploy-production-enhanced.yml` | Manual dispatch | Deploy to production | Required |
| `security-audit.yml` | Weekly Monday 9 AM | Full security audit | None |

## Common Tasks

### 1. Run CI Checks Locally

```bash
# Python linting
pip install ruff mypy
ruff check services/ shared/
mypy services/ shared/

# Python security
pip install bandit
bandit -r services/ shared/

# Dashboard linting
cd dashboard
npm ci
npx next lint
npx tsc --noEmit
```

### 2. Build an Image Locally

```bash
# Build gateway
docker build -f Dockerfile.service \
  --build-arg SERVICE_NAME=gateway \
  -t priya-global/gateway:dev .

# Build dashboard
docker build -f Dockerfile.dashboard \
  -t priya-global/dashboard:dev dashboard/

# Test image
docker run --rm priya-global/gateway:dev python -m pytest --version
```

### 3. Deploy to Staging

**Automatic:** Just push to develop
```bash
git push origin develop
```

**Manual:**
```bash
gh workflow run deploy-staging-enhanced.yml \
  -f image_tag=latest \
  -f skip_migrations=false
```

### 4. Deploy to Production

**Manual workflow dispatch:**
```bash
# Rolling deployment (default)
gh workflow run deploy-production-enhanced.yml \
  -f image_tag=sha-abc123d

# Canary deployment (10% traffic first)
gh workflow run deploy-production-enhanced.yml \
  -f image_tag=sha-abc123d \
  -f deployment_strategy=canary \
  -f canary_percentage=10

# Dry run (preview)
gh workflow run deploy-production-enhanced.yml \
  -f image_tag=sha-abc123d \
  -f dry_run=true
```

Then:
1. Check your email for approval request
2. Click "Review deployments"
3. Select "Approve and deploy"

### 5. Check Workflow Status

```bash
# List recent runs
gh run list --workflow=ci.yml --limit=10

# View specific run
gh run view <run-id> --log

# View step details
gh run view <run-id> --step=<step-number>

# Download artifacts
gh run download <run-id> -n coverage-*.xml
```

### 6. View Test Results

```bash
# Via GitHub CLI
gh run view <run-id> --json conclusion

# Via web
# Repository → Actions → Select workflow → Click run
```

### 7. View Security Results

**SARIF Results (GitHub Security tab):**
- Go to Security → Code scanning alerts

**Bandit Report:**
```bash
gh run download <run-id> -n bandit-report
unzip -p bandit-report/bandit-report.json | jq '.results[] | {test_id, issue_text, severity}'
```

**npm/pip Audit:**
```bash
gh run download <run-id> -n npm-audit-report
gh run download <run-id> -n pip-audit-report
```

### 8. Troubleshoot a Failed Job

```bash
# Get detailed logs
gh run view <run-id> --log

# View specific step
gh run view <run-id> --step=<step-id>

# Download full logs
gh run download <run-id> -p logs

# View on web for better formatting
# Repository → Actions → Select run → Click step
```

### 9. Rerun a Failed Workflow

```bash
# Rerun all jobs
gh run rerun <run-id>

# Rerun failed jobs only
gh run rerun <run-id> --failed
```

### 10. Cancel a Running Workflow

```bash
gh run cancel <run-id>
```

## Common Issues

### "Image not found in ECR"

```bash
# Make sure image was built
gh workflow run build-images.yml -f push_images=true

# Wait for build to complete
gh run watch --exit-status <run-id>

# Then deploy
gh workflow run deploy-production-enhanced.yml \
  -f image_tag=<the-tag-you-used>
```

### "Rollout timeout"

```bash
# Check pod status
kubectl get pods -n priya-core -o wide

# View pod logs
kubectl logs -n priya-core pod/priya-gateway-xxx

# Check resource usage
kubectl top nodes
kubectl top pods -n priya-core

# Restart deployment if needed
kubectl rollout restart deployment/priya-gateway -n priya-core
```

### "Smoke tests failed"

```bash
# Check deployment health
kubectl get deployments -n priya-core

# Check service connectivity
kubectl get svc -n priya-core

# Test endpoint manually
curl -v https://staging-api.currentglobal.com/health
```

### "Dependency vulnerability found"

Dependabot auto-creates PRs. Options:
1. **Let CI fix it** - Dependabot auto-merges patches
2. **Manual update** - Edit `requirements.txt` or `package.json`
3. **Ignore temporarily** - Add to workflow suppressions (not recommended)

```bash
# Update single package
pip install --upgrade <package>
npm update <package>

# See what's vulnerable
gh run download <audit-run-id> -n pip-audit-report
```

## Environment URLs

| Environment | URL | Status |
|-------------|-----|--------|
| Staging API | https://staging-api.currentglobal.com | Check via `curl` |
| Staging Dashboard | https://staging.currentglobal.com | Check via browser |
| Production API | https://api.currentglobal.com | Check via `curl` |
| Production Dashboard | https://app.currentglobal.com | Check via browser |

Health check:
```bash
curl -I https://staging-api.currentglobal.com/health
curl -I https://api.currentglobal.com/health
```

## Branch Policies

| Branch | Auto Deploys | Requires Approval |
|--------|--------------|-------------------|
| `main` | Builds images | No |
| `develop` | → Staging | No |
| `feature/*` | CI only | No |
| `hotfix/*` | CI only | No |

To deploy `main` to production:
```bash
gh workflow run deploy-production-enhanced.yml \
  -f image_tag=sha-<commit-from-main>
```

## Secrets Checklist

Verify all required secrets are set:

```bash
# List secrets (only shows existence, not values)
gh secret list

# Required secrets:
# - AWS_REGION
# - AWS_ACCOUNT_ID
# - AWS_ROLE_ARN
# - EKS_CLUSTER_NAME_STAGING
# - EKS_CLUSTER_NAME_PRODUCTION
# - SENTRY_AUTH_TOKEN
# - SENTRY_ORG
# - SENTRY_PROJECT
# - SLACK_WEBHOOK_URL
```

Add missing secret:
```bash
gh secret set SECRET_NAME --body "secret-value"
```

## Performance Tips

1. **Push only to develop for staging** - Avoids full build
2. **Use specific service deploy** - Faster than deploying all
3. **Skip migrations if not needed** - `skip_migrations=true`
4. **Batch dependency updates** - Let Dependabot group them
5. **Review test matrix** - Adjust if taking too long

## Monitoring

### Watch a deployment
```bash
gh run watch <run-id> --exit-status
```

### Get Slack notifications
Add webhook URL to secrets:
```bash
gh secret set SLACK_WEBHOOK_URL --body "https://hooks.slack.com/..."
```

### View Sentry releases
```bash
# See releases in Sentry UI
# Organization → Releases → filter by deployment
```

## Emergency Procedures

### Quick Rollback
```bash
# Immediate rollback to previous version
kubectl rollout undo deployment/priya-gateway -n priya-core
kubectl rollout undo deployment/priya-dashboard -n priya-core
```

### Scale Down Service
```bash
kubectl scale deployment/priya-gateway --replicas=0 -n priya-core
```

### Restart Service
```bash
kubectl rollout restart deployment/priya-gateway -n priya-core
```

## Getting Help

1. **Check logs**: `gh run view <run-id> --log`
2. **Review guide**: `.github/CICD_PIPELINE_GUIDE.md`
3. **Check code**: `.github/workflows/`
4. **Ask team**: Slack #platform-engineering

## Next Steps

- [ ] Set up AWS OIDC role
- [ ] Add GitHub secrets
- [ ] Test staging deployment
- [ ] Test production dry-run
- [ ] Configure Slack notifications
- [ ] Review Sentry setup
- [ ] Train team on workflows
