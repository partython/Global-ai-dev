"""
006 — Translation Glossary + Translation Audit Log

Tables:
- translation_glossary: Per-tenant terminology for consistent brand translations
- translation_audit_log: Tracks all translations for compliance and quality monitoring

Indexes:
- Unique constraint on (tenant_id, source_language, target_language, source_term)
- B-tree on language pairs for fast glossary lookup
- B-tree on tenant + timestamp for audit log queries

Security:
- All tables have tenant_id + RLS policies
- Glossary entries are soft-deletable (is_active flag)
"""

from alembic import op
import sqlalchemy as sa

revision = "006_translation"
down_revision = "005_memory"
branch_labels = None
depends_on = None


def upgrade():
    # ──────────────────────────────────────────────────────────────────────
    # 1. TRANSLATION GLOSSARY — per-tenant brand terminology
    # ──────────────────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS translation_glossary (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL,

        -- Term pair
        source_term     TEXT NOT NULL,
        target_term     TEXT NOT NULL,
        source_language VARCHAR(10) NOT NULL,
        target_language VARCHAR(10) NOT NULL,

        -- Metadata
        context         TEXT,
        is_case_sensitive BOOLEAN DEFAULT FALSE,
        is_active       BOOLEAN DEFAULT TRUE,

        -- Timestamps
        created_at      TIMESTAMPTZ DEFAULT NOW(),
        updated_at      TIMESTAMPTZ DEFAULT NOW(),

        -- Foreign keys
        CONSTRAINT fk_glossary_tenant FOREIGN KEY (tenant_id)
            REFERENCES tenants(id) ON DELETE CASCADE
    );

    -- Unique: one term per language pair per tenant
    CREATE UNIQUE INDEX IF NOT EXISTS idx_glossary_unique
        ON translation_glossary (tenant_id, source_language, target_language, source_term)
        WHERE is_active = TRUE;

    -- Fast lookup by language pair
    CREATE INDEX IF NOT EXISTS idx_glossary_lang_pair
        ON translation_glossary (tenant_id, source_language, target_language)
        WHERE is_active = TRUE;

    -- RLS Policy
    ALTER TABLE translation_glossary ENABLE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation_glossary ON translation_glossary
        USING (tenant_id::text = current_setting('app.current_tenant_id', true));
    """)

    # ──────────────────────────────────────────────────────────────────────
    # 2. TRANSLATION AUDIT LOG — compliance and quality tracking
    # ──────────────────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS translation_audit_log (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL,

        -- Translation details
        source_language VARCHAR(10) NOT NULL,
        target_language VARCHAR(10) NOT NULL,
        source_text_hash VARCHAR(64) NOT NULL,
        character_count INTEGER NOT NULL,
        model_used      VARCHAR(100),

        -- Context
        conversation_id UUID,
        customer_id     UUID,
        channel         VARCHAR(50),
        endpoint        VARCHAR(100),

        -- Quality
        confidence      FLOAT DEFAULT 0.0,
        cached          BOOLEAN DEFAULT FALSE,
        glossary_terms_applied INTEGER DEFAULT 0,

        -- Timestamps
        created_at      TIMESTAMPTZ DEFAULT NOW(),

        -- Foreign keys
        CONSTRAINT fk_audit_tenant FOREIGN KEY (tenant_id)
            REFERENCES tenants(id) ON DELETE CASCADE
    );

    -- Fast lookup by tenant + time for analytics
    CREATE INDEX IF NOT EXISTS idx_audit_tenant_time
        ON translation_audit_log (tenant_id, created_at DESC);

    -- Language pair analytics
    CREATE INDEX IF NOT EXISTS idx_audit_lang_pair
        ON translation_audit_log (tenant_id, source_language, target_language, created_at DESC);

    -- RLS Policy
    ALTER TABLE translation_audit_log ENABLE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation_audit ON translation_audit_log
        USING (tenant_id::text = current_setting('app.current_tenant_id', true));
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS translation_audit_log CASCADE;")
    op.execute("DROP TABLE IF EXISTS translation_glossary CASCADE;")
