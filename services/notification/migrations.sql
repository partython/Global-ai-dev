-- Notification Service Database Schema
-- Run this migration to set up all required tables

-- ============================================================================
-- Notifications Table - Core notification storage
-- ============================================================================

CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL,
    notification_type VARCHAR(50) NOT NULL,
    title VARCHAR(200) NOT NULL,
    body VARCHAR(1000) NOT NULL,
    data JSONB,
    priority VARCHAR(20) DEFAULT 'normal' CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
    is_read BOOLEAN DEFAULT false,
    is_archived BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    read_at TIMESTAMP WITH TIME ZONE,
    archived_at TIMESTAMP WITH TIME ZONE
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS notifications_tenant_user_created_idx
    ON notifications(tenant_id, user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS notifications_user_read_archived_idx
    ON notifications(user_id, is_read, is_archived) WHERE is_archived = false;
CREATE INDEX IF NOT EXISTS notifications_priority_idx
    ON notifications(priority) WHERE priority IN ('high', 'urgent');

-- RLS Policy for notifications
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS notifications_tenant_isolation ON notifications;
CREATE POLICY notifications_tenant_isolation ON notifications
    USING (tenant_id = current_setting('app.current_tenant_id')::UUID);

-- ============================================================================
-- Device Tokens Table - Firebase Cloud Messaging device management
-- ============================================================================

CREATE TABLE IF NOT EXISTS device_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL,
    device_token VARCHAR(512) NOT NULL,
    device_type VARCHAR(20) NOT NULL CHECK (device_type IN ('ios', 'android', 'web')),
    device_name VARCHAR(200),
    app_version VARCHAR(20),
    os_version VARCHAR(20),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id, user_id, device_token)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS device_tokens_user_active_idx
    ON device_tokens(user_id, is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS device_tokens_device_type_idx
    ON device_tokens(device_type);

-- RLS Policy for device tokens
ALTER TABLE device_tokens ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS device_tokens_tenant_isolation ON device_tokens;
CREATE POLICY device_tokens_tenant_isolation ON device_tokens
    USING (tenant_id = current_setting('app.current_tenant_id')::UUID);

-- ============================================================================
-- Notification Preferences Table - User notification settings
-- ============================================================================

CREATE TABLE IF NOT EXISTS notification_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL UNIQUE,
    do_not_disturb_enabled BOOLEAN DEFAULT false,
    do_not_disturb_start VARCHAR(5),  -- HH:MM format
    do_not_disturb_end VARCHAR(5),    -- HH:MM format
    preferred_channels TEXT[] DEFAULT ARRAY['in_app', 'push'],
    mute_all BOOLEAN DEFAULT false,
    notification_sounds BOOLEAN DEFAULT true,
    notification_badges BOOLEAN DEFAULT true,
    marketing_emails BOOLEAN DEFAULT true,
    system_alerts BOOLEAN DEFAULT true,
    per_type_preferences JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Index for lookups
CREATE INDEX IF NOT EXISTS notification_preferences_user_idx
    ON notification_preferences(user_id);

-- RLS Policy for notification preferences
ALTER TABLE notification_preferences ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS notification_preferences_tenant_isolation ON notification_preferences;
CREATE POLICY notification_preferences_tenant_isolation ON notification_preferences
    USING (tenant_id = current_setting('app.current_tenant_id')::UUID);

-- ============================================================================
-- Notification Templates Table - Template definitions per tenant
-- ============================================================================

CREATE TABLE IF NOT EXISTS notification_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    name VARCHAR(100) NOT NULL,
    notification_type VARCHAR(50) NOT NULL,
    title_template VARCHAR(200) NOT NULL,
    body_template VARCHAR(1000) NOT NULL,
    data_template JSONB,
    language VARCHAR(10) DEFAULT 'en',
    variables TEXT[] DEFAULT ARRAY[]::TEXT[],
    priority VARCHAR(20) DEFAULT 'normal' CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
    channels TEXT[] DEFAULT ARRAY['in_app', 'push'],
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id, name, language)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS notification_templates_type_lang_idx
    ON notification_templates(tenant_id, notification_type, language);
CREATE INDEX IF NOT EXISTS notification_templates_name_idx
    ON notification_templates(tenant_id, name);

-- RLS Policy for notification templates
ALTER TABLE notification_templates ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS notification_templates_tenant_isolation ON notification_templates;
CREATE POLICY notification_templates_tenant_isolation ON notification_templates
    USING (tenant_id = current_setting('app.current_tenant_id')::UUID);

-- ============================================================================
-- Notification Topic Subscriptions Table - User subscriptions to topics
-- ============================================================================

CREATE TABLE IF NOT EXISTS notification_topic_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL,
    topic VARCHAR(100) NOT NULL,
    subscribed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id, user_id, topic)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS topic_subscriptions_topic_idx
    ON notification_topic_subscriptions(tenant_id, topic);
CREATE INDEX IF NOT EXISTS topic_subscriptions_user_idx
    ON notification_topic_subscriptions(user_id);

-- RLS Policy for topic subscriptions
ALTER TABLE notification_topic_subscriptions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS topic_subscriptions_tenant_isolation ON notification_topic_subscriptions;
CREATE POLICY topic_subscriptions_tenant_isolation ON notification_topic_subscriptions
    USING (tenant_id = current_setting('app.current_tenant_id')::UUID);

-- ============================================================================
-- Notification Delivery Log Table - Track delivery attempts (optional, for audit)
-- ============================================================================

CREATE TABLE IF NOT EXISTS notification_delivery_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    notification_id UUID NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
    channel VARCHAR(50) NOT NULL CHECK (channel IN ('push', 'in_app', 'email')),
    delivery_status VARCHAR(50) DEFAULT 'pending' CHECK (delivery_status IN ('pending', 'sent', 'delivered', 'failed')),
    device_token VARCHAR(512),
    error_message TEXT,
    delivered_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Index for lookups
CREATE INDEX IF NOT EXISTS delivery_logs_notification_idx
    ON notification_delivery_logs(notification_id);
CREATE INDEX IF NOT EXISTS delivery_logs_status_idx
    ON notification_delivery_logs(delivery_status);

-- RLS Policy for delivery logs
ALTER TABLE notification_delivery_logs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS delivery_logs_tenant_isolation ON notification_delivery_logs;
CREATE POLICY delivery_logs_tenant_isolation ON notification_delivery_logs
    USING (tenant_id = current_setting('app.current_tenant_id')::UUID);

-- ============================================================================
-- Grants for RLS policies (if using separate app user)
-- ============================================================================
-- ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
--   GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;

-- ============================================================================
-- Clean up test data function (optional)
-- ============================================================================

CREATE OR REPLACE FUNCTION cleanup_old_notifications(days_old INT DEFAULT 90)
RETURNS TABLE(archived_count INT) AS $$
BEGIN
    RETURN QUERY
    UPDATE notifications
    SET is_archived = true, archived_at = NOW()
    WHERE is_archived = false 
      AND created_at < NOW() - INTERVAL '1 day' * days_old
      AND is_read = true
    RETURNING COUNT(*) OVER() as archived_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Helper function to get unread notification count per user
-- ============================================================================

CREATE OR REPLACE FUNCTION get_unread_notification_count(user_uuid UUID)
RETURNS INT AS $$
DECLARE
    count INT;
BEGIN
    SELECT COUNT(*) INTO count
    FROM notifications
    WHERE user_id = user_uuid 
      AND is_read = false 
      AND is_archived = false;
    RETURN count;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Completion message
-- ============================================================================
-- Migration completed. All notification service tables are now ready.
-- Tables: notifications, device_tokens, notification_preferences, notification_templates,
--         notification_topic_subscriptions, notification_delivery_logs
-- RLS policies enabled on all tables for tenant isolation.
