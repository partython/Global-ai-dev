# Database Migration Integration Guide

## Overview

This guide explains how to integrate the Alembic migration system into your development workflow, CI/CD pipeline, and deployment process.

## Quick Integration Steps

### 1. Update requirements.txt

Add these dependencies to your Python environment:

```
alembic==1.13.0
sqlalchemy==2.0.25
asyncpg==0.29.0
python-dotenv==1.0.0
```

Install:
```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Create or update `.env` in project root:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://priya_admin:password@localhost:5432/priya_global

# Or individual components (optional)
PG_HOST=localhost
PG_PORT=5432
PG_DATABASE=priya_global
PG_USER=priya_admin
PG_PASSWORD=your_password
PG_SSL_MODE=require
```

### 3. Initialize Database

For a new installation:

```bash
# Create database (as superuser)
createdb priya_global

# Run all migrations to create schema
./scripts/migrate.sh upgrade

# Verify
./scripts/migrate.sh current
```

### 4. Integrate with Python Application

In your application startup code:

```python
from shared.core.config import config
from shared.migrations.alembic import env
import asyncio

async def run_migrations():
    """Run pending migrations on startup."""
    import subprocess
    import os

    os.chdir('/path/to/project')
    result = subprocess.run(
        ['alembic', 'upgrade', 'head'],
        env={**os.environ, 'DATABASE_URL': config.db.dsn_async}
    )
    return result.returncode == 0

# In your app initialization:
if __name__ == "__main__":
    # Run migrations before starting
    success = asyncio.run(run_migrations())
    if not success:
        raise RuntimeError("Database migrations failed")

    # Start application
    app.run()
```

## Development Workflow

### Day-to-Day Development

#### 1. Make Schema Changes

```bash
# Create a new migration
./scripts/migrate.sh create "add_feature_xyz"

# Edit the migration file
# shared/migrations/alembic/versions/00X_add_feature_xyz.py
```

#### 2. Update Migration

```python
def upgrade() -> None:
    """Add feature XYZ tables."""
    op.create_table(
        'feature_xyz',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        # ... other columns
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.execute("ALTER TABLE feature_xyz ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY feature_xyz_tenant_isolation ON feature_xyz
        USING (tenant_id = current_tenant_id() OR is_admin_connection())
    """)

def downgrade() -> None:
    """Remove feature XYZ tables."""
    op.execute("DROP TABLE IF EXISTS feature_xyz CASCADE")
```

#### 3. Test Migration

```bash
# Apply in development
./scripts/migrate.sh upgrade

# Verify
./scripts/migrate.sh current
psql -d priya_global -c "\dt+"

# Test downgrade
./scripts/migrate.sh downgrade -1

# Re-apply
./scripts/migrate.sh upgrade
```

#### 4. Commit to Version Control

```bash
git add shared/migrations/alembic/versions/00X_add_feature_xyz.py
git commit -m "feat: add feature XYZ table"
git push
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Database Migrations

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  test-migrations:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_DB: priya_global_test
          POSTGRES_USER: priya_admin
          POSTGRES_PASSWORD: test_password
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt

      - name: Test migrations
        env:
          DATABASE_URL: postgresql+asyncpg://priya_admin:test_password@localhost:5432/priya_global_test
        run: |
          cd ${{ github.workspace }}

          # Check if migrations are pending
          alembic current

          # Apply all migrations
          alembic upgrade head

          # Validate no errors
          alembic current

          # Test downgrade
          alembic downgrade -1

          # Re-apply
          alembic upgrade head

      - name: Validate schema
        env:
          DATABASE_URL: postgresql://priya_admin:test_password@localhost:5432/priya_global_test
        run: |
          psql "$DATABASE_URL" -c "\dt+" | grep -q "tenants"
          psql "$DATABASE_URL" -c "\dt+" | grep -q "users"
          psql "$DATABASE_URL" -c "\dt+" | grep -q "conversations"
          echo "Schema validation passed"
```

### GitLab CI Example

```yaml
test-migrations:
  image: python:3.11
  services:
    - postgres:15
  variables:
    POSTGRES_DB: priya_global_test
    POSTGRES_USER: priya_admin
    POSTGRES_PASSWORD: test_password
    POSTGRES_HOST_AUTH_METHOD: trust
    DATABASE_URL: postgresql+asyncpg://priya_admin:test_password@postgres:5432/priya_global_test
  script:
    - pip install -r requirements.txt
    - alembic current
    - alembic upgrade head
    - alembic current
    - alembic downgrade -1
    - alembic upgrade head
  only:
    - main
    - develop
```

## Deployment Process

### Pre-Deployment Checklist

```bash
# 1. Backup production database
pg_dump $DATABASE_URL_PROD | gzip > backup_$(date +%Y%m%d_%H%M%S).sql.gz

# 2. Test migrations in staging
export DATABASE_URL=$DATABASE_URL_STAGING
./scripts/migrate.sh upgrade

# 3. Verify staging application still works
curl https://staging.priyaai.com/health

# 4. Test rollback
./scripts/migrate.sh downgrade -1
./scripts/migrate.sh upgrade

# 5. Confirm all tests pass
pytest tests/
```

### Staging Deployment

```bash
#!/bin/bash
set -e

export DATABASE_URL=$DATABASE_URL_STAGING

echo "Running migrations in staging..."
./scripts/migrate.sh upgrade

echo "Verifying schema..."
./scripts/migrate.sh current

echo "Running application tests..."
pytest tests/

echo "Staging deployment successful!"
```

### Production Deployment

```bash
#!/bin/bash
set -e

# Backup
BACKUP_FILE="backup_prod_$(date +%Y%m%d_%H%M%S).sql.gz"
echo "Backing up production database..."
pg_dump $DATABASE_URL_PROD | gzip > $BACKUP_FILE
echo "Backup saved: $BACKUP_FILE"

# Apply migrations with timeout
export DATABASE_URL=$DATABASE_URL_PROD
timeout 600 ./scripts/migrate.sh upgrade || {
    echo "Migrations failed! Rolling back..."
    gunzip < $BACKUP_FILE | psql $DATABASE_URL_PROD
    exit 1
}

# Verify
echo "Verifying production schema..."
./scripts/migrate.sh current

# Health check
echo "Running health checks..."
curl https://app.priyaai.com/health || {
    echo "Health check failed!"
    exit 1
}

echo "Production deployment successful!"
```

## Development Tools

### Visual Studio Code

Add to `.vscode/settings.json`:

```json
{
    "python.linting.pylintEnabled": true,
    "python.linting.pylintArgs": [
        "--load-plugins=pylint_sqlalchemy"
    ],
    "python.formatting.provider": "black",
    "[python]": {
        "editor.formatOnSave": true,
        "editor.defaultFormatter": "ms-python.python"
    }
}
```

### Pre-commit Hooks

Create `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.4.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files

  - repo: https://github.com/psf/black
    rev: 23.3.0
    hooks:
      - id: black
        language_version: python3.11

  - repo: https://github.com/PyCQA/isort
    rev: 5.12.0
    hooks:
      - id: isort

  - repo: https://github.com/sqlalchemyorg/sqlalchemy
    rev: rel_2_0_25
    hooks:
      - id: sqlalchemy-check
```

Install:
```bash
pre-commit install
```

## Database Cloning

### Clone Production Schema to Development

```bash
#!/bin/bash

# Dump production schema only (no data)
pg_dump -s $DATABASE_URL_PROD | \
  # Remove GRANT statements
  grep -v "^GRANT\|^REVOKE" | \
  # Apply to development
  psql $DATABASE_URL_DEV

echo "Schema cloned from production to development"
```

### Clone with Sample Data

```bash
#!/bin/bash

# Dump production (schema + sample data)
pg_dump $DATABASE_URL_PROD | \
  # Extract only first 1000 rows per table
  # (This is pseudo-code; use pg_partman or other tools for real use)
  psql $DATABASE_URL_DEV

echo "Production clone completed"
```

## Troubleshooting

### Migration Fails

```bash
# View detailed SQL
alembic upgrade head --sql | head -100

# Check current state
alembic current

# View history
alembic history

# Manually check database
psql $DATABASE_URL -c "\dt+"
```

### Stuck Migration

```bash
# Kill blocking queries
psql $DATABASE_URL -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE query != current_query AND state = 'active';"

# Retry migration
./scripts/migrate.sh upgrade
```

### Rollback Required

```bash
# Safe downgrade
./scripts/migrate.sh downgrade -1

# Or to specific revision
./scripts/migrate.sh downgrade 001_foundation_schema
```

### Restore from Backup

```bash
# Restore from backup
gunzip < backup_20250306_120000.sql.gz | psql $DATABASE_URL

# Verify restoration
alembic current

# Re-apply migrations if needed
./scripts/migrate.sh upgrade
```

## Best Practices

### Do's

- ✓ Always backup before production migrations
- ✓ Test migrations in development and staging first
- ✓ Keep migration history in version control
- ✓ Write descriptive migration comments
- ✓ Include downgrade() for all migrations
- ✓ Use transactions (Alembic handles this)
- ✓ Test both upgrade and downgrade
- ✓ Review auto-generated migrations
- ✓ Keep migrations small and focused
- ✓ Document non-obvious changes

### Don'ts

- ✗ Don't modify past migrations (rebase if needed)
- ✗ Don't run migrations manually (use scripts)
- ✗ Don't skip migrations in production
- ✗ Don't drop tables without backup
- ✗ Don't add constraints without testing
- ✗ Don't ignore downgrade() implementation
- ✗ Don't mix data and schema changes
- ✗ Don't deploy without testing downgrade
- ✗ Don't use raw SQL without reviewing
- ✗ Don't forget to update documentation

## Multi-Environment Setup

### Development
```
DATABASE_URL=postgresql+asyncpg://priya_admin:dev_password@localhost:5432/priya_global_dev
```

### Staging
```
DATABASE_URL=postgresql+asyncpg://priya_admin:staging_password@staging-db.internal:5432/priya_global_staging
```

### Production
```
DATABASE_URL=postgresql+asyncpg://priya_admin:prod_password@prod-db.internal:5432/priya_global_prod
```

## Useful SQL Commands

### Check Schema
```sql
-- List all tables
\dt

-- Detailed table info
\dt+

-- List indexes
\di+

-- View RLS policies
SELECT * FROM pg_policies;

-- Check triggers
SELECT * FROM information_schema.triggers;
```

### Data Verification
```sql
-- Check row count per table
SELECT schemaname, tablename,
  (SELECT count(*) FROM pg_class WHERE relname=tablename) as rows
FROM pg_tables;

-- Verify RLS is working
SET app.current_tenant_id = 'your-tenant-id';
SELECT COUNT(*) FROM customers;

-- Check current tenant
SELECT current_setting('app.current_tenant_id');
```

## Emergency Procedures

### Complete Downgrade
```bash
# Back to initial state (if migration 001 is base)
./scripts/migrate.sh downgrade base

# Or use alembic directly
alembic downgrade base
```

### Reset Database
```bash
# WARNING: Deletes all data!
psql $DATABASE_URL -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

# Re-create from migrations
./scripts/migrate.sh upgrade
```

## References

- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [PostgreSQL Async](https://magicstack.github.io/asyncpg/)
- [GitHub Actions](https://docs.github.com/en/actions)
- [GitLab CI](https://docs.gitlab.com/ee/ci/)

## Support

For issues or questions:
1. Review `/shared/migrations/README.md` (comprehensive guide)
2. Check ALEMBIC_SETUP.md (system overview)
3. Review existing migration files for patterns
4. Consult Alembic documentation
5. Test in development first
