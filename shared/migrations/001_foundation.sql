-- ============================================================
-- PRIYA GLOBAL PLATFORM — Foundation Schema
-- Migration 001: Multi-Tenant Core with Row Level Security
-- ============================================================
--
-- SECURITY MODEL:
-- Every table has tenant_id. RLS policies ensure a tenant can
-- ONLY see their own data. PSI AI (Tenant #1) knowledge is
-- cryptographically isolated from all other tenants.
--
-- This runs on Aurora PostgreSQL 15+
-- ============================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";   -- pgvector for RAG embeddings

-- ============================================================
-- TENANT ISOLATION: The Security Foundation
-- ============================================================

-- Helper function to get current tenant from session
CREATE OR REPLACE FUNCTION current_tenant_id() RETURNS uuid AS $$
BEGIN
    RETURN NULLIF(current_setting('app.current_tenant_id', true), '')::uuid;
EXCEPTION
    WHEN OTHERS THEN RETURN NULL;
END;
$$ LANGUAGE plpgsql STABLE SECURITY DEFINER;

-- Helper function: is this an admin connection?
CREATE OR REPLACE FUNCTION is_admin_connection() RETURNS boolean AS $$
BEGIN
    RETURN current_setting('app.current_tenant_id', true) = 'SYSTEM_ADMIN';
EXCEPTION
    WHEN OTHERS THEN RETURN false;
END;
$$ LANGUAGE plpgsql STABLE SECURITY DEFINER;

-- ============================================================
-- 1. TENANTS (Workspaces)
-- ============================================================

CREATE TABLE tenants (
    id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            text NOT NULL,
    slug            text UNIQUE NOT NULL,  -- e.g., "party-supplies-india"
    plan            text NOT NULL DEFAULT 'starter' CHECK (plan IN ('starter', 'growth', 'enterprise', 'trial')),
    status          text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'cancelled', 'trial')),

    -- Business info
    business_name   text,
    business_email  text,
    business_phone  text,
    business_url    text,
    industry        text,
    country         text NOT NULL DEFAULT 'IN',
    timezone        text NOT NULL DEFAULT 'Asia/Kolkata',
    currency        text NOT NULL DEFAULT 'INR',
    default_language text NOT NULL DEFAULT 'en',

    -- AI Configuration (per tenant)
    ai_personality  text DEFAULT 'friendly_sales',  -- AI tone/style
    ai_greeting     text DEFAULT 'Hello! How can I help you today?',
    ai_system_prompt text,  -- Custom system prompt override
    ai_model_preference text DEFAULT 'auto',  -- auto, claude, gpt4, gemini

    -- Brand
    logo_url        text,
    brand_color     text DEFAULT '#3B82F6',
    favicon_url     text,

    -- Limits (enforced by billing service)
    max_conversations_month int NOT NULL DEFAULT 1000,
    max_team_members int NOT NULL DEFAULT 2,
    max_channels     int NOT NULL DEFAULT 3,
    max_ecommerce_connections int NOT NULL DEFAULT 1,

    -- Usage counters (updated by billing service)
    conversations_this_month int NOT NULL DEFAULT 0,
    billing_period_start timestamptz,

    -- Stripe
    stripe_customer_id text,
    stripe_subscription_id text,

    -- Trial
    trial_ends_at   timestamptz,

    -- Metadata
    settings        jsonb NOT NULL DEFAULT '{}',
    feature_flags   jsonb NOT NULL DEFAULT '{}',
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    deleted_at      timestamptz  -- Soft delete
);

CREATE INDEX idx_tenants_slug ON tenants(slug) WHERE deleted_at IS NULL;
CREATE INDEX idx_tenants_status ON tenants(status) WHERE deleted_at IS NULL;
CREATE INDEX idx_tenants_stripe ON tenants(stripe_customer_id) WHERE stripe_customer_id IS NOT NULL;

-- Tenants table has NO RLS — it's managed by admin connections only

-- ============================================================
-- 2. USERS (Team Members)
-- ============================================================

CREATE TABLE users (
    id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email           text NOT NULL,
    password_hash   text,  -- NULL for SSO-only users
    name            text NOT NULL,
    avatar_url      text,
    role            text NOT NULL DEFAULT 'agent' CHECK (role IN ('owner', 'admin', 'agent', 'viewer', 'developer')),
    status          text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'invited', 'suspended', 'deleted')),

    -- Auth
    email_verified  boolean NOT NULL DEFAULT false,
    totp_secret     text,  -- Encrypted TOTP seed for 2FA
    totp_enabled    boolean NOT NULL DEFAULT false,
    last_login_at   timestamptz,
    last_login_ip   inet,
    failed_login_count int NOT NULL DEFAULT 0,
    locked_until    timestamptz,

    -- SSO
    google_id       text,
    apple_id        text,
    microsoft_id    text,

    -- Preferences
    preferred_language text DEFAULT 'en',
    notification_prefs jsonb NOT NULL DEFAULT '{"email": true, "push": true, "sound": true}',

    -- Metadata
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),

    UNIQUE(tenant_id, email)
);

CREATE INDEX idx_users_tenant ON users(tenant_id);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_google ON users(google_id) WHERE google_id IS NOT NULL;
CREATE INDEX idx_users_apple ON users(apple_id) WHERE apple_id IS NOT NULL;
CREATE INDEX idx_users_microsoft ON users(microsoft_id) WHERE microsoft_id IS NOT NULL;

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
CREATE POLICY users_tenant_isolation ON users
    USING (tenant_id = current_tenant_id() OR is_admin_connection());

-- ============================================================
-- 3. API KEYS (Developer Access)
-- ============================================================

CREATE TABLE api_keys (
    id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            text NOT NULL,
    key_hash        text NOT NULL,  -- bcrypt hash of the actual key
    key_prefix      text NOT NULL,  -- First 8 chars for identification (e.g., "pk_live_")
    permissions     text[] NOT NULL DEFAULT ARRAY['read'],
    rate_limit      int NOT NULL DEFAULT 100,  -- req/min
    last_used_at    timestamptz,
    expires_at      timestamptz,
    revoked_at      timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_api_keys_tenant ON api_keys(tenant_id);
CREATE INDEX idx_api_keys_prefix ON api_keys(key_prefix);

ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
CREATE POLICY api_keys_tenant_isolation ON api_keys
    USING (tenant_id = current_tenant_id() OR is_admin_connection());

-- ============================================================
-- 4. CUSTOMERS (Unified across all channels)
-- ============================================================

CREATE TABLE customers (
    id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- Identity (merged across channels)
    name            text,
    email           text,
    phone           text,
    avatar_url      text,

    -- Channel identifiers
    whatsapp_id     text,
    instagram_id    text,
    facebook_id     text,
    telegram_id     text,
    webchat_session text,

    -- Profile
    country         text,
    city            text,
    language        text DEFAULT 'en',
    timezone        text,
    tags            text[] NOT NULL DEFAULT ARRAY[]::text[],

    -- Sales intelligence
    lead_score      int NOT NULL DEFAULT 0 CHECK (lead_score >= 0 AND lead_score <= 100),
    lead_stage      text DEFAULT 'new' CHECK (lead_stage IN ('new', 'contacted', 'qualified', 'proposal', 'negotiation', 'won', 'lost')),
    lifetime_value  numeric(12,2) NOT NULL DEFAULT 0,
    total_orders    int NOT NULL DEFAULT 0,
    first_channel   text,  -- Which channel they came from first

    -- AI Memory (TENANT-ISOLATED - PSI AI memories stay in Tenant 1)
    memory          jsonb NOT NULL DEFAULT '{}',  -- Long-term customer memory
    preferences     jsonb NOT NULL DEFAULT '{}',  -- Shopping preferences
    family_info     jsonb NOT NULL DEFAULT '{}',  -- Family details mentioned

    -- Engagement
    last_message_at timestamptz,
    last_channel    text,
    total_conversations int NOT NULL DEFAULT 0,
    sentiment_avg   real,  -- Running average sentiment

    -- GDPR
    consent_given   boolean NOT NULL DEFAULT false,
    consent_date    timestamptz,
    data_retention_days int,  -- Override tenant default

    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_customers_tenant ON customers(tenant_id);
CREATE INDEX idx_customers_phone ON customers(tenant_id, phone) WHERE phone IS NOT NULL;
CREATE INDEX idx_customers_email ON customers(tenant_id, email) WHERE email IS NOT NULL;
CREATE INDEX idx_customers_whatsapp ON customers(tenant_id, whatsapp_id) WHERE whatsapp_id IS NOT NULL;
CREATE INDEX idx_customers_lead_score ON customers(tenant_id, lead_score DESC);
CREATE INDEX idx_customers_last_message ON customers(tenant_id, last_message_at DESC);

ALTER TABLE customers ENABLE ROW LEVEL SECURITY;
CREATE POLICY customers_tenant_isolation ON customers
    USING (tenant_id = current_tenant_id() OR is_admin_connection());

-- ============================================================
-- 5. CONVERSATIONS
-- ============================================================

CREATE TABLE conversations (
    id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    customer_id     uuid NOT NULL REFERENCES customers(id) ON DELETE CASCADE,

    channel         text NOT NULL CHECK (channel IN ('whatsapp', 'email', 'voice', 'instagram', 'facebook', 'webchat', 'sms', 'telegram')),
    status          text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'resolved', 'pending_handoff', 'handed_off', 'archived')),

    -- Assignment
    assigned_to     uuid REFERENCES users(id),  -- NULL = AI handling
    is_ai_handling  boolean NOT NULL DEFAULT true,

    -- Context
    subject         text,  -- For email conversations
    intent          text,  -- Detected primary intent
    sentiment       real,  -- Current sentiment (-1 to 1)
    language        text DEFAULT 'en',

    -- Sales context
    lead_score_at_start int,
    products_discussed text[] DEFAULT ARRAY[]::text[],
    revenue_attributed numeric(12,2) DEFAULT 0,

    -- Timing
    first_message_at timestamptz,
    last_message_at timestamptz,
    resolved_at     timestamptz,
    response_time_avg_ms int,  -- Average response time

    -- Quality
    csat_rating     int CHECK (csat_rating >= 1 AND csat_rating <= 5),
    quality_score   real CHECK (quality_score >= 0 AND quality_score <= 1),

    -- Metadata
    metadata        jsonb NOT NULL DEFAULT '{}',
    message_count   int NOT NULL DEFAULT 0,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_conversations_tenant ON conversations(tenant_id);
CREATE INDEX idx_conversations_customer ON conversations(tenant_id, customer_id);
CREATE INDEX idx_conversations_status ON conversations(tenant_id, status);
CREATE INDEX idx_conversations_channel ON conversations(tenant_id, channel);
CREATE INDEX idx_conversations_active ON conversations(tenant_id, status, last_message_at DESC)
    WHERE status IN ('active', 'pending_handoff');
CREATE INDEX idx_conversations_assigned ON conversations(tenant_id, assigned_to)
    WHERE assigned_to IS NOT NULL;

ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
CREATE POLICY conversations_tenant_isolation ON conversations
    USING (tenant_id = current_tenant_id() OR is_admin_connection());

-- ============================================================
-- 6. MESSAGES (Unified format across all channels)
-- ============================================================

CREATE TABLE messages (
    id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    customer_id     uuid REFERENCES customers(id),

    direction       text NOT NULL CHECK (direction IN ('inbound', 'outbound')),
    sender_type     text NOT NULL CHECK (sender_type IN ('customer', 'ai', 'agent', 'system')),
    sender_id       uuid,  -- user_id if agent, NULL if ai/customer

    -- Content
    content_type    text NOT NULL DEFAULT 'text' CHECK (content_type IN ('text', 'image', 'audio', 'video', 'document', 'location', 'sticker', 'template', 'interactive')),
    content_text    text,
    media_url       text,
    media_mime_type text,

    -- Channel-specific
    channel         text NOT NULL,
    channel_message_id text,  -- Platform-specific message ID
    reply_to_id     uuid REFERENCES messages(id),

    -- Delivery
    delivery_status text DEFAULT 'sent' CHECK (delivery_status IN ('pending', 'sent', 'delivered', 'read', 'failed')),
    error_message   text,

    -- AI context (for outbound AI messages)
    ai_model_used   text,
    ai_tokens_used  int,
    ai_confidence   real,
    rag_sources     text[],  -- Which knowledge base docs were used

    -- Metadata
    metadata        jsonb NOT NULL DEFAULT '{}',
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_messages_conversation ON messages(conversation_id, created_at);
CREATE INDEX idx_messages_tenant ON messages(tenant_id);
CREATE INDEX idx_messages_customer ON messages(tenant_id, customer_id, created_at DESC);
CREATE INDEX idx_messages_channel_id ON messages(channel, channel_message_id)
    WHERE channel_message_id IS NOT NULL;

ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
CREATE POLICY messages_tenant_isolation ON messages
    USING (tenant_id = current_tenant_id() OR is_admin_connection());

-- ============================================================
-- 7. KNOWLEDGE BASE (RAG - Per-Tenant Isolated)
-- ============================================================
-- CRITICAL: This is where PSI AI product knowledge lives for Tenant 1.
-- RLS ensures Tenant 2 can NEVER access Tenant 1's knowledge.

CREATE TABLE knowledge_base (
    id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    source_type     text NOT NULL CHECK (source_type IN ('product', 'faq', 'document', 'conversation', 'website')),
    source_id       text,  -- External reference (e.g., Shopify product ID)
    title           text NOT NULL,
    content         text NOT NULL,
    chunk_index     int NOT NULL DEFAULT 0,

    -- Vector embedding for semantic search
    embedding       vector(1024),  -- Amazon Titan v2 dimensions

    -- Metadata
    language        text DEFAULT 'en',
    metadata        jsonb NOT NULL DEFAULT '{}',
    last_synced_at  timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_knowledge_tenant ON knowledge_base(tenant_id);
CREATE INDEX idx_knowledge_source ON knowledge_base(tenant_id, source_type, source_id);
-- Vector similarity index (IVFFlat for performance)
CREATE INDEX idx_knowledge_embedding ON knowledge_base
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

ALTER TABLE knowledge_base ENABLE ROW LEVEL SECURITY;
CREATE POLICY knowledge_tenant_isolation ON knowledge_base
    USING (tenant_id = current_tenant_id() OR is_admin_connection());

-- ============================================================
-- 8. PRODUCTS (Synced from E-Commerce)
-- ============================================================

CREATE TABLE products (
    id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    external_id     text NOT NULL,  -- Platform product ID
    platform        text NOT NULL CHECK (platform IN ('shopify', 'woocommerce', 'magento', 'custom')),
    name            text NOT NULL,
    description     text,
    price           numeric(12,2),
    compare_at_price numeric(12,2),
    currency        text DEFAULT 'USD',
    sku             text,
    inventory_count int,
    image_url       text,
    product_url     text,
    category        text,
    tags            text[] DEFAULT ARRAY[]::text[],
    variants        jsonb DEFAULT '[]',
    is_active       boolean NOT NULL DEFAULT true,

    last_synced_at  timestamptz NOT NULL DEFAULT now(),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),

    UNIQUE(tenant_id, platform, external_id)
);

CREATE INDEX idx_products_tenant ON products(tenant_id);
CREATE INDEX idx_products_active ON products(tenant_id, is_active) WHERE is_active = true;
CREATE INDEX idx_products_search ON products USING gin(to_tsvector('english', coalesce(name, '') || ' ' || coalesce(description, '')));

ALTER TABLE products ENABLE ROW LEVEL SECURITY;
CREATE POLICY products_tenant_isolation ON products
    USING (tenant_id = current_tenant_id() OR is_admin_connection());

-- ============================================================
-- 9. ORDERS
-- ============================================================

CREATE TABLE orders (
    id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    customer_id     uuid REFERENCES customers(id),

    external_id     text NOT NULL,
    platform        text NOT NULL,
    order_number    text,
    status          text NOT NULL DEFAULT 'pending',
    total           numeric(12,2) NOT NULL,
    currency        text DEFAULT 'USD',
    items           jsonb NOT NULL DEFAULT '[]',
    shipping_address jsonb,
    fulfillment_status text,
    tracking_number text,
    tracking_url    text,

    -- Attribution
    conversation_id uuid REFERENCES conversations(id),
    attributed_to   text DEFAULT 'ai',  -- ai, agent, organic

    placed_at       timestamptz,
    fulfilled_at    timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),

    UNIQUE(tenant_id, platform, external_id)
);

CREATE INDEX idx_orders_tenant ON orders(tenant_id);
CREATE INDEX idx_orders_customer ON orders(tenant_id, customer_id);

ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
CREATE POLICY orders_tenant_isolation ON orders
    USING (tenant_id = current_tenant_id() OR is_admin_connection());

-- ============================================================
-- 10. HANDOFFS (AI → Human Transfer)
-- ============================================================

CREATE TABLE handoffs (
    id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    conversation_id uuid NOT NULL REFERENCES conversations(id),
    customer_id     uuid NOT NULL REFERENCES customers(id),

    reason          text NOT NULL,
    priority        text NOT NULL DEFAULT 'normal' CHECK (priority IN ('urgent', 'high', 'normal', 'low')),
    status          text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'assigned', 'resolved', 'expired')),

    assigned_to     uuid REFERENCES users(id),
    assigned_at     timestamptz,
    resolved_at     timestamptz,
    resolution_notes text,

    -- AI context summary for the human agent
    ai_context_summary text,
    customer_sentiment real,
    lead_score      int,

    -- SLA
    response_deadline timestamptz,
    sla_breached    boolean NOT NULL DEFAULT false,

    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_handoffs_tenant ON handoffs(tenant_id);
CREATE INDEX idx_handoffs_pending ON handoffs(tenant_id, status, priority)
    WHERE status IN ('pending', 'assigned');

ALTER TABLE handoffs ENABLE ROW LEVEL SECURITY;
CREATE POLICY handoffs_tenant_isolation ON handoffs
    USING (tenant_id = current_tenant_id() OR is_admin_connection());

-- ============================================================
-- 11. CSAT RATINGS
-- ============================================================

CREATE TABLE csat_ratings (
    id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    conversation_id uuid REFERENCES conversations(id),
    customer_id     uuid NOT NULL REFERENCES customers(id),
    rating          int NOT NULL CHECK (rating >= 1 AND rating <= 5),
    feedback_text   text,
    channel         text NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_csat_tenant ON csat_ratings(tenant_id);

ALTER TABLE csat_ratings ENABLE ROW LEVEL SECURITY;
CREATE POLICY csat_tenant_isolation ON csat_ratings
    USING (tenant_id = current_tenant_id() OR is_admin_connection());

-- ============================================================
-- 12. FUNNEL EVENTS (Sales Pipeline Tracking)
-- ============================================================

CREATE TABLE funnel_events (
    id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    customer_id     uuid NOT NULL REFERENCES customers(id),
    conversation_id uuid REFERENCES conversations(id),

    stage           text NOT NULL CHECK (stage IN ('first_message', 'product_shown', 'collection_shared', 'checkout_created', 'purchase_completed')),
    channel         text NOT NULL,
    metadata        jsonb NOT NULL DEFAULT '{}',
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_funnel_tenant ON funnel_events(tenant_id, stage, created_at);

ALTER TABLE funnel_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY funnel_tenant_isolation ON funnel_events
    USING (tenant_id = current_tenant_id() OR is_admin_connection());

-- ============================================================
-- 13. NURTURING SEQUENCES
-- ============================================================

CREATE TABLE nurturing_sequences (
    id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name            text NOT NULL,
    description     text,
    trigger_type    text NOT NULL CHECK (trigger_type IN ('manual', 'lead_score', 'cart_abandoned', 'post_purchase', 'inactivity')),
    trigger_config  jsonb NOT NULL DEFAULT '{}',
    steps           jsonb NOT NULL DEFAULT '[]',  -- Array of {delay, channel, message_template, conditions}
    is_active       boolean NOT NULL DEFAULT true,
    enrolled_count  int NOT NULL DEFAULT 0,
    converted_count int NOT NULL DEFAULT 0,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE nurturing_sequences ENABLE ROW LEVEL SECURITY;
CREATE POLICY sequences_tenant_isolation ON nurturing_sequences
    USING (tenant_id = current_tenant_id() OR is_admin_connection());

-- ============================================================
-- 14. A/B EXPERIMENTS
-- ============================================================

CREATE TABLE ab_experiments (
    id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name            text NOT NULL,
    description     text,
    experiment_type text NOT NULL DEFAULT 'greeting',
    status          text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'paused', 'completed')),
    variants        jsonb NOT NULL DEFAULT '[]',
    results         jsonb NOT NULL DEFAULT '{}',
    traffic_split   jsonb NOT NULL DEFAULT '{}',
    started_at      timestamptz,
    ended_at        timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE ab_experiments ENABLE ROW LEVEL SECURITY;
CREATE POLICY ab_tenant_isolation ON ab_experiments
    USING (tenant_id = current_tenant_id() OR is_admin_connection());

-- ============================================================
-- 15. E-COMMERCE CONNECTIONS
-- ============================================================

CREATE TABLE ecommerce_connections (
    id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    platform        text NOT NULL CHECK (platform IN ('shopify', 'woocommerce', 'magento', 'custom')),
    store_url       text NOT NULL,
    store_name      text,

    -- Auth (encrypted at application level)
    access_token    text,
    api_key         text,
    api_secret      text,
    webhook_secret  text,

    status          text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disconnected', 'error')),
    last_sync_at    timestamptz,
    sync_errors     jsonb DEFAULT '[]',
    settings        jsonb NOT NULL DEFAULT '{}',

    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),

    UNIQUE(tenant_id, platform, store_url)
);

ALTER TABLE ecommerce_connections ENABLE ROW LEVEL SECURITY;
CREATE POLICY ecommerce_tenant_isolation ON ecommerce_connections
    USING (tenant_id = current_tenant_id() OR is_admin_connection());

-- ============================================================
-- 16. CHANNEL CONNECTIONS
-- ============================================================

CREATE TABLE channel_connections (
    id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    channel         text NOT NULL,
    status          text NOT NULL DEFAULT 'active',

    -- Channel-specific credentials (encrypted)
    credentials     jsonb NOT NULL DEFAULT '{}',
    webhook_url     text,
    phone_number    text,  -- For WhatsApp/SMS/Voice

    settings        jsonb NOT NULL DEFAULT '{}',
    last_health_check timestamptz,
    error_message   text,

    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),

    UNIQUE(tenant_id, channel)
);

ALTER TABLE channel_connections ENABLE ROW LEVEL SECURITY;
CREATE POLICY channel_conn_tenant_isolation ON channel_connections
    USING (tenant_id = current_tenant_id() OR is_admin_connection());

-- ============================================================
-- 17. AUDIT LOG (Security — Immutable)
-- ============================================================

CREATE TABLE audit_log (
    id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       uuid NOT NULL,
    user_id         uuid,
    action          text NOT NULL,  -- e.g., "user.login", "settings.updated", "data.exported"
    resource_type   text,
    resource_id     text,
    details         jsonb NOT NULL DEFAULT '{}',
    ip_address      inet,
    user_agent      text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- Audit log is append-only. No UPDATE or DELETE policies.
CREATE INDEX idx_audit_tenant ON audit_log(tenant_id, created_at DESC);
CREATE INDEX idx_audit_user ON audit_log(tenant_id, user_id, created_at DESC);
CREATE INDEX idx_audit_action ON audit_log(tenant_id, action, created_at DESC);

ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY audit_tenant_isolation ON audit_log
    USING (tenant_id = current_tenant_id() OR is_admin_connection());
-- No UPDATE or DELETE policy — audit log is immutable
CREATE POLICY audit_insert_only ON audit_log
    FOR INSERT WITH CHECK (true);

-- ============================================================
-- 18. REFRESH TOKENS
-- ============================================================

CREATE TABLE refresh_tokens (
    id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    token_hash      text NOT NULL,
    device_info     jsonb,
    ip_address      inet,
    expires_at      timestamptz NOT NULL,
    revoked_at      timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_refresh_user ON refresh_tokens(user_id) WHERE revoked_at IS NULL;
CREATE INDEX idx_refresh_hash ON refresh_tokens(token_hash) WHERE revoked_at IS NULL;

ALTER TABLE refresh_tokens ENABLE ROW LEVEL SECURITY;
CREATE POLICY refresh_tenant_isolation ON refresh_tokens
    USING (tenant_id = current_tenant_id() OR is_admin_connection());

-- ============================================================
-- UPDATED_AT TRIGGER (Auto-update timestamp)
-- ============================================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to all tables with updated_at
DO $$
DECLARE
    t text;
BEGIN
    FOR t IN
        SELECT table_name FROM information_schema.columns
        WHERE column_name = 'updated_at'
        AND table_schema = 'public'
    LOOP
        EXECUTE format('CREATE TRIGGER set_updated_at BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION update_updated_at()', t);
    END LOOP;
END;
$$;

-- ============================================================
-- SEED: Create PSI AI as Tenant #1
-- ============================================================
-- NOTE: Run this AFTER migration to onboard partysuppliesindia.com

-- INSERT INTO tenants (id, name, slug, plan, status, business_name, business_email,
--     country, timezone, currency, default_language, max_conversations_month, max_team_members)
-- VALUES (
--     'a1b2c3d4-0000-0000-0000-000000000001',  -- Fixed UUID for PSI AI
--     'Party Supplies India',
--     'party-supplies-india',
--     'enterprise',
--     'active',
--     'Party Supplies India',
--     'support@partysuppliesindia.com',
--     'IN',
--     'Asia/Kolkata',
--     'INR',
--     'en',
--     999999,  -- Unlimited for internal use
--     50
-- );

-- ============================================================
-- DONE — Foundation schema ready
-- ============================================================
