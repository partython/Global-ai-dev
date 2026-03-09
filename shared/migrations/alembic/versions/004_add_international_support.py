"""Add International Support (Multi-Currency & Localization)

Revision ID: 004_add_international_support
Revises: 003_add_audit_and_compliance
Create Date: 2025-03-06

Add support for:
- Multi-currency transactions
- Regional tax configurations
- Localized content and messages
- Currency conversion rates
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "004_add_international_support"
down_revision: str = "003_add_audit_and_compliance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add international support tables and columns."""

    # ============================================================
    # 1. Add locale columns to tenants if not exist
    # ============================================================
    op.execute("""
        ALTER TABLE tenants
        ADD COLUMN IF NOT EXISTS locale text DEFAULT 'en-US',
        ADD COLUMN IF NOT EXISTS regional_settings jsonb DEFAULT '{}'
    """)

    # ============================================================
    # 2. CURRENCY_RATES (Exchange rates for international sales)
    # ============================================================
    op.create_table(
        'currency_rates',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column('from_currency', sa.Text(), nullable=False),  # e.g., 'USD'
        sa.Column('to_currency', sa.Text(), nullable=False),   # e.g., 'INR'
        sa.Column('rate', sa.Numeric(18, 8), nullable=False),  # Exchange rate with high precision
        sa.Column('source', sa.Text(), server_default='api'),  # Where the rate came from
        sa.Column('last_updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('from_currency', 'to_currency')
    )
    op.create_index('idx_currency_rates_pair', 'currency_rates', ['from_currency', 'to_currency'])
    op.create_index('idx_currency_rates_updated', 'currency_rates', [sa.desc('last_updated_at')])

    # ============================================================
    # 3. TAX_CONFIGURATIONS (Regional tax rules)
    # ============================================================
    op.create_table(
        'tax_configurations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('country', sa.Text(), nullable=False),  # ISO country code: 'IN', 'US', 'DE'
        sa.Column('region', sa.Text()),  # State/province: 'CA', 'TX'
        sa.Column('tax_name', sa.Text(), nullable=False),  # e.g., 'GST', 'VAT', 'Sales Tax'
        sa.Column('tax_rate', sa.Numeric(6, 4), nullable=False),  # e.g., 18.00 for 18%
        sa.Column('applies_to', postgresql.ARRAY(sa.Text()), nullable=False, server_default="ARRAY[]::text[]"),  # Product categories
        sa.Column('is_compound', sa.Boolean(), nullable=False, server_default=sa.false()),  # Can compound with other taxes
        sa.Column('effective_from', sa.DateTime(timezone=True)),
        sa.Column('effective_to', sa.DateTime(timezone=True)),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_tax_configs_tenant', 'tax_configurations', ['tenant_id', 'country', 'is_active'])
    op.create_index('idx_tax_configs_effective', 'tax_configurations', ['tenant_id'],
                    where="is_active = true AND (effective_from IS NULL OR effective_from <= now()) AND (effective_to IS NULL OR effective_to >= now())")

    op.execute("ALTER TABLE tax_configurations ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tax_configs_tenant_isolation ON tax_configurations
        USING (tenant_id = current_tenant_id() OR is_admin_connection())
    """)

    # ============================================================
    # 4. LOCALIZATION_STRINGS (Multi-language content)
    # ============================================================
    op.create_table(
        'localization_strings',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('locale', sa.Text(), nullable=False),  # e.g., 'en-US', 'hi-IN', 'es-ES'
        sa.Column('module', sa.Text(), nullable=False),  # e.g., 'greetings', 'responses', 'errors'
        sa.Column('key', sa.Text(), nullable=False),     # Unique key: 'welcome_message', 'cart_total'
        sa.Column('value', sa.Text(), nullable=False),   # Translated text
        sa.Column('context', sa.Text()),  # Optional context for translators
        sa.Column('is_approved', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('approved_by', postgresql.UUID(as_uuid=True)),
        sa.Column('approved_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['approved_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'locale', 'module', 'key')
    )
    op.create_index('idx_localization_tenant', 'localization_strings', ['tenant_id', 'locale', 'module'])
    op.create_index('idx_localization_key', 'localization_strings', ['tenant_id', 'key'])

    op.execute("ALTER TABLE localization_strings ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY localization_tenant_isolation ON localization_strings
        USING (tenant_id = current_tenant_id() OR is_admin_connection())
    """)

    # ============================================================
    # 5. COUNTRY_SETTINGS (Regional preferences and rules)
    # ============================================================
    op.create_table(
        'country_settings',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('country_code', sa.Text(), nullable=False),  # ISO 3166-1 alpha-2
        sa.Column('country_name', sa.Text(), nullable=False),
        sa.Column('default_currency', sa.Text(), nullable=False),
        sa.Column('default_timezone', sa.Text()),
        sa.Column('default_language', sa.Text()),
        sa.Column('phone_prefix', sa.Text()),
        sa.Column('date_format', sa.Text()),  # e.g., 'DD/MM/YYYY' or 'MM/DD/YYYY'
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('gdpr_applicable', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('payment_methods', postgresql.ARRAY(sa.Text()), server_default="ARRAY[]::text[]"),
        sa.Column('customs_info_required', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'country_code')
    )
    op.create_index('idx_country_settings_tenant', 'country_settings', ['tenant_id', 'is_enabled'])

    op.execute("ALTER TABLE country_settings ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY country_settings_tenant_isolation ON country_settings
        USING (tenant_id = current_tenant_id() OR is_admin_connection())
    """)

    # ============================================================
    # 6. PAYMENT_METHODS (Regional payment options)
    # ============================================================
    op.create_table(
        'payment_methods',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('customer_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('method_type', sa.Text(), nullable=False,
                  sa.CheckConstraint("method_type IN ('credit_card', 'debit_card', 'net_banking', 'wallet', 'upi', 'paypal')")),
        sa.Column('provider', sa.Text()),  # e.g., 'stripe', 'razorpay'
        # SECURITY: token field stores payment gateway tokens (vault references, not actual card data).
        # These are sensitive and MUST be encrypted at the application layer.
        # Application MUST implement transparent encryption on write and decryption on read.
        sa.Column('token', sa.Text(), nullable=False),  # Encrypted token
        sa.Column('last_four', sa.Text()),  # Last 4 digits for display
        sa.Column('is_primary', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('expires_at', sa.DateTime(timezone=True)),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_payment_methods_customer', 'payment_methods', ['tenant_id', 'customer_id', 'is_active'])

    op.execute("ALTER TABLE payment_methods ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY payment_methods_tenant_isolation ON payment_methods
        USING (tenant_id = current_tenant_id() OR is_admin_connection())
    """)

    # ============================================================
    # Update Trigger for new tables with updated_at
    # ============================================================
    # SECURITY: F-string table names are safe here - these are developer-controlled hardcoded values
    # from the list literal, NOT user input. This is acceptable for DDL.
    for table in ['tax_configurations', 'localization_strings', 'country_settings', 'payment_methods', 'currency_rates']:
        op.execute(f"""
            DROP TRIGGER IF EXISTS set_updated_at_{table} ON {table};
            CREATE TRIGGER set_updated_at_{table} BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION update_updated_at()
        """)


def downgrade() -> None:
    """Drop international support tables."""

    tables = [
        'payment_methods',
        'country_settings',
        'localization_strings',
        'tax_configurations',
        'currency_rates'
    ]

    for table in tables:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")

    # Remove added columns from tenants
    op.execute("""
        ALTER TABLE tenants
        DROP COLUMN IF EXISTS locale,
        DROP COLUMN IF EXISTS regional_settings
    """)
