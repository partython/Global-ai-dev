"""
007 — SMS Service Tables

Tables:
- sms_messages: Inbound/outbound SMS message storage with DLR tracking
- sms_templates: SMS message templates with variable substitution
- sms_opt_outs: Per-tenant opt-out registry for compliance (TRAI, TCPA, GDPR)

Indexes:
- B-tree on (tenant_id, to_number, created_at DESC) for message history
- B-tree on (tenant_id, status) for queue management
- Unique on (tenant_id, phone_number) for opt-out deduplication
- B-tree on (tenant_id, carrier, created_at DESC) for analytics

Security:
- All tables have tenant_id + RLS policies
- Opt-outs enforced at application layer (SMS service checks before sending)
"""

from alembic import op
import sqlalchemy as sa

revision = "007_sms"
down_revision = "006_translation"
branch_labels = None
depends_on = None


def upgrade():
    # ──────────────────────────────────────────────────────────────────────
    # 1. SMS MESSAGES — inbound + outbound with delivery tracking
    # ──────────────────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS sms_messages (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id           UUID NOT NULL,
        message_id          VARCHAR(100) NOT NULL,

        -- Endpoints
        from_number         VARCHAR(20) NOT NULL,
        to_number           VARCHAR(20) NOT NULL,

        -- Content
        content             TEXT NOT NULL,
        template_id         UUID,

        -- Status lifecycle: queued → sent → delivered/failed/rejected
        status              VARCHAR(20) NOT NULL DEFAULT 'queued',
        direction           VARCHAR(10) NOT NULL DEFAULT 'outbound',
        carrier             VARCHAR(50) NOT NULL,
        carrier_reference   VARCHAR(200),

        -- Delivery receipt
        dlr_status          VARCHAR(50),
        dlr_timestamp       TIMESTAMPTZ,
        error_code          VARCHAR(50),
        error_message       TEXT,

        -- Compliance
        opt_out             BOOLEAN DEFAULT FALSE,

        -- Segment tracking (for concatenated SMS)
        segment_count       INTEGER DEFAULT 1,
        encoding            VARCHAR(20) DEFAULT 'GSM-7',

        -- Metadata & timestamps
        metadata            JSONB DEFAULT '{}',
        created_at          TIMESTAMPTZ DEFAULT NOW(),
        updated_at          TIMESTAMPTZ DEFAULT NOW(),

        -- Foreign keys
        CONSTRAINT fk_sms_msg_tenant FOREIGN KEY (tenant_id)
            REFERENCES tenants(id) ON DELETE CASCADE
    );

    -- Message history lookup by recipient
    CREATE INDEX IF NOT EXISTS idx_sms_msg_recipient
        ON sms_messages (tenant_id, to_number, created_at DESC);

    -- Queue management (outbound pending messages)
    CREATE INDEX IF NOT EXISTS idx_sms_msg_status
        ON sms_messages (tenant_id, status, created_at)
        WHERE status IN ('queued', 'sent');

    -- Carrier analytics
    CREATE INDEX IF NOT EXISTS idx_sms_msg_carrier
        ON sms_messages (tenant_id, carrier, created_at DESC);

    -- Message ID lookup (for DLR matching)
    CREATE UNIQUE INDEX IF NOT EXISTS idx_sms_msg_id
        ON sms_messages (tenant_id, message_id);

    -- Direction-based queries
    CREATE INDEX IF NOT EXISTS idx_sms_msg_direction
        ON sms_messages (tenant_id, direction, created_at DESC);

    -- RLS Policy
    ALTER TABLE sms_messages ENABLE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation_sms_msg ON sms_messages
        USING (tenant_id::text = current_setting('app.current_tenant_id', true));
    """)

    # ──────────────────────────────────────────────────────────────────────
    # 2. SMS TEMPLATES — reusable message templates
    # ──────────────────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS sms_templates (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL,

        -- Template content
        name            VARCHAR(255) NOT NULL,
        content         TEXT NOT NULL,
        variables       TEXT[] DEFAULT '{}',
        category        VARCHAR(50) DEFAULT 'general',

        -- Status
        is_active       BOOLEAN DEFAULT TRUE,

        -- Metadata & timestamps
        metadata        JSONB DEFAULT '{}',
        created_at      TIMESTAMPTZ DEFAULT NOW(),
        updated_at      TIMESTAMPTZ DEFAULT NOW(),

        -- Foreign keys
        CONSTRAINT fk_sms_tpl_tenant FOREIGN KEY (tenant_id)
            REFERENCES tenants(id) ON DELETE CASCADE
    );

    -- Unique template name per tenant
    CREATE UNIQUE INDEX IF NOT EXISTS idx_sms_tpl_name
        ON sms_templates (tenant_id, name)
        WHERE is_active = TRUE;

    -- Category lookup
    CREATE INDEX IF NOT EXISTS idx_sms_tpl_category
        ON sms_templates (tenant_id, category)
        WHERE is_active = TRUE;

    -- RLS Policy
    ALTER TABLE sms_templates ENABLE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation_sms_tpl ON sms_templates
        USING (tenant_id::text = current_setting('app.current_tenant_id', true));
    """)

    # ──────────────────────────────────────────────────────────────────────
    # 3. SMS OPT-OUTS — compliance registry
    # ──────────────────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS sms_opt_outs (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL,

        -- Opt-out details
        phone_number    VARCHAR(20) NOT NULL,
        reason          TEXT DEFAULT 'customer_request',
        source          VARCHAR(50) DEFAULT 'sms_keyword',
        carrier         VARCHAR(50),

        -- Compliance metadata
        regulation      VARCHAR(50),
        regulation_ref  VARCHAR(200),

        -- Timestamps
        opted_out_at    TIMESTAMPTZ DEFAULT NOW(),
        created_at      TIMESTAMPTZ DEFAULT NOW(),

        -- Foreign keys
        CONSTRAINT fk_sms_opt_tenant FOREIGN KEY (tenant_id)
            REFERENCES tenants(id) ON DELETE CASCADE
    );

    -- Unique opt-out per phone per tenant
    CREATE UNIQUE INDEX IF NOT EXISTS idx_sms_opt_unique
        ON sms_opt_outs (tenant_id, phone_number);

    -- Fast lookup for compliance check before sending
    CREATE INDEX IF NOT EXISTS idx_sms_opt_lookup
        ON sms_opt_outs (tenant_id, phone_number);

    -- RLS Policy
    ALTER TABLE sms_opt_outs ENABLE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation_sms_opt ON sms_opt_outs
        USING (tenant_id::text = current_setting('app.current_tenant_id', true));
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS sms_opt_outs CASCADE;")
    op.execute("DROP TABLE IF EXISTS sms_templates CASCADE;")
    op.execute("DROP TABLE IF EXISTS sms_messages CASCADE;")
