"""
011 — Lead Scoring & Analytics Tables

Tables:
- lead_scoring_models: Scoring model registry with multiple strategy support
- lead_scoring_rules: Rule definitions for scoring models (rule_based strategy)
- lead_scores: Current scores and grades per contact per model
- lead_score_history: Audit trail of score changes and triggers

Models support three strategies:
- rule_based: Manual rule definition with field/operator/value matching
- ml_gradient_boost: Gradient boosting models (requires training)
- ml_neural: Neural network models (requires training)

Indexes:
- B-tree on (tenant_id) for tenant-scoped queries
- B-tree on (status) for model filtering
- Composite on (tenant_id, contact_id) for contact scoring lookup
- DESC on (score) for ranking queries
- B-tree on (grade) for grade-based filtering

Security:
- All tables reference tenants(id) with CASCADE
- RLS policies enforce tenant isolation
- Scores linked to contacts(id) via contact_id
"""

from alembic import op
import sqlalchemy as sa

revision = "011_lead_scoring"
down_revision = "010_developer_portal"
branch_labels = None
depends_on = None


def upgrade():
    # ──────────────────────────────────────────────────────────────────────
    # 1. LEAD SCORING MODELS — scoring model registry
    # ──────────────────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS lead_scoring_models (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL,
        name            VARCHAR(255) NOT NULL,
        description     TEXT,
        model_type      VARCHAR(50) NOT NULL DEFAULT 'rule_based',
        status          VARCHAR(20) DEFAULT 'draft',
        config          JSONB NOT NULL DEFAULT '{}',
        feature_weights JSONB DEFAULT '{}',
        accuracy        FLOAT,
        last_trained_at TIMESTAMPTZ,
        created_at      TIMESTAMPTZ DEFAULT NOW(),
        updated_at      TIMESTAMPTZ DEFAULT NOW(),

        CONSTRAINT fk_lsmodel_tenant FOREIGN KEY (tenant_id)
            REFERENCES tenants(id) ON DELETE CASCADE,
        UNIQUE(tenant_id, name)
    );

    CREATE INDEX IF NOT EXISTS idx_lsmodel_tenant ON lead_scoring_models(tenant_id);
    CREATE INDEX IF NOT EXISTS idx_lsmodel_status ON lead_scoring_models(tenant_id, status);

    ALTER TABLE lead_scoring_models ENABLE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation_lsmodel ON lead_scoring_models
        USING (tenant_id::text = current_setting('app.current_tenant_id', true));
    """)

    # ──────────────────────────────────────────────────────────────────────
    # 2. LEAD SCORING RULES — rule definitions for rule_based models
    # ──────────────────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS lead_scoring_rules (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        model_id        UUID NOT NULL,
        tenant_id       UUID NOT NULL,
        field           VARCHAR(100) NOT NULL,
        operator        VARCHAR(20) NOT NULL,
        value           JSONB NOT NULL,
        score_delta     INTEGER NOT NULL DEFAULT 0,
        priority        INTEGER DEFAULT 0,
        is_active       BOOLEAN DEFAULT true,
        created_at      TIMESTAMPTZ DEFAULT NOW(),

        CONSTRAINT fk_lsrule_model FOREIGN KEY (model_id)
            REFERENCES lead_scoring_models(id) ON DELETE CASCADE,
        CONSTRAINT fk_lsrule_tenant FOREIGN KEY (tenant_id)
            REFERENCES tenants(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_lsrule_model ON lead_scoring_rules(model_id);
    CREATE INDEX IF NOT EXISTS idx_lsrule_tenant ON lead_scoring_rules(tenant_id);
    CREATE INDEX IF NOT EXISTS idx_lsrule_active ON lead_scoring_rules(model_id, is_active)
        WHERE is_active = TRUE;

    ALTER TABLE lead_scoring_rules ENABLE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation_lsrule ON lead_scoring_rules
        USING (tenant_id::text = current_setting('app.current_tenant_id', true));
    """)

    # ──────────────────────────────────────────────────────────────────────
    # 3. LEAD SCORES — current scores per contact per model
    # ──────────────────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS lead_scores (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL,
        contact_id      UUID NOT NULL,
        model_id        UUID NOT NULL,
        score           INTEGER NOT NULL DEFAULT 0
            CONSTRAINT ck_score_range CHECK(score >= 0 AND score <= 100),
        grade           VARCHAR(2),
        factors         JSONB DEFAULT '[]',
        scored_at       TIMESTAMPTZ DEFAULT NOW(),
        expires_at      TIMESTAMPTZ,

        CONSTRAINT fk_lscore_tenant FOREIGN KEY (tenant_id)
            REFERENCES tenants(id) ON DELETE CASCADE,
        CONSTRAINT fk_lscore_model FOREIGN KEY (model_id)
            REFERENCES lead_scoring_models(id) ON DELETE CASCADE,
        UNIQUE(tenant_id, contact_id, model_id)
    );

    CREATE INDEX IF NOT EXISTS idx_lscore_tenant_contact ON lead_scores(tenant_id, contact_id);
    CREATE INDEX IF NOT EXISTS idx_lscore_tenant_score ON lead_scores(tenant_id, score DESC);
    CREATE INDEX IF NOT EXISTS idx_lscore_tenant_grade ON lead_scores(tenant_id, grade);
    CREATE INDEX IF NOT EXISTS idx_lscore_expires ON lead_scores(expires_at)
        WHERE expires_at IS NOT NULL;

    ALTER TABLE lead_scores ENABLE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation_lscore ON lead_scores
        USING (tenant_id::text = current_setting('app.current_tenant_id', true));
    """)

    # ──────────────────────────────────────────────────────────────────────
    # 4. LEAD SCORE HISTORY — audit trail of score changes
    # ──────────────────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS lead_score_history (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL,
        contact_id      UUID NOT NULL,
        model_id        UUID NOT NULL,
        old_score       INTEGER,
        new_score       INTEGER NOT NULL,
        old_grade       VARCHAR(2),
        new_grade       VARCHAR(2),
        trigger_event   VARCHAR(100),
        created_at      TIMESTAMPTZ DEFAULT NOW(),

        CONSTRAINT fk_lshist_tenant FOREIGN KEY (tenant_id)
            REFERENCES tenants(id) ON DELETE CASCADE,
        CONSTRAINT fk_lshist_model FOREIGN KEY (model_id)
            REFERENCES lead_scoring_models(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_lshist_tenant_contact ON lead_score_history(tenant_id, contact_id);
    CREATE INDEX IF NOT EXISTS idx_lshist_created ON lead_score_history(created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_lshist_model ON lead_score_history(tenant_id, model_id, created_at DESC);

    ALTER TABLE lead_score_history ENABLE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation_lshist ON lead_score_history
        USING (tenant_id::text = current_setting('app.current_tenant_id', true));
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS lead_score_history CASCADE;")
    op.execute("DROP TABLE IF EXISTS lead_scores CASCADE;")
    op.execute("DROP TABLE IF EXISTS lead_scoring_rules CASCADE;")
    op.execute("DROP TABLE IF EXISTS lead_scoring_models CASCADE;")
