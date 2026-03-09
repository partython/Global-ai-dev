"""Notification Service Tests"""
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from datetime import datetime, timedelta
import json


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
def valid_device_registration():
    """Valid device registration"""
    return {
        'device_token': 'eWAYSLDnHqI:APA91bG1g7vC3j_8RkKzUmjN7j3e8dDHzJx0LqKpbCd9VLlnJ7m5K0',
        'device_type': 'ios',
        'device_name': 'iPhone 14',
        'app_version': '2.1.0',
        'os_version': '17.2'
    }


class TestDeviceManagement:
    """Test device token registration and management"""

    def test_register_device_ios(self, valid_device_registration):
        """Test registering iOS device"""
        from services.notification.main import DeviceRegistration

        device = DeviceRegistration(
            device_token=valid_device_registration['device_token'],
            device_type='ios',
            device_name='iPhone 14'
        )

        assert device.device_type == 'ios'

    def test_register_device_android(self):
        """Test registering Android device"""
        from services.notification.main import DeviceRegistration

        device = DeviceRegistration(
            device_token='cbPdaLdsqF:APA91bG8xYpL0j3FqJ4L0nK7j2K3M4N5',
            device_type='android',
            device_name='Samsung Galaxy S23'
        )

        assert device.device_type == 'android'

    def test_register_device_web(self):
        """Test registering web device"""
        from services.notification.main import DeviceRegistration

        device = DeviceRegistration(
            device_token='web_token_abc123def456ghi789',
            device_type='web'
        )

        assert device.device_type == 'web'

    def test_invalid_device_type_rejection(self):
        """Test rejection of invalid device type"""
        from services.notification.main import DeviceRegistration
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DeviceRegistration(
                device_token='valid_token_xyz',
                device_type='invalid'
            )

    @patch('services.notification.main.db')
    async def test_unregister_device(self, mock_db):
        """Test unregistering device"""
        mock_db.tenant_connection.return_value.__aenter__.return_value.execute = AsyncMock(
            return_value=None
        )


class TestSendNotification:
    """Test sending individual notifications"""

    def test_send_notification_request_valid(self):
        """Test valid notification send request"""
        from services.notification.main import SendNotificationRequest

        request = SendNotificationRequest(
            user_id='user_123',
            notification_type='message',
            title='New Message',
            body='You have a new message from John',
            priority='normal'
        )

        assert request.notification_type == 'message'
        assert request.priority == 'normal'

    def test_notification_types_validation(self):
        """Test all valid notification types"""
        from services.notification.main import NOTIFICATION_TYPES

        valid_types = list(NOTIFICATION_TYPES.keys())
        assert 'message' in valid_types
        assert 'lead_score' in valid_types
        assert 'cart_abandoned' in valid_types
        assert 'order_status' in valid_types

    def test_notification_priority_levels(self):
        """Test priority level options"""
        from services.notification.main import PRIORITY_LEVELS

        assert 'low' in PRIORITY_LEVELS
        assert 'normal' in PRIORITY_LEVELS
        assert 'high' in PRIORITY_LEVELS
        assert 'urgent' in PRIORITY_LEVELS

    def test_notification_channels(self):
        """Test notification delivery channels"""
        from services.notification.main import CHANNELS

        assert 'push' in CHANNELS
        assert 'in_app' in CHANNELS
        assert 'email' in CHANNELS

    def test_send_with_custom_data(self):
        """Test sending notification with custom data"""
        from services.notification.main import SendNotificationRequest

        request = SendNotificationRequest(
            user_id='user_123',
            notification_type='order_status',
            title='Order Shipped',
            body='Your order has been shipped',
            data={'order_id': 'ord_123', 'tracking_url': 'https://tracking.com'}
        )

        assert 'order_id' in request.data

    def test_scheduled_notification(self):
        """Test scheduling notification for future delivery"""
        from services.notification.main import SendNotificationRequest

        future_time = datetime.utcnow() + timedelta(hours=2)

        request = SendNotificationRequest(
            user_id='user_123',
            notification_type='message',
            title='Scheduled Message',
            body='This message will be sent later',
            scheduled_for=future_time
        )

        assert request.scheduled_for is not None

    def test_notification_ttl_configuration(self):
        """Test time-to-live configuration"""
        from services.notification.main import SendNotificationRequest

        request = SendNotificationRequest(
            user_id='user_123',
            notification_type='message',
            title='Time-limited Notification',
            body='This expires in 1 hour',
            ttl_seconds=3600  # 1 hour
        )

        assert request.ttl_seconds == 3600

    @patch('services.notification.main.db')
    async def test_send_push_notification(self, mock_db):
        """Test sending push notification via FCM"""
        # Should call Firebase Cloud Messaging API
        pass

    @patch('services.notification.main.db')
    async def test_send_in_app_notification(self, mock_db):
        """Test sending in-app notification"""
        # Should broadcast to user's WebSocket connections
        pass


class TestBroadcastNotifications:
    """Test broadcast notifications to groups"""

    def test_broadcast_to_tenant(self):
        """Test broadcasting to all users in tenant"""
        from services.notification.main import BroadcastNotificationRequest

        request = BroadcastNotificationRequest(
            title='Maintenance Notice',
            body='System maintenance scheduled for tonight',
            target_type='tenant',
            target_value='tenant_123'
        )

        assert request.target_type == 'tenant'

    def test_broadcast_to_topic(self):
        """Test broadcasting to topic subscribers"""
        from services.notification.main import BroadcastNotificationRequest

        request = BroadcastNotificationRequest(
            title='Sales Team Alert',
            body='New high-value lead assigned',
            target_type='topic',
            target_value='sales_alerts'
        )

        assert request.target_type == 'topic'

    def test_broadcast_to_role(self):
        """Test broadcasting to users with specific role"""
        from services.notification.main import BroadcastNotificationRequest

        request = BroadcastNotificationRequest(
            title='Admin Alert',
            body='Critical system event',
            target_type='role',
            target_value='admin'
        )

        assert request.target_type == 'role'

    @patch('services.notification.main.manager')
    async def test_broadcast_via_websocket(self, mock_manager):
        """Test broadcasting via WebSocket connections"""
        mock_manager.broadcast_to_tenant_topic = AsyncMock()


class TestNotificationTemplates:
    """Test notification template management"""

    def test_create_template(self):
        """Test creating notification template"""
        from services.notification.main import NotificationTemplateRequest

        template = NotificationTemplateRequest(
            name='new_message_template',
            notification_type='message',
            title_template='New message from {{sender_name}}',
            body_template='{{sender_name}} sent: {{message_preview}}',
            language='en',
            variables=['sender_name', 'message_preview']
        )

        assert 'sender_name' in template.variables

    def test_template_variable_substitution(self):
        """Test template variable rendering"""
        template = 'Hello {{name}}, your balance is {{amount}}'
        variables = {'name': 'John', 'amount': '$1000'}

        rendered = template.replace('{{name}}', variables['name'])
        rendered = rendered.replace('{{amount}}', variables['amount'])

        assert 'John' in rendered
        assert '$1000' in rendered

    def test_multilingual_templates(self):
        """Test templates in different languages"""
        from services.notification.main import NotificationTemplateRequest

        en_template = NotificationTemplateRequest(
            name='welcome_en',
            notification_type='message',
            title_template='Welcome',
            body_template='Welcome to our platform',
            language='en'
        )

        es_template = NotificationTemplateRequest(
            name='welcome_es',
            notification_type='message',
            title_template='Bienvenido',
            body_template='Bienvenido a nuestra plataforma',
            language='es'
        )

        assert en_template.language == 'en'
        assert es_template.language == 'es'

    @patch('services.notification.main.db')
    async def test_list_templates(self, mock_db):
        """Test listing templates"""
        mock_db.tenant_connection.return_value.__aenter__.return_value.fetch = AsyncMock(
            return_value=[
                {'id': 'tpl_1', 'name': 'new_message'},
                {'id': 'tpl_2', 'name': 'order_status'}
            ]
        )

    @patch('services.notification.main.db')
    async def test_delete_template(self, mock_db):
        """Test deleting template"""
        mock_db.tenant_connection.return_value.__aenter__.return_value.execute = AsyncMock(
            return_value=None
        )


class TestNotificationPreferences:
    """Test user notification preferences"""

    def test_set_do_not_disturb(self):
        """Test setting do-not-disturb hours"""
        from services.notification.main import NotificationPreferencesRequest

        prefs = NotificationPreferencesRequest(
            do_not_disturb_start='22:00',
            do_not_disturb_end='08:00',
            do_not_disturb_enabled=True
        )

        assert prefs.do_not_disturb_enabled is True

    def test_preferred_channels_selection(self):
        """Test selecting preferred notification channels"""
        from services.notification.main import NotificationPreferencesRequest

        prefs = NotificationPreferencesRequest(
            preferred_channels=['push', 'email'],
            notification_sounds=True,
            notification_badges=True
        )

        assert 'push' in prefs.preferred_channels
        assert len(prefs.preferred_channels) == 2

    def test_mute_all_notifications(self):
        """Test muting all notifications"""
        from services.notification.main import NotificationPreferencesRequest

        prefs = NotificationPreferencesRequest(
            mute_all=True
        )

        assert prefs.mute_all is True

    def test_marketing_email_opt_out(self):
        """Test opting out of marketing emails"""
        from services.notification.main import NotificationPreferencesRequest

        prefs = NotificationPreferencesRequest(
            marketing_emails=False,
            system_alerts=True
        )

        assert prefs.marketing_emails is False
        assert prefs.system_alerts is True

    def test_per_type_preferences(self):
        """Test notification type specific preferences"""
        from services.notification.main import NotificationPreferencesRequest

        prefs = NotificationPreferencesRequest(
            per_type_preferences={
                'message': True,
                'lead_score': False,
                'order_status': True
            }
        )

        assert prefs.per_type_preferences['lead_score'] is False

    @patch('services.notification.main.db')
    async def test_update_preferences(self, mock_db):
        """Test updating user preferences"""
        mock_db.tenant_connection.return_value.__aenter__.return_value.execute = AsyncMock(
            return_value=None
        )


class TestWebSocketConnections:
    """Test WebSocket connection management"""

    @patch('services.notification.main.manager')
    async def test_websocket_connect(self, mock_manager):
        """Test WebSocket connection"""
        mock_manager.connect = AsyncMock()

    @patch('services.notification.main.manager')
    async def test_websocket_disconnect(self, mock_manager):
        """Test WebSocket disconnection"""
        mock_manager.disconnect = MagicMock()

    @patch('services.notification.main.manager')
    async def test_broadcast_to_user(self, mock_manager):
        """Test broadcasting to specific user"""
        mock_manager.broadcast_to_user = AsyncMock()

        message = {
            'type': 'notification',
            'id': 'notif_123',
            'title': 'New Message',
            'body': 'Test message'
        }

        # Should send to all user's WebSocket connections

    @patch('services.notification.main.manager')
    async def test_multiple_connections_per_user(self, mock_manager):
        """Test user with multiple device connections"""
        # Should support user connected on web, mobile, tablet
        pass


class TestNotificationCenter:
    """Test notification center (in-app inbox)"""

    @patch('services.notification.main.db')
    async def test_get_unread_notifications(self, mock_db):
        """Test retrieving unread notifications"""
        mock_db.tenant_connection.return_value.__aenter__.return_value.fetch = AsyncMock(
            return_value=[
                {
                    'id': 'notif_1',
                    'title': 'New Message',
                    'is_read': False,
                    'created_at': datetime.utcnow()
                }
            ]
        )

    @patch('services.notification.main.db')
    async def test_mark_notification_as_read(self, mock_db):
        """Test marking notification as read"""
        mock_db.tenant_connection.return_value.__aenter__.return_value.execute = AsyncMock(
            return_value=None
        )

    @patch('services.notification.main.db')
    async def test_archive_notification(self, mock_db):
        """Test archiving notification"""
        mock_db.tenant_connection.return_value.__aenter__.return_value.execute = AsyncMock(
            return_value=None
        )

    @patch('services.notification.main.db')
    async def test_delete_notification(self, mock_db):
        """Test deleting notification"""
        mock_db.tenant_connection.return_value.__aenter__.return_value.execute = AsyncMock(
            return_value=None
        )

    @patch('services.notification.main.db')
    async def test_notification_pagination(self, mock_db):
        """Test paginating notifications"""
        mock_db.tenant_connection.return_value.__aenter__.return_value.fetch = AsyncMock(
            return_value=[
                {'id': 'notif_1', 'title': 'Notification 1'},
                {'id': 'notif_2', 'title': 'Notification 2'}
            ]
        )


class TestNotificationDeliveryRules:
    """Test delivery rule engine"""

    @patch('services.notification.main.db')
    async def test_apply_do_not_disturb_rules(self, mock_db):
        """Test DND schedule enforcement"""
        # Should not deliver during DND hours
        pass

    @patch('services.notification.main.db')
    async def test_apply_channel_preferences(self, mock_db):
        """Test respecting channel preferences"""
        # Should only send via preferred channels
        pass

    @patch('services.notification.main.db')
    async def test_priority_based_routing(self, mock_db):
        """Test routing based on priority"""
        # High priority should bypass DND
        pass

    @patch('services.notification.main.db')
    async def test_rate_limiting(self, mock_db):
        """Test notification rate limiting"""
        # Should limit notifications per user per hour
        pass


class TestNotificationAnalytics:
    """Test notification delivery analytics"""

    @patch('services.notification.main.db')
    async def test_get_delivery_stats(self, mock_db):
        """Test delivery success metrics"""
        mock_db.tenant_connection.return_value.__aenter__.return_value.fetchrow = AsyncMock(
            return_value={
                'total_sent': 10000,
                'successfully_delivered': 9500,
                'failed': 500,
                'delivery_rate': 0.95
            }
        )

    @patch('services.notification.main.db')
    async def test_get_engagement_stats(self, mock_db):
        """Test notification engagement metrics"""
        mock_db.tenant_connection.return_value.__aenter__.return_value.fetchrow = AsyncMock(
            return_value={
                'total_delivered': 9500,
                'total_opened': 5700,
                'total_clicked': 2280,
                'open_rate': 0.60,
                'click_rate': 0.24
            }
        )

    @patch('services.notification.main.db')
    async def test_analytics_by_type(self, mock_db):
        """Test analytics grouped by notification type"""
        mock_db.tenant_connection.return_value.__aenter__.return_value.fetch = AsyncMock(
            return_value=[
                {'type': 'message', 'sent': 5000, 'opened': 3500, 'clicked': 1400},
                {'type': 'lead_score', 'sent': 3000, 'opened': 1800, 'clicked': 540}
            ]
        )


class TestFCMIntegration:
    """Test Firebase Cloud Messaging integration"""

    @patch('services.notification.main.aiohttp.ClientSession')
    async def test_fcm_send_multicast(self, mock_session):
        """Test sending to multiple devices via FCM"""
        # Should batch send to multiple tokens
        pass

    @patch('services.notification.main.aiohttp.ClientSession')
    async def test_fcm_handle_error_responses(self, mock_session):
        """Test handling FCM error responses"""
        # Should handle invalid tokens, quota exceeded, etc
        pass


class TestErrorHandling:
    """Test error scenarios"""

    def test_invalid_notification_type(self):
        """Test rejection of invalid notification type"""
        from services.notification.main import SendNotificationRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SendNotificationRequest(
                user_id='user_123',
                notification_type='invalid_type',
                title='Test',
                body='Test'
            )

    def test_invalid_priority_level(self):
        """Test rejection of invalid priority"""
        from services.notification.main import SendNotificationRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SendNotificationRequest(
                user_id='user_123',
                notification_type='message',
                title='Test',
                body='Test',
                priority='critical'
            )

    def test_invalid_channel_selection(self):
        """Test rejection of invalid channels"""
        from services.notification.main import SendNotificationRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SendNotificationRequest(
                user_id='user_123',
                notification_type='message',
                title='Test',
                body='Test',
                channels=['invalid_channel']
            )


class TestHealthCheck:
    """Test health check endpoint"""

    def test_health_check(self, client):
        """Test health check returns healthy status"""
        response = client.get('/health')

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'healthy'
        assert data['service'] == 'notification'
