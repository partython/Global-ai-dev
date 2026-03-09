"""
008 — Universal REST API Connector Tables

Tables:
- rest_connectors: Connector configurations with auth, URLs, sync settings
- rest_endpoints: Endpoint definitions (path, method, pagination)
- rest_field_mappings: Field mapping rules (source → target with transforms)
- rest_sync_logs: Execution audit trail with timing and error tracking

Indexes:
- B-tree on (tenant_id, status) for connector listing
- B-tree on (tenant_id, connector_id) for endpoint lookup
- B-tree on (tenant_id, endpoint_id) for mapping lookup
- B-tree on (tenant_id, connector_id, created_at DESC) for sync log queries
- Unique on (tenant_id, name) for connector name dedup

Security:
- All tables have tenant_id + RLS policies
- Auth credentials stored as JSONB (encrypted at DB layer)
- Webhook secrets stored separately
"""

from alembic import op
import sqlalchemy as sa

revision = "008_rest_connector"
down_revision = "007_sms"
branch_labels = None
depends_on = None


def upgrade():
    # ──────────────────────────────────────────────────────────────────────
    # 1. REST CONNECTORS — connector configuration
    # ──────────────────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS rest_connectors (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id           UUID NOT NULL,

        -- Identity
        name                VARCHAR(255) NOT NULL,
        description         TEXT,
        base_url            VARCHAR(2048) NOT NULL,

        -- Authentication (JSONB — encrypted at DB layer)
        auth_config         JSONB DEFAULT '{}',

        -- HTTP defaults
        default_headers     JSONB DEFAULT '{}',

        -- Webhooks
        webhook_secret      VARCHAR(1024),

        -- Sync configuration
        sync_direction      VARCHAR(20) DEFAULT 'inbound',
        retry_enabled       BOOLEAN DEFAULT TRUE,

        -- Status
        status              VARCHAR(20) DEFAULT 'active',
        last_sync_at        TIMESTAMPTZ,

        -- Metadata
        metadata            JSONB DEFAULT '{}',
        created_at          TIMESTAMPTZ DEFAULT NOW(),
        updated_at          TIMESTAMPTZ DEFAULT NOW(),

        CONSTRAINT fk_rest_conn_tenant FOREIGN KEY (tenant_id)
            REFERENCES tenants(id) ON DELETE CASCADE
    );

    -- Unique connector name per tenant
    CREATE UNIQUE INDEX IF NOT EXISTS idx_rest_conn_name
        ON rest_connectors (tenant_id, name)
        WHERE status != 'inactive';

    -- Active connectors lookup
    CREATE INDEX IF NOT EXISTS idx_rest_conn_status
        ON rest_connectors (tenant_id, status);

    -- RLS
    ALTER TABLE rest_connectors ENABLE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation_rest_conn ON rest_connectors
        USING (tenant_id::text = current_setting('app.current_tenant_id', true));
    """)

    # ──────────────────────────────────────────────────────────────────────
    # 2. REST ENDPOINTS — endpoint definitions per connector
    # ──────────────────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS rest_endpoints (
        id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id               UUID NOT NULL,
        connector_id            UUID NOT NULL,

        -- Endpoint config
        name                    VARCHAR(255) NOT NULL,
        path                    VARCHAR(1024) NOT NULL,
        method                  VARCHAR(10) DEFAULT 'GET',
        description             TEXT,

        -- Request config
        query_params            JSONB DEFAULT '{}',
        request_body_template   JSONB DEFAULT '{}',

        -- Response config
        response_root_path      VARCHAR(500),

        -- Pagination
        pagination_type         VARCHAR(20),
        pagination_config       JSONB DEFAULT '{}',

        -- Status
        is_active               BOOLEAN DEFAULT TRUE,

        -- Timestamps
        created_at              TIMESTAMPTZ DEFAULT NOW(),
        updated_at              TIMESTAMPTZ DEFAULT NOW(),

        CONSTRAINT fk_rest_ep_tenant FOREIGN KEY (tenant_id)
            REFERENCES tenants(id) ON DELETE CASCADE,
        CONSTRAINT fk_rest_ep_connector FOREIGN KEY (connector_id)
            REFERENCES rest_connectors(id) ON DELETE CASCADE
    );

    -- Endpoints per connector
    CREATE INDEX IF NOT EXISTS idx_rest_ep_connector
        ON rest_endpoints (tenant_id, connector_id)
        WHERE is_active = TRUE;

    -- Unique endpoint name per connector
    CREATE UNIQUE INDEX IF NOT EXISTS idx_rest_ep_name
        ON rest_endpoints (tenant_id, connector_id, name)
        WHERE is_active = TRUE;

    -- RLS
    ALTER TABLE rest_endpoints ENABLE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation_rest_ep ON rest_endpoints
        USING (tenant_id::text = current_setting('app.current_tenant_id', true));
    """)

    # ──────────────────────────────────────────────────────────────────────
    # 3. REST FIELD MAPPINGS — source→target field mapping rules
    # ──────────────────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS rest_field_mappings (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL,
        connector_id    UUID NOT NULL,
        endpoint_id     UUID NOT NULL,

        -- Mapping rule
        source_path     VARCHAR(500) NOT NULL,
        target_field    VARCHAR(255) NOT NULL,
        data_type       VARCHAR(20) DEFAULT 'string',
        default_value   VARCHAR(1000),
        is_required     BOOLEAN DEFAULT FALSE,
        transform       VARCHAR(50),

        -- Timestamps
        created_at      TIMESTAMPTZ DEFAULT NOW(),

        CONSTRAINT fk_rest_map_tenant FOREIGN KEY (tenant_id)
            REFERENCES tenants(id) ON DELETE CASCADE,
        CONSTRAINT fk_rest_map_connector FOREIGN KEY (connector_id)
            REFERENCES rest_connectors(id) ON DELETE CASCADE,
        CONSTRAINT fk_rest_map_endpoint FOREIGN KEY (endpoint_id)
            REFERENCES rest_endpoints(id) ON DELETE CASCADE
    );

    -- Mappings per endpoint
    CREATE INDEX IF NOT EXISTS idx_rest_map_endpoint
        ON rest_field_mappings (tenant_id, endpoint_id);

    -- Unique source→target per endpoint
    CREATE UNIQUE INDEX IF NOT EXISTS idx_rest_map_unique
        ON rest_field_mappings (tenant_id, endpoint_id, source_path, target_field);

    -- RLS
    ALTER TABLE rest_field_mappings ENABLE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation_rest_map ON rest_field_mappings
        USING (tenant_id::text = current_setting('app.current_tenant_id', true));
    """)

    # ──────────────────────────────────────────────────────────────────────
    # 4. REST SYNC LOGS — execution audit trail
    # ──────────────────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS rest_sync_logs (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL,
        connector_id    UUID NOT NULL,
        endpoint_id     UUID,

        -- Execution details
        direction       VARCHAR(20) NOT NULL,
        event_type      VARCHAR(100),
        status_code     INTEGER,
        records_count   INTEGER DEFAULT 0,
        elapsed_ms      INTEGER DEFAULT 0,
        error_message   TEXT,

        -- Timestamps
        created_at      TIMESTAMPTZ DEFAULT NOW(),

        CONSTRAINT fk_rest_log_tenant FOREIGN KEY (tenant_id)
            REFERENCES tenants(id) ON DELETE CASCADE,
        CONSTRAINT fk_rest_log_connector FOREIGN KEY (connector_id)
            REFERENCES rest_connectors(id) ON DELETE CASCADE
    );

    -- Log queries by connector + time
    CREATE INDEX IF NOT EXISTS idx_rest_log_connector
        ON rest_sync_logs (tenant_id, connector_id, created_at DESC);

    -- Error log lookup
    CREATE INDEX IF NOT EXISTS idx_rest_log_errors
        ON rest_sync_logs (tenant_id, created_at DESC)
        WHERE error_message IS NOT NULL;

    -- RLS
    ALTER TABLE rest_sync_logs ENABLE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation_rest_log ON rest_sync_logs
        USING (tenant_id::text = current_setting('app.current_tenant_id', true));
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS rest_sync_logs CASCADE;")
    op.execute("DROP TABLE IF EXISTS rest_field_mappings CASCADE;")
    op.execute("DROP TABLE IF EXISTS rest_endpoints CASCADE;")
    op.execute("DROP TABLE IF EXISTS rest_connectors CASCADE;")
