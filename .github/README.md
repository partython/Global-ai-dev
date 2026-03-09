# Priya Global Platform — GitHub Configuration

Complete GitHub Actions CI/CD pipeline configuration for automated building, testing, security scanning, and deployment.

## Directory Structure

```
.github/
├── workflows/              # GitHub Actions workflow definitions
│   ├── ci.yml                          # CI pipeline (lint, test, security)
│   ├── build-images.yml                # Build and push Docker images
│   ├── deploy-staging.yml              # Deploy to staging (original)
│   ├── deploy-staging-enhanced.yml     # Deploy to staging (enhanced with OIDC)
│   ├── deploy-production.yml           # Deploy to production (original)
│   ├── deploy-production-enhanced.yml # Deploy to production (enhanced)
│   ├── security-audit.yml              # Weekly security audit
│   └── build-push.yml                  # Legacy build workflow
├── dependabot.yml          # Dependabot configuration for dependency updates
├── README.md              # This file
├── CICD_PIPELINE_GUIDE.md # Comprehensive CI/CD documentation
└── QUICK_START.md         # Quick reference for common tasks
```

## Quick Links

- **New to CI/CD?** → Start with [`QUICK_START.md`](./QUICK_START.md)
- **Need full details?** → Read [`CICD_PIPELINE_GUIDE.md`](./CICD_PIPELINE_GUIDE.md)
- **Troubleshooting?** → Check [`CICD_PIPELINE_GUIDE.md#troubleshooting`](./CICD_PIPELINE_GUIDE.md#troubleshooting)

## Pipeline Overview

### Flow Diagram

```
Code Push
    ↓
CI Pipeline (Lint + Security + Test)
    ├─ Success ─→ Build Docker Images
    │               ├─ Gateway
    │               ├─ Microservices (parallel)
    │               └─ Dashboard
    │                   ↓
    │           Push to ECR
    │
    └─ Failure ─→ Notify + Stop

Push to develop
    ↓
Deploy to Staging (automatic)
    ├─ Pre-flight checks
    ├─ Database migrations
    ├─ Rolling deployment
    ├─ Smoke tests
    └─ Slack notification

Manual trigger
    ↓
Deploy to Production (with approval)
    ├─ Image validation
    ├─ Cluster health check
    ├─ Snapshot current state
    ├─ Canary deployment (10% → 50% → 100%)
    ├─ Health monitoring
    ├─ Rollback on failure
    ├─ Smoke tests
    └─ Slack notification

Weekly (Monday 9 AM UTC)
    ↓
Security Audit
    ├─ Python dependencies
    ├─ Node.js dependencies
    ├─ Container images
    ├─ Code security
    └─ Create GitHub issue if vulnerabilities found
```

## Workflows

### 1. CI Pipeline (`workflows/ci.yml`)

**What:** Lint, test, and security scan on every commit

**Triggers:**
- Push to `main`, `staging`, `develop`
- Pull request to `main`, `staging`, `develop`

**What it does:**
1. Python linting (ruff) and formatting
2. Python security scan (bandit, safety)
3. Secret detection (TruffleHog)
4. Dockerfile linting (hadolint)
5. Dashboard linting (ESLint, TypeScript)
6. Terraform validation
7. Python unit tests (services, shared modules)
8. Dashboard tests (Jest, build verification)
9. Final CI summary

**Example:**
```bash
git push origin main
# → Workflow automatically starts
# → GitHub shows status checks on PR or in Actions tab
```

### 2. Build Docker Images (`workflows/build-images.yml`)

**What:** Build and push Docker images to ECR

**Triggers:**
- Push to `main`
- Manual workflow dispatch

**What it does:**
1. Detect changed services
2. Build gateway service
3. Build all microservices (parallel)
4. Build dashboard frontend
5. Scan images for vulnerabilities (Trivy)
6. Push to ECR with tags (SHA, latest, version)

**Example:**
```bash
git push origin main
# → Images automatically built and pushed to ECR
```

### 3. Deploy to Staging (`workflows/deploy-staging-enhanced.yml`)

**What:** Deploy to staging environment

**Triggers:**
- Push to `develop` branch
- Manual workflow dispatch

**What it does:**
1. Pre-flight checks (validate image tags, determine services)
2. EKS cluster health check
3. Run database migrations
4. Rolling deployment
5. Wait for rollout (5m timeout)
6. Run smoke tests
7. Post-deployment validation
8. Slack notification

**Example:**
```bash
git push origin develop
# → Automatically deploys to staging

# Or manual
gh workflow run deploy-staging-enhanced.yml \
  -f image_tag=latest \
  -f skip_migrations=false
```

**Configuration:**
```
Environment: Staging
URL: https://staging.currentglobal.com
Strategy: Rolling update
Timeout: 5 minutes
```

### 4. Deploy to Production (`workflows/deploy-production-enhanced.yml`)

**What:** Deploy to production with manual approval

**Triggers:**
- Manual workflow dispatch only
- Requires GitHub environment approval

**What it does:**
1. Validate image tag in ECR
2. Cluster health check
3. Snapshot current deployment (for rollback)
4. Optional dry-run validation
5. Canary/rolling/blue-green deployment (configurable)
6. Monitor canary health (2 minutes)
7. Automatic rollback on failure
8. Production smoke tests
9. Sentry release finalization
10. Slack notification

**Example:**
```bash
# Canary deployment (10% traffic, then expand)
gh workflow run deploy-production-enhanced.yml \
  -f image_tag=sha-abc123d \
  -f deployment_strategy=canary \
  -f canary_percentage=10

# Rolling deployment (gradual pod replacement)
gh workflow run deploy-production-enhanced.yml \
  -f image_tag=sha-abc123d \
  -f deployment_strategy=rolling

# Dry run (preview without deploying)
gh workflow run deploy-production-enhanced.yml \
  -f image_tag=sha-abc123d \
  -f dry_run=true
```

**Configuration:**
```
Environment: Production
URL: https://app.currentglobal.com
Approval: Required
Strategies: rolling (default), canary, blue-green
Rollback: Automatic on health check failure
```

### 5. Security Audit (`workflows/security-audit.yml`)

**What:** Comprehensive security scanning

**Triggers:**
- Weekly (Monday 9 AM UTC)
- Manual workflow dispatch

**What it does:**
1. Scan Python dependencies (pip-audit)
2. Scan Node.js dependencies (npm audit)
3. Scan container images (Trivy)
4. Scan Python code (Bandit)
5. Create GitHub issue if vulnerabilities found
6. Upload SARIF to GitHub Security tab
7. Retain reports for 30 days

**Example:**
```bash
# Manual trigger
gh workflow run security-audit.yml

# Results: GitHub issue created if vulnerabilities found
# View: Repository → Security → Code scanning alerts
```

## Configuration

### Required GitHub Secrets

Add these to `Settings → Secrets and variables → Actions`:

```yaml
# AWS
AWS_REGION                    # e.g., ap-south-1
AWS_ACCOUNT_ID                # 12-digit account ID
AWS_ROLE_ARN                  # OIDC role (recommended)

# EKS
EKS_CLUSTER_NAME_STAGING      # Staging cluster
EKS_CLUSTER_NAME_PRODUCTION   # Production cluster

# Sentry (error tracking)
SENTRY_AUTH_TOKEN             # API token
SENTRY_ORG                    # Organization slug
SENTRY_PROJECT                # Project name

# Slack notifications
SLACK_WEBHOOK_URL             # Incoming webhook
```

**Set secrets via CLI:**
```bash
gh secret set AWS_REGION --body "ap-south-1"
gh secret set AWS_ACCOUNT_ID --body "123456789012"
gh secret set AWS_ROLE_ARN --body "arn:aws:iam::..."
# ... etc
```

### Dependabot Configuration

File: `dependabot.yml`

**Updates:**
- Python (pip) - daily
- Node.js (npm) - daily
- GitHub Actions - weekly
- Docker - weekly

**Features:**
- Auto-merge for minor/patch updates
- Grouped updates
- Development dependencies separated

## Usage

### For Developers

1. **Make changes** → CI pipeline runs automatically
2. **Review lint/test results** → Fix any issues
3. **Push to develop** → Auto-deploys to staging
4. **Deploy to production** → Manual workflow dispatch with approval

### For DevOps/SRE

1. **Monitor workflows** → `gh run list`
2. **Check logs** → `gh run view <id> --log`
3. **Trigger deployments** → `gh workflow run deploy-production-enhanced.yml ...`
4. **Review security audits** → GitHub Security tab
5. **Manage Dependabot** → Review and merge dependency PRs

### Checking Status

```bash
# List recent workflows
gh run list --limit 20

# Watch a specific run
gh run watch <run-id> --exit-status

# Download artifacts
gh run download <run-id> -n coverage-*.xml

# View logs
gh run view <run-id> --log
```

## Deployment Strategies

### Rolling (Recommended for most cases)
- Gradual pod replacement
- Zero downtime
- Quick rollback if needed
- Default strategy

### Canary (Recommended for critical changes)
- Initial 10% traffic to new version
- Monitor for 2 minutes
- Expand to 50% if healthy
- Full rollout if monitoring passes
- Automatic rollback on failure

### Blue-Green (For instant switchover)
- Run both versions in parallel
- Switch all traffic at once
- Quick rollback by switching back
- More resource intensive

## Troubleshooting

### CI Failures

**Python lint error:**
```bash
ruff check services/ shared/ --fix
git add .
git commit -m "fix: resolve lint issues"
```

**Test failures:**
```bash
pytest services/gateway/tests -v
# Fix issues locally, then push
```

**Security scan warning:**
```bash
# Review Bandit report
gh run download <run-id> -n bandit-security-report
```

### Build Failures

**Docker build error:**
- Check base images are accessible
- Verify Dockerfile syntax
- Test locally: `docker build -f Dockerfile.service .`

**ECR push failure:**
- Verify AWS credentials/OIDC role
- Check ECR repository exists
- Confirm image name matches policy

### Deployment Failures

**Cluster unreachable:**
```bash
kubectl cluster-info
kubectl get nodes
```

**Pod not starting:**
```bash
kubectl describe pod <pod-name> -n <namespace>
kubectl logs <pod-name> -n <namespace>
```

**Timeout on rollout:**
- Check pod resources
- Review application startup time
- Increase timeout if needed

## Best Practices

1. **Commit messages** → Use conventional commits (`feat:`, `fix:`, `docs:`)
2. **Branch naming** → `feature/name`, `hotfix/name`
3. **Testing** → Run locally before pushing
4. **Security** → Never commit secrets (use GitHub secrets)
5. **Reviews** → Require approval for main/develop merges
6. **Monitoring** → Check Slack notifications
7. **Documentation** → Update deployment docs with changes

## Common Commands

```bash
# Trigger CI pipeline (automatic)
git push origin feature/my-feature

# Deploy to staging (automatic)
git push origin develop

# Manual staging deployment
gh workflow run deploy-staging-enhanced.yml -f image_tag=latest

# Production deployment (with approval)
gh workflow run deploy-production-enhanced.yml \
  -f image_tag=sha-abc123d \
  -f deployment_strategy=canary

# Check workflow status
gh run list --workflow=ci.yml --limit=10

# View workflow logs
gh run view <run-id> --log

# Cancel running workflow
gh run cancel <run-id>

# Rerun failed workflow
gh run rerun <run-id> --failed
```

## Environment Information

| Env | API Endpoint | Dashboard | EKS Cluster |
|-----|--------------|-----------|-------------|
| Staging | https://staging-api.currentglobal.com | https://staging.currentglobal.com | priya-global-staging |
| Production | https://api.currentglobal.com | https://app.currentglobal.com | priya-global-production |

## Support

- **Issues?** → Review `CICD_PIPELINE_GUIDE.md#troubleshooting`
- **Quick help?** → Check `QUICK_START.md`
- **Full docs?** → Read `CICD_PIPELINE_GUIDE.md`
- **Slack?** → Ask in #platform-engineering
- **Issues?** → Create GitHub issue with workflow logs

## Files Reference

| File | Purpose |
|------|---------|
| `workflows/ci.yml` | Lint, test, security scan |
| `workflows/build-images.yml` | Build Docker images |
| `workflows/deploy-staging-enhanced.yml` | Staging deployment (OIDC) |
| `workflows/deploy-production-enhanced.yml` | Production deployment (OIDC) |
| `workflows/security-audit.yml` | Weekly security scan |
| `dependabot.yml` | Dependency update configuration |
| `CICD_PIPELINE_GUIDE.md` | Complete documentation |
| `QUICK_START.md` | Quick reference |
| `README.md` | This file |

## Version Info

- **Created:** 2026-03-07
- **Python:** 3.12
- **Node.js:** 20
- **GitHub Actions:** Latest (v4)
- **Docker:** Multi-platform support
- **AWS:** OIDC authentication

---

**Last Updated:** 2026-03-07
**Status:** Production-ready
**Maintained By:** Platform Engineering Team
