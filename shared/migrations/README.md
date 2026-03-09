# Alembic Database Migrations — Priya Global Platform

Comprehensive database migration system for the Priya Global Platform with multi-tenant support, Row Level Security (RLS), and full schema versioning.

## Overview

This directory contains all database migrations using Alembic, an SQLAlchemy migration tool. The system is designed to:

- **Multi-Tenant Architecture**: Every table has `tenant_id` with RLS policies
- **Immutable Audit Trail**: Track all schema changes
- **Reproducible Deployments**: Same migrations work across dev, staging, prod
- **Async Support**: Uses asyncpg for high-performance PostgreSQL
- **RLS-Aware**: Manages Row Level Security policies alongside migrations

## Directory Structure

```
shared/migrations/
├── 001_foundation.sql                 # Legacy SQL foundation
├── alembic/
│   ├── env.py                         # Alembic environment config
│   ├── script.py.mako                 # Migration template
│   ├── versions/
│   │   ├── 001_foundation_schema.py   # Core tables & RLS
│   │   ├── 002_add_onboarding_tables.py
│   │   ├── 003_add_audit_and_compliance.py
│   │   └── 004_add_international_support.py
│   └── __init__.py
└── README.md (this file)

alembic.ini                            # Alembic configuration
```

## Quick Start

### 1. Install Dependencies

```bash
pip install alembic sqlalchemy asyncpg
```

### 2. Set Up Database URL

```bash
export DATABASE_URL="postgresql+asyncpg://user:password@localhost/priya_global"
```

Or add to `.env`:
```
DATABASE_URL=postgresql+asyncpg://user:password@localhost/priya_global
```

### 3. Run Migrations

```bash
# Apply all pending migrations
./scripts/migrate.sh upgrade

# Or directly with alembic
alembic upgrade head
```

### 4. Verify Current State

```bash
./scripts/migrate.sh current
./scripts/migrate.sh history
```

## Migration Files

### 001: Foundation Schema
Creates the complete core schema:
- **Tenants**: Workspace management
- **Users**: Team members & authentication
- **Customers**: Unified customer profiles
- **Conversations**: Multi-channel conversations
- **Messages**: Unified message format
- **Knowledge Base**: RAG with vector embeddings
- **Products & Orders**: E-commerce integration
- **Audit Log**: Immutable security trail

All tables have:
- `tenant_id` for multi-tenant isolation
- Row Level Security (RLS) policies
- Proper indexes for query performance
- `created_at` and `updated_at` timestamps with auto-triggers

### 002: Onboarding Tables
Tracks customer onboarding journey:
- **onboarding_progress**: Multi-step onboarding workflow
- **channel_configurations**: Per-channel setup and credentials
- **ai_configurations**: Custom AI model settings per tenant
- **onboarding_analytics**: Journey metrics and completion rates

### 003: Audit & Compliance
GDPR and compliance tracking:
- **data_deletion_requests**: GDPR right-to-be-forgotten
- **consent_records**: Consent audit trail
- **compliance_reports**: Regulatory reports
- **detailed_audit_logs**: Enhanced audit trail
- **security_events**: Real-time security tracking

### 004: International Support
Multi-currency and localization:
- **currency_rates**: Exchange rate tracking
- **tax_configurations**: Regional tax rules
- **localization_strings**: Multi-language content
- **country_settings**: Per-country preferences
- **payment_methods**: Regional payment options

## Using the Migration Script

The `scripts/migrate.sh` helper provides convenient commands:

### Apply Migrations

```bash
# Apply all pending migrations
./scripts/migrate.sh upgrade

# Apply specific target
./scripts/migrate.sh upgrade +1           # Next migration only
./scripts/migrate.sh upgrade base         # To specific revision

# Rollback
./scripts/migrate.sh downgrade -1         # Previous version
./scripts/migrate.sh downgrade base       # To initial state
```

### Create Migrations

```bash
# Create empty migration (edit manually)
./scripts/migrate.sh create "add_new_table"

# Auto-generate from SQLAlchemy models (review before applying!)
./scripts/migrate.sh generate "auto_from_models"
```

### View State

```bash
# Current database revision
./scripts/migrate.sh current

# All migrations and their status
./scripts/migrate.sh history

# Validate all migrations
./scripts/migrate.sh test
```

### Advanced

```bash
# Stamp database at specific revision (no migration execution)
./scripts/migrate.sh stamp 001_foundation_schema

# Show migration branches
./scripts/migrate.sh branches
```

## Direct Alembic Commands

```bash
# View current revision
alembic current

# View history with timestamps
alembic history

# Apply all pending
alembic upgrade head

# Apply specific count
alembic upgrade +1

# Rollback
alembic downgrade -1

# View SQL that would be executed (dry run)
alembic upgrade head --sql

# Create new migration
alembic revision -m "description"

# Auto-generate from models
alembic revision --autogenerate -m "description"

# Stamp at specific revision
alembic stamp 001_foundation_schema
```

## Writing New Migrations

### Basic Structure

```python
"""Migration description with context.

Revision ID: 005_add_features
Revises: 004_add_international_support
Create Date: 2025-03-06
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "005_add_features"
down_revision: str = "004_add_international_support"

def upgrade() -> None:
    """Apply migration."""
    # Create tables, add columns, create indexes, etc.
    pass

def downgrade() -> None:
    """Revert migration."""
    # Drop tables, remove columns, drop indexes, etc.
    pass
```

### Key Patterns

#### Create Table with Multi-Tenant Support

```python
op.create_table(
    'my_table',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False,
              server_default=sa.text("uuid_generate_v4()")),
    sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
              server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
              server_default=sa.func.now()),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
)

# Enable RLS
op.execute("ALTER TABLE my_table ENABLE ROW LEVEL SECURITY")
op.execute("""
    CREATE POLICY my_table_tenant_isolation ON my_table
    USING (tenant_id = current_tenant_id() OR is_admin_connection())
""")

# Auto-update timestamp
op.execute("""
    CREATE TRIGGER set_updated_at_my_table BEFORE UPDATE ON my_table
    FOR EACH ROW EXECUTE FUNCTION update_updated_at()
""")
```

#### Add Index for Performance

```python
op.create_index(
    'idx_my_table_tenant_status',
    'my_table',
    ['tenant_id', 'status'],
    where="deleted_at IS NULL"
)
```

#### Add JSONB Column

```python
op.add_column(
    'tenants',
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()),
              nullable=False, server_default='{}')
)
```

## Multi-Tenant Best Practices

### Rules for Every Table

1. **Include tenant_id**
   ```python
   sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
   sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
   ```

2. **Enable RLS**
   ```python
   op.execute("ALTER TABLE my_table ENABLE ROW LEVEL SECURITY")
   op.execute("""
       CREATE POLICY my_table_tenant_isolation ON my_table
       USING (tenant_id = current_tenant_id() OR is_admin_connection())
   """)
   ```

3. **Add Timestamps**
   ```python
   sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
             server_default=sa.func.now()),
   sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
             server_default=sa.func.now()),
   ```

4. **Index Properly**
   ```python
   op.create_index('idx_my_table_tenant', 'my_table', ['tenant_id'])
   op.create_index('idx_my_table_lookup', 'my_table', ['tenant_id', 'status'])
   ```

## Testing Migrations

### Before Applying

```bash
# View what SQL will execute
alembic upgrade head --sql | head -100

# Test in separate database
# (Create test_priya_global db and test there first)
```

### After Applying

```bash
# Verify current revision
alembic current

# Check audit log for migration
SELECT * FROM audit_log WHERE action LIKE 'migration%' ORDER BY created_at DESC;

# Verify tables and indexes
\dt+  -- List tables
\di+  -- List indexes
```

### Rollback Testing

```bash
# Test downgrade in development
alembic downgrade -1

# Verify it worked
alembic current

# Re-apply
alembic upgrade head
```

## Common Tasks

### Add New Table to Existing Tenant

```bash
# Create migration
./scripts/migrate.sh create "add_new_feature_table"

# Edit the file, add your table with:
# - tenant_id FK
# - RLS policy
# - Indexes
# - Timestamps with triggers

# Apply
./scripts/migrate.sh upgrade
```

### Add Column to Existing Table

```bash
# Create migration
./scripts/migrate.sh create "add_column_to_table"

# Edit to add:
op.add_column('table_name',
    sa.Column('new_column', sa.Text(), server_default='default_value'))

# Apply
./scripts/migrate.sh upgrade
```

### Rollback Last Migration

```bash
./scripts/migrate.sh downgrade -1
```

### Emergency: Rollback to Foundation

```bash
./scripts/migrate.sh downgrade base
```

## Troubleshooting

### Migration Hangs on RLS

If a migration hangs when creating RLS policies, the current_tenant_id() function might not be set. This is OK—RLS is applied but the migration user is in "SYSTEM_ADMIN" mode.

### Foreign Key Constraint Errors

Ensure tables are created in correct order:
1. tenants
2. users (depends on tenants)
3. Other tables (depend on users or tenants)

### Vector/pgvector Errors

The `vector` extension must be created first:
```sql
CREATE EXTENSION IF NOT EXISTS "vector";
```

This is handled in migration 001.

### Alembic Not Found

```bash
pip install alembic sqlalchemy asyncpg
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

### DATABASE_URL Not Set

```bash
# Set in current shell
export DATABASE_URL="postgresql+asyncpg://user:pass@localhost/priya_global"

# Or add to .env
echo 'DATABASE_URL=postgresql+asyncpg://user:pass@localhost/priya_global' >> .env
source .env
```

## Performance Notes

### Indexes

All tables include strategic indexes:
- `tenant_id` for RLS filtering
- Combined indexes like `(tenant_id, status)` for common queries
- Partial indexes like `WHERE deleted_at IS NULL` for soft deletes

### JSONB Columns

Used for flexible, semi-structured data:
- settings, metadata, preferences
- Can be queried with SQL: `WHERE settings->>'theme' = 'dark'`
- Index with GIN if querying frequently

### Vector Embeddings

Knowledge base uses pgvector for RAG:
```python
sa.Column('embedding', postgresql.ARRAY(sa.Float()), nullable=True)
```

Query example:
```sql
SELECT * FROM knowledge_base
WHERE tenant_id = current_tenant_id()
ORDER BY embedding <=> query_embedding
LIMIT 10;
```

## Security Considerations

### RLS Policies

Every migration creates RLS policies to ensure:
- Tenants can ONLY see their own data
- `is_admin_connection()` can see all (for operations)
- PSI AI (Tenant #1) data is cryptographically isolated

### Audit Logging

- `audit_log` is append-only (INSERT only)
- No UPDATE or DELETE policies on audit_log
- All administrative changes are tracked

### Sensitive Data

Credentials and secrets are encrypted at application level:
- `credentials_encrypted` columns in channel configs
- `access_token`, `api_secret` in connections
- **Never** store plaintext secrets in migrations

## Deployment

### Development

```bash
./scripts/migrate.sh upgrade
```

### Staging

```bash
# Backup first
pg_dump $DATABASE_URL > backup.sql

# Apply
./scripts/migrate.sh upgrade

# Verify
./scripts/migrate.sh current
```

### Production

```bash
# Critical: Always backup before production migrations
pg_dump $DATABASE_URL | gzip > prod_backup_$(date +%Y%m%d_%H%M%S).sql.gz

# Verify in staging first!
# Then apply with caution
./scripts/migrate.sh upgrade

# Verify immediately
./scripts/migrate.sh current
SELECT COUNT(*) FROM audit_log WHERE action LIKE 'migration%';
```

## References

- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [SQLAlchemy Core](https://docs.sqlalchemy.org/)
- [PostgreSQL Async](https://magicstack.github.io/asyncpg/)
- [Row Level Security](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)
- [pgvector](https://github.com/pgvector/pgvector)

## Support

For issues or questions:
1. Check the Alembic docs
2. Review existing migrations for patterns
3. Test in development first
4. Always backup production before migrations
