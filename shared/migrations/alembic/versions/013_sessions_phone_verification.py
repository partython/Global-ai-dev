"""
013 - User Sessions, Phone Verification & Notification Preferences

Adds:
1. user_sessions — httpOnly cookie session tracking (replaces localStorage JWT)
2. phone_verifications — phone number OTP verification for paid feature gating
3. notification_preferences — per-user, per-category, per-channel notification settings
4. notification_log — delivery tracking for all outbound notifications

Modifies:
5. users — add phone_number, phone_verified, phone_verified_at columns

Security:
- RLS enabled on all new tenant-scoped tables
- user_sessions has no tenant_id (user-scoped, not tenant-scoped)
"""

from alembic import op
import sqlalchemy as sa

revision = "013_sessions_phone"
down_revision = "012_wallet_passwordless"
branch_labels = None
depends_on = None


def upgrade():
    # ─── User Sessions (httpOnly cookie tracking) ─────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_sessions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            token_hash VARCHAR(128) NOT NULL UNIQUE,
            refresh_token_hash VARCHAR(128) UNIQUE,
            device_info TEXT,
            ip_address VARCHAR(45),
            user_agent TEXT,
            last_used_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
            refresh_expires_at TIMESTAMP WITH TIME ZONE,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_sessions_user
            ON user_sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_token
            ON user_sessions(token_hash);
        CREATE INDEX IF NOT EXISTS idx_sessions_refresh
            ON user_sessions(refresh_token_hash);
        CREATE INDEX IF NOT EXISTS idx_sessions_tenant
            ON user_sessions(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_expires
            ON user_sessions(expires_at);

        -- Auto-cleanup expired sessions (application should also clean up)
    """)

    # ─── Phone Verifications ──────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS phone_verifications (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID REFERENCES users(id) ON DELETE CASCADE,
            tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
            phone_number VARCHAR(20) NOT NULL,
            country_code VARCHAR(5) NOT NULL DEFAULT '+91',
            otp_hash VARCHAR(128) NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 3,
            verified BOOLEAN NOT NULL DEFAULT false,
            expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
            ip_address VARCHAR(45),
            provider VARCHAR(20) DEFAULT 'msg91',
            provider_request_id VARCHAR(100),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_phone_verify_user
            ON phone_verifications(user_id);
        CREATE INDEX IF NOT EXISTS idx_phone_verify_phone
            ON phone_verifications(phone_number);
        CREATE INDEX IF NOT EXISTS idx_phone_verify_expires
            ON phone_verifications(expires_at);
    """)

    # ─── Add phone columns to users table ─────────────────────────────────
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'phone_number'
            ) THEN
                ALTER TABLE users ADD COLUMN phone_number VARCHAR(20);
                ALTER TABLE users ADD COLUMN phone_verified BOOLEAN NOT NULL DEFAULT false;
                ALTER TABLE users ADD COLUMN phone_verified_at TIMESTAMP WITH TIME ZONE;
            END IF;
        END $$;

        -- Unique phone per account (only for verified numbers)
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone_unique
            ON users(phone_number) WHERE phone_number IS NOT NULL AND phone_verified = true;
    """)

    # ─── Notification Preferences ─────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS notification_preferences (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            category VARCHAR(50) NOT NULL,
            channel VARCHAR(20) NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            UNIQUE(tenant_id, user_id, category, channel)
        );

        CREATE INDEX IF NOT EXISTS idx_notif_pref_tenant
            ON notification_preferences(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_notif_pref_user
            ON notification_preferences(user_id);
    """)

    # ─── Notification Log ─────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS notification_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            template_name VARCHAR(100),
            channel VARCHAR(20) NOT NULL,
            recipient VARCHAR(255) NOT NULL,
            subject VARCHAR(500),
            status VARCHAR(20) NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued', 'sent', 'delivered', 'failed', 'bounced')),
            provider VARCHAR(30),
            provider_message_id VARCHAR(255),
            metadata JSONB,
            sent_at TIMESTAMP WITH TIME ZONE,
            delivered_at TIMESTAMP WITH TIME ZONE,
            failed_reason TEXT,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_notif_log_tenant
            ON notification_log(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_notif_log_user
            ON notification_log(user_id);
        CREATE INDEX IF NOT EXISTS idx_notif_log_status
            ON notification_log(status);
        CREATE INDEX IF NOT EXISTS idx_notif_log_created
            ON notification_log(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_notif_log_template
            ON notification_log(template_name);
    """)

    # ─── Scheduled Notifications ──────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_notifications (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            template_name VARCHAR(100) NOT NULL,
            channel VARCHAR(20) NOT NULL,
            recipient VARCHAR(255) NOT NULL,
            variables JSONB,
            scheduled_for TIMESTAMP WITH TIME ZONE NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'sent', 'cancelled', 'failed')),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_sched_notif_tenant
            ON scheduled_notifications(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_sched_notif_scheduled
            ON scheduled_notifications(scheduled_for)
            WHERE status = 'pending';
    """)

    # ─── RLS on new tables ────────────────────────────────────────────────
    rls_tables = [
        "user_sessions",
        "notification_preferences",
        "notification_log",
        "scheduled_notifications",
    ]

    for table in rls_tables:
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

    # phone_verifications — RLS by tenant_id (if present)
    op.execute("""
        ALTER TABLE phone_verifications ENABLE ROW LEVEL SECURITY;
        ALTER TABLE phone_verifications FORCE ROW LEVEL SECURITY;

        DROP POLICY IF EXISTS phone_verifications_select ON phone_verifications;
        CREATE POLICY phone_verifications_select ON phone_verifications
            FOR SELECT USING (
                tenant_id::text = current_setting('app.current_tenant_id', true)
                OR tenant_id IS NULL
            );

        DROP POLICY IF EXISTS phone_verifications_insert ON phone_verifications;
        CREATE POLICY phone_verifications_insert ON phone_verifications
            FOR INSERT WITH CHECK (true);

        GRANT ALL ON phone_verifications TO priya_service_role;
    """)


def downgrade():
    # ─── Remove RLS policies ─────────────────────────────────────────────
    for table in ["user_sessions", "notification_preferences", "notification_log",
                  "scheduled_notifications", "phone_verifications"]:
        op.execute(f"""
            DROP POLICY IF EXISTS {table}_select ON {table};
            DROP POLICY IF EXISTS {table}_insert ON {table};
            DROP POLICY IF EXISTS {table}_update ON {table};
            DROP POLICY IF EXISTS {table}_delete ON {table};
            ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
        """)

    # ─── Revert users changes ────────────────────────────────────────────
    op.execute("""
        DROP INDEX IF EXISTS idx_users_phone_unique;
        ALTER TABLE users DROP COLUMN IF EXISTS phone_number;
        ALTER TABLE users DROP COLUMN IF EXISTS phone_verified;
        ALTER TABLE users DROP COLUMN IF EXISTS phone_verified_at;
    """)

    # ─── Drop tables in dependency order ──────────────────────────────────
    op.execute("DROP TABLE IF EXISTS scheduled_notifications CASCADE;")
    op.execute("DROP TABLE IF EXISTS notification_log CASCADE;")
    op.execute("DROP TABLE IF EXISTS notification_preferences CASCADE;")
    op.execute("DROP TABLE IF EXISTS phone_verifications CASCADE;")
    op.execute("DROP TABLE IF EXISTS user_sessions CASCADE;")
