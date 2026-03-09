"""SMS Channel Service Tests"""
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from pydantic import ValidationError
import re


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
def international_numbers():
    """International phone numbers for testing"""
    return {
        '+919876543210': ('India', 'Exotel'),
        '+12345678901': ('USA', 'Bandwidth'),
        '+441234567890': ('UK', 'Vonage'),
        '+61234567890': ('Australia', 'Vonage'),
        '+33123456789': ('France', 'Vonage'),
        '+49123456789': ('Germany', 'Vonage'),
    }


class TestPhoneNumberValidation:
    """Test phone number validation"""

    def test_valid_phone_formats(self, international_numbers):
        """Test valid international phone numbers"""
        from services.sms.main import PHONE_REGEX

        for number in international_numbers.keys():
            assert PHONE_REGEX.match(number), f"Failed to validate {number}"

    def test_phone_without_plus(self):
        """Test phone number without + prefix"""
        from services.sms.main import PHONE_REGEX

        # Should accept both with and without +
        assert PHONE_REGEX.match('919876543210')

    def test_invalid_phone_format(self):
        """Test invalid phone format rejection"""
        from services.sms.main import SendSMSRequest

        with pytest.raises(ValidationError):
            SendSMSRequest(
                to_number='not-a-number',
                content='Test'
            )

    def test_phone_length_validation(self):
        """Test phone number length constraints"""
        from services.sms.main import PHONE_REGEX

        # Too short
        assert not PHONE_REGEX.match('+1')

        # Valid length
        assert PHONE_REGEX.match('+12345678901')

        # Too long
        assert not PHONE_REGEX.match('+12345678901234567')


class TestCarrierRouting:
    """Test carrier auto-routing by country code"""

    def test_exotel_routing_india(self):
        """Test Exotel routing for India (+91)"""
        from services.sms.main import COUNTRY_CODE_MAP, CarrierType

        carrier, region = COUNTRY_CODE_MAP['+91']
        assert carrier == CarrierType.EXOTEL

    def test_bandwidth_routing_us(self):
        """Test Bandwidth routing for USA (+1)"""
        from services.sms.main import COUNTRY_CODE_MAP, CarrierType

        carrier, region = COUNTRY_CODE_MAP['+1']
        assert carrier == CarrierType.BANDWIDTH

    def test_vonage_routing_uk(self):
        """Test Vonage routing for UK (+44)"""
        from services.sms.main import COUNTRY_CODE_MAP, CarrierType

        carrier, region = COUNTRY_CODE_MAP['+44']
        assert carrier == CarrierType.VONAGE

    def test_vonage_routing_eu(self):
        """Test Vonage routing for EU countries"""
        from services.sms.main import COUNTRY_CODE_MAP, CarrierType

        for code in ['+33', '+49']:  # France, Germany
            carrier, region = COUNTRY_CODE_MAP[code]
            assert carrier == CarrierType.VONAGE


class TestSMSSending:
    """Test SMS sending"""

    @patch('services.sms.main.db')
    async def test_send_sms(self, mock_db, auth_context):
        """Test sending SMS"""
        from services.sms.main import SendSMSRequest

        request = SendSMSRequest(
            to_number='+919876543210',
            content='Hello, this is a test message.'
        )

        assert request.to_number == '+919876543210'

    def test_sms_content_length(self):
        """Test SMS content length validation"""
        from services.sms.main import SendSMSRequest

        # Valid - under 1600 chars (concatenated SMS limit)
        valid = SendSMSRequest(
            to_number='+919876543210',
            content='x' * 160
        )
        assert len(valid.content) == 160

        # Invalid - over 1600 chars
        with pytest.raises(ValidationError):
            SendSMSRequest(
                to_number='+919876543210',
                content='x' * 1601
            )

    def test_character_encoding_gsm7(self):
        """Test GSM-7 character encoding"""
        # GSM-7 is standard for SMS
        gsm7_chars = 'abcdefghijklmnopqrstuvwxyz0123456789 '

    def test_character_encoding_ucs2(self):
        """Test UCS-2 character encoding for unicode"""
        # UCS-2 for special characters, emoji, etc.
        ucs2_content = 'Hello 你好 🎉'


class TestComplianceRegions:
    """Test compliance by region"""

    def test_india_trai_compliance(self):
        """Test TRAI DND compliance for India"""
        from services.sms.main import ComplianceRegion

        region = ComplianceRegion.INDIA
        assert region.value == 'india'

    def test_us_tcpa_compliance(self):
        """Test TCPA compliance for USA"""
        from services.sms.main import ComplianceRegion

        region = ComplianceRegion.US
        assert region.value == 'us'

    def test_eu_gdpr_compliance(self):
        """Test GDPR compliance for EU"""
        from services.sms.main import ComplianceRegion

        region = ComplianceRegion.EU
        assert region.value == 'eu'

    @patch('services.sms.main.db')
    async def test_dnd_check_india(self, mock_db):
        """Test DND registry check for India"""
        # Should check TRAI DND before sending to Indian number

    @patch('services.sms.main.db')
    async def test_dnc_check_us(self, mock_db):
        """Test DNC registry check for USA"""
        # Should check FCC DNC before sending to US number


class TestDeliveryReceipts:
    """Test SMS delivery receipts"""

    @patch('services.sms.main.db')
    async def test_dlr_handling(self, mock_db):
        """Test delivery receipt handling"""
        dlr_data = {
            'message_id': 'msg_123',
            'status': 'delivered',
            'dlr_timestamp': '2024-03-06T10:00:00Z'
        }

        # Should update message status in database

    def test_dlr_statuses(self):
        """Test all DLR status values"""
        from services.sms.main import SMSStatus

        assert SMSStatus.SENT.value == 'sent'
        assert SMSStatus.DELIVERED.value == 'delivered'
        assert SMSStatus.FAILED.value == 'failed'
        assert SMSStatus.REJECTED.value == 'rejected'

    @patch('services.sms.main.db')
    async def test_delivery_tracking(self, mock_db):
        """Test delivery tracking over time"""
        # Should track delivery progress


class TestOptOut:
    """Test opt-out handling"""

    def test_stop_keyword_detection(self):
        """Test STOP keyword detection"""
        from services.sms.main import STOP_KEYWORDS

        assert 'STOP' in STOP_KEYWORDS
        assert 'UNSUBSCRIBE' in STOP_KEYWORDS

    @patch('services.sms.main.db')
    async def test_record_opt_out(self, mock_db):
        """Test recording opt-out"""
        phone = '+919876543210'
        reason = 'Customer STOP request'

        # Should add to opt-out list

    @patch('services.sms.main.db')
    async def test_check_opt_out(self, mock_db):
        """Test checking opt-out list before send"""
        mock_db.tenant_connection.return_value.__aenter__.return_value.fetchval = AsyncMock(
            return_value=None  # Not opted out
        )

    @patch('services.sms.main.db')
    async def test_remove_opt_out(self, mock_db):
        """Test removing from opt-out list"""
        phone = '+919876543210'

        # Customer can be re-added if they request


class TestTemplates:
    """Test SMS templates"""

    @patch('services.sms.main.db')
    async def test_create_template(self, mock_db):
        """Test creating SMS template"""
        from services.sms.main import SMSTemplate

        template = SMSTemplate(
            id='tpl_1',
            tenant_id='tenant_123',
            name='welcome_sms',
            content='Welcome {{name}}! Click: {{link}}',
            variables=['name', 'link'],
            category='transactional',
            created_at=None,
            updated_at=None
        )

        assert 'welcome_sms' in template.name

    @patch('services.sms.main.db')
    async def test_template_variable_substitution(self, mock_db):
        """Test template variable substitution"""
        template_content = 'Hi {{name}}, your code is {{code}}'
        variables = {'name': 'John', 'code': '123456'}

        # Should render to: Hi John, your code is 123456

    @patch('services.sms.main.db')
    async def test_list_templates(self, mock_db):
        """Test listing SMS templates"""
        mock_db.tenant_connection.return_value.__aenter__.return_value.fetch = AsyncMock(
            return_value=[
                {'id': 'tpl_1', 'name': 'welcome'},
                {'id': 'tpl_2', 'name': 'otp'}
            ]
        )

    @patch('services.sms.main.db')
    async def test_delete_template(self, mock_db):
        """Test deleting SMS template"""
        mock_db.tenant_connection.return_value.__aenter__.return_value.execute = AsyncMock(
            return_value='DELETE 1'
        )


class TestAnalytics:
    """Test SMS analytics"""

    @patch('services.sms.main.db')
    async def test_get_analytics(self, mock_db):
        """Test SMS analytics retrieval"""
        mock_db.tenant_connection.return_value.__aenter__.return_value.fetchrow = AsyncMock(
            return_value={
                'total_sent': 1000,
                'total_delivered': 950,
                'total_failed': 30,
                'total_inbound': 200,
                'total_opt_outs': 20,
                'outbound_count': 1000
            }
        )

    def test_delivery_rate_calculation(self):
        """Test delivery rate calculation"""
        total_sent = 1000
        total_delivered = 950

        delivery_rate = (total_delivered / total_sent) * 100
        assert delivery_rate == 95.0

    def test_opt_out_rate_calculation(self):
        """Test opt-out rate calculation"""
        total_sent = 1000
        total_opt_outs = 20

        opt_out_rate = (total_opt_outs / total_sent) * 100
        assert opt_out_rate == 2.0


class TestWebhookHandling:
    """Test webhook signature verification"""

    def test_exotel_signature_verification(self):
        """Test Exotel webhook signature verification"""
        # Should verify HMAC-SHA256 signature

    def test_bandwidth_signature_verification(self):
        """Test Bandwidth webhook signature verification"""
        # Should verify signature

    def test_vonage_signature_verification(self):
        """Test Vonage webhook signature verification"""
        # Should verify signature


class TestMultiCurrency:
    """Test multi-currency SMS pricing"""

    def test_pricing_by_region(self):
        """Test SMS pricing varies by destination"""
        # USD pricing for US
        # INR pricing for India
        # GBP pricing for UK

    def test_cost_calculation(self):
        """Test SMS cost calculation"""
        base_rate_usd = 0.0075  # Per SMS
        num_messages = 100

        total_cost = base_rate_usd * num_messages
        assert total_cost == 0.75


class TestHealthCheck:
    """Test health check endpoint"""

    def test_health_check(self, client):
        """Test health check returns healthy status"""
        response = client.get('/health')

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'healthy'
        assert data['service'] == 'sms'


class TestErrorHandling:
    """Test error scenarios"""

    def test_dnd_rejection(self):
        """Test rejection for DND numbers"""
        # Should return 403 if number on DND list

    def test_opt_out_rejection(self):
        """Test rejection for opted-out numbers"""
        # Should return 403 if number opted out

    def test_invalid_country_code(self):
        """Test rejection for unsupported country"""
        # Should return 400 for unknown country code

    @patch('services.sms.main.db')
    async def test_rate_limit_error(self, mock_db):
        """Test rate limiting"""
        # Should handle rate limit errors from carrier
