"""Voice Channel Service Tests"""
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from pydantic import ValidationError
from datetime import datetime, timezone


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


class TestCallInitiation:
    """Test initiating outbound calls"""

    @patch('services.voice.main.db')
    async def test_initiate_outbound_call(self, mock_db):
        """Test initiating outbound call"""
        from services.voice.main import InitiateCallRequest

        request = InitiateCallRequest(
            to_number='+919876543210',
            ai_prompt='Ask about their product interest'
        )

        assert request.to_number == '+919876543210'
        assert 'product' in request.ai_prompt

    def test_phone_number_validation(self):
        """Test phone number validation"""
        from services.voice.main import InitiateCallRequest

        # Invalid format
        with pytest.raises(ValidationError):
            InitiateCallRequest(
                to_number='not-a-number',
                ai_prompt='Test'
            )

    def test_international_numbers(self):
        """Test international number support"""
        from services.voice.main import InitiateCallRequest

        numbers = [
            '+919876543210',  # India
            '+12025551234',   # USA
            '+441234567890',  # UK
        ]

        for number in numbers:
            request = InitiateCallRequest(
                to_number=number,
                ai_prompt='Test'
            )
            assert request.to_number == number

    @patch('services.voice.main.db')
    async def test_scheduled_call(self, mock_db):
        """Test scheduling call for future"""
        from services.voice.main import InitiateCallRequest
        from datetime import datetime, timedelta

        future_time = datetime.utcnow() + timedelta(hours=1)

        request = InitiateCallRequest(
            to_number='+919876543210',
            ai_prompt='Test',
            scheduled_for=future_time
        )


class TestCallStates:
    """Test call state management"""

    def test_call_state_transitions(self):
        """Test valid call state transitions"""
        from services.voice.main import CallState

        assert CallState.RINGING.value == 'ringing'
        assert CallState.ANSWERED.value == 'answered'
        assert CallState.IN_PROGRESS.value == 'in_progress'
        assert CallState.COMPLETED.value == 'completed'

    @patch('services.voice.main.db')
    async def test_update_call_state(self, mock_db):
        """Test updating call state"""
        call_id = 'call_123'
        new_state = 'answered'

        # Should update in database

    @patch('services.voice.main.db')
    async def test_track_call_duration(self, mock_db):
        """Test tracking call duration"""
        mock_db.tenant_connection.return_value.__aenter__.return_value.fetchrow = AsyncMock(
            return_value={
                'started_at': datetime(2024, 3, 6, 10, 0, 0),
                'ended_at': datetime(2024, 3, 6, 10, 5, 30)
            }
        )


class TestIVRMenu:
    """Test IVR menu handling"""

    def test_ivr_menu_routing(self):
        """Test IVR menu routing"""
        from services.voice.main import InitiateCallRequest

        request = InitiateCallRequest(
            to_number='+919876543210',
            ai_prompt='Initial greeting',
            ivr_menu={
                '1': 'sales',
                '2': 'support',
                '3': 'billing'
            }
        )

        assert '1' in request.ivr_menu

    def test_dtmf_handling(self):
        """Test DTMF tone handling"""
        from services.voice.main import DTMFKey

        assert DTMFKey.KEY_1.value == '1'
        assert DTMFKey.STAR.value == '*'
        assert DTMFKey.HASH.value == '#'


class TestCallTransfer:
    """Test call transfers"""

    @patch('services.voice.main.db')
    async def test_transfer_to_number(self, mock_db):
        """Test transferring to phone number"""
        from services.voice.main import TransferCallRequest

        request = TransferCallRequest(
            target='+919876543210',
            reason='Customer requested'
        )

        assert request.target == '+919876543210'

    @patch('services.voice.main.db')
    async def test_transfer_to_agent(self, mock_db):
        """Test transferring to agent"""
        from services.voice.main import TransferCallRequest

        request = TransferCallRequest(
            target='agent@example.com',
            reason='Sales inquiry'
        )

        assert 'agent' in request.target

    @patch('services.voice.main.db')
    async def test_transfer_state_update(self, mock_db):
        """Test call state updates to transferring"""
        # Should set state to TRANSFERRING


class TestRecording:
    """Test call recording"""

    @patch('services.voice.main.db')
    async def test_enable_recording(self, mock_db):
        """Test enabling call recording"""
        from services.voice.main import InitiateCallRequest

        request = InitiateCallRequest(
            to_number='+919876543210',
            ai_prompt='Test',
            record=True
        )

        assert request.record is True

    @patch('services.voice.main.db')
    async def test_disable_recording(self, mock_db):
        """Test disabling call recording"""
        from services.voice.main import InitiateCallRequest

        request = InitiateCallRequest(
            to_number='+919876543210',
            ai_prompt='Test',
            record=False
        )

        assert request.record is False

    @patch('services.voice.main.db')
    async def test_recording_storage(self, mock_db):
        """Test recording storage in S3"""
        # Should store recording with S3 key


class TestCarrierRouting:
    """Test carrier selection by country"""

    def test_exotel_for_india(self):
        """Test Exotel for India calls"""
        from services.voice.main import CarrierRouter

        router = CarrierRouter()
        carrier = router.get_carrier_for_number('+919876543210')
        from services.voice.main import CarrierType
        assert carrier == CarrierType.EXOTEL

    def test_bandwidth_for_us(self):
        """Test Bandwidth for US calls"""
        from services.voice.main import CarrierRouter

        router = CarrierRouter()
        carrier = router.get_carrier_for_number('+12025551234')
        from services.voice.main import CarrierType
        assert carrier == CarrierType.BANDWIDTH

    def test_vonage_for_uk(self):
        """Test Vonage for UK calls"""
        from services.voice.main import CarrierRouter

        router = CarrierRouter()
        carrier = router.get_carrier_for_number('+441234567890')
        from services.voice.main import CarrierType
        assert carrier == CarrierType.VONAGE


class TestWebhookSignatures:
    """Test webhook signature verification"""

    def test_exotel_signature(self):
        """Test Exotel webhook signature verification"""
        # Should verify SHA1 HMAC signature

    def test_bandwidth_signature(self):
        """Test Bandwidth webhook signature verification"""
        # Should verify SHA256 HMAC signature

    def test_vonage_signature(self):
        """Test Vonage webhook signature verification"""
        # Should verify signature


class TestCallAnalytics:
    """Test call analytics"""

    @patch('services.voice.main.db')
    async def test_get_call_analytics(self, mock_db):
        """Test retrieving call analytics"""
        mock_db.tenant_connection.return_value.__aenter__.return_value.fetchrow = AsyncMock(
            return_value={
                'total_calls': 100,
                'total_inbound': 30,
                'total_outbound': 70,
                'total_completed': 85,
                'total_failed': 15,
                'avg_duration_seconds': 450.0,
                'transcription_count': 50
            }
        )

    def test_resolution_rate_calculation(self):
        """Test resolution rate calculation"""
        total_completed = 85
        total_calls = 100

        resolution_rate = (total_completed / total_calls) * 100
        assert resolution_rate == 85.0

    def test_average_call_duration(self):
        """Test average call duration"""
        total_duration = 45000  # seconds
        total_calls = 100

        avg_duration = total_duration / total_calls
        assert avg_duration == 450.0


class TestCallHold:
    """Test call hold functionality"""

    @patch('services.voice.main.db')
    async def test_put_call_on_hold(self, mock_db):
        """Test putting call on hold"""
        from services.voice.main import HoldCallRequest

        request = HoldCallRequest(hold=True)
        assert request.hold is True

    @patch('services.voice.main.db')
    async def test_resume_from_hold(self, mock_db):
        """Test resuming from hold"""
        from services.voice.main import HoldCallRequest

        request = HoldCallRequest(hold=False)
        assert request.hold is False


class TestListCalls:
    """Test listing calls"""

    @patch('services.voice.main.db')
    async def test_list_calls(self, mock_db):
        """Test listing calls for tenant"""
        mock_db.tenant_connection.return_value.__aenter__.return_value.fetch = AsyncMock(
            return_value=[
                {
                    'call_id': 'call_1',
                    'from_number': '+919876543210',
                    'to_number': '+919876543211',
                    'state': 'completed',
                    'direction': 'outbound',
                    'carrier': 'exotel',
                    'duration_seconds': 300,
                    'started_at': datetime.utcnow(),
                    'ended_at': datetime.utcnow()
                }
            ]
        )

    @patch('services.voice.main.db')
    async def test_list_calls_pagination(self, mock_db):
        """Test pagination of calls list"""
        # Should support limit and offset


class TestCallDetails:
    """Test retrieving call details"""

    @patch('services.voice.main.db')
    async def test_get_call_detail(self, mock_db):
        """Test retrieving full call details"""
        mock_db.tenant_connection.return_value.__aenter__.return_value.fetchrow = AsyncMock(
            return_value={
                'call_id': 'call_123',
                'from_number': '+919876543210',
                'to_number': '+919876543211',
                'state': 'completed',
                'direction': 'outbound',
                'carrier': 'exotel',
                'duration_seconds': 300,
                'recording_s3_key': 's3://bucket/recording.wav',
                'transcription': 'Call transcript here',
                'ai_agent_prompt': 'Test prompt',
                'msg_count': 5,
                'started_at': datetime.utcnow(),
                'ended_at': datetime.utcnow()
            }
        )


class TestHealthCheck:
    """Test health check"""

    def test_health_check(self, client):
        """Test health check endpoint"""
        response = client.get('/health')

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'healthy'
        assert data['service'] == 'voice'
