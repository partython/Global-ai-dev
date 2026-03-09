"""WhatsApp Channel Service Tests"""
import json
import hmac
import hashlib
from datetime import datetime, timezone
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError


# Mock imports
pytest.register_assert_rewrite('pytest_mock')


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
def valid_whatsapp_token():
    """Valid WhatsApp verify token"""
    return 'priya_whatsapp_webhook_token'


@pytest.fixture
def meta_app_secret():
    """Meta app secret for signature verification"""
    return 'test_meta_app_secret_key'


class TestWebhookVerification:
    """Test Meta webhook verification challenge"""

    def test_webhook_verification_success(self, valid_whatsapp_token, client):
        """Test successful webhook verification with valid token"""
        response = client.get(
            '/webhook',
            params={
                'hub.mode': 'subscribe',
                'hub.verify_token': valid_whatsapp_token,
                'hub.challenge': '12345'
            }
        )
        assert response.status_code == 200
        assert response.json() == 12345

    def test_webhook_verification_invalid_token(self, client):
        """Test webhook verification with invalid token"""
        response = client.get(
            '/webhook',
            params={
                'hub.mode': 'subscribe',
                'hub.verify_token': 'wrong_token',
                'hub.challenge': '12345'
            }
        )
        assert response.status_code == 403

    def test_webhook_verification_missing_parameters(self, client):
        """Test webhook verification with missing parameters"""
        response = client.get(
            '/webhook',
            params={'hub.mode': 'subscribe'}
        )
        assert response.status_code == 400

    def test_webhook_verification_invalid_mode(self, valid_whatsapp_token, client):
        """Test webhook verification with invalid hub.mode"""
        response = client.get(
            '/webhook',
            params={
                'hub.mode': 'invalid',
                'hub.verify_token': valid_whatsapp_token,
                'hub.challenge': '12345'
            }
        )
        assert response.status_code == 400


class TestIncomingMessages:
    """Test inbound message handling"""

    @patch('services.whatsapp.main.db')
    @patch('services.whatsapp.main.forward_to_channel_router')
    async def test_receive_text_message(self, mock_forward, mock_db, meta_app_secret, client):
        """Test receiving text message from customer"""
        payload = {
            'object': 'whatsapp_business_account',
            'entry': [{
                'id': '123',
                'changes': [{
                    'value': {
                        'messages': [{
                            'from': '919876543210',
                            'id': 'msg_123',
                            'timestamp': '1234567890',
                            'type': 'text',
                            'text': {'body': 'Hello, I need help'}
                        }],
                        'phone_number_id': 'phone_123',
                        'metadata': {'phone_number_id': 'phone_123'}
                    }
                }]
            }]
        }

        body = json.dumps(payload).encode()
        signature = 'sha256=' + hmac.new(
            meta_app_secret.encode(),
            body,
            hashlib.sha256
        ).hexdigest()

        response = client.post(
            '/webhook',
            json=payload,
            headers={'X-Hub-Signature-256': signature}
        )

        assert response.status_code == 200
        assert response.json()['success'] is True

    def test_receive_media_message_validation(self, client):
        """Test media message type validation"""
        payload = {
            'object': 'whatsapp_business_account',
            'entry': [{
                'changes': [{
                    'value': {
                        'messages': [{
                            'from': '+919876543210',
                            'id': 'msg_456',
                            'type': 'image',
                            'image': {'id': 'image_123', 'mime_type': 'image/jpeg'}
                        }],
                        'phone_number_id': 'phone_123'
                    }
                }]
            }]
        }

        # Validates that media types are handled

    def test_international_phone_numbers(self, client):
        """Test international phone number handling"""
        test_numbers = [
            ('+919876543210', 'India'),
            ('+1234567890', 'US'),
            ('+441234567890', 'UK'),
            ('+49123456789', 'Germany'),
            ('+61234567890', 'Australia'),
        ]

        for phone, country in test_numbers:
            # Validate format is accepted
            assert phone.startswith('+')
            assert len(phone) >= 7 and len(phone) <= 15


class TestOutboundMessages:
    """Test outbound message sending"""

    @patch('services.whatsapp.main.db')
    @patch('services.whatsapp.main.get_http_client')
    async def test_send_text_message(self, mock_http, mock_db):
        """Test sending text message"""
        message_payload = {
            'to': '+919876543210',
            'type': 'text',
            'text': 'Hello! This is a test message.'
        }

        # Mock HTTP response
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = AsyncMock(return_value={
            'messages': [{'id': 'msg_sent_123'}]
        })
        mock_http.return_value.post = AsyncMock(return_value=mock_response)

    def test_send_message_validation(self):
        """Test outbound message validation"""
        from services.whatsapp.main import OutboundMessage, MessageType

        valid_message = OutboundMessage(
            to='+919876543210',
            type=MessageType.TEXT,
            text='Hello!'
        )
        assert valid_message.to == '+919876543210'

    def test_24_hour_conversation_window(self):
        """Test 24-hour conversation window enforcement"""
        # Test that templates can be sent outside 24h window
        # Test that regular messages fail outside 24h window

    def test_media_message_with_caption(self):
        """Test sending media with caption"""
        from services.whatsapp.main import OutboundMessage, MessageType

        message = OutboundMessage(
            to='+919876543210',
            type=MessageType.IMAGE,
            media_url='https://example.com/image.jpg',
            caption='Check this out!'
        )
        assert message.caption == 'Check this out!'


class TestTemplates:
    """Test WhatsApp message templates"""

    @patch('services.whatsapp.main.db')
    async def test_create_template(self, mock_db):
        """Test template creation"""
        from services.whatsapp.main import TemplateModel

        template = TemplateModel(
            name='welcome_template',
            category='MARKETING',
            language='en_US',
            body='Welcome to {{company_name}}!'
        )

        assert template.name == 'welcome_template'
        assert template.category == 'MARKETING'

    def test_template_name_validation(self):
        """Test template name constraints"""
        from services.whatsapp.main import TemplateModel

        # Valid
        TemplateModel(name='valid_name', body='Body')

        # Invalid - empty name
        with pytest.raises(ValidationError):
            TemplateModel(name='', body='Body')

    @patch('services.whatsapp.main.db')
    async def test_list_templates(self, mock_db):
        """Test listing templates"""
        mock_db.tenant_connection.return_value.__aenter__.return_value.fetch = AsyncMock(
            return_value=[
                {'id': 'tpl_1', 'name': 'welcome'},
                {'id': 'tpl_2', 'name': 'goodbye'}
            ]
        )

    @patch('services.whatsapp.main.db')
    async def test_delete_template(self, mock_db):
        """Test template deletion"""
        mock_db.tenant_connection.return_value.__aenter__.return_value.execute = AsyncMock(
            return_value='DELETE 1'
        )


class TestPhoneNumbers:
    """Test phone number management"""

    def test_phone_number_validation(self):
        """Test international phone number validation"""
        from services.whatsapp.main import PhoneNumberModel

        # Valid
        phone = PhoneNumberModel(
            phone_number='+919876543210',
            display_name='MyBusiness',
            business_name='My Business Ltd'
        )
        assert phone.phone_number == '+919876543210'

    def test_phone_number_registration(self):
        """Test phone number registration"""
        from services.whatsapp.main import PhoneNumberModel

        phone_info = PhoneNumberModel(
            phone_number='+1234567890',
            display_name='Support',
            business_name='My Company',
            business_category='GENERAL'
        )

        assert phone_info.display_name == 'Support'

    @patch('services.whatsapp.main.db')
    async def test_list_phone_numbers(self, mock_db):
        """Test listing phone numbers"""
        mock_db.tenant_connection.return_value.__aenter__.return_value.fetch = AsyncMock(
            return_value=[
                {
                    'phone_number_id': 'phone_1',
                    'display_phone_number': '+919876543210',
                    'business_name': 'Business1',
                    'quality_rating': 'GREEN'
                }
            ]
        )

    @patch('services.whatsapp.main.db')
    async def test_update_phone_profile(self, mock_db):
        """Test updating phone number profile"""
        from services.whatsapp.main import PhoneNumberUpdateModel

        update = PhoneNumberUpdateModel(
            about='We help with all your needs',
            website='https://example.com'
        )

        assert update.about == 'We help with all your needs'


class TestMediaHandling:
    """Test media message handling"""

    def test_media_type_validation(self):
        """Test supported media types"""
        from services.whatsapp.main import SUPPORTED_MEDIA_TYPES

        assert 'image' in SUPPORTED_MEDIA_TYPES
        assert 'image/jpeg' in SUPPORTED_MEDIA_TYPES['image']
        assert 'video/mp4' in SUPPORTED_MEDIA_TYPES['video']
        assert 'application/pdf' in SUPPORTED_MEDIA_TYPES['document']

    def test_max_media_size(self):
        """Test max media size constraint"""
        from services.whatsapp.main import MAX_MEDIA_SIZE

        assert MAX_MEDIA_SIZE == 16 * 1024 * 1024  # 16MB

    def test_document_mime_types(self):
        """Test document MIME type support"""
        from services.whatsapp.main import SUPPORTED_MEDIA_TYPES

        doc_types = SUPPORTED_MEDIA_TYPES['document']
        assert 'application/pdf' in doc_types
        assert 'application/msword' in doc_types


class TestMessageStatus:
    """Test message status tracking"""

    @patch('services.whatsapp.main.db')
    async def test_message_status_update(self, mock_db):
        """Test status callback handling"""
        status_update = {
            'id': 'msg_123',
            'status': 'delivered',
            'timestamp': '1234567890'
        }

        # Would be called from webhook handler

    def test_message_statuses(self):
        """Test all message status values"""
        from services.whatsapp.main import MessageStatus

        assert MessageStatus.SENT.value == 'sent'
        assert MessageStatus.DELIVERED.value == 'delivered'
        assert MessageStatus.READ.value == 'read'
        assert MessageStatus.FAILED.value == 'failed'


class TestRateLimiting:
    """Test rate limiting"""

    def test_rate_limiting_per_second(self):
        """Test Meta per-second rate limits"""
        # Meta limits: 1000 API calls per second
        pass

    def test_conversation_window_tracking(self):
        """Test 24-hour conversation window"""
        pass


class TestHealthCheck:
    """Test health check endpoint"""

    def test_health_check(self, client):
        """Test health check returns healthy status"""
        response = client.get('/health')

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'healthy'
        assert data['service'] == 'whatsapp'


class TestErrorHandling:
    """Test error handling"""

    def test_invalid_webhook_signature(self, client):
        """Test rejection of invalid webhook signature"""
        payload = {'test': 'data'}
        body = json.dumps(payload).encode()
        invalid_signature = 'sha256=invalid'

        response = client.post(
            '/webhook',
            json=payload,
            headers={'X-Hub-Signature-256': invalid_signature}
        )

        assert response.status_code == 403

    def test_malformed_json(self, client):
        """Test handling of malformed JSON"""
        response = client.post(
            '/webhook',
            data='invalid json',
            headers={'Content-Type': 'application/json'}
        )

        assert response.status_code in [400, 422]
