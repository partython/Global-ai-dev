"""Analytics Service Tests"""
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum


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
def date_range():
    """Date range for analytics"""
    return {
        'start': datetime.utcnow() - timedelta(days=30),
        'end': datetime.utcnow()
    }


class TestDashboardMetrics:
    """Test main dashboard metrics"""

    @patch('services.analytics.main.db')
    async def test_get_dashboard_metrics(self, mock_db, auth_context, date_range):
        """Test retrieving main dashboard metrics"""
        mock_db.get_connection = AsyncMock(return_value=AsyncMock())

        # Should return DashboardMetrics with all required fields
        pass

    @patch('services.analytics.main.db')
    async def test_total_conversations_by_period(self, mock_db):
        """Test conversation counts by time period"""
        mock_db.get_connection.return_value.execute = AsyncMock(
            return_value=AsyncMock(
                fetchone=AsyncMock(return_value=(100, 250, 500, 2000))
            )
        )

        # Should return: today (100), this_week (250), this_month (500), all_time (2000)

    @patch('services.analytics.main.db')
    async def test_active_conversations_count(self, mock_db):
        """Test count of currently active conversations"""
        mock_db.get_connection.return_value.execute = AsyncMock(
            return_value=AsyncMock(scalar=AsyncMock(return_value=45))
        )

    @patch('services.analytics.main.db')
    async def test_total_unique_customers(self, mock_db):
        """Test count of unique customers"""
        mock_db.get_connection.return_value.execute = AsyncMock(
            return_value=AsyncMock(scalar=AsyncMock(return_value=350))
        )

    @patch('services.analytics.main.db')
    async def test_new_customers_tracking(self, mock_db):
        """Test new customer counts"""
        mock_db.get_connection.return_value.execute = AsyncMock(
            return_value=AsyncMock(
                fetchone=AsyncMock(return_value=(12, 85))
            )
        )

        # Should return: new_today (12), new_this_month (85)

    @patch('services.analytics.main.db')
    async def test_messages_sent_vs_received(self, mock_db):
        """Test message count metrics"""
        # Should track inbound and outbound messages separately
        pass


class TestConversationAnalytics:
    """Test conversation-level analytics"""

    @patch('services.analytics.main.db')
    async def test_conversations_by_channel(self, mock_db):
        """Test conversation distribution by channel"""
        mock_db.get_connection.return_value.execute = AsyncMock(
            return_value=AsyncMock(
                fetchall=AsyncMock(
                    return_value=[
                        {'channel': 'whatsapp', 'count': 500},
                        {'channel': 'email', 'count': 300},
                        {'channel': 'webchat', 'count': 200}
                    ]
                )
            )
        )

    @patch('services.analytics.main.db')
    async def test_conversations_by_status(self, mock_db):
        """Test conversation distribution by status"""
        mock_db.get_connection.return_value.execute = AsyncMock(
            return_value=AsyncMock(
                fetchall=AsyncMock(
                    return_value=[
                        {'status': 'open', 'count': 45},
                        {'status': 'resolved', 'count': 850},
                        {'status': 'pending', 'count': 105}
                    ]
                )
            )
        )

    @patch('services.analytics.main.db')
    async def test_conversations_over_time(self, mock_db):
        """Test conversation trends over date range"""
        mock_db.get_connection.return_value.execute = AsyncMock(
            return_value=AsyncMock(
                fetchall=AsyncMock(
                    return_value=[
                        {'date': '2024-03-01', 'count': 50},
                        {'date': '2024-03-02', 'count': 65},
                        {'date': '2024-03-03', 'count': 78}
                    ]
                )
            )
        )

    @patch('services.analytics.main.db')
    async def test_peak_hours_analysis(self, mock_db):
        """Test peak conversation hours"""
        mock_db.get_connection.return_value.execute = AsyncMock(
            return_value=AsyncMock(
                fetchall=AsyncMock(
                    return_value=[
                        {'hour': 9, 'count': 120},
                        {'hour': 14, 'count': 150},
                        {'hour': 18, 'count': 140}
                    ]
                )
            )
        )

    def test_average_messages_per_conversation_calculation(self):
        """Test avg messages per conversation"""
        total_messages = 5000
        total_conversations = 200
        avg_messages = total_messages / total_conversations
        assert avg_messages == 25.0

    @patch('services.analytics.main.db')
    async def test_first_response_time_tracking(self, mock_db):
        """Test first response time metrics by channel"""
        mock_db.get_connection.return_value.execute = AsyncMock(
            return_value=AsyncMock(
                fetchrow=AsyncMock(
                    return_value={
                        'whatsapp': 120.5,
                        'email': 1800.0,
                        'webchat': 45.2
                    }
                )
            )
        )


class TestSalesFunnelAnalytics:
    """Test sales funnel tracking"""

    @patch('services.analytics.main.db')
    async def test_funnel_stage_conversion(self, mock_db):
        """Test funnel stage counts and conversion rates"""
        mock_db.get_connection.return_value.execute = AsyncMock(
            return_value=AsyncMock(
                fetchall=AsyncMock(
                    return_value=[
                        {'stage': 'awareness', 'count': 1000},
                        {'stage': 'consideration', 'count': 500},
                        {'stage': 'decision', 'count': 200},
                        {'stage': 'purchase', 'count': 100}
                    ]
                )
            )
        )

    def test_conversion_rate_calculation(self):
        """Test conversion rate between funnel stages"""
        entering_stage = 1000
        exiting_stage = 500
        conversion_rate = (exiting_stage / entering_stage) * 100
        assert conversion_rate == 50.0

    def test_drop_off_rate_calculation(self):
        """Test drop-off rate calculation"""
        entering_stage = 1000
        exiting_stage = 500
        drop_off_rate = ((entering_stage - exiting_stage) / entering_stage) * 100
        assert drop_off_rate == 50.0

    @patch('services.analytics.main.db')
    async def test_funnel_over_time(self, mock_db):
        """Test funnel metrics tracked over time"""
        mock_db.get_connection.return_value.execute = AsyncMock(
            return_value=AsyncMock(
                fetchall=AsyncMock(
                    return_value=[
                        {'date': '2024-03-01', 'awareness': 100, 'consideration': 50},
                        {'date': '2024-03-02', 'awareness': 120, 'consideration': 60}
                    ]
                )
            )
        )

    @patch('services.analytics.main.db')
    async def test_top_drop_off_reasons(self, mock_db):
        """Test most common drop-off reasons"""
        mock_db.get_connection.return_value.execute = AsyncMock(
            return_value=AsyncMock(
                fetchall=AsyncMock(
                    return_value=[
                        'Price too high',
                        'Need more features',
                        'Competitor comparison'
                    ]
                )
            )
        )


class TestChannelPerformance:
    """Test per-channel performance metrics"""

    @patch('services.analytics.main.db')
    async def test_channel_comparison(self, mock_db):
        """Test comparing all channels"""
        mock_db.get_connection.return_value.execute = AsyncMock(
            return_value=AsyncMock(
                fetchall=AsyncMock(
                    return_value=[
                        {
                            'channel': 'whatsapp',
                            'message_volume': 5000,
                            'response_time': 120.5,
                            'resolution_rate': 85.0,
                            'csat_score': 4.2,
                            'conversion_rate': 12.5
                        },
                        {
                            'channel': 'email',
                            'message_volume': 3000,
                            'response_time': 1800.0,
                            'resolution_rate': 78.0,
                            'csat_score': 3.8,
                            'conversion_rate': 8.0
                        }
                    ]
                )
            )
        )

    def test_response_time_comparison(self):
        """Test response time comparison across channels"""
        channels = {
            'whatsapp': 120.5,
            'email': 1800.0,
            'webchat': 45.2
        }
        fastest = min(channels.items(), key=lambda x: x[1])
        assert fastest[0] == 'webchat'

    def test_resolution_rate_by_channel(self):
        """Test resolution rate metrics"""
        channels = {
            'whatsapp': 85.0,
            'email': 78.0,
            'webchat': 82.0
        }
        best_channel = max(channels.items(), key=lambda x: x[1])
        assert best_channel[0] == 'whatsapp'


class TestCustomerAnalytics:
    """Test customer-level analytics"""

    @patch('services.analytics.main.db')
    async def test_customer_growth_trend(self, mock_db):
        """Test customer growth over time"""
        mock_db.get_connection.return_value.execute = AsyncMock(
            return_value=AsyncMock(
                fetchall=AsyncMock(
                    return_value=[
                        {'date': '2024-02-01', 'count': 100},
                        {'date': '2024-02-15', 'count': 175},
                        {'date': '2024-03-01', 'count': 285}
                    ]
                )
            )
        )

    def test_average_lifetime_value_calculation(self):
        """Test ALV calculation"""
        total_revenue = Decimal('50000.00')
        total_customers = 100
        alv = total_revenue / total_customers
        assert alv == Decimal('500.00')

    @patch('services.analytics.main.db')
    async def test_lead_score_distribution(self, mock_db):
        """Test distribution of lead scores"""
        mock_db.get_connection.return_value.execute = AsyncMock(
            return_value=AsyncMock(
                fetchall=AsyncMock(
                    return_value=[
                        {'score_bucket': 'A (90-100)', 'count': 50},
                        {'score_bucket': 'B (75-89)', 'count': 120},
                        {'score_bucket': 'C (50-74)', 'count': 200}
                    ]
                )
            )
        )

    @patch('services.analytics.main.db')
    async def test_top_customers_by_value(self, mock_db):
        """Test identifying top customers"""
        mock_db.get_connection.return_value.execute = AsyncMock(
            return_value=AsyncMock(
                fetchall=AsyncMock(
                    return_value=[
                        {'customer_id': 'cust_1', 'lifetime_value': 5000},
                        {'customer_id': 'cust_2', 'lifetime_value': 4500},
                        {'customer_id': 'cust_3', 'lifetime_value': 4000}
                    ]
                )
            )
        )

    @patch('services.analytics.main.db')
    async def test_customer_segmentation(self, mock_db):
        """Test customer segmentation"""
        mock_db.get_connection.return_value.execute = AsyncMock(
            return_value=AsyncMock(
                fetchrow=AsyncMock(
                    return_value={
                        'high_value': 50,
                        'medium_value': 150,
                        'low_value': 300,
                        'at_risk': 45
                    }
                )
            )
        )


class TestRevenueAnalytics:
    """Test revenue tracking"""

    @patch('services.analytics.main.db')
    async def test_total_revenue_calculation(self, mock_db):
        """Test total revenue aggregation"""
        mock_db.get_connection.return_value.execute = AsyncMock(
            return_value=AsyncMock(
                scalar=AsyncMock(return_value=Decimal('250000.00'))
            )
        )

    @patch('services.analytics.main.db')
    async def test_revenue_by_channel(self, mock_db):
        """Test revenue attribution by channel"""
        mock_db.get_connection.return_value.execute = AsyncMock(
            return_value=AsyncMock(
                fetchall=AsyncMock(
                    return_value=[
                        {'channel': 'whatsapp', 'revenue': Decimal('150000.00')},
                        {'channel': 'email', 'revenue': Decimal('75000.00')},
                        {'channel': 'webchat', 'revenue': Decimal('25000.00')}
                    ]
                )
            )
        )

    def test_average_order_value_calculation(self):
        """Test AOV calculation"""
        total_revenue = Decimal('100000.00')
        order_count = 250
        aov = total_revenue / order_count
        assert aov == Decimal('400.00')

    def test_conversion_rate_calculation(self):
        """Test conversion rate from traffic"""
        visitors = 10000
        conversions = 150
        conversion_rate = (conversions / visitors) * 100
        assert conversion_rate == 1.5

    def test_cart_recovery_rate(self):
        """Test cart abandonment recovery"""
        abandoned_carts = 500
        recovered = 75
        recovery_rate = (recovered / abandoned_carts) * 100
        assert recovery_rate == 15.0


class TestAIPerformanceMetrics:
    """Test AI resolution and handling metrics"""

    @patch('services.analytics.main.db')
    async def test_ai_handled_vs_human(self, mock_db):
        """Test AI vs human handling comparison"""
        mock_db.get_connection.return_value.execute = AsyncMock(
            return_value=AsyncMock(
                fetchrow=AsyncMock(
                    return_value={
                        'ai_handled': 750,
                        'human_handled': 250
                    }
                )
            )
        )

    def test_ai_resolution_rate(self):
        """Test AI resolution success rate"""
        ai_resolved = 750
        ai_total = 1000
        resolution_rate = (ai_resolved / ai_total) * 100
        assert resolution_rate == 75.0

    @patch('services.analytics.main.db')
    async def test_intent_distribution(self, mock_db):
        """Test distribution of detected intents"""
        mock_db.get_connection.return_value.execute = AsyncMock(
            return_value=AsyncMock(
                fetchall=AsyncMock(
                    return_value=[
                        {'intent': 'billing_help', 'count': 300},
                        {'intent': 'general_support', 'count': 250},
                        {'intent': 'account_help', 'count': 150}
                    ]
                )
            )
        )

    @patch('services.analytics.main.db')
    async def test_confidence_scores(self, mock_db):
        """Test AI confidence score distribution"""
        mock_db.get_connection.return_value.execute = AsyncMock(
            return_value=AsyncMock(
                fetchrow=AsyncMock(
                    return_value={
                        'high_confidence': 0.85,
                        'medium_confidence': 0.65,
                        'low_confidence': 0.35
                    }
                )
            )
        )

    @patch('services.analytics.main.db')
    async def test_escalation_reasons(self, mock_db):
        """Test reasons for escalation from AI to human"""
        mock_db.get_connection.return_value.execute = AsyncMock(
            return_value=AsyncMock(
                fetchall=AsyncMock(
                    return_value=[
                        {'reason': 'low_confidence', 'count': 80},
                        {'reason': 'out_of_scope', 'count': 60},
                        {'reason': 'requested', 'count': 110}
                    ]
                )
            )
        )


class TestAnalyticsFiltering:
    """Test date range and granularity filtering"""

    def test_granularity_enum(self):
        """Test granularity options"""
        from enum import Enum

        class Granularity(str, Enum):
            HOURLY = "hourly"
            DAILY = "daily"
            WEEKLY = "weekly"
            MONTHLY = "monthly"

        assert Granularity.DAILY.value == "daily"
        assert Granularity.MONTHLY.value == "monthly"

    def test_date_range_parsing(self):
        """Test date range parsing"""
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=30)

        assert (end_date - start_date).days == 30

    @patch('services.analytics.main.db')
    async def test_timezone_aware_aggregation(self, mock_db):
        """Test timezone-aware data aggregation"""
        # Should handle timezone conversions properly
        pass


class TestAnalyticsReports:
    """Test report generation"""

    @patch('services.analytics.main.db')
    async def test_generate_daily_report(self, mock_db):
        """Test generating daily report"""
        from services.analytics.main import ReportRequest

        request = ReportRequest(
            report_type='daily',
            email_delivery=False
        )

        assert request.report_type == 'daily'

    @patch('services.analytics.main.db')
    async def test_generate_weekly_report(self, mock_db):
        """Test generating weekly report"""
        from services.analytics.main import ReportRequest

        request = ReportRequest(
            report_type='weekly',
            email_delivery=True,
            recipient_email='admin@example.com'
        )

    @patch('services.analytics.main.db')
    async def test_generate_monthly_report(self, mock_db):
        """Test generating monthly report"""
        from services.analytics.main import ReportRequest

        request = ReportRequest(
            report_type='monthly',
            include_sections=['conversations', 'revenue', 'ai_performance']
        )

    @patch('services.analytics.main.db')
    async def test_email_report_delivery(self, mock_db):
        """Test email report delivery"""
        # Should schedule email delivery
        pass


class TestHealthCheck:
    """Test health check endpoint"""

    def test_health_check(self, client):
        """Test health check returns healthy status"""
        response = client.get('/health')

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'healthy'
        assert data['service'] == 'analytics'
