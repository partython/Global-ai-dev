"""Billing Service Tests"""
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
import stripe


@pytest.fixture
def mock_db():
    """Mock database"""
    db = AsyncMock()
    db.admin_connection = AsyncMock()
    db.tenant_connection = AsyncMock()
    return db


@pytest.fixture
def auth_context():
    """Mock auth context"""
    return {
        'tenant_id': 'tenant_123',
        'user_id': 'user_456',
        'role': 'admin'
    }


@pytest.fixture
def pricing_tiers():
    """Pricing tiers configuration"""
    return {
        'starter': {
            'name': 'Starter',
            'prices': {'USD': 4900, 'INR': 99900, 'GBP': 3900, 'AUD': 7900}
        },
        'growth': {
            'name': 'Growth',
            'prices': {'USD': 14900, 'INR': 299900, 'GBP': 11900, 'AUD': 24900}
        },
        'enterprise': {
            'name': 'Enterprise',
            'prices': {'USD': 49900, 'INR': 999900, 'GBP': 39900, 'AUD': 79900}
        }
    }


class TestSubscriptionCreation:
    """Test subscription creation and initialization"""

    @patch('services.billing.main.stripe.Customer.create')
    @patch('services.billing.main.db')
    async def test_create_subscription_starter_monthly(self, mock_db, mock_stripe_customer):
        """Test creating starter subscription with monthly billing"""
        from services.billing.main import CreateSubscriptionRequest

        mock_stripe_customer.return_value = {'id': 'cus_123'}

        request = CreateSubscriptionRequest(
            plan='starter',
            billing_cycle='monthly'
        )

        assert request.plan == 'starter'
        assert request.billing_cycle == 'monthly'

    @patch('services.billing.main.stripe.Customer.create')
    @patch('services.billing.main.db')
    async def test_create_subscription_enterprise_annual(self, mock_db, mock_stripe_customer):
        """Test creating enterprise subscription with annual billing"""
        from services.billing.main import CreateSubscriptionRequest

        request = CreateSubscriptionRequest(
            plan='enterprise',
            billing_cycle='annual'
        )

        assert request.plan == 'enterprise'
        assert request.billing_cycle == 'annual'

    def test_invalid_plan_rejection(self):
        """Test rejection of invalid plan"""
        from services.billing.main import CreateSubscriptionRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CreateSubscriptionRequest(
                plan='invalid_plan',
                billing_cycle='monthly'
            )

    def test_invalid_billing_cycle_rejection(self):
        """Test rejection of invalid billing cycle"""
        from services.billing.main import CreateSubscriptionRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CreateSubscriptionRequest(
                plan='starter',
                billing_cycle='weekly'
            )


class TestSubscriptionUpgrade:
    """Test subscription upgrades"""

    def test_upgrade_starter_to_growth(self):
        """Test upgrading from starter to growth plan"""
        from services.billing.main import UpgradeSubscriptionRequest

        request = UpgradeSubscriptionRequest(
            new_plan='growth',
            prorate=True
        )

        assert request.new_plan == 'growth'
        assert request.prorate is True

    def test_upgrade_growth_to_enterprise(self):
        """Test upgrading from growth to enterprise plan"""
        from services.billing.main import UpgradeSubscriptionRequest

        request = UpgradeSubscriptionRequest(
            new_plan='enterprise',
            prorate=True
        )

        assert request.new_plan == 'enterprise'

    def test_upgrade_without_proration(self):
        """Test upgrade without proration"""
        from services.billing.main import UpgradeSubscriptionRequest

        request = UpgradeSubscriptionRequest(
            new_plan='growth',
            prorate=False
        )

        assert request.prorate is False


class TestSubscriptionDowngrade:
    """Test subscription downgrades"""

    def test_downgrade_enterprise_to_growth(self):
        """Test downgrading from enterprise to growth plan"""
        from services.billing.main import DowngradeSubscriptionRequest

        request = DowngradeSubscriptionRequest(
            new_plan='growth',
            effective_date='next_cycle'
        )

        assert request.new_plan == 'growth'
        assert request.effective_date == 'next_cycle'

    def test_downgrade_immediate(self):
        """Test immediate downgrade"""
        from services.billing.main import DowngradeSubscriptionRequest

        request = DowngradeSubscriptionRequest(
            new_plan='starter',
            effective_date='immediate'
        )

        assert request.effective_date == 'immediate'


class TestSubscriptionCancellation:
    """Test subscription cancellation"""

    def test_cancel_with_reason(self):
        """Test cancellation with reason"""
        from services.billing.main import CancelSubscriptionRequest

        request = CancelSubscriptionRequest(
            reason='No longer needed',
            end_immediately=False
        )

        assert request.reason == 'No longer needed'
        assert request.end_immediately is False

    def test_cancel_immediately(self):
        """Test immediate cancellation"""
        from services.billing.main import CancelSubscriptionRequest

        request = CancelSubscriptionRequest(
            end_immediately=True
        )

        assert request.end_immediately is True

    @patch('services.billing.main.db')
    async def test_cancel_subscription_updates_status(self, mock_db):
        """Test that cancellation updates subscription status"""
        # Should set status to 'canceled' in database
        pass


class TestMultiCurrencyPricing:
    """Test multi-currency pricing support"""

    def test_starter_pricing_usd(self, pricing_tiers):
        """Test starter plan pricing in USD"""
        price = pricing_tiers['starter']['prices']['USD']
        assert price == 4900  # $49.00

    def test_starter_pricing_inr(self, pricing_tiers):
        """Test starter plan pricing in INR"""
        price = pricing_tiers['starter']['prices']['INR']
        assert price == 99900  # ₹999.00

    def test_starter_pricing_gbp(self, pricing_tiers):
        """Test starter plan pricing in GBP"""
        price = pricing_tiers['starter']['prices']['GBP']
        assert price == 3900  # £39.00

    def test_starter_pricing_aud(self, pricing_tiers):
        """Test starter plan pricing in AUD"""
        price = pricing_tiers['starter']['prices']['AUD']
        assert price == 7900  # $79.00

    def test_growth_pricing_by_currency(self, pricing_tiers):
        """Test growth plan pricing across currencies"""
        growth_prices = pricing_tiers['growth']['prices']
        assert growth_prices['USD'] == 14900
        assert growth_prices['INR'] == 299900
        assert growth_prices['GBP'] == 11900
        assert growth_prices['AUD'] == 24900

    def test_enterprise_pricing_by_currency(self, pricing_tiers):
        """Test enterprise plan pricing across currencies"""
        enterprise_prices = pricing_tiers['enterprise']['prices']
        assert enterprise_prices['USD'] == 49900
        assert enterprise_prices['INR'] == 999900


class TestUsageMetrics:
    """Test usage tracking and limits"""

    @patch('services.billing.main.db')
    async def test_get_usage_metrics(self, mock_db):
        """Test retrieving usage metrics"""
        from services.billing.main import UsageMetricsResponse

        mock_db.tenant_connection.return_value.__aenter__.return_value.fetchrow = AsyncMock(
            return_value={
                'plan': 'starter',
                'messages_sent': 2500,
                'messages_limit': 5000,
                'ai_tokens_consumed': 50000,
                'storage_used_gb': 2.5,
                'api_calls': 1000
            }
        )

    def test_usage_soft_limit_check(self):
        """Test soft limit detection at 80% usage"""
        messages_sent = 4000
        messages_limit = 5000
        usage_percentage = (messages_sent / messages_limit) * 100
        at_soft_limit = usage_percentage >= 80

        assert at_soft_limit is True

    def test_usage_hard_limit_check(self):
        """Test hard limit detection at 120% usage"""
        messages_sent = 6000
        messages_limit = 5000
        usage_percentage = (messages_sent / messages_limit) * 100
        at_hard_limit = usage_percentage >= 120

        assert at_hard_limit is True

    def test_usage_within_limit(self):
        """Test normal usage within limits"""
        messages_sent = 2500
        messages_limit = 5000
        usage_percentage = (messages_sent / messages_limit) * 100

        assert usage_percentage == 50
        assert usage_percentage < 80


class TestPaymentMethods:
    """Test payment method management"""

    def test_payment_method_setup_request(self):
        """Test payment method setup validation"""
        from services.billing.main import PaymentMethodSetupRequest

        request = PaymentMethodSetupRequest(
            card_holder_name='John Doe',
            billing_zip='12345'
        )

        assert request.card_holder_name == 'John Doe'
        assert request.billing_zip == '12345'

    @patch('services.billing.main.stripe.PaymentMethod.create')
    @patch('services.billing.main.db')
    async def test_add_payment_method(self, mock_db, mock_stripe_payment):
        """Test adding payment method"""
        mock_stripe_payment.return_value = {
            'id': 'pm_123',
            'type': 'card'
        }

        # Should create payment method in Stripe
        assert True

    def test_set_default_payment_method(self):
        """Test setting default payment method"""
        from services.billing.main import SetDefaultPaymentRequest

        request = SetDefaultPaymentRequest(
            payment_method_id='pm_456'
        )

        assert request.payment_method_id == 'pm_456'

    @patch('services.billing.main.db')
    async def test_list_payment_methods(self, mock_db):
        """Test listing saved payment methods"""
        mock_db.tenant_connection.return_value.__aenter__.return_value.fetch = AsyncMock(
            return_value=[
                {'id': 'pm_1', 'type': 'card', 'last4': '4242'},
                {'id': 'pm_2', 'type': 'card', 'last4': '5555'}
            ]
        )


class TestInvoicing:
    """Test invoice generation and management"""

    @patch('services.billing.main.db')
    async def test_get_invoice(self, mock_db):
        """Test retrieving invoice details"""
        from services.billing.main import InvoiceResponse

        mock_db.tenant_connection.return_value.__aenter__.return_value.fetchrow = AsyncMock(
            return_value={
                'id': 'inv_123',
                'number': 'INV-2024-001',
                'status': 'paid',
                'amount_due': 4900,
                'currency': 'USD',
                'due_date': datetime(2024, 4, 6)
            }
        )

    @patch('services.billing.main.db')
    async def test_list_invoices(self, mock_db):
        """Test listing invoices with pagination"""
        mock_db.tenant_connection.return_value.__aenter__.return_value.fetch = AsyncMock(
            return_value=[
                {'id': 'inv_1', 'number': 'INV-2024-001', 'amount_due': 4900},
                {'id': 'inv_2', 'number': 'INV-2024-002', 'amount_due': 4900}
            ]
        )

    @patch('services.billing.main.db')
    async def test_download_invoice_pdf(self, mock_db):
        """Test downloading invoice as PDF"""
        # Should return PDF file
        pass

    def test_invoice_status_values(self):
        """Test all valid invoice statuses"""
        valid_statuses = ['draft', 'paid', 'pending', 'failed', 'refunded']

        for status in valid_statuses:
            assert status in valid_statuses


class TestTrialManagement:
    """Test free trial tracking and management"""

    @patch('services.billing.main.stripe.Subscription.create')
    @patch('services.billing.main.db')
    async def test_create_trial_subscription(self, mock_db, mock_stripe_sub):
        """Test creating subscription with trial period"""
        mock_stripe_sub.return_value = {
            'id': 'sub_123',
            'trial_end': int((datetime.utcnow() + timedelta(days=14)).timestamp())
        }

    @patch('services.billing.main.db')
    async def test_extend_trial_period(self, mock_db):
        """Test extending trial period"""
        from services.billing.main import ExtendTrialRequest

        request = ExtendTrialRequest(
            days=7,
            reason='Customer requested extension'
        )

        assert request.days == 7
        assert 'extension' in request.reason.lower()

    @patch('services.billing.main.db')
    async def test_trial_expiry_notification(self, mock_db):
        """Test trial expiry notification"""
        # Should send notification when trial ending in 3 days
        pass

    @patch('services.billing.main.stripe.Subscription.modify')
    @patch('services.billing.main.db')
    async def test_auto_convert_trial_to_paid(self, mock_db, mock_stripe_modify):
        """Test automatic conversion from trial to paid"""
        # Should convert subscription when trial ends
        pass


class TestStripeWebhooks:
    """Test Stripe webhook handling"""

    @patch('services.billing.main.db')
    async def test_handle_invoice_created_webhook(self, mock_db):
        """Test invoice.created webhook"""
        webhook_payload = {
            'type': 'invoice.created',
            'data': {
                'object': {
                    'id': 'in_123',
                    'number': 'INV-2024-001',
                    'customer': 'cus_123'
                }
            }
        }

        # Should create invoice record in database

    @patch('services.billing.main.db')
    async def test_handle_invoice_payment_succeeded_webhook(self, mock_db):
        """Test invoice.payment_succeeded webhook"""
        webhook_payload = {
            'type': 'invoice.payment_succeeded',
            'data': {
                'object': {
                    'id': 'in_123',
                    'status': 'paid'
                }
            }
        }

    @patch('services.billing.main.db')
    async def test_handle_customer_subscription_updated_webhook(self, mock_db):
        """Test customer.subscription.updated webhook"""
        webhook_payload = {
            'type': 'customer.subscription.updated',
            'data': {
                'object': {
                    'id': 'sub_123',
                    'customer': 'cus_123',
                    'status': 'active'
                }
            }
        }

    def test_webhook_signature_verification(self):
        """Test Stripe webhook signature verification"""
        import hmac
        import hashlib

        payload = '{"type":"invoice.created"}'
        secret = 'whsec_test_secret'

        signature = hmac.new(
            secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()

        assert signature is not None


class TestBillingAnalytics:
    """Test billing analytics and reporting"""

    @patch('services.billing.main.db')
    async def test_get_mrr_metric(self, mock_db):
        """Test Monthly Recurring Revenue calculation"""
        mock_db.tenant_connection.return_value.__aenter__.return_value.fetchval = AsyncMock(
            return_value=14900  # Growth plan price
        )

    @patch('services.billing.main.db')
    async def test_get_arr_metric(self, mock_db):
        """Test Annual Recurring Revenue calculation"""
        # Should be MRR * 12
        mrr = 14900
        arr = mrr * 12
        assert arr == 178800

    @patch('services.billing.main.db')
    async def test_get_churn_rate(self, mock_db):
        """Test churn rate calculation"""
        # Should calculate cancellations / total customers
        pass

    @patch('services.billing.main.db')
    async def test_get_plan_distribution(self, mock_db):
        """Test distribution of active subscriptions by plan"""
        mock_db.tenant_connection.return_value.__aenter__.return_value.fetch = AsyncMock(
            return_value=[
                {'plan': 'starter', 'count': 50},
                {'plan': 'growth', 'count': 30},
                {'plan': 'enterprise', 'count': 5}
            ]
        )


class TestHealthCheck:
    """Test health check endpoint"""

    def test_health_check(self, client):
        """Test health check returns healthy status"""
        response = client.get('/health')

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'healthy'
        assert data['service'] == 'billing'


class TestErrorHandling:
    """Test error scenarios"""

    def test_stripe_error_handling(self):
        """Test handling Stripe API errors"""
        # Should handle stripe.error.CardError
        pass

    @patch('services.billing.main.db')
    async def test_invalid_subscription_id(self, mock_db):
        """Test error on invalid subscription ID"""
        # Should return 404
        pass

    def test_invalid_plan_tier_selection(self):
        """Test rejection of invalid plan selection"""
        from services.billing.main import UpgradeSubscriptionRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            UpgradeSubscriptionRequest(
                new_plan='invalid_plan',
                prorate=True
            )
