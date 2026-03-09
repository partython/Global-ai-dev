"""
Test examples and integration tests for Conversation Intelligence Service
"""

import asyncio
import json
from datetime import datetime
import jwt
from httpx import AsyncClient
import asyncpg

# Test Configuration
SERVICE_URL = "http://localhost:9028"
JWT_SECRET = "dev-secret-key-change-in-production"
TEST_TENANT_ID = "550e8400-e29b-41d4-a716-446655440000"
TEST_USER_ID = "user-test-123"

# Sample conversation for testing
SAMPLE_CONVERSATION = {
    "conversation_id": "conv-test-2026-001",
    "customer_id": "cust-demo-123",
    "agent_id": "agent-demo-456",
    "messages": [
        {
            "speaker": "agent",
            "text": "Hi there! Welcome to our sales team. How can I help you today?",
            "timestamp": datetime.now().isoformat(),
            "speaker_role": "agent"
        },
        {
            "speaker": "customer",
            "text": "I'm interested in your premium pricing plan",
            "timestamp": datetime.now().isoformat(),
            "speaker_role": "customer"
        },
        {
            "speaker": "agent",
            "text": "Great! That's our most popular plan. It includes advanced analytics and API access. What features are most important to you?",
            "timestamp": datetime.now().isoformat(),
            "speaker_role": "agent"
        },
        {
            "speaker": "customer",
            "text": "I'm concerned about integration with Salesforce. How difficult is it?",
            "timestamp": datetime.now().isoformat(),
            "speaker_role": "customer"
        },
        {
            "speaker": "agent",
            "text": "Excellent question! Our Salesforce integration is seamless - it takes about 10 minutes with our guided setup. We have a dedicated integration team to help.",
            "timestamp": datetime.now().isoformat(),
            "speaker_role": "agent"
        },
        {
            "speaker": "customer",
            "text": "That sounds good. What's your support level for this plan?",
            "timestamp": datetime.now().isoformat(),
            "speaker_role": "customer"
        },
        {
            "speaker": "agent",
            "text": "Premium plan includes 24/7 email support, phone support during business hours, and a dedicated account manager. We also provide monthly strategy calls.",
            "timestamp": datetime.now().isoformat(),
            "speaker_role": "agent"
        },
        {
            "speaker": "customer",
            "text": "Perfect! I'm ready to move forward. Let's sign up for the annual plan.",
            "timestamp": datetime.now().isoformat(),
            "speaker_role": "customer"
        },
        {
            "speaker": "agent",
            "text": "Wonderful! Let me get you set up with our onboarding team. You made a great choice!",
            "timestamp": datetime.now().isoformat(),
            "speaker_role": "agent"
        }
    ],
    "metadata": {
        "source": "web_chat",
        "duration_seconds": 420,
        "customer_segment": "mid-market"
    }
}


def generate_jwt_token(tenant_id: str = TEST_TENANT_ID, user_id: str = TEST_USER_ID) -> str:
    """Generate a valid JWT token for testing"""
    payload = {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "roles": ["admin", "analyst"]
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


async def test_health_check():
    """Test health check endpoint"""
    print("\n=== Testing Health Check ===")
    async with AsyncClient() as client:
        response = await client.get(f"{SERVICE_URL}/api/v1/intel/health")
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


async def test_analyze_conversation():
    """Test conversation analysis endpoint"""
    print("\n=== Testing Analyze Conversation ===")
    token = generate_jwt_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    async with AsyncClient() as client:
        response = await client.post(
            f"{SERVICE_URL}/api/v1/intel/analyze",
            json=SAMPLE_CONVERSATION,
            headers=headers
        )
        print(f"Status: {response.status_code}")
        result = response.json()
        print(f"Conversation ID: {result.get('conversation_id')}")
        print(f"Overall Sentiment: {result.get('overall_sentiment')}")
        print(f"Key Moments: {len(result.get('key_moments', []))} detected")
        print(f"Topics: {[t['topic'] for t in result.get('topics', [])]}")
        print(f"Objections: {result.get('objections_count')}")
        print(f"Upsell Opportunities: {result.get('upsell_opportunities')}")
        print(f"Pain Points: {result.get('pain_points')}")
        print(f"Talk-Listen Ratio: Agent={result.get('talk_listen_ratio', {}).get('agent'):.2%}, Customer={result.get('talk_listen_ratio', {}).get('customer'):.2%}")
        
        assert response.status_code == 200


async def test_get_conversation_analysis():
    """Test retrieving conversation analysis"""
    print("\n=== Testing Get Conversation Analysis ===")
    token = generate_jwt_token()
    headers = {"Authorization": f"Bearer {token}"}
    conv_id = SAMPLE_CONVERSATION["conversation_id"]
    
    async with AsyncClient() as client:
        response = await client.get(
            f"{SERVICE_URL}/api/v1/intel/conversation/{conv_id}",
            headers=headers
        )
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"Found analysis for {conv_id}")
            print(f"Topics: {result.get('topics')}")
        else:
            print("Analysis not found (expected on first test run)")


async def test_sentiment_timeline():
    """Test sentiment timeline endpoint"""
    print("\n=== Testing Sentiment Timeline ===")
    token = generate_jwt_token()
    headers = {"Authorization": f"Bearer {token}"}
    conv_id = SAMPLE_CONVERSATION["conversation_id"]
    
    async with AsyncClient() as client:
        response = await client.get(
            f"{SERVICE_URL}/api/v1/intel/sentiment/{conv_id}",
            headers=headers
        )
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            sentiments = response.json()
            print(f"Sentiment timeline with {len(sentiments)} messages")
            for s in sentiments[:3]:
                print(f"  Message {s.get('message_idx')}: {s.get('sentiment')} (score: {s.get('score'):.2f})")


async def test_topic_distribution():
    """Test topic distribution endpoint"""
    print("\n=== Testing Topic Distribution ===")
    token = generate_jwt_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    async with AsyncClient() as client:
        response = await client.get(
            f"{SERVICE_URL}/api/v1/intel/topics?days=30",
            headers=headers
        )
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            topics = response.json()
            print(f"Topics found: {topics}")


async def test_keyword_analysis():
    """Test keyword analysis endpoint"""
    print("\n=== Testing Keyword Analysis ===")
    token = generate_jwt_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    async with AsyncClient() as client:
        response = await client.get(
            f"{SERVICE_URL}/api/v1/intel/keywords?days=30",
            headers=headers
        )
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            keywords = response.json()
            print(f"Top keywords: {list(keywords.keys())[:10]}")


async def test_summarize_conversation():
    """Test conversation summarization"""
    print("\n=== Testing Conversation Summarization ===")
    token = generate_jwt_token()
    headers = {"Authorization": f"Bearer {token}"}
    conv_id = SAMPLE_CONVERSATION["conversation_id"]
    
    async with AsyncClient() as client:
        response = await client.post(
            f"{SERVICE_URL}/api/v1/intel/summarize/{conv_id}",
            headers=headers
        )
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"Summary: {result.get('summary')}")
        else:
            print("Conversation not found for summarization")


async def test_agent_coaching():
    """Test agent coaching insights"""
    print("\n=== Testing Agent Coaching Insights ===")
    token = generate_jwt_token()
    headers = {"Authorization": f"Bearer {token}"}
    agent_id = SAMPLE_CONVERSATION["agent_id"]
    
    async with AsyncClient() as client:
        response = await client.get(
            f"{SERVICE_URL}/api/v1/intel/coaching/{agent_id}",
            headers=headers
        )
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"Agent: {result.get('agent_id')}")
            print(f"Performance Score: {result.get('performance_score'):.2f}")
            print(f"Conversations: {result.get('conversation_count')}")
            print(f"Avg Sentiment: {result.get('avg_sentiment'):.2f}")
            print(f"Strengths: {result.get('strengths')}")
            print(f"Improvements: {result.get('improvements')}")


async def test_sales_opportunities():
    """Test sales opportunities endpoint"""
    print("\n=== Testing Sales Opportunities ===")
    token = generate_jwt_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    async with AsyncClient() as client:
        response = await client.get(
            f"{SERVICE_URL}/api/v1/intel/opportunities?days=30",
            headers=headers
        )
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            opportunities = response.json()
            print(f"Opportunities found: {len(opportunities)}")
            for opp in opportunities[:3]:
                print(f"  {opp.get('opportunity_type')}: {opp.get('description')}")


async def test_conversation_trends():
    """Test conversation trends endpoint"""
    print("\n=== Testing Conversation Trends ===")
    token = generate_jwt_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    async with AsyncClient() as client:
        response = await client.get(
            f"{SERVICE_URL}/api/v1/intel/trends?days=30",
            headers=headers
        )
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            trends = response.json()
            print(f"Trend data points: {len(trends)}")
            for trend in trends[:3]:
                print(f"  {trend.get('date')}: {trend.get('conversation_count')} conversations, sentiment={trend.get('avg_sentiment'):.2f}")


async def test_invalid_token():
    """Test endpoint with invalid token"""
    print("\n=== Testing Invalid Token ===")
    headers = {"Authorization": "Bearer invalid.token.here"}
    
    async with AsyncClient() as client:
        response = await client.get(
            f"{SERVICE_URL}/api/v1/intel/health",
            headers=headers
        )
        print(f"Status: {response.status_code}")
        # Health check doesn't require auth, so let's test a protected endpoint
        response = await client.get(
            f"{SERVICE_URL}/api/v1/intel/topics",
            headers=headers
        )
        print(f"Topics with invalid token status: {response.status_code}")
        assert response.status_code == 401


async def run_all_tests():
    """Run all tests sequentially"""
    print("=" * 60)
    print("CONVERSATION INTELLIGENCE SERVICE - TEST SUITE")
    print("=" * 60)
    
    try:
        # Basic connectivity
        await test_health_check()
        
        # Analysis workflow
        await test_analyze_conversation()
        await test_get_conversation_analysis()
        await test_sentiment_timeline()
        
        # Analytics
        await test_topic_distribution()
        await test_keyword_analysis()
        await test_conversation_trends()
        
        # Intelligence
        await test_summarize_conversation()
        await test_agent_coaching()
        await test_sales_opportunities()
        
        # Security
        await test_invalid_token()
        
        print("\n" + "=" * 60)
        print("ALL TESTS COMPLETED SUCCESSFULLY")
        print("=" * 60)
        
    except Exception as e:
        print(f"\nTEST ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(run_all_tests())
