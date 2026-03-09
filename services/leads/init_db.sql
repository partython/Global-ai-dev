-- Lead Scoring & Sales Pipeline Database Schema

-- Leads table (core table)
CREATE TABLE IF NOT EXISTS leads (
    lead_id VARCHAR(255) PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL,
    first_name VARCHAR(255) NOT NULL,
    last_name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    phone VARCHAR(20),
    company VARCHAR(255),
    current_score FLOAT DEFAULT 0,
    lead_grade VARCHAR(1) DEFAULT 'F',
    pipeline_stage VARCHAR(50) DEFAULT 'New',
    source_channel VARCHAR(50) NOT NULL,
    assigned_to VARCHAR(255),
    deal_value FLOAT,
    win_probability FLOAT,
    custom_data JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_leads_tenant_id ON leads(tenant_id);
CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(email);
CREATE INDEX IF NOT EXISTS idx_leads_tenant_email ON leads(tenant_id, email);
CREATE INDEX IF NOT EXISTS idx_leads_stage ON leads(pipeline_stage);
CREATE INDEX IF NOT EXISTS idx_leads_tenant_stage ON leads(tenant_id, pipeline_stage);
CREATE INDEX IF NOT EXISTS idx_leads_assigned_to ON leads(assigned_to);
CREATE INDEX IF NOT EXISTS idx_leads_created_at ON leads(created_at DESC);

-- Lead score history table
CREATE TABLE IF NOT EXISTS lead_score_history (
    id SERIAL PRIMARY KEY,
    lead_id VARCHAR(255) NOT NULL,
    tenant_id VARCHAR(255) NOT NULL,
    score FLOAT NOT NULL,
    grade VARCHAR(1) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_score_history_lead ON lead_score_history(lead_id);
CREATE INDEX IF NOT EXISTS idx_score_history_tenant ON lead_score_history(tenant_id);
CREATE INDEX IF NOT EXISTS idx_score_history_created ON lead_score_history(created_at DESC);

-- Lead activity table
CREATE TABLE IF NOT EXISTS lead_activity (
    id SERIAL PRIMARY KEY,
    lead_id VARCHAR(255) NOT NULL,
    tenant_id VARCHAR(255) NOT NULL,
    activity_type VARCHAR(50) NOT NULL,
    details JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_activity_lead ON lead_activity(lead_id);
CREATE INDEX IF NOT EXISTS idx_activity_tenant ON lead_activity(tenant_id);
CREATE INDEX IF NOT EXISTS idx_activity_type ON lead_activity(activity_type);
CREATE INDEX IF NOT EXISTS idx_activity_created ON lead_activity(created_at DESC);

-- Pipeline configuration table
CREATE TABLE IF NOT EXISTS pipeline_config (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL,
    stage_name VARCHAR(100) NOT NULL,
    order_index INT NOT NULL,
    stage_gate_requirements JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tenant_id, stage_name)
);

CREATE INDEX IF NOT EXISTS idx_pipeline_tenant ON pipeline_config(tenant_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_order ON pipeline_config(tenant_id, order_index);

-- Optional: Scoring rules configuration per tenant
CREATE TABLE IF NOT EXISTS scoring_rules (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL,
    rule_name VARCHAR(100) NOT NULL,
    engagement_weight FLOAT DEFAULT 0.3,
    demographic_weight FLOAT DEFAULT 0.25,
    behavior_weight FLOAT DEFAULT 0.25,
    intent_weight FLOAT DEFAULT 0.2,
    custom_weights JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tenant_id, rule_name)
);

CREATE INDEX IF NOT EXISTS idx_scoring_rules_tenant ON scoring_rules(tenant_id);

-- Optional: Lead nurturing sequences
CREATE TABLE IF NOT EXISTS nurturing_sequences (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL,
    lead_id VARCHAR(255) NOT NULL,
    sequence_name VARCHAR(100),
    current_step INT DEFAULT 1,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_nurturing_tenant ON nurturing_sequences(tenant_id);
CREATE INDEX IF NOT EXISTS idx_nurturing_lead ON nurturing_sequences(lead_id);
CREATE INDEX IF NOT EXISTS idx_nurturing_status ON nurturing_sequences(status);

-- Enable Row Level Security (optional, for additional tenant isolation)
-- ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE lead_score_history ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE lead_activity ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE pipeline_config ENABLE ROW LEVEL SECURITY;

-- Insert default pipeline stages for new tenants (optional)
-- INSERT INTO pipeline_config (tenant_id, stage_name, order_index, stage_gate_requirements)
-- VALUES 
--   ('default', 'New', 1, '{}'),
--   ('default', 'Qualified', 2, '{"min_score": 50}'),
--   ('default', 'Proposal', 3, '{"requires_assignment": true}'),
--   ('default', 'Negotiation', 4, '{}'),
--   ('default', 'Won', 5, '{}'),
--   ('default', 'Lost', 6, '{}')
-- ON CONFLICT DO NOTHING;
