"""
009 — Plugin SDK & Marketplace Tables

Tables:
- plugins: Plugin registry with marketplace and lifecycle management
- plugin_configs: Per-tenant plugin configurations
- plugin_api_keys: Scoped API keys for plugin access
- plugin_subscriptions: Event subscriptions per plugin
- plugin_event_logs: Event delivery audit trail
- plugin_resource_usage: Resource tracking per plugin
- developers: Developer accounts for plugin publishing
- plugin_analytics: Daily analytics per plugin

Indexes:
- B-tree on (tenant_id) for tenant-scoped queries
- B-tree on (marketplace) for marketplace listing
- Unique on (tenant_id, name, version) for dedup

Security:
- All tenant-scoped tables have RLS policies
- API key hashes stored (never plaintext)
- Developer table is global (no tenant_id)
"""

from alembic import op
import sqlalchemy as sa

revision = "009_plugins"
down_revision = "008_rest_connector"
branch_labels = None
depends_on = None


def upgrade():
    # ──────────────────────────────────────────────────────────────────────
    # 1. DEVELOPERS — global developer accounts
    # ──────────────────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS developers (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        email           VARCHAR(255) NOT NULL UNIQUE,
        company         VARCHAR(255),
        name            VARCHAR(255) NOT NULL,
        api_key         VARCHAR(255) NOT NULL UNIQUE,
        is_verified     BOOLEAN DEFAULT FALSE,
        created_at      TIMESTAMPTZ DEFAULT NOW(),
        updated_at      TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_developers_email ON developers(email);
    """)

    # ──────────────────────────────────────────────────────────────────────
    # 2. PLUGINS — plugin registry
    # ──────────────────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS plugins (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL,
        name            VARCHAR(255) NOT NULL,
        version         VARCHAR(20) NOT NULL,
        author          VARCHAR(255) NOT NULL,
        description     TEXT,
        category        VARCHAR(50) NOT NULL,
        permissions     JSONB DEFAULT '[]',
        webhook_url     VARCHAR(2048),
        config_schema   JSONB,
        status          VARCHAR(50) DEFAULT 'published',
        installed_at    TIMESTAMPTZ,
        activated_at    TIMESTAMPTZ,
        is_active       BOOLEAN DEFAULT FALSE,
        marketplace     BOOLEAN DEFAULT FALSE,
        developer_id    UUID,
        icon_url        VARCHAR(2048),
        homepage_url    VARCHAR(2048),
        created_at      TIMESTAMPTZ DEFAULT NOW(),
        updated_at      TIMESTAMPTZ DEFAULT NOW(),

        CONSTRAINT fk_plugin_tenant FOREIGN KEY (tenant_id)
            REFERENCES tenants(id) ON DELETE CASCADE,
        UNIQUE(tenant_id, name, version)
    );

    CREATE INDEX IF NOT EXISTS idx_plugins_tenant ON plugins(tenant_id);
    CREATE INDEX IF NOT EXISTS idx_plugins_marketplace ON plugins(marketplace) WHERE marketplace = TRUE;
    CREATE INDEX IF NOT EXISTS idx_plugins_category ON plugins(category);
    CREATE INDEX IF NOT EXISTS idx_plugins_status ON plugins(tenant_id, status);

    ALTER TABLE plugins ENABLE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation_plugins ON plugins
        USING (tenant_id::text = current_setting('app.current_tenant_id', true));
    """)

    # ──────────────────────────────────────────────────────────────────────
    # 3. PLUGIN CONFIGS — per-tenant configuration
    # ──────────────────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS plugin_configs (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL,
        plugin_id       UUID NOT NULL,
        config          JSONB DEFAULT '{}',
        created_at      TIMESTAMPTZ DEFAULT NOW(),
        updated_at      TIMESTAMPTZ DEFAULT NOW(),

        CONSTRAINT fk_pconfig_tenant FOREIGN KEY (tenant_id)
            REFERENCES tenants(id) ON DELETE CASCADE,
        CONSTRAINT fk_pconfig_plugin FOREIGN KEY (plugin_id)
            REFERENCES plugins(id) ON DELETE CASCADE,
        UNIQUE(tenant_id, plugin_id)
    );

    ALTER TABLE plugin_configs ENABLE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation_pconfig ON plugin_configs
        USING (tenant_id::text = current_setting('app.current_tenant_id', true));
    """)

    # ──────────────────────────────────────────────────────────────────────
    # 4. PLUGIN API KEYS — scoped access keys
    # ──────────────────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS plugin_api_keys (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL,
        plugin_id       UUID NOT NULL,
        key_hash        VARCHAR(255) NOT NULL UNIQUE,
        scope           VARCHAR(50) NOT NULL,
        rate_limit      INTEGER DEFAULT 1000,
        last_used       TIMESTAMPTZ,
        created_at      TIMESTAMPTZ DEFAULT NOW(),
        expires_at      TIMESTAMPTZ,

        CONSTRAINT fk_pkey_tenant FOREIGN KEY (tenant_id)
            REFERENCES tenants(id) ON DELETE CASCADE,
        CONSTRAINT fk_pkey_plugin FOREIGN KEY (plugin_id)
            REFERENCES plugins(id) ON DELETE CASCADE,
        UNIQUE(tenant_id, plugin_id, scope)
    );

    CREATE INDEX IF NOT EXISTS idx_pkey_hash ON plugin_api_keys(key_hash);

    ALTER TABLE plugin_api_keys ENABLE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation_pkey ON plugin_api_keys
        USING (tenant_id::text = current_setting('app.current_tenant_id', true));
    """)

    # ──────────────────────────────────────────────────────────────────────
    # 5. PLUGIN SUBSCRIPTIONS — event subscriptions
    # ──────────────────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS plugin_subscriptions (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL,
        plugin_id       UUID NOT NULL,
        event_type      VARCHAR(255) NOT NULL,
        webhook_url     VARCHAR(2048) NOT NULL,
        created_at      TIMESTAMPTZ DEFAULT NOW(),

        CONSTRAINT fk_psub_tenant FOREIGN KEY (tenant_id)
            REFERENCES tenants(id) ON DELETE CASCADE,
        CONSTRAINT fk_psub_plugin FOREIGN KEY (plugin_id)
            REFERENCES plugins(id) ON DELETE CASCADE,
        UNIQUE(tenant_id, plugin_id, event_type)
    );

    CREATE INDEX IF NOT EXISTS idx_psub_tenant ON plugin_subscriptions(tenant_id);
    CREATE INDEX IF NOT EXISTS idx_psub_event ON plugin_subscriptions(tenant_id, event_type);

    ALTER TABLE plugin_subscriptions ENABLE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation_psub ON plugin_subscriptions
        USING (tenant_id::text = current_setting('app.current_tenant_id', true));
    """)

    # ──────────────────────────────────────────────────────────────────────
    # 6. PLUGIN EVENT LOGS — delivery audit trail
    # ──────────────────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS plugin_event_logs (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL,
        plugin_id       UUID NOT NULL,
        event_type      VARCHAR(255) NOT NULL,
        payload         JSONB,
        status          VARCHAR(50) DEFAULT 'pending',
        retry_count     INTEGER DEFAULT 0,
        last_error      TEXT,
        created_at      TIMESTAMPTZ DEFAULT NOW(),
        updated_at      TIMESTAMPTZ DEFAULT NOW(),

        CONSTRAINT fk_plog_tenant FOREIGN KEY (tenant_id)
            REFERENCES tenants(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_plog_status ON plugin_event_logs(status);
    CREATE INDEX IF NOT EXISTS idx_plog_tenant ON plugin_event_logs(tenant_id, created_at DESC);

    ALTER TABLE plugin_event_logs ENABLE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation_plog ON plugin_event_logs
        USING (tenant_id::text = current_setting('app.current_tenant_id', true));
    """)

    # ──────────────────────────────────────────────────────────────────────
    # 7. PLUGIN RESOURCE USAGE — tracking
    # ──────────────────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS plugin_resource_usage (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL,
        plugin_id       UUID NOT NULL,
        api_calls       INTEGER DEFAULT 0,
        webhook_calls   INTEGER DEFAULT 0,
        error_count     INTEGER DEFAULT 0,
        last_used       TIMESTAMPTZ,
        created_at      TIMESTAMPTZ DEFAULT NOW(),
        updated_at      TIMESTAMPTZ DEFAULT NOW(),

        CONSTRAINT fk_pusage_tenant FOREIGN KEY (tenant_id)
            REFERENCES tenants(id) ON DELETE CASCADE,
        UNIQUE(tenant_id, plugin_id)
    );

    CREATE INDEX IF NOT EXISTS idx_pusage_tenant ON plugin_resource_usage(tenant_id);

    ALTER TABLE plugin_resource_usage ENABLE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation_pusage ON plugin_resource_usage
        USING (tenant_id::text = current_setting('app.current_tenant_id', true));
    """)

    # ──────────────────────────────────────────────────────────────────────
    # 8. PLUGIN ANALYTICS — daily metrics
    # ──────────────────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS plugin_analytics (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL,
        plugin_id       UUID NOT NULL,
        event_type      VARCHAR(255),
        success_count   INTEGER DEFAULT 0,
        failure_count   INTEGER DEFAULT 0,
        avg_latency_ms  FLOAT DEFAULT 0,
        date            DATE DEFAULT CURRENT_DATE,
        created_at      TIMESTAMPTZ DEFAULT NOW(),

        CONSTRAINT fk_panalytics_tenant FOREIGN KEY (tenant_id)
            REFERENCES tenants(id) ON DELETE CASCADE,
        UNIQUE(tenant_id, plugin_id, event_type, date)
    );

    CREATE INDEX IF NOT EXISTS idx_panalytics_plugin ON plugin_analytics(plugin_id);
    CREATE INDEX IF NOT EXISTS idx_panalytics_date ON plugin_analytics(tenant_id, date DESC);

    ALTER TABLE plugin_analytics ENABLE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation_panalytics ON plugin_analytics
        USING (tenant_id::text = current_setting('app.current_tenant_id', true));
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS plugin_analytics CASCADE;")
    op.execute("DROP TABLE IF EXISTS plugin_resource_usage CASCADE;")
    op.execute("DROP TABLE IF EXISTS plugin_event_logs CASCADE;")
    op.execute("DROP TABLE IF EXISTS plugin_subscriptions CASCADE;")
    op.execute("DROP TABLE IF EXISTS plugin_api_keys CASCADE;")
    op.execute("DROP TABLE IF EXISTS plugin_configs CASCADE;")
    op.execute("DROP TABLE IF EXISTS plugins CASCADE;")
    op.execute("DROP TABLE IF EXISTS developers CASCADE;")
