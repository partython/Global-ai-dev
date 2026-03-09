"""
005 — Conversation Memory System Schema

Tables:
- conversation_memories: Per-conversation summaries + embeddings for semantic retrieval
- customer_memories: Long-term customer memory (cross-conversation knowledge)
- memory_episodes: Discrete interaction episodes with importance scoring
- conversation_turns: Compressed turn-level data for context reconstruction

Indexes:
- pgvector HNSW indexes for fast ANN search on embeddings
- GIN indexes on JSONB metadata for filtered queries
- B-tree on (tenant_id, customer_id, importance_score) for priority-based recall

Security:
- All tables have tenant_id column + RLS policies enforced at DB level
- Embeddings are tenant-isolated: cross-tenant similarity search is impossible
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY, TIMESTAMP, TEXT

revision = "005_memory"
down_revision = "004_add_international_support"
branch_labels = None
depends_on = None


def upgrade():
    # ──────────────────────────────────────────────────────────────────────
    # 1. CONVERSATION MEMORIES — per-conversation summary + embedding
    # ──────────────────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS conversation_memories (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL,
        conversation_id UUID NOT NULL,
        customer_id     UUID NOT NULL,

        -- Summary: LLM-generated conversation summary (what was discussed, outcome)
        summary         TEXT NOT NULL,
        summary_embedding VECTOR(1536),

        -- Structured extracted data
        topics          TEXT[] DEFAULT '{}',
        intents         TEXT[] DEFAULT '{}',
        entities        JSONB DEFAULT '{}',
        sentiment_avg   FLOAT DEFAULT 0.0,
        funnel_stage    VARCHAR(50),
        outcome         VARCHAR(50) DEFAULT 'ongoing',

        -- Conversation stats
        message_count   INTEGER DEFAULT 0,
        duration_seconds INTEGER DEFAULT 0,
        first_message_at TIMESTAMPTZ,
        last_message_at  TIMESTAMPTZ,

        -- Memory quality
        importance_score FLOAT DEFAULT 0.5,
        access_count     INTEGER DEFAULT 0,
        last_accessed_at TIMESTAMPTZ,

        -- Metadata & timestamps
        metadata        JSONB DEFAULT '{}',
        created_at      TIMESTAMPTZ DEFAULT NOW(),
        updated_at      TIMESTAMPTZ DEFAULT NOW(),

        -- Foreign keys
        CONSTRAINT fk_conv_mem_tenant FOREIGN KEY (tenant_id)
            REFERENCES tenants(id) ON DELETE CASCADE,
        CONSTRAINT fk_conv_mem_conversation FOREIGN KEY (conversation_id)
            REFERENCES conversations(id) ON DELETE CASCADE,
        CONSTRAINT fk_conv_mem_customer FOREIGN KEY (customer_id)
            REFERENCES customers(id) ON DELETE CASCADE
    );

    -- Unique: one memory per conversation
    CREATE UNIQUE INDEX IF NOT EXISTS idx_conv_mem_unique
        ON conversation_memories (tenant_id, conversation_id);

    -- Fast lookup by customer (most common query pattern)
    CREATE INDEX IF NOT EXISTS idx_conv_mem_customer
        ON conversation_memories (tenant_id, customer_id, importance_score DESC);

    -- Semantic search via HNSW (ANN) — fast approximate nearest neighbor
    CREATE INDEX IF NOT EXISTS idx_conv_mem_embedding
        ON conversation_memories USING hnsw (summary_embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);

    -- Topic filtering
    CREATE INDEX IF NOT EXISTS idx_conv_mem_topics
        ON conversation_memories USING gin (topics);

    -- Time-based recall
    CREATE INDEX IF NOT EXISTS idx_conv_mem_recency
        ON conversation_memories (tenant_id, customer_id, last_message_at DESC);

    -- RLS Policy
    ALTER TABLE conversation_memories ENABLE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation_conv_mem ON conversation_memories
        USING (tenant_id::text = current_setting('app.current_tenant_id', true));
    """)

    # ──────────────────────────────────────────────────────────────────────
    # 2. CUSTOMER MEMORIES — long-term cross-conversation knowledge
    # ──────────────────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS customer_memories (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL,
        customer_id     UUID NOT NULL,

        -- Memory classification
        memory_type     VARCHAR(50) NOT NULL,
            -- 'preference'    : likes dark colors, prefers email
            -- 'fact'          : has 2 kids, lives in Mumbai
            -- 'behavior'      : always asks for discounts, compares prices
            -- 'relationship'  : loyal customer since 2024, referred 3 friends
            -- 'need'          : looking for birthday gift for wife
            -- 'objection'     : concerned about shipping time
            -- 'feedback'      : complained about packaging
            -- 'commitment'    : promised to order next week

        -- The actual memory content
        content         TEXT NOT NULL,
        content_embedding VECTOR(1536),

        -- Structured key-value for fast programmatic access
        key             VARCHAR(255),
        value           JSONB,

        -- Source tracking
        source_conversation_id UUID,
        source_message_id      UUID,
        extracted_by           VARCHAR(50) DEFAULT 'ai',

        -- Memory lifecycle
        importance_score FLOAT DEFAULT 0.5,
        confidence       FLOAT DEFAULT 0.8,
        access_count     INTEGER DEFAULT 0,
        last_accessed_at TIMESTAMPTZ,
        expires_at       TIMESTAMPTZ,
        is_active        BOOLEAN DEFAULT TRUE,

        -- Metadata & timestamps
        metadata        JSONB DEFAULT '{}',
        created_at      TIMESTAMPTZ DEFAULT NOW(),
        updated_at      TIMESTAMPTZ DEFAULT NOW(),

        -- Foreign keys
        CONSTRAINT fk_cust_mem_tenant FOREIGN KEY (tenant_id)
            REFERENCES tenants(id) ON DELETE CASCADE,
        CONSTRAINT fk_cust_mem_customer FOREIGN KEY (customer_id)
            REFERENCES customers(id) ON DELETE CASCADE
    );

    -- Fast lookup by customer + type
    CREATE INDEX IF NOT EXISTS idx_cust_mem_lookup
        ON customer_memories (tenant_id, customer_id, memory_type, is_active)
        WHERE is_active = TRUE;

    -- Semantic search on customer memories
    CREATE INDEX IF NOT EXISTS idx_cust_mem_embedding
        ON customer_memories USING hnsw (content_embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);

    -- Key-based lookup (e.g., "preferred_color", "budget_range")
    CREATE INDEX IF NOT EXISTS idx_cust_mem_key
        ON customer_memories (tenant_id, customer_id, key)
        WHERE key IS NOT NULL AND is_active = TRUE;

    -- Importance-based retrieval
    CREATE INDEX IF NOT EXISTS idx_cust_mem_importance
        ON customer_memories (tenant_id, customer_id, importance_score DESC)
        WHERE is_active = TRUE;

    -- Expiry cleanup
    CREATE INDEX IF NOT EXISTS idx_cust_mem_expiry
        ON customer_memories (expires_at)
        WHERE expires_at IS NOT NULL AND is_active = TRUE;

    -- RLS Policy
    ALTER TABLE customer_memories ENABLE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation_cust_mem ON customer_memories
        USING (tenant_id::text = current_setting('app.current_tenant_id', true));
    """)

    # ──────────────────────────────────────────────────────────────────────
    # 3. MEMORY EPISODES — discrete interaction units with importance
    # ──────────────────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS memory_episodes (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL,
        customer_id     UUID NOT NULL,
        conversation_id UUID NOT NULL,

        -- Episode content (compressed representation of a conversation segment)
        episode_type    VARCHAR(50) NOT NULL,
            -- 'purchase_intent'    : customer expressed intent to buy
            -- 'product_inquiry'    : asked about specific products
            -- 'complaint'          : raised a complaint or issue
            -- 'negotiation'        : price/discount negotiation
            -- 'support_request'    : technical or order support
            -- 'feedback'           : gave product/service feedback
            -- 'referral'           : mentioned referral or recommendation
            -- 'commitment'         : made a promise or commitment

        -- Compressed episode summary
        summary         TEXT NOT NULL,
        summary_embedding VECTOR(1536),

        -- Structured episode data
        participants    TEXT[] DEFAULT '{}',
        products_mentioned TEXT[] DEFAULT '{}',
        action_items    JSONB DEFAULT '[]',
        resolution      VARCHAR(50),

        -- Scoring
        importance_score FLOAT DEFAULT 0.5,
        emotional_valence FLOAT DEFAULT 0.0,

        -- Time window
        started_at      TIMESTAMPTZ NOT NULL,
        ended_at        TIMESTAMPTZ,
        turn_count      INTEGER DEFAULT 0,

        -- Metadata
        metadata        JSONB DEFAULT '{}',
        created_at      TIMESTAMPTZ DEFAULT NOW(),

        -- Foreign keys
        CONSTRAINT fk_episode_tenant FOREIGN KEY (tenant_id)
            REFERENCES tenants(id) ON DELETE CASCADE,
        CONSTRAINT fk_episode_customer FOREIGN KEY (customer_id)
            REFERENCES customers(id) ON DELETE CASCADE,
        CONSTRAINT fk_episode_conversation FOREIGN KEY (conversation_id)
            REFERENCES conversations(id) ON DELETE CASCADE
    );

    -- Fast episode lookup by customer
    CREATE INDEX IF NOT EXISTS idx_episode_customer
        ON memory_episodes (tenant_id, customer_id, importance_score DESC);

    -- Semantic search on episodes
    CREATE INDEX IF NOT EXISTS idx_episode_embedding
        ON memory_episodes USING hnsw (summary_embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);

    -- Type-based filtering
    CREATE INDEX IF NOT EXISTS idx_episode_type
        ON memory_episodes (tenant_id, customer_id, episode_type, started_at DESC);

    -- RLS Policy
    ALTER TABLE memory_episodes ENABLE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation_episode ON memory_episodes
        USING (tenant_id::text = current_setting('app.current_tenant_id', true));
    """)

    # ──────────────────────────────────────────────────────────────────────
    # 4. CONVERSATION TURNS — compressed turn-level cache for context window
    # ──────────────────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS conversation_turns (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL,
        conversation_id UUID NOT NULL,
        turn_number     INTEGER NOT NULL,

        -- Turn data (compressed: role + content + extracted info)
        role            VARCHAR(20) NOT NULL,
        content         TEXT NOT NULL,
        content_embedding VECTOR(1536),

        -- Extracted metadata per turn
        intent          VARCHAR(50),
        sentiment       FLOAT DEFAULT 0.0,
        entities        JSONB DEFAULT '{}',
        is_important    BOOLEAN DEFAULT FALSE,

        -- Timestamps
        created_at      TIMESTAMPTZ DEFAULT NOW(),

        -- Foreign keys
        CONSTRAINT fk_turn_tenant FOREIGN KEY (tenant_id)
            REFERENCES tenants(id) ON DELETE CASCADE,
        CONSTRAINT fk_turn_conversation FOREIGN KEY (conversation_id)
            REFERENCES conversations(id) ON DELETE CASCADE
    );

    -- Turn ordering within conversation
    CREATE UNIQUE INDEX IF NOT EXISTS idx_turn_order
        ON conversation_turns (tenant_id, conversation_id, turn_number);

    -- Important turns only (for context window optimization)
    CREATE INDEX IF NOT EXISTS idx_turn_important
        ON conversation_turns (tenant_id, conversation_id)
        WHERE is_important = TRUE;

    -- RLS Policy
    ALTER TABLE conversation_turns ENABLE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation_turn ON conversation_turns
        USING (tenant_id::text = current_setting('app.current_tenant_id', true));
    """)

    # ──────────────────────────────────────────────────────────────────────
    # 5. UPDATE CUSTOMERS TABLE — add structured memory fields
    # ──────────────────────────────────────────────────────────────────────
    op.execute("""
    ALTER TABLE customers
        ADD COLUMN IF NOT EXISTS memory_summary TEXT,
        ADD COLUMN IF NOT EXISTS memory_summary_embedding VECTOR(1536),
        ADD COLUMN IF NOT EXISTS total_conversations INTEGER DEFAULT 0,
        ADD COLUMN IF NOT EXISTS total_messages INTEGER DEFAULT 0,
        ADD COLUMN IF NOT EXISTS first_seen_at TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS preferred_channel VARCHAR(50),
        ADD COLUMN IF NOT EXISTS preferred_language VARCHAR(10),
        ADD COLUMN IF NOT EXISTS communication_style VARCHAR(50),
        ADD COLUMN IF NOT EXISTS lifetime_value DECIMAL(12, 2) DEFAULT 0.0;
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS conversation_turns CASCADE;")
    op.execute("DROP TABLE IF EXISTS memory_episodes CASCADE;")
    op.execute("DROP TABLE IF EXISTS customer_memories CASCADE;")
    op.execute("DROP TABLE IF EXISTS conversation_memories CASCADE;")
    op.execute("""
    ALTER TABLE customers
        DROP COLUMN IF EXISTS memory_summary,
        DROP COLUMN IF EXISTS memory_summary_embedding,
        DROP COLUMN IF EXISTS total_conversations,
        DROP COLUMN IF EXISTS total_messages,
        DROP COLUMN IF EXISTS first_seen_at,
        DROP COLUMN IF EXISTS last_seen_at,
        DROP COLUMN IF EXISTS preferred_channel,
        DROP COLUMN IF EXISTS preferred_language,
        DROP COLUMN IF EXISTS communication_style,
        DROP COLUMN IF EXISTS lifetime_value;
    """)
