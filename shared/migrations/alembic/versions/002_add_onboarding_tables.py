"""Add Onboarding Tables for Customer Journey

Revision ID: 002_add_onboarding_tables
Revises: 001_foundation_schema
Create Date: 2025-03-06

Onboarding progress tracking, channel & AI configuration,
and analytics for tenant onboarding flows.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002_add_onboarding_tables"
down_revision: str = "001_foundation_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create onboarding tables."""

    # ============================================================
    # 1. ONBOARDING_PROGRESS
    # ============================================================
    op.create_table(
        'onboarding_progress',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('step', sa.Text(), nullable=False),  # e.g., 'welcome', 'choose_channels', 'configure_ai'
        sa.Column('status', sa.Text(), nullable=False, server_default='pending',
                  sa.CheckConstraint("status IN ('pending', 'in_progress', 'completed', 'skipped')")),
        sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),  # Step-specific data
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'user_id', 'step')
    )
    op.create_index('idx_onboarding_tenant', 'onboarding_progress', ['tenant_id'])
    op.create_index('idx_onboarding_status', 'onboarding_progress', ['tenant_id', 'status'])

    op.execute("ALTER TABLE onboarding_progress ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY onboarding_tenant_isolation ON onboarding_progress
        USING (tenant_id = current_tenant_id() OR is_admin_connection())
    """)

    # ============================================================
    # 2. CHANNEL_CONFIGURATIONS
    # ============================================================
    op.create_table(
        'channel_configurations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('channel_type', sa.Text(), nullable=False,
                  sa.CheckConstraint("channel_type IN ('whatsapp', 'email', 'voice', 'instagram', 'facebook', 'webchat', 'sms', 'telegram')")),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        # SECURITY: credentials_encrypted column name implies encryption, but this is not enforced at DB level.
        # Application MUST implement mandatory encryption at the application layer before write and decryption after read.
        # This field contains sensitive API tokens and secrets - treat all values as potentially sensitive.
        sa.Column('credentials_encrypted', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('status', sa.Text(), nullable=False, server_default='pending',
                  sa.CheckConstraint("status IN ('pending', 'connected', 'error', 'expired')")),
        sa.Column('error_message', sa.Text()),
        sa.Column('sync_enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('last_synced_at', sa.DateTime(timezone=True)),
        sa.Column('sync_interval_minutes', sa.Integer(), server_default='5'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'channel_type')
    )
    op.create_index('idx_channel_configs_tenant', 'channel_configurations', ['tenant_id'])
    op.create_index('idx_channel_configs_status', 'channel_configurations', ['tenant_id', 'status'])

    op.execute("ALTER TABLE channel_configurations ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY channel_configs_tenant_isolation ON channel_configurations
        USING (tenant_id = current_tenant_id() OR is_admin_connection())
    """)

    # ============================================================
    # 3. AI_CONFIGURATIONS
    # ============================================================
    op.create_table(
        'ai_configurations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('model', sa.Text(), nullable=False, server_default='claude-3-5-sonnet-20241022'),
        sa.Column('tone', sa.Text(), nullable=False, server_default='friendly',
                  sa.CheckConstraint("tone IN ('friendly', 'professional', 'casual', 'formal', 'supportive')")),
        sa.Column('language', sa.Text(), nullable=False, server_default='en'),
        sa.Column('custom_instructions', sa.Text()),
        sa.Column('system_prompt_override', sa.Text()),
        sa.Column('max_context_messages', sa.Integer(), server_default='10'),
        sa.Column('temperature', sa.Float(), server_default='0.7',
                  sa.CheckConstraint("temperature >= 0 AND temperature <= 1")),
        sa.Column('max_tokens', sa.Integer(), server_default='2048'),
        sa.Column('knowledge_base_enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('fallback_to_human', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_ai_configs_tenant', 'ai_configurations', ['tenant_id'])

    op.execute("ALTER TABLE ai_configurations ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY ai_configs_tenant_isolation ON ai_configurations
        USING (tenant_id = current_tenant_id() OR is_admin_connection())
    """)

    # ============================================================
    # 4. ONBOARDING_ANALYTICS
    # ============================================================
    op.create_table(
        'onboarding_analytics',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('total_users_onboarded', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('completion_rate', sa.Float(), server_default='0',
                  sa.CheckConstraint("completion_rate >= 0 AND completion_rate <= 1")),
        sa.Column('total_time_minutes', sa.Integer(), server_default='0'),
        sa.Column('average_time_per_step_minutes', sa.Integer(), server_default='0'),
        sa.Column('step_timings', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('most_skipped_step', sa.Text()),
        sa.Column('channels_configured_count', sa.Integer(), server_default='0'),
        sa.Column('ai_customizations_count', sa.Integer(), server_default='0'),
        sa.Column('first_conversation_date', sa.DateTime(timezone=True)),
        sa.Column('first_conversion_date', sa.DateTime(timezone=True)),
        sa.Column('churn_at', sa.DateTime(timezone=True)),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id')
    )
    op.create_index('idx_onboarding_analytics_tenant', 'onboarding_analytics', ['tenant_id'])

    op.execute("ALTER TABLE onboarding_analytics ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY onboarding_analytics_tenant_isolation ON onboarding_analytics
        USING (tenant_id = current_tenant_id() OR is_admin_connection())
    """)

    # ============================================================
    # Update Trigger for new tables with updated_at
    # ============================================================
    # SECURITY: F-string table names are safe here - these are developer-controlled hardcoded values
    # from the list literal, NOT user input. This is acceptable for DDL.
    for table in ['onboarding_progress', 'channel_configurations', 'ai_configurations', 'onboarding_analytics']:
        op.execute(f"""
            DROP TRIGGER IF EXISTS set_updated_at_{table} ON {table};
            CREATE TRIGGER set_updated_at_{table} BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION update_updated_at()
        """)


def downgrade() -> None:
    """Drop onboarding tables."""

    tables = [
        'onboarding_analytics',
        'ai_configurations',
        'channel_configurations',
        'onboarding_progress'
    ]

    for table in tables:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
