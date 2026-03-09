"""
Example test suite for Lead Scoring & Sales Pipeline Service
Run with: pytest test_example.py
"""

import pytest
import asyncio
import json
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime
import jwt

# Mock the main module dependencies
@pytest.fixture
def auth_context():
    """Create mock auth context"""
    class MockAuth:
        tenant_id = "test_tenant_123"
        user_id = "user_456"
        user_email = "user@example.com"
    return MockAuth()

@pytest.fixture
def mock_db_pool():
    """Create mock database pool"""
    pool = AsyncMock()
    return pool

@pytest.fixture
async def mock_connection():
    """Create mock database connection"""
    conn = AsyncMock()
    return conn

class TestLeadCreation:
    """Test lead creation functionality"""
    
    def test_lead_create_request_validation(self):
        """Test lead creation request validation"""
        # Valid request
        from main import LeadCreate, LeadChannel
        
        lead = LeadCreate(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            company="Acme Corp",
            source_channel=LeadChannel.WEB
        )
        assert lead.first_name == "John"
        assert lead.email == "john@example.com"
    
    def test_lead_create_invalid_email(self):
        """Test invalid email validation"""
        from main import LeadCreate, LeadChannel
        
        with pytest.raises(ValueError):
            LeadCreate(
                first_name="John",
                last_name="Doe",
                email="invalid_email",
                source_channel=LeadChannel.WEB
            )

class TestScoring:
    """Test lead scoring functionality"""
    
    def test_calculate_lead_grade(self):
        """Test lead grade calculation"""
        from main import calculate_lead_grade, LeadGrade
        
        assert calculate_lead_grade(95) == LeadGrade.A
        assert calculate_lead_grade(80) == LeadGrade.B
        assert calculate_lead_grade(60) == LeadGrade.C
        assert calculate_lead_grade(30) == LeadGrade.D
        assert calculate_lead_grade(10) == LeadGrade.F
    
    def test_calculate_composite_score(self):
        """Test composite score calculation"""
        from main import LeadScoreRequest, calculate_composite_score
        
        score_req = LeadScoreRequest(
            engagement_score=100,
            demographic_score=100,
            behavior_score=100,
            intent_score=100
        )
        score = calculate_composite_score(score_req)
        assert score == 100
    
    def test_composite_score_with_custom_factors(self):
        """Test score calculation with custom factors"""
        from main import LeadScoreRequest, calculate_composite_score
        
        score_req = LeadScoreRequest(
            engagement_score=80,
            demographic_score=70,
            behavior_score=75,
            intent_score=85,
            custom_factors={"referral_quality": 90}
        )
        score = calculate_composite_score(score_req)
        assert 0 <= score <= 100

class TestAuthentication:
    """Test JWT authentication"""
    
    def test_jwt_decode_valid_token(self):
        """Test valid JWT token decoding"""
        import os
        secret = "test_secret"
        
        payload = {
            "sub": "user_123",
            "tenant_id": "tenant_456",
            "email": "user@example.com"
        }
        
        token = jwt.encode(payload, secret, algorithm="HS256")
        decoded = jwt.decode(token, secret, algorithms=["HS256"])
        
        assert decoded["sub"] == "user_123"
        assert decoded["tenant_id"] == "tenant_456"
    
    def test_jwt_decode_invalid_token(self):
        """Test invalid JWT token"""
        secret = "test_secret"
        wrong_secret = "wrong_secret"
        
        token = jwt.encode({"sub": "user"}, secret, algorithm="HS256")
        
        with pytest.raises(jwt.InvalidTokenError):
            jwt.decode(token, wrong_secret, algorithms=["HS256"])

class TestPipelineStages:
    """Test pipeline stage management"""
    
    def test_pipeline_stage_enum(self):
        """Test pipeline stage enum"""
        from main import PipelineStage
        
        assert PipelineStage.NEW.value == "New"
        assert PipelineStage.QUALIFIED.value == "Qualified"
        assert PipelineStage.PROPOSAL.value == "Proposal"
        assert PipelineStage.WON.value == "Won"
        assert PipelineStage.LOST.value == "Lost"
    
    def test_pipeline_config_validation(self):
        """Test pipeline configuration validation"""
        from main import PipelineConfig, PipelineStageConfig
        
        stages = [
            PipelineStageConfig(stage_name="New", order=1),
            PipelineStageConfig(stage_name="Qualified", order=2),
        ]
        
        config = PipelineConfig(
            tenant_id="tenant_123",
            stages=stages
        )
        assert len(config.stages) == 2
        assert config.stages[0].stage_name == "New"

class TestDuplicateDetection:
    """Test duplicate lead detection"""
    
    def test_duplicate_detection_request(self):
        """Test duplicate detection request validation"""
        from main import DuplicateDetectionRequest
        
        # By email
        req = DuplicateDetectionRequest(email="john@example.com")
        assert req.email == "john@example.com"
        
        # By phone
        req = DuplicateDetectionRequest(phone="+1234567890")
        assert req.phone == "+1234567890"
        
        # By name
        req = DuplicateDetectionRequest(
            first_name="John",
            last_name="Doe"
        )
        assert req.first_name == "John"

class TestModels:
    """Test Pydantic model validation"""
    
    def test_lead_update_partial_validation(self):
        """Test partial lead update"""
        from main import LeadUpdate
        
        update = LeadUpdate(first_name="Jane")
        assert update.first_name == "Jane"
        assert update.email is None
    
    def test_advance_pipeline_request(self):
        """Test advance pipeline request"""
        from main import AdvancePipelineRequest
        
        req = AdvancePipelineRequest(
            lead_id="lead_123",
            new_stage="Proposal",
            deal_value=50000,
            win_probability=0.75
        )
        assert req.lead_id == "lead_123"
        assert req.new_stage == "Proposal"
        assert req.win_probability == 0.75
    
    def test_assign_lead_request(self):
        """Test assign lead request"""
        from main import AssignLeadRequest
        
        req = AssignLeadRequest(
            lead_id="lead_123",
            assigned_to="agent_456",
            assignment_method="skills-based"
        )
        assert req.lead_id == "lead_123"
        assert req.assigned_to == "agent_456"

class TestHealthCheck:
    """Test health check endpoint"""
    
    def test_health_response_model(self):
        """Test health response model"""
        from main import HealthResponse
        
        health = HealthResponse(
            status="healthy",
            timestamp=datetime.utcnow()
        )
        assert health.status == "healthy"
        assert health.service == "Lead Scoring & Sales Pipeline"

class TestScoreBoundaries:
    """Test score calculation boundaries"""
    
    def test_score_min_boundary(self):
        """Test minimum score boundary"""
        from main import LeadScoreRequest, calculate_composite_score, MIN_SCORE
        
        score_req = LeadScoreRequest(
            engagement_score=0,
            demographic_score=0,
            behavior_score=0,
            intent_score=0
        )
        score = calculate_composite_score(score_req)
        assert score >= MIN_SCORE
    
    def test_score_max_boundary(self):
        """Test maximum score boundary"""
        from main import LeadScoreRequest, calculate_composite_score, MAX_SCORE
        
        score_req = LeadScoreRequest(
            engagement_score=100,
            demographic_score=100,
            behavior_score=100,
            intent_score=100,
            custom_factors={"factor1": 100, "factor2": 100}
        )
        score = calculate_composite_score(score_req)
        assert score <= MAX_SCORE

class TestDataValidation:
    """Test data validation"""
    
    def test_email_normalization(self):
        """Test email is normalized to lowercase"""
        from main import LeadCreate, LeadChannel
        
        lead = LeadCreate(
            first_name="John",
            last_name="Doe",
            email="JOHN@EXAMPLE.COM",
            source_channel=LeadChannel.WEB
        )
        assert lead.email == "john@example.com"
    
    def test_win_probability_boundaries(self):
        """Test win probability is between 0 and 1"""
        from main import AdvancePipelineRequest
        
        # Valid
        req = AdvancePipelineRequest(
            lead_id="lead_123",
            new_stage="Proposal",
            win_probability=0.5
        )
        assert req.win_probability == 0.5
        
        # Invalid values should raise validation error
        with pytest.raises(ValueError):
            AdvancePipelineRequest(
                lead_id="lead_123",
                new_stage="Proposal",
                win_probability=1.5
            )

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
