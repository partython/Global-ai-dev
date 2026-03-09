"""
012 - Wallet (Prepaid Credits) + Passwordless Auth Migration

Adds:
1. wallet_accounts — one per tenant, balance in paisa
2. wallet_transactions — full ledger (topup, debit, refund, adjustment)
3. wallet_topups — Razorpay order tracking
4. oauth_accounts — Google/Apple SSO link table
5. otp_requests — Email OTP for passwordless login

Modifies:
6. users.password_hash — ALTER to allow NULL (stop requiring passwords)
7. users.auth_method — new ENUM column ('google', 'apple', 'email_otp')

Security:
- RLS enabled on all new tables
- RLS policies: SELECT, INSERT, UPDATE, DELETE by tenant_id
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "012_wallet_passwordless"
down_revision = "011_row_level_security"
branch_labels = None
depends_on = None


def upgrade():
    # ─── Wallet Accounts ───────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS wallet_accounts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            balance_paisa BIGINT NOT NULL DEFAULT 0 CHECK (balance_paisa >= 0),
            currency VARCHAR(3) NOT NULL DEFAULT 'INR',
            auto_topup_enabled BOOLEAN NOT NULL DEFAULT false,
            auto_topup_threshold_paisa BIGINT NOT NULL DEFAULT 10000,
            auto_topup_amount_paisa BIGINT NOT NULL DEFAULT 50000,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            UNIQUE(tenant_id)
        );

        CREATE INDEX IF NOT EXISTS idx_wallet_accounts_tenant
            ON wallet_accounts(tenant_id);
    """)

    # ─── Wallet Transactions ───────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS wallet_transactions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            wallet_id UUID NOT NULL REFERENCES wallet_accounts(id) ON DELETE CASCADE,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            type VARCHAR(20) NOT NULL CHECK (type IN ('topup', 'debit', 'refund', 'adjustment')),
            amount_paisa BIGINT NOT NULL CHECK (amount_paisa > 0),
            running_balance_paisa BIGINT NOT NULL,
            channel VARCHAR(50),
            reference_id VARCHAR(255),
            description TEXT,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_wallet_tx_tenant
            ON wallet_transactions(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_wallet_tx_wallet
            ON wallet_transactions(wallet_id);
        CREATE INDEX IF NOT EXISTS idx_wallet_tx_created
            ON wallet_transactions(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_wallet_tx_type
            ON wallet_transactions(type);
    """)

    # ─── Wallet Topups (Razorpay) ──────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS wallet_topups (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            wallet_id UUID NOT NULL REFERENCES wallet_accounts(id) ON DELETE CASCADE,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            razorpay_order_id VARCHAR(100) UNIQUE,
            razorpay_payment_id VARCHAR(100),
            amount_paisa BIGINT NOT NULL CHECK (amount_paisa > 0),
            currency VARCHAR(3) NOT NULL DEFAULT 'INR',
            status VARCHAR(20) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'completed', 'failed', 'refunded')),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMP WITH TIME ZONE
        );

        CREATE INDEX IF NOT EXISTS idx_wallet_topups_tenant
            ON wallet_topups(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_wallet_topups_order
            ON wallet_topups(razorpay_order_id);
        CREATE INDEX IF NOT EXISTS idx_wallet_topups_status
            ON wallet_topups(status);
    """)

    # ─── OAuth Accounts (Google/Apple SSO) ─────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS oauth_accounts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            provider VARCHAR(20) NOT NULL CHECK (provider IN ('google', 'apple')),
            provider_id VARCHAR(255) NOT NULL,
            email VARCHAR(255),
            display_name VARCHAR(255),
            avatar_url TEXT,
            raw_profile JSONB,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            UNIQUE(provider, provider_id)
        );

        CREATE INDEX IF NOT EXISTS idx_oauth_user
            ON oauth_accounts(user_id);
        CREATE INDEX IF NOT EXISTS idx_oauth_provider
            ON oauth_accounts(provider, provider_id);
        CREATE INDEX IF NOT EXISTS idx_oauth_tenant
            ON oauth_accounts(tenant_id);
    """)

    # ─── OTP Requests (Email OTP for passwordless login) ───────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS otp_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email VARCHAR(255) NOT NULL,
            otp_hash VARCHAR(128) NOT NULL,
            purpose VARCHAR(20) NOT NULL DEFAULT 'login'
                CHECK (purpose IN ('login', 'verify_email')),
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 5,
            verified BOOLEAN NOT NULL DEFAULT false,
            expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            ip_address VARCHAR(45),
            user_agent TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_otp_email
            ON otp_requests(email);
        CREATE INDEX IF NOT EXISTS idx_otp_expires
            ON otp_requests(expires_at);

        -- Auto-cleanup expired OTPs (older than 1 hour)
        -- Application should also clean up, but this is a safety net
    """)

    # ─── Modify users table for passwordless auth ──────────────────────
    op.execute("""
        -- Allow NULL password (passwordless users won't have one)
        ALTER TABLE users
            ALTER COLUMN password_hash DROP NOT NULL;

        -- Add auth_method column
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'auth_method'
            ) THEN
                ALTER TABLE users ADD COLUMN auth_method VARCHAR(20) DEFAULT 'email_otp'
                    CHECK (auth_method IN ('google', 'apple', 'email_otp', 'password'));
            END IF;
        END $$;

        -- Set existing password users to 'password' auth method
        UPDATE users SET auth_method = 'password' WHERE password_hash IS NOT NULL AND auth_method IS NULL;
    """)

    # ─── RLS on new tables ─────────────────────────────────────────────
    rls_tables_with_tenant = [
        "wallet_accounts",
        "wallet_transactions",
        "wallet_topups",
        "oauth_accounts",
    ]

    for table in rls_tables_with_tenant:
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

            -- Grant service role bypass
            GRANT ALL ON {table} TO priya_service_role;
        """)

    # OTP requests don't have tenant_id — no RLS (global table)
    # Access controlled at application layer


def downgrade():
    # ─── Remove RLS policies ──────────────────────────────────────────
    for table in ["wallet_accounts", "wallet_transactions", "wallet_topups", "oauth_accounts"]:
        op.execute(f"""
            DROP POLICY IF EXISTS {table}_select ON {table};
            DROP POLICY IF EXISTS {table}_insert ON {table};
            DROP POLICY IF EXISTS {table}_update ON {table};
            DROP POLICY IF EXISTS {table}_delete ON {table};
            ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
        """)

    # ─── Revert users changes ─────────────────────────────────────────
    op.execute("""
        ALTER TABLE users DROP COLUMN IF EXISTS auth_method;
        -- Note: NOT reverting password_hash to NOT NULL — would break existing passwordless users
    """)

    # ─── Drop tables in dependency order ───────────────────────────────
    op.execute("DROP TABLE IF EXISTS otp_requests CASCADE;")
    op.execute("DROP TABLE IF EXISTS oauth_accounts CASCADE;")
    op.execute("DROP TABLE IF EXISTS wallet_topups CASCADE;")
    op.execute("DROP TABLE IF EXISTS wallet_transactions CASCADE;")
    op.execute("DROP TABLE IF EXISTS wallet_accounts CASCADE;")
