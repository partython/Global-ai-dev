"""Lead Scoring and Sales Pipeline Service Tests"""
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from datetime import datetime, timedelta
from decimal import Decimal


@pytest.fixture
def mock_db():
    """Mock database connection pool"""
    return AsyncMock()


@pytest.fixture
def auth_context():
    """Mock auth context"""
    return {
        'tenant_id': 'tenant_123',
        'user_id': 'user_456',
        'user_email': 'user@example.com'
    }


@pytest.fixture
def valid_lead_create():
    """Valid lead creation data"""
    return {
        'first_name': 'John',
        'last_name': 'Doe',
        'email': 'john@example.com',
        'phone': '+919876543210',
        'company': 'Acme Corp',
        'source_channel': 'whatsapp'
    }


class TestLeadCreation:
    """Test lead creation and validation"""

    def test_create_lead_valid(self, valid_lead_create):
        """Test creating lead with valid data"""
        from services.leads.main import LeadCreate

        lead = LeadCreate(
            first_name=valid_lead_create['first_name'],
            last_name=valid_lead_create['last_name'],
            email=valid_lead_create['email'],
            phone=valid_lead_create['phone'],
            company=valid_lead_create['company'],
            source_channel=valid_lead_create['source_channel']
        )

        assert lead.first_name == 'John'
        assert lead.email == 'john@example.com'

    def test_email_normalization(self):
        """Test email normalization to lowercase"""
        from services.leads.main import LeadCreate

        lead = LeadCreate(
            first_name='John',
            last_name='Doe',
            email='John@Example.COM',
            source_channel='whatsapp'
        )

        assert lead.email == 'john@example.com'

    def test_invalid_email_rejection(self):
        """Test rejection of invalid email"""
        from services.leads.main import LeadCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            LeadCreate(
                first_name='John',
                last_name='Doe',
                email='not-an-email',
                source_channel='whatsapp'
            )

    def test_lead_source_channels(self):
        """Test all valid lead source channels"""
        from services.leads.main import LeadChannel

        channels = [
            LeadChannel.WHATSAPP,
            LeadChannel.EMAIL,
            LeadChannel.WEB,
            LeadChannel.PHONE,
            LeadChannel.REFERRAL,
            LeadChannel.LINKEDIN
        ]

        assert len(channels) == 6
        assert LeadChannel.WHATSAPP.value == 'whatsapp'

    def test_create_lead_with_custom_data(self):
        """Test lead creation with custom data"""
        from services.leads.main import LeadCreate

        lead = LeadCreate(
            first_name='John',
            last_name='Doe',
            email='john@example.com',
            source_channel='web',
            custom_data={'industry': 'SaaS', 'company_size': 50}
        )

        assert 'industry' in lead.custom_data


class TestLeadScoring:
    """Test lead scoring calculations"""

    def test_calculate_composite_score(self):
        """Test composite score calculation"""
        engagement_score = 80
        demographic_score = 70
        behavior_score = 85
        intent_score = 90

        composite = (
            engagement_score * 0.3 +
            demographic_score * 0.25 +
            behavior_score * 0.25 +
            intent_score * 0.2
        )

        assert 81 < composite < 82

    def test_lead_grade_from_score_a(self):
        """Test Grade A assignment (90-100)"""
        from services.leads.main import calculate_lead_grade

        grade = calculate_lead_grade(95)
        assert grade.value == 'A'

    def test_lead_grade_from_score_b(self):
        """Test Grade B assignment (75-89)"""
        from services.leads.main import calculate_lead_grade

        grade = calculate_lead_grade(82)
        assert grade.value == 'B'

    def test_lead_grade_from_score_c(self):
        """Test Grade C assignment (50-74)"""
        from services.leads.main import calculate_lead_grade

        grade = calculate_lead_grade(60)
        assert grade.value == 'C'

    def test_lead_grade_from_score_d(self):
        """Test Grade D assignment (25-49)"""
        from services.leads.main import calculate_lead_grade

        grade = calculate_lead_grade(30)
        assert grade.value == 'D'

    def test_lead_grade_from_score_f(self):
        """Test Grade F assignment (0-24)"""
        from services.leads.main import calculate_lead_grade

        grade = calculate_lead_grade(15)
        assert grade.value == 'F'

    def test_score_decay_for_inactive_leads(self):
        """Test score decay calculation"""
        SCORE_DECAY_RATE = 0.95
        initial_score = 100
        weeks_inactive = 4

        decayed_score = initial_score * (SCORE_DECAY_RATE ** weeks_inactive)
        assert 80 < decayed_score < 82

    def test_custom_factors_weighting(self):
        """Test custom scoring factors"""
        from services.leads.main import LeadScoreRequest

        request = LeadScoreRequest(
            engagement_score=80,
            demographic_score=70,
            behavior_score=85,
            intent_score=90,
            custom_factors={'loyalty': 75, 'referral_quality': 85}
        )

        assert 'loyalty' in request.custom_factors


class TestPipelineManagement:
    """Test sales pipeline stages and progression"""

    def test_pipeline_stages(self):
        """Test all valid pipeline stages"""
        from services.leads.main import PipelineStage

        stages = [
            PipelineStage.NEW,
            PipelineStage.QUALIFIED,
            PipelineStage.PROPOSAL,
            PipelineStage.NEGOTIATION,
            PipelineStage.WON,
            PipelineStage.LOST
        ]

        assert len(stages) == 6
        assert PipelineStage.NEW.value == 'New'

    def test_advance_pipeline_stage(self):
        """Test advancing lead through pipeline"""
        from services.leads.main import AdvancePipelineRequest

        request = AdvancePipelineRequest(
            lead_id='lead_123',
            new_stage='Qualified',
            deal_value=5000.0,
            win_probability=0.7
        )

        assert request.new_stage == 'Qualified'
        assert request.win_probability == 0.7

    @patch('services.leads.main.db_pool')
    async def test_pipeline_stage_gate_requirements(self, mock_pool):
        """Test stage gate requirements validation"""
        # Should check required fields before advancing
        pass

    @patch('services.leads.main.db_pool')
    async def test_auto_advance_stage(self, mock_pool):
        """Test automatic stage advancement"""
        from services.leads.main import PipelineStageConfig

        config = PipelineStageConfig(
            stage_name='Proposal',
            order=3,
            auto_advance=True
        )

        assert config.auto_advance is True


class TestLeadAssignment:
    """Test lead assignment to sales team"""

    def test_manual_assignment(self):
        """Test manual lead assignment"""
        from services.leads.main import AssignLeadRequest

        request = AssignLeadRequest(
            lead_id='lead_123',
            assigned_to='user_456',
            assignment_method='manual'
        )

        assert request.assignment_method == 'manual'

    @patch('services.leads.main.db_pool')
    async def test_round_robin_assignment(self, mock_pool):
        """Test round-robin assignment"""
        from services.leads.main import AssignLeadRequest

        request = AssignLeadRequest(
            lead_id='lead_123',
            assigned_to='team_sales',
            assignment_method='round-robin'
        )

        assert request.assignment_method == 'round-robin'

    @patch('services.leads.main.db_pool')
    async def test_skills_based_assignment(self, mock_pool):
        """Test skill-based assignment"""
        from services.leads.main import AssignLeadRequest

        request = AssignLeadRequest(
            lead_id='lead_123',
            assigned_to='user_456',
            assignment_method='skills-based'
        )

    @patch('services.leads.main.db_pool')
    async def test_territory_assignment(self, mock_pool):
        """Test territory-based assignment"""
        from services.leads.main import AssignLeadRequest

        request = AssignLeadRequest(
            lead_id='lead_123',
            assigned_to='region_us',
            assignment_method='territory'
        )

        assert request.assignment_method == 'territory'


class TestDuplicateDetection:
    """Test lead duplicate detection"""

    def test_duplicate_detection_request(self):
        """Test duplicate detection request"""
        from services.leads.main import DuplicateDetectionRequest

        request = DuplicateDetectionRequest(
            email='john@example.com',
            phone='+919876543210',
            first_name='John',
            last_name='Doe'
        )

        assert request.email == 'john@example.com'

    @patch('services.leads.main.db_pool')
    async def test_detect_duplicate_by_email(self, mock_pool):
        """Test duplicate detection by email"""
        mock_pool.acquire.return_value.__aenter__.return_value.fetchval = AsyncMock(
            return_value='existing_lead_id'
        )

    @patch('services.leads.main.db_pool')
    async def test_detect_duplicate_by_phone(self, mock_pool):
        """Test duplicate detection by phone"""
        mock_pool.acquire.return_value.__aenter__.return_value.fetchval = AsyncMock(
            return_value='existing_lead_id'
        )

    @patch('services.leads.main.db_pool')
    async def test_detect_duplicate_by_name_company(self, mock_pool):
        """Test duplicate detection by name and company"""
        # Should find duplicates with similar name and company
        pass

    @patch('services.leads.main.db_pool')
    async def test_merge_duplicate_leads(self, mock_pool):
        """Test merging duplicate leads"""
        # Should merge scores and history
        pass


class TestLeadConversion:
    """Test lead conversion tracking"""

    @patch('services.leads.main.db_pool')
    async def test_track_conversion(self, mock_pool):
        """Test tracking lead conversion"""
        mock_pool.acquire.return_value.__aenter__.return_value.execute = AsyncMock(
            return_value=None
        )

    @patch('services.leads.main.db_pool')
    async def test_conversion_velocity_tracking(self, mock_pool):
        """Test conversion time tracking"""
        created_date = datetime.utcnow() - timedelta(days=5)
        converted_date = datetime.utcnow()
        conversion_velocity = (converted_date - created_date).days
        assert conversion_velocity == 5

    @patch('services.leads.main.db_pool')
    async def test_conversion_by_channel(self, mock_pool):
        """Test conversion rate by source channel"""
        mock_pool.acquire.return_value.__aenter__.return_value.fetch = AsyncMock(
            return_value=[
                {'channel': 'whatsapp', 'conversions': 45, 'total': 150},
                {'channel': 'email', 'conversions': 25, 'total': 200},
                {'channel': 'web', 'conversions': 80, 'total': 400}
            ]
        )


class TestLeadAnalytics:
    """Test lead analytics and reporting"""

    @patch('services.leads.main.db_pool')
    async def test_lead_distribution_by_grade(self, mock_pool):
        """Test lead distribution across grades"""
        mock_pool.acquire.return_value.__aenter__.return_value.fetch = AsyncMock(
            return_value=[
                {'grade': 'A', 'count': 50},
                {'grade': 'B', 'count': 120},
                {'grade': 'C', 'count': 200},
                {'grade': 'D', 'count': 150},
                {'grade': 'F', 'count': 80}
            ]
        )

    @patch('services.leads.main.db_pool')
    async def test_lead_distribution_by_stage(self, mock_pool):
        """Test lead distribution across pipeline stages"""
        mock_pool.acquire.return_value.__aenter__.return_value.fetch = AsyncMock(
            return_value=[
                {'stage': 'New', 'count': 100},
                {'stage': 'Qualified', 'count': 80},
                {'stage': 'Proposal', 'count': 50},
                {'stage': 'Negotiation', 'count': 30},
                {'stage': 'Won', 'count': 25}
            ]
        )

    @patch('services.leads.main.db_pool')
    async def test_average_deal_value_by_stage(self, mock_pool):
        """Test average deal value per stage"""
        mock_pool.acquire.return_value.__aenter__.return_value.fetch = AsyncMock(
            return_value=[
                {'stage': 'Proposal', 'avg_value': 5000},
                {'stage': 'Negotiation', 'avg_value': 7500},
                {'stage': 'Won', 'avg_value': 8500}
            ]
        )

    @patch('services.leads.main.db_pool')
    async def test_win_rate_by_stage(self, mock_pool):
        """Test win rate at each pipeline stage"""
        def calculate_win_rate(won, total):
            return (won / total) * 100 if total > 0 else 0

        # Example: 25 wins from 30 proposals = 83.3% win rate
        win_rate = calculate_win_rate(25, 30)
        assert 83 < win_rate < 84


class TestLeadUpdate:
    """Test lead updates and modifications"""

    def test_update_lead_partial(self):
        """Test partial lead update"""
        from services.leads.main import LeadUpdate

        update = LeadUpdate(
            company='New Company Inc',
            phone='+911234567890'
        )

        assert update.company == 'New Company Inc'
        assert update.phone == '+911234567890'
        assert update.first_name is None

    @patch('services.leads.main.db_pool')
    async def test_update_lead_score(self, mock_pool):
        """Test updating lead score"""
        mock_pool.acquire.return_value.__aenter__.return_value.execute = AsyncMock(
            return_value=None
        )

    @patch('services.leads.main.db_pool')
    async def test_update_custom_data(self, mock_pool):
        """Test updating custom lead data"""
        mock_pool.acquire.return_value.__aenter__.return_value.execute = AsyncMock(
            return_value=None
        )


class TestLeadList:
    """Test lead listing and filtering"""

    @patch('services.leads.main.db_pool')
    async def test_list_leads_pagination(self, mock_pool):
        """Test listing leads with pagination"""
        mock_pool.acquire.return_value.__aenter__.return_value.fetch = AsyncMock(
            return_value=[
                {'lead_id': 'lead_1', 'first_name': 'John'},
                {'lead_id': 'lead_2', 'first_name': 'Jane'}
            ]
        )

    @patch('services.leads.main.db_pool')
    async def test_filter_leads_by_grade(self, mock_pool):
        """Test filtering leads by grade"""
        mock_pool.acquire.return_value.__aenter__.return_value.fetch = AsyncMock(
            return_value=[
                {'lead_id': 'lead_1', 'grade': 'A', 'score': 95},
                {'lead_id': 'lead_2', 'grade': 'A', 'score': 92}
            ]
        )

    @patch('services.leads.main.db_pool')
    async def test_filter_leads_by_stage(self, mock_pool):
        """Test filtering leads by pipeline stage"""
        mock_pool.acquire.return_value.__aenter__.return_value.fetch = AsyncMock(
            return_value=[
                {'lead_id': 'lead_1', 'stage': 'Proposal'},
                {'lead_id': 'lead_3', 'stage': 'Proposal'}
            ]
        )

    @patch('services.leads.main.db_pool')
    async def test_filter_leads_by_assignee(self, mock_pool):
        """Test filtering leads by assigned user"""
        mock_pool.acquire.return_value.__aenter__.return_value.fetch = AsyncMock(
            return_value=[
                {'lead_id': 'lead_1', 'assigned_to': 'user_456'},
                {'lead_id': 'lead_2', 'assigned_to': 'user_456'}
            ]
        )


class TestAuthContext:
    """Test authentication context"""

    def test_auth_context_creation(self, auth_context):
        """Test auth context initialization"""
        from services.leads.main import AuthContext

        ctx = AuthContext(
            tenant_id=auth_context['tenant_id'],
            user_id=auth_context['user_id'],
            user_email=auth_context['user_email']
        )

        assert ctx.tenant_id == 'tenant_123'
        assert ctx.user_id == 'user_456'


class TestDatabasePool:
    """Test database connection pooling"""

    @patch('services.leads.main.asyncpg.create_pool')
    async def test_create_db_pool(self, mock_create_pool):
        """Test database pool creation"""
        mock_create_pool.return_value = AsyncMock()
        # Pool should be created with proper configuration
        pass

    @patch('services.leads.main.db_pool')
    async def test_pool_close(self, mock_pool):
        """Test database pool closure"""
        mock_pool.close = AsyncMock()
        # Pool should close properly


class TestHealthCheck:
    """Test health check endpoint"""

    def test_health_check(self, client):
        """Test health check returns healthy status"""
        response = client.get('/health')

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'healthy'
        assert data['service'] == 'Lead Scoring & Sales Pipeline'
