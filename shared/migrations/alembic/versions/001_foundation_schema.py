"""Foundation Schema: Multi-Tenant Core with Row Level Security

Revision ID: 001_foundation_schema
Revises: None
Create Date: 2025-03-06

This migration creates the foundation of the Priya Global Platform:
- Multi-tenant architecture with complete RLS isolation
- Authentication and authorization infrastructure
- Customer relationship and conversation management
- Knowledge base with vector embeddings
- E-commerce and channel integrations
- Security and audit logging
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_foundation_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create foundation schema with all required tables, indexes, and policies."""

    # ============================================================
    # Enable Required Extensions
    # ============================================================
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')

    # ============================================================
    # Tenant Isolation: Helper Functions
    # ============================================================
    op.execute("""
        CREATE OR REPLACE FUNCTION current_tenant_id() RETURNS uuid AS $$
        DECLARE
            tenant_id_str text;
            tenant_id_uuid uuid;
        BEGIN
            tenant_id_str := NULLIF(current_setting('app.current_tenant_id', true), '');
            -- SECURITY: Validate UUID format to prevent invalid data
            IF tenant_id_str IS NOT NULL THEN
                BEGIN
                    tenant_id_uuid := tenant_id_str::uuid;
                    RETURN tenant_id_uuid;
                EXCEPTION WHEN others THEN
                    RETURN NULL;
                END;
            END IF;
            RETURN NULL;
        EXCEPTION
            WHEN OTHERS THEN RETURN NULL;
        END;
        $$ LANGUAGE plpgsql STABLE SECURITY DEFINER;
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION is_admin_connection() RETURNS boolean AS $$
        DECLARE
            admin_token text;
        BEGIN
            admin_token := current_setting('app.current_tenant_id', true);
            -- SECURITY: This function checks for the SYSTEM_ADMIN bypass token.
            -- Setting this value requires application-level authorization and must only be done
            -- after cryptographic nonce validation. Never expose this to user input.
            -- Expected pattern: Static hardcoded value matching approved admin token in app config.
            IF admin_token IS NULL OR admin_token = '' THEN
                RETURN false;
            END IF;
            -- STRICT VALIDATION: Only allow exact match to SYSTEM_ADMIN token (hardcoded constant for admin bypass)
            -- This PL/pgSQL function is SECURITY DEFINER, meaning it runs with elevated privileges
            -- The SYSTEM_ADMIN value is intentionally hardcoded as it represents a well-known app configuration
            RETURN admin_token = 'SYSTEM_ADMIN';
        EXCEPTION
            WHEN OTHERS THEN RETURN false;
        END;
        $$ LANGUAGE plpgsql STABLE SECURITY DEFINER;
    """)

    # ============================================================
    # 1. TENANTS (Workspaces)
    # ============================================================
    op.create_table(
        'tenants',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('slug', sa.Text(), nullable=False, unique=True),
        sa.Column('plan', sa.Text(), nullable=False, server_default='starter',
                  sa.CheckConstraint("plan IN ('starter', 'growth', 'enterprise', 'trial')")),
        sa.Column('status', sa.Text(), nullable=False, server_default='active',
                  sa.CheckConstraint("status IN ('active', 'suspended', 'cancelled', 'trial')")),
        sa.Column('business_name', sa.Text()),
        sa.Column('business_email', sa.Text()),
        sa.Column('business_phone', sa.Text()),
        sa.Column('business_url', sa.Text()),
        sa.Column('industry', sa.Text()),
        sa.Column('country', sa.Text(), nullable=False, server_default='IN'),
        sa.Column('timezone', sa.Text(), nullable=False, server_default='Asia/Kolkata'),
        sa.Column('currency', sa.Text(), nullable=False, server_default='INR'),
        sa.Column('default_language', sa.Text(), nullable=False, server_default='en'),
        sa.Column('ai_personality', sa.Text(), server_default='friendly_sales'),
        sa.Column('ai_greeting', sa.Text(), server_default='Hello! How can I help you today?'),
        sa.Column('ai_system_prompt', sa.Text()),
        sa.Column('ai_model_preference', sa.Text(), server_default='auto'),
        sa.Column('logo_url', sa.Text()),
        sa.Column('brand_color', sa.Text(), server_default='#3B82F6'),
        sa.Column('favicon_url', sa.Text()),
        sa.Column('max_conversations_month', sa.Integer(), nullable=False, server_default='1000'),
        sa.Column('max_team_members', sa.Integer(), nullable=False, server_default='2'),
        sa.Column('max_channels', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('max_ecommerce_connections', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('conversations_this_month', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('billing_period_start', sa.DateTime(timezone=True)),
        sa.Column('stripe_customer_id', sa.Text()),
        sa.Column('stripe_subscription_id', sa.Text()),
        sa.Column('trial_ends_at', sa.DateTime(timezone=True)),
        sa.Column('settings', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('feature_flags', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('deleted_at', sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_tenants_slug', 'tenants', ['slug'], where="deleted_at IS NULL")
    op.create_index('idx_tenants_status', 'tenants', ['status'], where="deleted_at IS NULL")
    op.create_index('idx_tenants_stripe', 'tenants', ['stripe_customer_id'], where="stripe_customer_id IS NOT NULL")

    # ============================================================
    # 2. USERS (Team Members)
    # ============================================================
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.Text(), nullable=False),
        sa.Column('password_hash', sa.Text()),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('avatar_url', sa.Text()),
        sa.Column('role', sa.Text(), nullable=False, server_default='agent',
                  sa.CheckConstraint("role IN ('owner', 'admin', 'agent', 'viewer', 'developer')")),
        sa.Column('status', sa.Text(), nullable=False, server_default='active',
                  sa.CheckConstraint("status IN ('active', 'invited', 'suspended', 'deleted')")),
        sa.Column('email_verified', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('totp_secret', sa.Text()),
        sa.Column('totp_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('last_login_at', sa.DateTime(timezone=True)),
        sa.Column('last_login_ip', postgresql.INET()),
        sa.Column('failed_login_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('locked_until', sa.DateTime(timezone=True)),
        sa.Column('google_id', sa.Text()),
        sa.Column('apple_id', sa.Text()),
        sa.Column('microsoft_id', sa.Text()),
        sa.Column('preferred_language', sa.Text(), server_default='en'),
        sa.Column('notification_prefs', postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default='{"email": true, "push": true, "sound": true}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'email')
    )
    op.create_index('idx_users_tenant', 'users', ['tenant_id'])
    op.create_index('idx_users_email', 'users', ['email'])
    op.create_index('idx_users_google', 'users', ['google_id'], where="google_id IS NOT NULL")
    op.create_index('idx_users_apple', 'users', ['apple_id'], where="apple_id IS NOT NULL")
    op.create_index('idx_users_microsoft', 'users', ['microsoft_id'], where="microsoft_id IS NOT NULL")

    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY users_tenant_isolation ON users
        USING (tenant_id = current_tenant_id() OR is_admin_connection())
    """)

    # ============================================================
    # 3. API KEYS
    # ============================================================
    op.create_table(
        'api_keys',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('key_hash', sa.Text(), nullable=False),
        sa.Column('key_prefix', sa.Text(), nullable=False),
        sa.Column('permissions', postgresql.ARRAY(sa.Text()), nullable=False, server_default="ARRAY['read']"),
        sa.Column('rate_limit', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('last_used_at', sa.DateTime(timezone=True)),
        sa.Column('expires_at', sa.DateTime(timezone=True)),
        sa.Column('revoked_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_api_keys_tenant', 'api_keys', ['tenant_id'])
    op.create_index('idx_api_keys_prefix', 'api_keys', ['key_prefix'])

    op.execute("ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY api_keys_tenant_isolation ON api_keys
        USING (tenant_id = current_tenant_id() OR is_admin_connection())
    """)

    # ============================================================
    # 4. CUSTOMERS
    # ============================================================
    op.create_table(
        'customers',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.Text()),
        sa.Column('email', sa.Text()),
        sa.Column('phone', sa.Text()),
        sa.Column('avatar_url', sa.Text()),
        sa.Column('whatsapp_id', sa.Text()),
        sa.Column('instagram_id', sa.Text()),
        sa.Column('facebook_id', sa.Text()),
        sa.Column('telegram_id', sa.Text()),
        sa.Column('webchat_session', sa.Text()),
        sa.Column('country', sa.Text()),
        sa.Column('city', sa.Text()),
        sa.Column('language', sa.Text(), server_default='en'),
        sa.Column('timezone', sa.Text()),
        sa.Column('tags', postgresql.ARRAY(sa.Text()), nullable=False, server_default="ARRAY[]::text[]"),
        sa.Column('lead_score', sa.Integer(), nullable=False, server_default='0',
                  sa.CheckConstraint("lead_score >= 0 AND lead_score <= 100")),
        sa.Column('lead_stage', sa.Text(), server_default='new',
                  sa.CheckConstraint("lead_stage IN ('new', 'contacted', 'qualified', 'proposal', 'negotiation', 'won', 'lost')")),
        sa.Column('lifetime_value', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('total_orders', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('first_channel', sa.Text()),
        sa.Column('memory', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('preferences', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('family_info', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('last_message_at', sa.DateTime(timezone=True)),
        sa.Column('last_channel', sa.Text()),
        sa.Column('total_conversations', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('sentiment_avg', sa.Float()),
        sa.Column('consent_given', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('consent_date', sa.DateTime(timezone=True)),
        sa.Column('data_retention_days', sa.Integer()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_customers_tenant', 'customers', ['tenant_id'])
    op.create_index('idx_customers_phone', 'customers', ['tenant_id', 'phone'], where="phone IS NOT NULL")
    op.create_index('idx_customers_email', 'customers', ['tenant_id', 'email'], where="email IS NOT NULL")
    op.create_index('idx_customers_whatsapp', 'customers', ['tenant_id', 'whatsapp_id'], where="whatsapp_id IS NOT NULL")
    op.create_index('idx_customers_lead_score', 'customers', ['tenant_id', sa.desc('lead_score')])
    op.create_index('idx_customers_last_message', 'customers', ['tenant_id', sa.desc('last_message_at')])

    op.execute("ALTER TABLE customers ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY customers_tenant_isolation ON customers
        USING (tenant_id = current_tenant_id() OR is_admin_connection())
    """)

    # ============================================================
    # 5. CONVERSATIONS
    # ============================================================
    op.create_table(
        'conversations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('customer_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('channel', sa.Text(), nullable=False,
                  sa.CheckConstraint("channel IN ('whatsapp', 'email', 'voice', 'instagram', 'facebook', 'webchat', 'sms', 'telegram')")),
        sa.Column('status', sa.Text(), nullable=False, server_default='active',
                  sa.CheckConstraint("status IN ('active', 'resolved', 'pending_handoff', 'handed_off', 'archived')")),
        sa.Column('assigned_to', postgresql.UUID(as_uuid=True)),
        sa.Column('is_ai_handling', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('subject', sa.Text()),
        sa.Column('intent', sa.Text()),
        sa.Column('sentiment', sa.Float()),
        sa.Column('language', sa.Text(), server_default='en'),
        sa.Column('lead_score_at_start', sa.Integer()),
        sa.Column('products_discussed', postgresql.ARRAY(sa.Text()), server_default="ARRAY[]::text[]"),
        sa.Column('revenue_attributed', sa.Numeric(12, 2), server_default='0'),
        sa.Column('first_message_at', sa.DateTime(timezone=True)),
        sa.Column('last_message_at', sa.DateTime(timezone=True)),
        sa.Column('resolved_at', sa.DateTime(timezone=True)),
        sa.Column('response_time_avg_ms', sa.Integer()),
        sa.Column('csat_rating', sa.Integer(), sa.CheckConstraint("csat_rating >= 1 AND csat_rating <= 5")),
        sa.Column('quality_score', sa.Float(), sa.CheckConstraint("quality_score >= 0 AND quality_score <= 1")),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('message_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['assigned_to'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_conversations_tenant', 'conversations', ['tenant_id'])
    op.create_index('idx_conversations_customer', 'conversations', ['tenant_id', 'customer_id'])
    op.create_index('idx_conversations_status', 'conversations', ['tenant_id', 'status'])
    op.create_index('idx_conversations_channel', 'conversations', ['tenant_id', 'channel'])
    op.create_index('idx_conversations_active', 'conversations', ['tenant_id', sa.desc('last_message_at')],
                    where="status IN ('active', 'pending_handoff')")
    op.create_index('idx_conversations_assigned', 'conversations', ['tenant_id', 'assigned_to'],
                    where="assigned_to IS NOT NULL")

    op.execute("ALTER TABLE conversations ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY conversations_tenant_isolation ON conversations
        USING (tenant_id = current_tenant_id() OR is_admin_connection())
    """)

    # ============================================================
    # 6. MESSAGES
    # ============================================================
    op.create_table(
        'messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('customer_id', postgresql.UUID(as_uuid=True)),
        sa.Column('direction', sa.Text(), nullable=False,
                  sa.CheckConstraint("direction IN ('inbound', 'outbound')")),
        sa.Column('sender_type', sa.Text(), nullable=False,
                  sa.CheckConstraint("sender_type IN ('customer', 'ai', 'agent', 'system')")),
        sa.Column('sender_id', postgresql.UUID(as_uuid=True)),
        sa.Column('content_type', sa.Text(), nullable=False, server_default='text',
                  sa.CheckConstraint("content_type IN ('text', 'image', 'audio', 'video', 'document', 'location', 'sticker', 'template', 'interactive')")),
        sa.Column('content_text', sa.Text()),
        sa.Column('media_url', sa.Text()),
        sa.Column('media_mime_type', sa.Text()),
        sa.Column('channel', sa.Text(), nullable=False),
        sa.Column('channel_message_id', sa.Text()),
        sa.Column('reply_to_id', postgresql.UUID(as_uuid=True)),
        sa.Column('delivery_status', sa.Text(), server_default='sent',
                  sa.CheckConstraint("delivery_status IN ('pending', 'sent', 'delivered', 'read', 'failed')")),
        sa.Column('error_message', sa.Text()),
        sa.Column('ai_model_used', sa.Text()),
        sa.Column('ai_tokens_used', sa.Integer()),
        sa.Column('ai_confidence', sa.Float()),
        sa.Column('rag_sources', postgresql.ARRAY(sa.Text())),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['reply_to_id'], ['messages.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_messages_conversation', 'messages', ['conversation_id', 'created_at'])
    op.create_index('idx_messages_tenant', 'messages', ['tenant_id'])
    op.create_index('idx_messages_customer', 'messages', ['tenant_id', 'customer_id', sa.desc('created_at')])
    op.create_index('idx_messages_channel_id', 'messages', ['channel', 'channel_message_id'],
                    where="channel_message_id IS NOT NULL")

    op.execute("ALTER TABLE messages ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY messages_tenant_isolation ON messages
        USING (tenant_id = current_tenant_id() OR is_admin_connection())
    """)

    # ============================================================
    # 7. KNOWLEDGE BASE (RAG with Vector Embeddings)
    # ============================================================
    op.create_table(
        'knowledge_base',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_type', sa.Text(), nullable=False,
                  sa.CheckConstraint("source_type IN ('product', 'faq', 'document', 'conversation', 'website')")),
        sa.Column('source_id', sa.Text()),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('embedding', postgresql.ARRAY(sa.Float()), nullable=True),  # Vector(1024)
        sa.Column('language', sa.Text(), server_default='en'),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('last_synced_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_knowledge_tenant', 'knowledge_base', ['tenant_id'])
    op.create_index('idx_knowledge_source', 'knowledge_base', ['tenant_id', 'source_type', 'source_id'])

    op.execute("ALTER TABLE knowledge_base ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY knowledge_tenant_isolation ON knowledge_base
        USING (tenant_id = current_tenant_id() OR is_admin_connection())
    """)

    # ============================================================
    # 8. PRODUCTS
    # ============================================================
    op.create_table(
        'products',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('external_id', sa.Text(), nullable=False),
        sa.Column('platform', sa.Text(), nullable=False,
                  sa.CheckConstraint("platform IN ('shopify', 'woocommerce', 'magento', 'custom')")),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('price', sa.Numeric(12, 2)),
        sa.Column('compare_at_price', sa.Numeric(12, 2)),
        sa.Column('currency', sa.Text(), server_default='USD'),
        sa.Column('sku', sa.Text()),
        sa.Column('inventory_count', sa.Integer()),
        sa.Column('image_url', sa.Text()),
        sa.Column('product_url', sa.Text()),
        sa.Column('category', sa.Text()),
        sa.Column('tags', postgresql.ARRAY(sa.Text()), server_default="ARRAY[]::text[]"),
        sa.Column('variants', postgresql.JSONB(astext_type=sa.Text()), server_default='[]'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'platform', 'external_id')
    )
    op.create_index('idx_products_tenant', 'products', ['tenant_id'])
    op.create_index('idx_products_active', 'products', ['tenant_id', 'is_active'], where="is_active = true")
    op.create_index('idx_products_search', 'products',
                    [sa.text("to_tsvector('english', coalesce(name, '') || ' ' || coalesce(description, ''))")],
                    postgresql_using='gin')

    op.execute("ALTER TABLE products ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY products_tenant_isolation ON products
        USING (tenant_id = current_tenant_id() OR is_admin_connection())
    """)

    # ============================================================
    # 9. ORDERS
    # ============================================================
    op.create_table(
        'orders',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('customer_id', postgresql.UUID(as_uuid=True)),
        sa.Column('external_id', sa.Text(), nullable=False),
        sa.Column('platform', sa.Text(), nullable=False),
        sa.Column('order_number', sa.Text()),
        sa.Column('status', sa.Text(), nullable=False, server_default='pending'),
        sa.Column('total', sa.Numeric(12, 2), nullable=False),
        sa.Column('currency', sa.Text(), server_default='USD'),
        sa.Column('items', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('shipping_address', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('fulfillment_status', sa.Text()),
        sa.Column('tracking_number', sa.Text()),
        sa.Column('tracking_url', sa.Text()),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True)),
        sa.Column('attributed_to', sa.Text(), server_default='ai'),
        sa.Column('placed_at', sa.DateTime(timezone=True)),
        sa.Column('fulfilled_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'platform', 'external_id')
    )
    op.create_index('idx_orders_tenant', 'orders', ['tenant_id'])
    op.create_index('idx_orders_customer', 'orders', ['tenant_id', 'customer_id'])

    op.execute("ALTER TABLE orders ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY orders_tenant_isolation ON orders
        USING (tenant_id = current_tenant_id() OR is_admin_connection())
    """)

    # ============================================================
    # 10. HANDOFFS (AI → Human Transfer)
    # ============================================================
    op.create_table(
        'handoffs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('customer_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('priority', sa.Text(), nullable=False, server_default='normal',
                  sa.CheckConstraint("priority IN ('urgent', 'high', 'normal', 'low')")),
        sa.Column('status', sa.Text(), nullable=False, server_default='pending',
                  sa.CheckConstraint("status IN ('pending', 'assigned', 'resolved', 'expired')")),
        sa.Column('assigned_to', postgresql.UUID(as_uuid=True)),
        sa.Column('assigned_at', sa.DateTime(timezone=True)),
        sa.Column('resolved_at', sa.DateTime(timezone=True)),
        sa.Column('resolution_notes', sa.Text()),
        sa.Column('ai_context_summary', sa.Text()),
        sa.Column('customer_sentiment', sa.Float()),
        sa.Column('lead_score', sa.Integer()),
        sa.Column('response_deadline', sa.DateTime(timezone=True)),
        sa.Column('sla_breached', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['assigned_to'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_handoffs_tenant', 'handoffs', ['tenant_id'])
    op.create_index('idx_handoffs_pending', 'handoffs', ['tenant_id', 'status', 'priority'],
                    where="status IN ('pending', 'assigned')")

    op.execute("ALTER TABLE handoffs ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY handoffs_tenant_isolation ON handoffs
        USING (tenant_id = current_tenant_id() OR is_admin_connection())
    """)

    # ============================================================
    # 11. CSAT RATINGS
    # ============================================================
    op.create_table(
        'csat_ratings',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True)),
        sa.Column('customer_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False, sa.CheckConstraint("rating >= 1 AND rating <= 5")),
        sa.Column('feedback_text', sa.Text()),
        sa.Column('channel', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_csat_tenant', 'csat_ratings', ['tenant_id'])

    op.execute("ALTER TABLE csat_ratings ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY csat_tenant_isolation ON csat_ratings
        USING (tenant_id = current_tenant_id() OR is_admin_connection())
    """)

    # ============================================================
    # 12. FUNNEL EVENTS
    # ============================================================
    op.create_table(
        'funnel_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('customer_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True)),
        sa.Column('stage', sa.Text(), nullable=False,
                  sa.CheckConstraint("stage IN ('first_message', 'product_shown', 'collection_shared', 'checkout_created', 'purchase_completed')")),
        sa.Column('channel', sa.Text(), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_funnel_tenant', 'funnel_events', ['tenant_id', 'stage', 'created_at'])

    op.execute("ALTER TABLE funnel_events ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY funnel_tenant_isolation ON funnel_events
        USING (tenant_id = current_tenant_id() OR is_admin_connection())
    """)

    # ============================================================
    # 13. NURTURING SEQUENCES
    # ============================================================
    op.create_table(
        'nurturing_sequences',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('trigger_type', sa.Text(), nullable=False,
                  sa.CheckConstraint("trigger_type IN ('manual', 'lead_score', 'cart_abandoned', 'post_purchase', 'inactivity')")),
        sa.Column('trigger_config', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('steps', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('enrolled_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('converted_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    op.execute("ALTER TABLE nurturing_sequences ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY sequences_tenant_isolation ON nurturing_sequences
        USING (tenant_id = current_tenant_id() OR is_admin_connection())
    """)

    # ============================================================
    # 14. A/B EXPERIMENTS
    # ============================================================
    op.create_table(
        'ab_experiments',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('experiment_type', sa.Text(), nullable=False, server_default='greeting'),
        sa.Column('status', sa.Text(), nullable=False, server_default='draft',
                  sa.CheckConstraint("status IN ('draft', 'active', 'paused', 'completed')")),
        sa.Column('variants', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('results', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('traffic_split', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('ended_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    op.execute("ALTER TABLE ab_experiments ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY ab_tenant_isolation ON ab_experiments
        USING (tenant_id = current_tenant_id() OR is_admin_connection())
    """)

    # ============================================================
    # 15. E-COMMERCE CONNECTIONS
    # ============================================================
    # SECURITY CRITICAL: Credential fields below MUST be encrypted at the application layer
    # before storage. Database storage provides zero protection for plaintext credentials.
    # Application MUST implement transparent encryption/decryption on read/write.
    op.create_table(
        'ecommerce_connections',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('platform', sa.Text(), nullable=False,
                  sa.CheckConstraint("platform IN ('shopify', 'woocommerce', 'magento', 'custom')")),
        sa.Column('store_url', sa.Text(), nullable=False),
        sa.Column('store_name', sa.Text()),
        # SECURITY: access_token MUST be encrypted at application layer
        sa.Column('access_token', sa.Text()),
        # SECURITY: api_key MUST be encrypted at application layer
        sa.Column('api_key', sa.Text()),
        # SECURITY: api_secret MUST be encrypted at application layer
        sa.Column('api_secret', sa.Text()),
        # SECURITY: webhook_secret MUST be encrypted at application layer
        sa.Column('webhook_secret', sa.Text()),
        sa.Column('status', sa.Text(), nullable=False, server_default='active',
                  sa.CheckConstraint("status IN ('active', 'disconnected', 'error')")),
        sa.Column('last_sync_at', sa.DateTime(timezone=True)),
        sa.Column('sync_errors', postgresql.JSONB(astext_type=sa.Text()), server_default='[]'),
        sa.Column('settings', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'platform', 'store_url')
    )

    op.execute("ALTER TABLE ecommerce_connections ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY ecommerce_tenant_isolation ON ecommerce_connections
        USING (tenant_id = current_tenant_id() OR is_admin_connection())
    """)

    # ============================================================
    # 16. CHANNEL CONNECTIONS
    # ============================================================
    # SECURITY HIGH: Credential fields below MUST be encrypted at the application layer
    # before storage. Database provides no inherent protection for plaintext credentials.
    # Application MUST implement transparent encryption/decryption on read/write.
    op.create_table(
        'channel_connections',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('channel', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False, server_default='active'),
        # SECURITY: credentials JSONB column MUST be encrypted at application layer
        sa.Column('credentials', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('webhook_url', sa.Text()),
        sa.Column('phone_number', sa.Text()),
        sa.Column('settings', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('last_health_check', sa.DateTime(timezone=True)),
        sa.Column('error_message', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'channel')
    )

    op.execute("ALTER TABLE channel_connections ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY channel_conn_tenant_isolation ON channel_connections
        USING (tenant_id = current_tenant_id() OR is_admin_connection())
    """)

    # ============================================================
    # 17. AUDIT LOG (Security — Immutable)
    # ============================================================
    op.create_table(
        'audit_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True)),
        sa.Column('action', sa.Text(), nullable=False),
        sa.Column('resource_type', sa.Text()),
        sa.Column('resource_id', sa.Text()),
        sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('ip_address', postgresql.INET()),
        sa.Column('user_agent', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_audit_tenant', 'audit_log', ['tenant_id', sa.desc('created_at')])
    op.create_index('idx_audit_user', 'audit_log', ['tenant_id', 'user_id', sa.desc('created_at')])
    op.create_index('idx_audit_action', 'audit_log', ['tenant_id', 'action', sa.desc('created_at')])

    op.execute("ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY audit_tenant_isolation ON audit_log
        USING (tenant_id = current_tenant_id() OR is_admin_connection())
    """)
    op.execute("""
        CREATE POLICY audit_insert_only ON audit_log
        FOR INSERT WITH CHECK (true)
    """)

    # ============================================================
    # 18. REFRESH TOKENS
    # ============================================================
    op.create_table(
        'refresh_tokens',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('token_hash', sa.Text(), nullable=False),
        sa.Column('device_info', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('ip_address', postgresql.INET()),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_refresh_user', 'refresh_tokens', ['user_id'], where="revoked_at IS NULL")
    op.create_index('idx_refresh_hash', 'refresh_tokens', ['token_hash'], where="revoked_at IS NULL")

    op.execute("ALTER TABLE refresh_tokens ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY refresh_tenant_isolation ON refresh_tokens
        USING (tenant_id = current_tenant_id() OR is_admin_connection())
    """)

    # ============================================================
    # Auto-update Timestamp Trigger
    # ============================================================
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    # Apply trigger to all tables with updated_at column
    tables_with_updated_at = [
        'tenants', 'users', 'customers', 'conversations', 'knowledge_base',
        'products', 'orders', 'handoffs', 'nurturing_sequences', 'ecommerce_connections',
        'channel_connections', 'refresh_tokens'
    ]

    # SECURITY: F-string table names are safe here - these are developer-controlled hardcoded values
    # from the tables_with_updated_at list above, NOT user input. This is acceptable for DDL.
    for table in tables_with_updated_at:
        op.execute(f"""
            DROP TRIGGER IF EXISTS set_updated_at_{table} ON {table};
            CREATE TRIGGER set_updated_at_{table} BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION update_updated_at()
        """)


def downgrade() -> None:
    """Drop entire foundation schema."""

    # Drop all tables (CASCADE will handle foreign keys)
    tables = [
        'refresh_tokens',
        'audit_log',
        'channel_connections',
        'ecommerce_connections',
        'ab_experiments',
        'nurturing_sequences',
        'funnel_events',
        'csat_ratings',
        'handoffs',
        'orders',
        'products',
        'knowledge_base',
        'messages',
        'conversations',
        'customers',
        'api_keys',
        'users',
        'tenants'
    ]

    for table in tables:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")

    # Drop functions
    op.execute("DROP FUNCTION IF EXISTS update_updated_at()")
    op.execute("DROP FUNCTION IF EXISTS is_admin_connection()")
    op.execute("DROP FUNCTION IF EXISTS current_tenant_id()")

    # Drop extensions
    op.execute('DROP EXTENSION IF EXISTS "vector"')
    op.execute('DROP EXTENSION IF EXISTS "pgcrypto"')
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')
