-- Appointment Booking Service Schema
-- Multi-tenant PostgreSQL schema with Row-Level Security

-- ============================================================================
-- ENUMS
-- ============================================================================

CREATE TYPE appointment_status AS ENUM (
    'pending',
    'confirmed',
    'completed',
    'cancelled',
    'no_show',
    'rescheduled'
);

CREATE TYPE availability_type AS ENUM (
    'working_hours',
    'break',
    'holiday',
    'unavailable'
);

CREATE TYPE reminder_type AS ENUM (
    'email',
    'sms',
    'push',
    'in_app'
);

-- ============================================================================
-- APPOINTMENTS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS appointments (
    appointment_id VARCHAR(255) PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL,
    customer_id VARCHAR(255) NOT NULL,
    agent_id VARCHAR(255) NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    scheduled_start TIMESTAMP WITH TIME ZONE NOT NULL,
    scheduled_end TIMESTAMP WITH TIME ZONE NOT NULL,
    timezone VARCHAR(63) NOT NULL,
    status appointment_status NOT NULL DEFAULT 'pending',
    meeting_link VARCHAR(2048),
    pre_appointment_form_url VARCHAR(2048),
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    reminder_sent BOOLEAN DEFAULT FALSE,
    no_show_count INTEGER DEFAULT 0,
    
    CONSTRAINT rls_tenant CHECK (tenant_id IS NOT NULL),
    CONSTRAINT valid_dates CHECK (scheduled_start < scheduled_end)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_appointments_tenant ON appointments(tenant_id);
CREATE INDEX IF NOT EXISTS idx_appointments_agent_date ON appointments(agent_id, scheduled_start);
CREATE INDEX IF NOT EXISTS idx_appointments_customer ON appointments(customer_id);
CREATE INDEX IF NOT EXISTS idx_appointments_status ON appointments(status);
CREATE INDEX IF NOT EXISTS idx_appointments_date_range ON appointments(scheduled_start, scheduled_end);

-- ============================================================================
-- AVAILABILITY WINDOWS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS availability_windows (
    availability_id VARCHAR(255) PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL,
    agent_id VARCHAR(255) NOT NULL,
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE NOT NULL,
    availability_type availability_type NOT NULL,
    recurring_pattern VARCHAR(50),  -- 'daily', 'weekly', 'monthly'
    timezone VARCHAR(63) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT rls_tenant CHECK (tenant_id IS NOT NULL),
    CONSTRAINT valid_window_dates CHECK (start_time < end_time)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_availability_tenant ON availability_windows(tenant_id);
CREATE INDEX IF NOT EXISTS idx_availability_agent ON availability_windows(agent_id);
CREATE INDEX IF NOT EXISTS idx_availability_agent_date ON availability_windows(agent_id, start_time);
CREATE INDEX IF NOT EXISTS idx_availability_date_range ON availability_windows(start_time, end_time);

-- ============================================================================
-- REMINDERS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS reminders (
    reminder_id VARCHAR(255) PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL,
    appointment_id VARCHAR(255) NOT NULL,
    reminder_type reminder_type NOT NULL,
    sent_at TIMESTAMP WITH TIME ZONE NOT NULL,
    delivery_status VARCHAR(50) DEFAULT 'pending',  -- 'pending', 'sent', 'failed'
    delivery_error TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    
    CONSTRAINT rls_tenant CHECK (tenant_id IS NOT NULL),
    FOREIGN KEY (appointment_id) REFERENCES appointments(appointment_id) ON DELETE CASCADE
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_reminders_tenant ON reminders(tenant_id);
CREATE INDEX IF NOT EXISTS idx_reminders_appointment ON reminders(appointment_id);
CREATE INDEX IF NOT EXISTS idx_reminders_status ON reminders(delivery_status);

-- ============================================================================
-- BOOKING PREFERENCES TABLE (for per-tenant configuration)
-- ============================================================================

CREATE TABLE IF NOT EXISTS booking_preferences (
    preference_id VARCHAR(255) PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL UNIQUE,
    buffer_minutes INTEGER DEFAULT 15,
    min_advance_booking_hours INTEGER DEFAULT 1,
    max_advance_booking_days INTEGER DEFAULT 90,
    slot_duration_minutes INTEGER DEFAULT 60,
    timezone VARCHAR(63) DEFAULT 'UTC',
    enable_waitlist BOOLEAN DEFAULT TRUE,
    enable_auto_reminders BOOLEAN DEFAULT TRUE,
    reminder_before_minutes INTEGER DEFAULT 60,
    allow_rescheduling BOOLEAN DEFAULT TRUE,
    allow_cancellation BOOLEAN DEFAULT TRUE,
    cancellation_window_minutes INTEGER DEFAULT 120,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    
    CONSTRAINT rls_tenant CHECK (tenant_id IS NOT NULL)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_booking_preferences_tenant ON booking_preferences(tenant_id);

-- ============================================================================
-- WAITLIST TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS waitlist (
    waitlist_id VARCHAR(255) PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL,
    customer_id VARCHAR(255) NOT NULL,
    agent_id VARCHAR(255) NOT NULL,
    preferred_date DATE NOT NULL,
    preferred_time_start TIMESTAMP WITH TIME ZONE,
    preferred_time_end TIMESTAMP WITH TIME ZONE,
    duration_minutes INTEGER DEFAULT 60,
    status VARCHAR(50) DEFAULT 'waiting',  -- 'waiting', 'contacted', 'booked', 'cancelled'
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    
    CONSTRAINT rls_tenant CHECK (tenant_id IS NOT NULL)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_waitlist_tenant ON waitlist(tenant_id);
CREATE INDEX IF NOT EXISTS idx_waitlist_customer ON waitlist(customer_id);
CREATE INDEX IF NOT EXISTS idx_waitlist_agent ON waitlist(agent_id);
CREATE INDEX IF NOT EXISTS idx_waitlist_status ON waitlist(status);

-- ============================================================================
-- AUDIT LOG TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS appointment_audit_log (
    log_id VARCHAR(255) PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL,
    appointment_id VARCHAR(255) NOT NULL,
    action VARCHAR(100) NOT NULL,  -- 'created', 'updated', 'cancelled', 'confirmed', etc.
    changed_by VARCHAR(255),
    old_values JSONB,
    new_values JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    
    CONSTRAINT rls_tenant CHECK (tenant_id IS NOT NULL),
    FOREIGN KEY (appointment_id) REFERENCES appointments(appointment_id) ON DELETE CASCADE
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_audit_tenant ON appointment_audit_log(tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_appointment ON appointment_audit_log(appointment_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON appointment_audit_log(created_at);

-- ============================================================================
-- ANALYTICS VIEW
-- ============================================================================

CREATE OR REPLACE VIEW appointment_analytics AS
SELECT
    tenant_id,
    agent_id,
    DATE(scheduled_start) as appointment_date,
    COUNT(*) as total_appointments,
    COUNT(CASE WHEN status = 'confirmed' THEN 1 END) as confirmed_appointments,
    COUNT(CASE WHEN status = 'cancelled' THEN 1 END) as cancelled_appointments,
    COUNT(CASE WHEN status = 'no_show' THEN 1 END) as no_show_appointments,
    AVG(EXTRACT(EPOCH FROM (scheduled_end - scheduled_start))/60) as avg_duration_minutes
FROM appointments
GROUP BY tenant_id, agent_id, DATE(scheduled_start);

-- ============================================================================
-- ROW LEVEL SECURITY POLICIES (if using RLS)
-- ============================================================================

-- Uncomment to enable RLS (requires proper database role setup)
/*
ALTER TABLE appointments ENABLE ROW LEVEL SECURITY;
ALTER TABLE availability_windows ENABLE ROW LEVEL SECURITY;
ALTER TABLE reminders ENABLE ROW LEVEL SECURITY;
ALTER TABLE booking_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE waitlist ENABLE ROW LEVEL SECURITY;
ALTER TABLE appointment_audit_log ENABLE ROW LEVEL SECURITY;

-- Policies would be created based on tenant_id from application context
-- Example: CREATE POLICY tenant_isolation ON appointments
--   USING (tenant_id = current_setting('app.current_tenant_id'))
*/

-- ============================================================================
-- SAMPLE DATA (for testing)
-- ============================================================================

-- Note: Insert sample data only in development environment
-- Example booking preferences
/*
INSERT INTO booking_preferences (
    preference_id, tenant_id, buffer_minutes, min_advance_booking_hours,
    max_advance_booking_days, slot_duration_minutes, timezone, created_at, updated_at
) VALUES (
    'pref_123', 'tenant_001', 15, 1, 90, 60, 'UTC',
    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
);
*/
