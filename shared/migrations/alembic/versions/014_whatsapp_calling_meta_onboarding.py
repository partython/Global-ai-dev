"""
014 - WhatsApp Business Calling & Meta Embedded Signup

Adds:
1. whatsapp_call_consents — tracks voice call consent requests/grants
2. whatsapp_calls — call history, duration, recording references
3. channel_connections UNIQUE constraint — (tenant_id, channel) for upsert
4. Indexes for call history queries

Modifies:
5. channel_connections — add unique index on (tenant_id, channel)

Security:
- RLS enabled on all new tables
- Calls are tenant-scoped, consent is tenant-scoped
"""

from alembic import op
import sqlalchemy as sa

revision = "014_calling_meta"
down_revision = "013_sessions_phone"
branch_labels = None
depends_on = None


def upgrade():
    # ─── WhatsApp Call Consents ──────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS whatsapp_call_consents (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            phone_number_id VARCHAR(50) NOT NULL,
            customer_phone VARCHAR(20) NOT NULL,
            consent_message_id VARCHAR(100),
            status VARCHAR(20) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'granted', 'revoked', 'expired')),
            granted_at TIMESTAMP WITH TIME ZONE,
            expires_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE(tenant_id, customer_phone)
        );

        CREATE INDEX IF NOT EXISTS idx_call_consent_tenant
            ON whatsapp_call_consents(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_call_consent_phone
            ON whatsapp_call_consents(customer_phone);
        CREATE INDEX IF NOT EXISTS idx_call_consent_status
            ON whatsapp_call_consents(status)
            WHERE status = 'granted';
    """)

    # ─── WhatsApp Calls ──────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS whatsapp_calls (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            phone_number_id VARCHAR(50) NOT NULL,
            customer_phone VARCHAR(20) NOT NULL,
            call_id VARCHAR(100) NOT NULL,
            call_type VARCHAR(10) NOT NULL DEFAULT 'audio'
                CHECK (call_type IN ('audio', 'video')),
            status VARCHAR(20) NOT NULL DEFAULT 'ringing'
                CHECK (status IN ('ringing', 'answered', 'completed', 'missed',
                                  'rejected', 'failed', 'busy')),
            initiated_by VARCHAR(10) NOT NULL DEFAULT 'business'
                CHECK (initiated_by IN ('business', 'customer')),
            duration_seconds INTEGER,
            recording_url TEXT,
            recording_consent BOOLEAN DEFAULT false,
            ai_transcript TEXT,
            ai_summary TEXT,
            sentiment_score NUMERIC(3,2),
            metadata JSONB,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            ended_at TIMESTAMP WITH TIME ZONE,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_calls_tenant
            ON whatsapp_calls(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_calls_customer
            ON whatsapp_calls(customer_phone);
        CREATE INDEX IF NOT EXISTS idx_calls_call_id
            ON whatsapp_calls(call_id);
        CREATE INDEX IF NOT EXISTS idx_calls_status
            ON whatsapp_calls(status);
        CREATE INDEX IF NOT EXISTS idx_calls_created
            ON whatsapp_calls(created_at DESC);
    """)

    # ─── Unique constraint on channel_connections for upsert ─────────────
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE indexname = 'idx_channel_conn_tenant_channel'
            ) THEN
                CREATE UNIQUE INDEX idx_channel_conn_tenant_channel
                    ON channel_connections(tenant_id, channel);
            END IF;
        END $$;
    """)

    # ─── RLS on new tables ───────────────────────────────────────────────
    for table in ["whatsapp_call_consents", "whatsapp_calls"]:
        op.execute(f"""
            ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
            ALTER TABLE {table} FORCE ROW LEVEL SECURITY;

            DROP POLICY IF EXISTS {table}_select ON {table};
            CREATE POLICY {table}_select ON {table}
                FOR SELECT USING (tenant_id::text = current_setting('app.current_tenant_id', true));

            DROP POLICY IF EXISTS {table}_insert ON {table};
            CREATE POLICY {table}_insert ON {table}
                FOR INSERT WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true));

            DROP POLICY IF EXISTS {table}_update ON {table};
            CREATE POLICY {table}_update ON {table}
                FOR UPDATE USING (tenant_id::text = current_setting('app.current_tenant_id', true));

            DROP POLICY IF EXISTS {table}_delete ON {table};
            CREATE POLICY {table}_delete ON {table}
                FOR DELETE USING (tenant_id::text = current_setting('app.current_tenant_id', true));

            GRANT ALL ON {table} TO priya_service_role;
        """)


def downgrade():
    for table in ["whatsapp_call_consents", "whatsapp_calls"]:
        op.execute(f"""
            DROP POLICY IF EXISTS {table}_select ON {table};
            DROP POLICY IF EXISTS {table}_insert ON {table};
            DROP POLICY IF EXISTS {table}_update ON {table};
            DROP POLICY IF EXISTS {table}_delete ON {table};
            ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
        """)

    op.execute("DROP INDEX IF EXISTS idx_channel_conn_tenant_channel;")
    op.execute("DROP TABLE IF EXISTS whatsapp_calls CASCADE;")
    op.execute("DROP TABLE IF EXISTS whatsapp_call_consents CASCADE;")
