-- WhatsApp Channel Service Database Schema
-- Run this migration to set up all required tables with RLS policies

-- ============================================================================
-- 1. WhatsApp Conversations Table
-- ============================================================================
-- Tracks customer conversations and 24-hour service windows

CREATE TABLE IF NOT EXISTS whatsapp_conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    phone_number_id VARCHAR(255) NOT NULL,
    customer_phone VARCHAR(20) NOT NULL,
    conversation_category VARCHAR(20),  -- 'user_initiated' or 'business_initiated'
    last_customer_message_at TIMESTAMP WITH TIME ZONE,
    last_business_message_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT fk_conversations_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
    UNIQUE(tenant_id, phone_number_id, customer_phone)
);

-- Row Level Security for conversations
ALTER TABLE whatsapp_conversations ENABLE ROW LEVEL SECURITY;

CREATE POLICY whatsapp_conversations_isolation ON whatsapp_conversations
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Indexes for fast lookups
CREATE INDEX idx_whatsapp_conversations_tenant_id ON whatsapp_conversations(tenant_id);
CREATE INDEX idx_whatsapp_conversations_phone_customer ON whatsapp_conversations(phone_number_id, customer_phone);
CREATE INDEX idx_whatsapp_conversations_last_customer_msg ON whatsapp_conversations(last_customer_message_at DESC);

-- ============================================================================
-- 2. WhatsApp Messages Table
-- ============================================================================
-- Audit trail of all messages sent/received

CREATE TABLE IF NOT EXISTS whatsapp_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    phone_number_id VARCHAR(255) NOT NULL,
    message_id VARCHAR(255) UNIQUE NOT NULL,
    customer_phone VARCHAR(20) NOT NULL,
    message_type VARCHAR(50),  -- text, image, audio, video, document, etc
    message_direction VARCHAR(10),  -- 'inbound' or 'outbound'
    status VARCHAR(20),  -- sent, delivered, read, failed
    error_details JSONB,
    content_preview TEXT,  -- First 200 chars of message (no PII)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT fk_messages_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
);

-- Row Level Security
ALTER TABLE whatsapp_messages ENABLE ROW LEVEL SECURITY;

CREATE POLICY whatsapp_messages_isolation ON whatsapp_messages
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Indexes for querying
CREATE INDEX idx_whatsapp_messages_tenant_id ON whatsapp_messages(tenant_id);
CREATE INDEX idx_whatsapp_messages_meta_id ON whatsapp_messages(message_id);
CREATE INDEX idx_whatsapp_messages_phone ON whatsapp_messages(phone_number_id, customer_phone);
CREATE INDEX idx_whatsapp_messages_status ON whatsapp_messages(status);
CREATE INDEX idx_whatsapp_messages_created ON whatsapp_messages(created_at DESC);

-- ============================================================================
-- 3. WhatsApp Templates Table
-- ============================================================================
-- Message templates with approval tracking

CREATE TABLE IF NOT EXISTS whatsapp_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    template_id VARCHAR(255),  -- Meta's template ID after approval
    name VARCHAR(512) NOT NULL,
    category VARCHAR(50),  -- MARKETING, AUTHENTICATION, UTILITY
    language VARCHAR(10) DEFAULT 'en_US',
    body TEXT NOT NULL,
    header_text TEXT,
    header_type VARCHAR(50),  -- TEXT, IMAGE, VIDEO, DOCUMENT
    footer TEXT,
    components JSONB,  -- Full template structure for Meta
    status VARCHAR(20),  -- PENDING, APPROVED, REJECTED, DISABLED
    rejection_reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT fk_templates_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
    CONSTRAINT unique_tenant_template_name UNIQUE(tenant_id, name)
);

-- Row Level Security
ALTER TABLE whatsapp_templates ENABLE ROW LEVEL SECURITY;

CREATE POLICY whatsapp_templates_isolation ON whatsapp_templates
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Indexes
CREATE INDEX idx_whatsapp_templates_tenant_id ON whatsapp_templates(tenant_id);
CREATE INDEX idx_whatsapp_templates_status ON whatsapp_templates(status);
CREATE INDEX idx_whatsapp_templates_created ON whatsapp_templates(created_at DESC);

-- ============================================================================
-- 4. WhatsApp Media Cache Table
-- ============================================================================
-- Temporarily store downloaded media with TTL

CREATE TABLE IF NOT EXISTS whatsapp_media (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    media_id VARCHAR(255) UNIQUE NOT NULL,
    media_type VARCHAR(50),  -- image, audio, video, document, sticker
    media_url TEXT NOT NULL,
    size_bytes INTEGER,
    mime_type VARCHAR(100),
    filename VARCHAR(255),
    expires_at TIMESTAMP WITH TIME ZONE,  -- Meta URLs expire after ~24h
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT fk_media_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
);

-- Row Level Security
ALTER TABLE whatsapp_media ENABLE ROW LEVEL SECURITY;

CREATE POLICY whatsapp_media_isolation ON whatsapp_media
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Indexes
CREATE INDEX idx_whatsapp_media_tenant_id ON whatsapp_media(tenant_id);
CREATE INDEX idx_whatsapp_media_id ON whatsapp_media(media_id);
CREATE INDEX idx_whatsapp_media_expires ON whatsapp_media(expires_at);

-- ============================================================================
-- 5. Update channel_connections for WhatsApp metadata
-- ============================================================================
-- Existing table, just documenting the structure for WhatsApp

-- channel_connections table already exists globally
-- For WhatsApp, store in channel_metadata JSONB:
-- {
--   "phone_number_id": "1234567890123456",
--   "business_account_id": "123456789012345",
--   "access_token": "EABs...",
--   "display_phone_number": "+1 (234) 567-8900",
--   "business_name": "Acme Sales",
--   "business_category": "GENERAL",
--   "quality_rating": "GREEN",
--   "quality_score": 100.0,
--   "about": "We're here to help!",
--   "business_vertical": "RETAIL",
--   "profile_photo_url": "https://...",
--   "website": "https://example.com"
-- }

-- Verify channel_connections exists (from core platform)
-- CREATE TABLE IF NOT EXISTS channel_connections (
--     id UUID PRIMARY KEY,
--     channel VARCHAR(50) NOT NULL,  -- whatsapp, email, sms, etc
--     tenant_id UUID NOT NULL,
--     channel_metadata JSONB,
--     created_at TIMESTAMP DEFAULT NOW(),
--     updated_at TIMESTAMP DEFAULT NOW()
-- );

-- ============================================================================
-- 6. Audit Logging for WhatsApp
-- ============================================================================
-- Track all webhook events and API calls for compliance

CREATE TABLE IF NOT EXISTS whatsapp_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    action VARCHAR(100) NOT NULL,  -- webhook_received, message_sent, template_created, etc
    resource_type VARCHAR(50),  -- conversation, message, template, media, phone_number
    resource_id VARCHAR(255),
    actor_id VARCHAR(255),  -- user_id or system
    actor_type VARCHAR(50),  -- user, webhook, system
    details JSONB,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT fk_audit_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
);

-- Row Level Security
ALTER TABLE whatsapp_audit_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY whatsapp_audit_log_isolation ON whatsapp_audit_log
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Indexes
CREATE INDEX idx_whatsapp_audit_tenant_id ON whatsapp_audit_log(tenant_id);
CREATE INDEX idx_whatsapp_audit_action ON whatsapp_audit_log(action);
CREATE INDEX idx_whatsapp_audit_resource ON whatsapp_audit_log(resource_type, resource_id);
CREATE INDEX idx_whatsapp_audit_created ON whatsapp_audit_log(created_at DESC);

-- ============================================================================
-- 7. Phone Number Quality Rating Tracking
-- ============================================================================
-- Monitor Meta's quality rating changes

CREATE TABLE IF NOT EXISTS whatsapp_phone_quality (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    phone_number_id VARCHAR(255) NOT NULL,
    quality_rating VARCHAR(10),  -- GREEN, YELLOW, RED
    quality_score NUMERIC(5, 2),  -- 0-100
    status_reason TEXT,
    threshold_exceeded BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT fk_quality_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
    CONSTRAINT unique_tenant_phone_quality UNIQUE(tenant_id, phone_number_id)
);

-- Row Level Security
ALTER TABLE whatsapp_phone_quality ENABLE ROW LEVEL SECURITY;

CREATE POLICY whatsapp_phone_quality_isolation ON whatsapp_phone_quality
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Indexes
CREATE INDEX idx_whatsapp_phone_quality_tenant ON whatsapp_phone_quality(tenant_id);
CREATE INDEX idx_whatsapp_phone_quality_rating ON whatsapp_phone_quality(quality_rating);

-- ============================================================================
-- 8. Webhook Event Queue
-- ============================================================================
-- For deduplication and retry logic

CREATE TABLE IF NOT EXISTS whatsapp_webhook_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID,  -- May be NULL if lookup fails
    meta_webhook_id VARCHAR(255) UNIQUE NOT NULL,
    payload JSONB NOT NULL,
    processed BOOLEAN DEFAULT FALSE,
    processing_attempts INTEGER DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE
);

-- This table can be admin-only (not per-tenant) since it's for system processing
-- Indexes
CREATE INDEX idx_webhook_events_processed ON whatsapp_webhook_events(processed);
CREATE INDEX idx_webhook_events_created ON whatsapp_webhook_events(created_at DESC);

-- ============================================================================
-- Functions & Triggers
-- ============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_whatsapp_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for conversations
CREATE TRIGGER whatsapp_conversations_updated_at
    BEFORE UPDATE ON whatsapp_conversations
    FOR EACH ROW EXECUTE FUNCTION update_whatsapp_updated_at();

-- Triggers for messages
CREATE TRIGGER whatsapp_messages_updated_at
    BEFORE UPDATE ON whatsapp_messages
    FOR EACH ROW EXECUTE FUNCTION update_whatsapp_updated_at();

-- Triggers for templates
CREATE TRIGGER whatsapp_templates_updated_at
    BEFORE UPDATE ON whatsapp_templates
    FOR EACH ROW EXECUTE FUNCTION update_whatsapp_updated_at();

-- Triggers for media
CREATE TRIGGER whatsapp_media_updated_at
    BEFORE UPDATE ON whatsapp_media
    FOR EACH ROW EXECUTE FUNCTION update_whatsapp_updated_at();

-- ============================================================================
-- Cleanup Job
-- ============================================================================
-- Remove expired media and old webhook events (run periodically)

-- SELECT cleanup_whatsapp_data();
CREATE OR REPLACE FUNCTION cleanup_whatsapp_data()
RETURNS TABLE(deleted_media_count BIGINT, deleted_webhooks_count BIGINT) AS $$
DECLARE
    v_deleted_media BIGINT;
    v_deleted_webhooks BIGINT;
BEGIN
    -- Delete expired media (older than 7 days)
    DELETE FROM whatsapp_media
    WHERE created_at < NOW() - INTERVAL '7 days';
    GET DIAGNOSTICS v_deleted_media = ROW_COUNT;

    -- Delete processed webhook events (older than 30 days)
    DELETE FROM whatsapp_webhook_events
    WHERE processed = TRUE AND created_at < NOW() - INTERVAL '30 days';
    GET DIAGNOSTICS v_deleted_webhooks = ROW_COUNT;

    RETURN QUERY SELECT v_deleted_media, v_deleted_webhooks;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Grant Permissions
-- ============================================================================
-- Assuming app user is 'priya_app'

GRANT SELECT, INSERT, UPDATE, DELETE ON whatsapp_conversations TO priya_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON whatsapp_messages TO priya_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON whatsapp_templates TO priya_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON whatsapp_media TO priya_app;
GRANT SELECT, INSERT ON whatsapp_audit_log TO priya_app;
GRANT SELECT, INSERT, UPDATE ON whatsapp_phone_quality TO priya_app;
GRANT SELECT, INSERT, UPDATE ON whatsapp_webhook_events TO priya_app;

-- ============================================================================
-- Verification Queries
-- ============================================================================
-- Run these to verify setup:

-- SELECT tablename FROM pg_tables WHERE tablename LIKE 'whatsapp_%';
-- SELECT * FROM information_schema.role_table_grants WHERE table_name LIKE 'whatsapp_%';
-- SELECT schemaname, tablename FROM pg_tables WHERE tablename = 'channel_connections';

-- ============================================================================
-- END OF MIGRATION
-- ============================================================================
