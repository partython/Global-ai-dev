"""Add Audit and Compliance Tables

Revision ID: 003_add_audit_and_compliance
Revises: 002_add_onboarding_tables
Create Date: 2025-03-06

Compliance and regulatory tracking:
- Detailed audit logs with immutable records
- GDPR data deletion requests
- Consent management records
- Compliance reports
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "003_add_audit_and_compliance"
down_revision: str = "002_add_onboarding_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create audit and compliance tables."""

    # ============================================================
    # 1. DATA_DELETION_REQUESTS (GDPR)
    # ============================================================
    op.create_table(
        'data_deletion_requests',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True)),
        sa.Column('customer_id', postgresql.UUID(as_uuid=True)),
        sa.Column('request_type', sa.Text(), nullable=False,
                  sa.CheckConstraint("request_type IN ('user_data', 'customer_data', 'all_data')")),
        sa.Column('status', sa.Text(), nullable=False, server_default='pending',
                  sa.CheckConstraint("status IN ('pending', 'processing', 'completed', 'rejected')")),
        sa.Column('reason', sa.Text()),
        sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('retention_period_days', sa.Integer()),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_deletion_requests_tenant', 'data_deletion_requests', ['tenant_id', 'status'])
    op.create_index('idx_deletion_requests_customer', 'data_deletion_requests', ['tenant_id', 'customer_id'])
    op.create_index('idx_deletion_requests_user', 'data_deletion_requests', ['tenant_id', 'user_id'])

    op.execute("ALTER TABLE data_deletion_requests ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY deletion_requests_tenant_isolation ON data_deletion_requests
        USING (tenant_id = current_tenant_id() OR is_admin_connection())
    """)

    # ============================================================
    # 2. CONSENT_RECORDS
    # ============================================================
    op.create_table(
        'consent_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True)),
        sa.Column('customer_id', postgresql.UUID(as_uuid=True)),
        sa.Column('consent_type', sa.Text(), nullable=False,
                  sa.CheckConstraint("consent_type IN ('marketing', 'data_processing', 'cookies', 'analytics', 'sms', 'email')")),
        sa.Column('granted', sa.Boolean(), nullable=False),
        sa.Column('version', sa.Text()),  # e.g., 'v1.0', 'v1.1' for tracking policy changes
        sa.Column('ip_address', postgresql.INET()),
        sa.Column('user_agent', sa.Text()),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_consent_tenant', 'consent_records', ['tenant_id', 'consent_type'])
    op.create_index('idx_consent_customer', 'consent_records', ['tenant_id', 'customer_id', 'consent_type'])
    op.create_index('idx_consent_timestamp', 'consent_records', ['tenant_id', sa.desc('timestamp')])

    op.execute("ALTER TABLE consent_records ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY consent_tenant_isolation ON consent_records
        USING (tenant_id = current_tenant_id() OR is_admin_connection())
    """)

    # ============================================================
    # 3. COMPLIANCE_REPORTS
    # ============================================================
    op.create_table(
        'compliance_reports',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('report_type', sa.Text(), nullable=False,
                  sa.CheckConstraint("report_type IN ('gdpr', 'ccpa', 'audit', 'data_inventory', 'dpia', 'custom')")),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('status', sa.Text(), nullable=False, server_default='draft',
                  sa.CheckConstraint("status IN ('draft', 'pending_review', 'approved', 'published', 'archived')")),
        sa.Column('generated_by', postgresql.UUID(as_uuid=True)),
        sa.Column('approved_by', postgresql.UUID(as_uuid=True)),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('approved_at', sa.DateTime(timezone=True)),
        sa.Column('expires_at', sa.DateTime(timezone=True)),
        sa.Column('file_url', sa.Text()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['generated_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['approved_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_compliance_reports_tenant', 'compliance_reports', ['tenant_id', 'report_type'])
    op.create_index('idx_compliance_reports_status', 'compliance_reports', ['tenant_id', 'status'])
    op.create_index('idx_compliance_reports_generated', 'compliance_reports', ['tenant_id', sa.desc('generated_at')])

    op.execute("ALTER TABLE compliance_reports ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY compliance_reports_tenant_isolation ON compliance_reports
        USING (tenant_id = current_tenant_id() OR is_admin_connection())
    """)

    # ============================================================
    # 4. ENHANCED_AUDIT_LOG (Extended audit table for detailed tracking)
    # ============================================================
    op.create_table(
        'detailed_audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True)),
        sa.Column('action', sa.Text(), nullable=False),  # e.g., 'settings.updated', 'data.exported'
        sa.Column('resource_type', sa.Text()),  # e.g., 'customer', 'conversation', 'settings'
        sa.Column('resource_id', sa.Text()),
        sa.Column('old_value', postgresql.JSONB(astext_type=sa.Text())),  # Before change
        sa.Column('new_value', postgresql.JSONB(astext_type=sa.Text())),  # After change
        sa.Column('change_reason', sa.Text()),  # Why the change was made
        sa.Column('ip_address', postgresql.INET()),
        sa.Column('user_agent', sa.Text()),
        sa.Column('session_id', sa.Text()),
        sa.Column('success', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('error_message', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_detailed_audit_tenant', 'detailed_audit_logs', ['tenant_id', sa.desc('created_at')])
    op.create_index('idx_detailed_audit_user', 'detailed_audit_logs', ['tenant_id', 'user_id', sa.desc('created_at')])
    op.create_index('idx_detailed_audit_action', 'detailed_audit_logs', ['tenant_id', 'action', sa.desc('created_at')])
    op.create_index('idx_detailed_audit_resource', 'detailed_audit_logs', ['tenant_id', 'resource_type', 'resource_id'])

    op.execute("ALTER TABLE detailed_audit_logs ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY detailed_audit_tenant_isolation ON detailed_audit_logs
        USING (tenant_id = current_tenant_id() OR is_admin_connection())
    """)
    op.execute("""
        CREATE POLICY detailed_audit_insert_only ON detailed_audit_logs
        FOR INSERT WITH CHECK (true)
    """)

    # ============================================================
    # 5. SECURITY_EVENTS (Real-time security tracking)
    # ============================================================
    op.create_table(
        'security_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('event_type', sa.Text(), nullable=False,
                  sa.CheckConstraint("event_type IN ('failed_login', 'suspicious_activity', 'policy_violation', 'credential_exposure', 'unauthorized_access')")),
        sa.Column('severity', sa.Text(), nullable=False, server_default='medium',
                  sa.CheckConstraint("severity IN ('low', 'medium', 'high', 'critical')")),
        sa.Column('user_id', postgresql.UUID(as_uuid=True)),
        sa.Column('ip_address', postgresql.INET()),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('remediation_status', sa.Text(), server_default='pending',
                  sa.CheckConstraint("remediation_status IN ('pending', 'in_progress', 'resolved', 'escalated')")),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_security_events_tenant', 'security_events', ['tenant_id', 'severity', sa.desc('created_at')])
    op.create_index('idx_security_events_type', 'security_events', ['tenant_id', 'event_type'])
    op.create_index('idx_security_events_ip', 'security_events', ['ip_address'])

    op.execute("ALTER TABLE security_events ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY security_events_tenant_isolation ON security_events
        USING (tenant_id = current_tenant_id() OR is_admin_connection())
    """)


def downgrade() -> None:
    """Drop audit and compliance tables."""

    tables = [
        'security_events',
        'detailed_audit_logs',
        'compliance_reports',
        'consent_records',
        'data_deletion_requests'
    ]

    for table in tables:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
