"""
010 — Developer Portal Tables

Tables:
- developer_api_keys: API key management for developer accounts
- plugin_submissions: Plugin submission workflow with review
- developer_usage_logs: API usage tracking per developer
- sandbox_logs: Sandbox test execution history

Indexes:
- B-tree on (developer_id) for developer-scoped queries
- Unique on (key_hash) for fast key lookup
- B-tree on (status) for submission filtering

Security:
- developer_api_keys stores only SHA-256 hashes (never plaintext)
- All tables reference developers(id) with CASCADE
"""

from alembic import op
import sqlalchemy as sa

revision = "010_developer_portal"
down_revision = "009_plugins"
branch_labels = None
depends_on = None


def upgrade():
    # ──────────────────────────────────────────────────────────────────────
    # 1. DEVELOPER API KEYS — scoped API keys for developer accounts
    # ──────────────────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS developer_api_keys (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        developer_id    UUID NOT NULL,
        key_hash        VARCHAR(255) NOT NULL UNIQUE,
        key_prefix      VARCHAR(10) NOT NULL,
        scope           VARCHAR(50) NOT NULL DEFAULT 'read',
        name            VARCHAR(255) NOT NULL,
        rate_limit      INTEGER DEFAULT 100,
        is_active       BOOLEAN DEFAULT TRUE,
        last_used_at    TIMESTAMPTZ,
        created_at      TIMESTAMPTZ DEFAULT NOW(),
        expires_at      TIMESTAMPTZ,

        CONSTRAINT fk_devkey_developer FOREIGN KEY (developer_id)
            REFERENCES developers(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_devkey_developer ON developer_api_keys(developer_id);
    CREATE INDEX IF NOT EXISTS idx_devkey_hash ON developer_api_keys(key_hash);
    CREATE INDEX IF NOT EXISTS idx_devkey_active ON developer_api_keys(developer_id, is_active)
        WHERE is_active = TRUE;
    """)

    # ──────────────────────────────────────────────────────────────────────
    # 2. PLUGIN SUBMISSIONS — submission workflow with review
    # ──────────────────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS plugin_submissions (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        developer_id    UUID NOT NULL,
        name            VARCHAR(255) NOT NULL,
        version         VARCHAR(20) NOT NULL,
        description     TEXT,
        category        VARCHAR(50) NOT NULL,
        permissions     JSONB DEFAULT '[]',
        webhook_url     VARCHAR(2048),
        config_schema   JSONB,
        icon_url        VARCHAR(2048),
        homepage_url    VARCHAR(2048),
        source_url      VARCHAR(2048),
        status          VARCHAR(50) DEFAULT 'pending_review',
        reviewer_notes  TEXT,
        submitted_at    TIMESTAMPTZ DEFAULT NOW(),
        reviewed_at     TIMESTAMPTZ,

        CONSTRAINT fk_psub_developer FOREIGN KEY (developer_id)
            REFERENCES developers(id) ON DELETE CASCADE,
        UNIQUE(developer_id, name, version)
    );

    CREATE INDEX IF NOT EXISTS idx_psub_developer ON plugin_submissions(developer_id);
    CREATE INDEX IF NOT EXISTS idx_psub_status ON plugin_submissions(status);
    CREATE INDEX IF NOT EXISTS idx_psub_submitted ON plugin_submissions(submitted_at DESC);
    """)

    # ──────────────────────────────────────────────────────────────────────
    # 3. DEVELOPER USAGE LOGS — API usage tracking
    # ──────────────────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS developer_usage_logs (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        developer_id    UUID NOT NULL,
        key_id          UUID,
        endpoint        VARCHAR(255) NOT NULL,
        method          VARCHAR(10) NOT NULL,
        status_code     INTEGER,
        latency_ms      FLOAT DEFAULT 0,
        created_at      TIMESTAMPTZ DEFAULT NOW(),

        CONSTRAINT fk_dusage_developer FOREIGN KEY (developer_id)
            REFERENCES developers(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_dusage_developer ON developer_usage_logs(developer_id, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_dusage_method ON developer_usage_logs(method);
    """)

    # ──────────────────────────────────────────────────────────────────────
    # 4. SANDBOX LOGS — test execution history
    # ──────────────────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS sandbox_logs (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        developer_id    UUID NOT NULL,
        request_type    VARCHAR(50) NOT NULL,
        request_data    JSONB,
        response_data   JSONB,
        status          VARCHAR(50) DEFAULT 'pending',
        created_at      TIMESTAMPTZ DEFAULT NOW(),

        CONSTRAINT fk_sandbox_developer FOREIGN KEY (developer_id)
            REFERENCES developers(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_sandbox_developer ON sandbox_logs(developer_id, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_sandbox_status ON sandbox_logs(status);
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS sandbox_logs CASCADE;")
    op.execute("DROP TABLE IF EXISTS developer_usage_logs CASCADE;")
    op.execute("DROP TABLE IF EXISTS plugin_submissions CASCADE;")
    op.execute("DROP TABLE IF EXISTS developer_api_keys CASCADE;")
