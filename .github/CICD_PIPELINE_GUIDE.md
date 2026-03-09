# Priya Global Platform — CI/CD Pipeline Guide

Complete documentation for the GitHub Actions CI/CD pipeline for Priya Global.

## Overview

This CI/CD pipeline provides comprehensive automation for building, testing, securing, and deploying the Priya Global platform across staging and production environments.

### Pipeline Components

```
┌─────────────────────────────────────────────────────────────┐
│                    CI/CD Pipeline Flow                       │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  1. Trigger (Push/PR) → CI Pipeline (Lint, Test, Scan)     │
│                                ↓                             │
│  2. Build Images (main) → Build Docker Images (ECR)        │
│                                ↓                             │
│  3. Deploy Staging (develop) → Test & Validate             │
│                                ↓                             │
│  4. Deploy Production (manual) → Canary → Full Rollout     │
│                                ↓                             │
│  5. Weekly Security Audit → Report Issues                  │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## Workflows

### 1. CI Pipeline (`ci.yml`)

**Triggers:** Push to main/staging/develop, PR to main/staging/develop

**Jobs:**
- `python-lint` - Ruff lint and format checks
- `python-security` - Bandit security scans, Safety checks
- `secret-scan` - TruffleHog secret detection
- `dockerfile-lint` - Hadolint Docker validation
- `dashboard-lint` - ESLint and TypeScript checks
- `terraform-validate` - Terraform format and syntax
- `python-tests` - Pytest with coverage (service groups)
- `dashboard-tests` - Jest/Playwright tests and build
- `shared-tests` - Shared module tests
- `ci-complete` - Summary and final checks

**Key Features:**
- Parallel execution for speed
- Service group matrix for balanced test execution
- PostgreSQL and Redis test services
- Coverage reporting with artifacts
- Comprehensive linting and security checks

**Configuration:**
```yaml
Python Version: 3.12
Node.js Version: 20
Matrix: 5 service groups
Coverage: XML + term-missing
```

### 2. Build & Push Images (`build-images.yml`)

**Triggers:** Push to main, manual dispatch

**Jobs:**
- `detect-changes` - Identify modified services
- `setup-matrix` - Generate dynamic build matrix
- `build-gateway` - Build gateway API
- `build-services` - Build all microservices (parallel)
- `build-dashboard` - Build frontend
- `scan-images` - Trivy vulnerability scanning
- `build-summary` - Final report

**Key Features:**
- Smart change detection
- Docker Buildx for multi-platform builds
- ECR push with AWS OIDC authentication
- Image tagging: SHA, latest, version
- Automated vulnerability scanning

**Image Tagging:**
```
- sha-<commit-sha> (immutable)
- latest (mutable)
- v<version> (for releases)
```

### 3. Deploy to Staging (`deploy-staging-enhanced.yml`)

**Triggers:** Push to develop, manual dispatch

**Jobs:**
- `preflight` - Determine services and image tag
- `health-check` - Verify EKS cluster health
- `migrations` - Run Alembic database migrations
- `deploy` - Rolling deployment to staging
- `smoke-tests` - Post-deployment validation
- `validation` - Verify deployment
- `notify` - Slack notification

**Key Features:**
- OIDC-based AWS authentication (no stored credentials)
- Database migrations before deployment
- Health checks before proceeding
- Rolling update strategy
- Smoke test validation
- Sentry release tracking
- Slack notifications

**Configuration:**
```yaml
Environment: Staging
Update Strategy: Rolling
Rollout Timeout: 5 minutes
Health Check: Cluster + namespace verification
```

### 4. Deploy to Production (`deploy-production-enhanced.yml`)

**Triggers:** Manual workflow dispatch with approval

**Jobs:**
- `validate` - ECR image and tag validation
- `health-check` - Production cluster health
- `snapshot` - Capture current state for rollback
- `dry-run` - Preview deployment (optional)
- `deploy` - Canary/rolling/blue-green deployment
- `smoke-tests` - Production validation
- `notify` - Slack notification

**Key Features:**
- Manual approval required
- Multiple deployment strategies:
  - Rolling (default)
  - Canary (traffic shifting: 10% → 50% → 100%)
  - Blue-Green
- Automatic rollback on failure
- Health monitoring during canary
- State snapshot for rollback
- Sentry release finalization

**Configuration:**
```yaml
Environment: Production
Approval: Required
Strategies: rolling, canary, blue-green
Canary Initial: 10% (configurable)
Canary Monitor: 2 minutes
Rollback: Automatic on error
```

### 5. Security Audit (`security-audit.yml`)

**Triggers:** Weekly (Monday 9 AM UTC), manual dispatch

**Jobs:**
- `python-dependencies` - pip-audit scan
- `node-dependencies` - npm audit scan
- `container-scan` - Trivy filesystem scan
- `python-code-security` - Bandit code scan
- `create-issue` - GitHub issue for vulnerabilities
- `audit-summary` - Summary report

**Key Features:**
- Comprehensive dependency scanning
- Container vulnerability detection
- Code security analysis
- Automatic GitHub issue creation
- SARIF report generation for GitHub Security tab
- Artifact retention for 30 days

**Scan Tools:**
- `pip-audit` - Python dependencies
- `npm audit` - Node.js dependencies
- `trivy` - Container images and filesystem
- `bandit` - Python code security

### 6. Dependabot Configuration (`dependabot.yml`)

**Package Ecosystems:**
- Python (pip) - Daily checks
- Node.js (npm) - Daily checks
- GitHub Actions - Weekly checks
- Docker base images - Weekly checks

**Features:**
- Auto-merge for minor/patch updates
- Grouped dependency updates
- Development vs. production separation
- Custom commit and PR messages
- Team assignment and labels

## GitHub Secrets Required

### AWS Configuration
```
AWS_REGION                    # e.g., ap-south-1
AWS_ACCOUNT_ID                # 12-digit AWS account ID
AWS_ROLE_ARN                  # OIDC role for authentication
AWS_ACCESS_KEY_ID             # (alternative to OIDC)
AWS_SECRET_ACCESS_KEY         # (alternative to OIDC)
```

### EKS Clusters
```
EKS_CLUSTER_NAME_STAGING      # Staging cluster name
EKS_CLUSTER_NAME_PRODUCTION   # Production cluster name
```

### Sentry (Error Tracking)
```
SENTRY_AUTH_TOKEN             # Sentry API token
SENTRY_ORG                     # Organization slug
SENTRY_PROJECT                # Project name
```

### Slack Notifications
```
SLACK_WEBHOOK_URL             # Incoming webhook URL
```

## Configuration Steps

### 1. AWS OIDC Setup

Create IAM role for GitHub Actions:

```bash
# Create trust policy
cat > trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:ORG/priya-global:*"
        }
      }
    }
  ]
}
EOF

# Create role
aws iam create-role \
  --role-name github-actions-priya-global \
  --assume-role-policy-document file://trust-policy.json
```

Attach permissions:

```bash
aws iam attach-role-policy \
  --role-name github-actions-priya-global \
  --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser

aws iam attach-role-policy \
  --role-name github-actions-priya-global \
  --policy-arn arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy
```

### 2. GitHub Secrets

Add to repository settings (Settings → Secrets and variables → Actions):

```bash
gh secret set AWS_REGION --body "ap-south-1"
gh secret set AWS_ACCOUNT_ID --body "123456789012"
gh secret set AWS_ROLE_ARN --body "arn:aws:iam::123456789012:role/github-actions-priya-global"
gh secret set EKS_CLUSTER_NAME_STAGING --body "priya-global-staging"
gh secret set EKS_CLUSTER_NAME_PRODUCTION --body "priya-global-production"
gh secret set SENTRY_AUTH_TOKEN --body "your-token"
gh secret set SENTRY_ORG --body "priya-global"
gh secret set SENTRY_PROJECT --body "priya-platform"
gh secret set SLACK_WEBHOOK_URL --body "https://hooks.slack.com/..."
```

### 3. Kubernetes ServiceAccount

Create for database migrations:

```bash
kubectl create serviceaccount priya-migrations -n priya-core
kubectl create clusterrolebinding priya-migrations \
  --clusterrole=edit \
  --serviceaccount=priya-core:priya-migrations
```

## Usage Examples

### Triggering CI Pipeline

CI runs automatically on:
- Push to `main`, `staging`, `develop`
- Pull request to `main`, `staging`, `develop`

View results: Repository → Actions → CI — Lint, Scan & Test

### Building Docker Images

Push to main branch triggers build:

```bash
git commit -m "feat: Add new feature"
git push origin main
# → Triggers Build & Push Images workflow
```

Manual build trigger:

```bash
gh workflow run build-images.yml \
  -f push_images=true \
  -f service=gateway
```

### Deploying to Staging

Automatic on push to develop:

```bash
git commit -m "feature: new feature"
git push origin develop
# → Triggers Deploy to Staging
```

Manual deployment:

```bash
gh workflow run deploy-staging-enhanced.yml \
  -f service=billing \
  -f image_tag=sha-abc123d \
  -f skip_migrations=false
```

### Deploying to Production

Manual workflow dispatch (requires approval):

```bash
gh workflow run deploy-production-enhanced.yml \
  -f image_tag=sha-abc123d \
  -f deployment_strategy=canary \
  -f canary_percentage=10 \
  -f rollback_on_error=true
```

### Dry Run Deployment

Preview without making changes:

```bash
gh workflow run deploy-production-enhanced.yml \
  -f image_tag=sha-abc123d \
  -f dry_run=true
```

### Running Security Audit

Manual trigger:

```bash
gh workflow run security-audit.yml
```

Results appear as:
- GitHub issue (if vulnerabilities found)
- Artifacts (reports)
- Security tab (SARIF upload)

## Troubleshooting

### CI Pipeline Failures

1. **Lint failures:**
   ```bash
   # Run locally
   ruff check services/ shared/
   ruff format services/ shared/ --check
   ```

2. **Test failures:**
   ```bash
   # Run locally
   pytest services/gateway/tests -v
   ```

3. **Security scan issues:**
   ```bash
   # Review Bandit report
   bandit -r services/ shared/ --severity-level medium
   ```

### Build Failures

1. **Docker build error:**
   - Check Dockerfile syntax
   - Verify base image availability
   - Check build context

2. **ECR push failure:**
   - Verify AWS credentials
   - Check ECR repository exists
   - Verify image name matches policy

### Deployment Failures

1. **Cluster unreachable:**
   - Verify EKS cluster is running
   - Check kubeconfig
   - Verify security groups

2. **Rollout timeout:**
   - Check pod resources
   - Review pod logs: `kubectl logs -n namespace pod-name`
   - Check image pull status

3. **Health check failure:**
   - Verify application startup
   - Check dependent services
   - Review application logs

### Rollback

Manual rollback if needed:

```bash
kubectl rollout undo deployment/priya-gateway -n priya-core
```

## Best Practices

### Branching Strategy

```
main        → Production (auto-deploy after manual trigger)
develop     → Staging (auto-deploy)
feature/*   → Feature branches (CI only)
hotfix/*    → Hotfix branches (CI only)
```

### Commit Messages

Follow conventional commits:

```
feat: Add new payment integration
fix: Resolve database connection leak
docs: Update API documentation
chore: Update dependencies
```

### Docker Image Management

- Always push to ECR
- Use semantic versioning for releases
- Keep `latest` tag current
- Archive old images after 30 days

### Testing

- Unit tests must pass before merge
- Integration tests run on CI
- E2E tests run on staging deployment
- Coverage must not decrease

### Security

- Enable secret scanning
- Run security audit weekly
- Review Dependabot PRs
- Address critical vulnerabilities immediately

### Monitoring

- Monitor Sentry releases
- Check Slack notifications
- Review CloudWatch logs
- Track deployment metrics

## Maintenance

### Regular Tasks

- [ ] Review Dependabot PRs weekly
- [ ] Check security audit results
- [ ] Monitor CI failure rates
- [ ] Cleanup old images in ECR
- [ ] Review and rotate secrets quarterly
- [ ] Test rollback procedures monthly

### Updating Workflows

1. Create branch: `git checkout -b ci/workflow-update`
2. Update workflow file
3. Test in staging environment
4. Create PR for review
5. Merge after approval

## Support and Documentation

- **Workflow Documentation**: `.github/workflows/`
- **Script Documentation**: `scripts/` directory
- **Deployment Guide**: `DEPLOYMENT_CHECKLIST.md`
- **Kubernetes Manifests**: `terraform/` directory

## Related Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [AWS OIDC for GitHub Actions](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/about-security-hardening-with-openid-connect)
- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
- [Kubernetes Deployment Strategies](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
