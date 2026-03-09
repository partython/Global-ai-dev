"""
011 - Row Level Security (RLS) Implementation

Implements comprehensive Row Level Security policies across all tenant-scoped tables.

SECURITY ARCHITECTURE:
- Enables RLS on all tables with tenant_id column
- Forces RLS to apply even to table owners (prevents bypass via owner privilege escalation)
- Creates four policies per table: SELECT, INSERT, UPDATE, DELETE
- All policies filter by comparing tenant_id to app.current_tenant_id setting
- Creates priya_service_role with BYPASSRLS for backend service operations
- RLS enforcement at database layer ensures data isolation even if app code has bugs

TABLES (32):
All tables with tenant_id column:
- ab_experiments, api_keys, audit_log, channel_connections, conversations
- csat_ratings, customers, ecommerce_connections, funnel_events, handoffs
- knowledge_base, messages, nurturing_sequences, orders, products
- refresh_tokens, tenants, users
- ai_configurations, channel_configurations, compliance_reports, consent_records
- country_settings, currency_rates, data_deletion_requests, detailed_audit_logs
- localization_strings, onboarding_analytics, onboarding_progress, payment_methods
- security_events, tax_configurations

RLS POLICIES PER TABLE:
1. SELECT - Only view rows where tenant_id = current_tenant
2. INSERT - Only create rows with current_tenant as tenant_id
3. UPDATE - Only modify rows where tenant_id = current_tenant
4. DELETE - Only remove rows where tenant_id = current_tenant

SERVICE ROLE:
- priya_service_role: Backend service role with BYPASSRLS permission
- Used by backend services to perform cross-tenant admin operations
- Must be granted appropriate permissions for each table
"""

from alembic import op
import sqlalchemy as sa

revision = "011_row_level_security"
down_revision = "010_developer_portal"
branch_labels = None
depends_on = None


# Complete list of all tables with tenant_id that require RLS
TENANT_SCOPED_TABLES = [
    'ab_experiments',
    'ai_configurations',
    'api_keys',
    'audit_log',
    'channel_configurations',
    'channel_connections',
    'compliance_reports',
    'consent_records',
    'conversations',
    'country_settings',
    'csat_ratings',
    'currency_rates',
    'customers',
    'data_deletion_requests',
    'detailed_audit_logs',
    'ecommerce_connections',
    'funnel_events',
    'handoffs',
    'knowledge_base',
    'localization_strings',
    'messages',
    'nurturing_sequences',
    'onboarding_analytics',
    'onboarding_progress',
    'orders',
    'payment_methods',
    'products',
    'refresh_tokens',
    'security_events',
    'tax_configurations',
    'tenants',
    'users',
    # Memory and conversation-related tables (newer migrations)
    'conversation_memories',
    'customer_memories',
    'memory_episodes',
    'conversation_turns',
    # Plugin-related tables
    'plugins',
    'plugin_configs',
    'plugin_analytics',
    'plugin_api_keys',
    'plugin_event_logs',
    'plugin_resource_usage',
    'plugin_subscriptions',
    # SMS tables
    'sms_messages',
    'sms_opt_outs',
    'sms_templates',
    # REST connector tables
    'rest_connectors',
    'rest_endpoints',
    'rest_field_mappings',
    'rest_sync_logs',
    # Translation tables
    'translation_glossary',
    'translation_audit_log',
]


def upgrade():
    """
    Enable Row Level Security on all tenant-scoped tables and create isolation policies.
    """

    # ──────────────────────────────────────────────────────────────────────
    # STEP 1: Create Service Role for Backend
    # ──────────────────────────────────────────────────────────────────────
    # This role is used by backend services to perform operations that need
    # to bypass RLS (e.g., system admin tasks, cross-tenant operations)
    op.execute("""
    DO $$
    BEGIN
        -- Create role if it doesn't exist
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'priya_service_role') THEN
            CREATE ROLE priya_service_role NOLOGIN;
            GRANT CONNECT ON DATABASE postgres TO priya_service_role;
        END IF;
    END
    $$;
    """)

    # Grant BYPASSRLS permission so this role can bypass RLS policies
    op.execute("ALTER ROLE priya_service_role BYPASSRLS;")

    # ──────────────────────────────────────────────────────────────────────
    # STEP 2: Enable RLS and Create Policies for Each Table
    # ──────────────────────────────────────────────────────────────────────
    for table_name in TENANT_SCOPED_TABLES:
        # Check if table exists before enabling RLS
        op.execute(f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = '{table_name}' AND table_schema = 'public'
            ) THEN
                -- Enable RLS on the table
                ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;

                -- Force RLS even for table owners
                ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY;
            END IF;
        END
        $$;
        """)

        # Create SELECT policy - users can only see their tenant's rows
        op.execute(f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = '{table_name}' AND table_schema = 'public'
            ) THEN
                -- Drop existing policy if present
                DROP POLICY IF EXISTS {table_name}_tenant_isolation_select ON {table_name};

                -- Create new SELECT policy
                CREATE POLICY {table_name}_tenant_isolation_select ON {table_name}
                    FOR SELECT
                    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
            END IF;
        END
        $$;
        """)

        # Create INSERT policy - users can only insert rows with their tenant_id
        op.execute(f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = '{table_name}' AND table_schema = 'public'
            ) THEN
                -- Drop existing policy if present
                DROP POLICY IF EXISTS {table_name}_tenant_isolation_insert ON {table_name};

                -- Create new INSERT policy
                CREATE POLICY {table_name}_tenant_isolation_insert ON {table_name}
                    FOR INSERT
                    WITH CHECK (tenant_id = current_setting('app.current_tenant_id')::uuid);
            END IF;
        END
        $$;
        """)

        # Create UPDATE policy - users can only update their tenant's rows
        op.execute(f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = '{table_name}' AND table_schema = 'public'
            ) THEN
                -- Drop existing policy if present
                DROP POLICY IF EXISTS {table_name}_tenant_isolation_update ON {table_name};

                -- Create new UPDATE policy
                CREATE POLICY {table_name}_tenant_isolation_update ON {table_name}
                    FOR UPDATE
                    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
            END IF;
        END
        $$;
        """)

        # Create DELETE policy - users can only delete their tenant's rows
        op.execute(f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = '{table_name}' AND table_schema = 'public'
            ) THEN
                -- Drop existing policy if present
                DROP POLICY IF EXISTS {table_name}_tenant_isolation_delete ON {table_name};

                -- Create new DELETE policy
                CREATE POLICY {table_name}_tenant_isolation_delete ON {table_name}
                    FOR DELETE
                    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
            END IF;
        END
        $$;
        """)

        # Grant permissions to service role
        op.execute(f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = '{table_name}' AND table_schema = 'public'
            ) THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON {table_name} TO priya_service_role;
            END IF;
        END
        $$;
        """)


def downgrade():
    """
    Disable Row Level Security and remove all policies.
    This is a destructive operation and should only be used for testing/development.
    """

    # ──────────────────────────────────────────────────────────────────────
    # STEP 1: Drop All RLS Policies
    # ──────────────────────────────────────────────────────────────────────
    for table_name in TENANT_SCOPED_TABLES:
        op.execute(f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = '{table_name}' AND table_schema = 'public'
            ) THEN
                -- Drop all policies for this table
                DROP POLICY IF EXISTS {table_name}_tenant_isolation_select ON {table_name};
                DROP POLICY IF EXISTS {table_name}_tenant_isolation_insert ON {table_name};
                DROP POLICY IF EXISTS {table_name}_tenant_isolation_update ON {table_name};
                DROP POLICY IF EXISTS {table_name}_tenant_isolation_delete ON {table_name};
            END IF;
        END
        $$;
        """)

    # ──────────────────────────────────────────────────────────────────────
    # STEP 2: Disable RLS on All Tables
    # ──────────────────────────────────────────────────────────────────────
    for table_name in TENANT_SCOPED_TABLES:
        op.execute(f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = '{table_name}' AND table_schema = 'public'
            ) THEN
                -- Disable RLS on the table
                ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY;
            END IF;
        END
        $$;
        """)

    # ──────────────────────────────────────────────────────────────────────
    # STEP 3: Revoke Service Role Permissions
    # ──────────────────────────────────────────────────────────────────────
    for table_name in TENANT_SCOPED_TABLES:
        op.execute(f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = '{table_name}' AND table_schema = 'public'
            ) THEN
                REVOKE SELECT, INSERT, UPDATE, DELETE ON {table_name} FROM priya_service_role;
            END IF;
        END
        $$;
        """)

    # ──────────────────────────────────────────────────────────────────────
    # STEP 4: Drop Service Role
    # ──────────────────────────────────────────────────────────────────────
    # Only drop the role if no other dependencies exist
    op.execute("""
    DO $$
    BEGIN
        -- Drop role if it exists (ignoring cascade errors if it has dependencies)
        DROP ROLE IF EXISTS priya_service_role;
    EXCEPTION
        WHEN OTHERS THEN NULL;
    END
    $$;
    """)
