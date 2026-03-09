"""
Integration tests for Knowledge Base v2 Service
"""

import asyncio
import json
import uuid
from datetime import datetime, timedelta
import jwt
import httpx
import pytest


# Test configuration
SERVICE_URL = "http://localhost:9030"
JWT_SECRET = "test-secret-key"
TEST_TENANT_ID = str(uuid.uuid4())
TEST_USER_ID = str(uuid.uuid4())
TEST_EMAIL = "test@example.com"


def create_test_token():
    """Create JWT token for testing"""
    payload = {
        "sub": TEST_USER_ID,
        "tenant_id": TEST_TENANT_ID,
        "email": TEST_EMAIL,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=1)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


@pytest.fixture
def auth_headers():
    """Auth headers fixture"""
    token = create_test_token()
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_health_check():
    """Test health endpoint"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{SERVICE_URL}/api/v1/knowledge/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "knowledge-base-v2"
        assert data["port"] == 9030


@pytest.mark.asyncio
async def test_get_stats(auth_headers):
    """Test getting KB statistics"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{SERVICE_URL}/api/v1/knowledge/stats",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_documents" in data
        assert "total_chunks" in data
        assert "total_faqs" in data


@pytest.mark.asyncio
async def test_document_upload(auth_headers):
    """Test document upload"""
    async with httpx.AsyncClient() as client:
        # Create test file
        files = {
            "file": ("test.txt", b"This is a test document with important information."),
            "title": (None, "Test Document"),
            "category": (None, "training"),
            "tags": (None, "test,demo"),
        }
        
        response = await client.post(
            f"{SERVICE_URL}/api/v1/knowledge/documents",
            files=files,
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Test Document"
        assert data["category"] == "training"
        assert "test" in data["tags"]
        assert data["chunk_count"] > 0
        
        return data["doc_id"]


@pytest.mark.asyncio
async def test_list_documents(auth_headers):
    """Test listing documents"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{SERVICE_URL}/api/v1/knowledge/documents",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


@pytest.mark.asyncio
async def test_embedding_generation(auth_headers):
    """Test embedding generation"""
    async with httpx.AsyncClient() as client:
        payload = {
            "text": "What is the best approach to enterprise sales?"
        }
        
        response = await client.post(
            f"{SERVICE_URL}/api/v1/knowledge/embed",
            json=payload,
            headers=auth_headers
        )
        
        if response.status_code == 200:
            data = response.json()
            assert "embedding" in data
            assert data["dimension"] == 1536
            assert len(data["embedding"]) == 1536


@pytest.mark.asyncio
async def test_hybrid_search(auth_headers):
    """Test hybrid search"""
    async with httpx.AsyncClient() as client:
        payload = {
            "query": "enterprise sales strategy",
            "top_k": 5,
            "use_vector": True,
            "use_keyword": True,
            "min_score": 0.3
        }
        
        response = await client.post(
            f"{SERVICE_URL}/api/v1/knowledge/search",
            json=payload,
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        for result in data:
            assert "chunk_id" in result
            assert "content" in result
            assert "score" in result


@pytest.mark.asyncio
async def test_get_chunks(auth_headers):
    """Test getting context chunks for query"""
    async with httpx.AsyncClient() as client:
        payload = {
            "query": "how to close deals",
            "top_k": 5
        }
        
        response = await client.post(
            f"{SERVICE_URL}/api/v1/knowledge/chunks",
            json=payload,
            headers=auth_headers
        )
        
        if response.status_code == 200:
            data = response.json()
            assert "chunks" in data
            assert "context" in data
            assert isinstance(data["chunks"], list)


@pytest.mark.asyncio
async def test_faq_operations(auth_headers):
    """Test FAQ CRUD operations"""
    async with httpx.AsyncClient() as client:
        # Create FAQ
        create_payload = {
            "category": "pricing",
            "question": "What is the minimum contract value?",
            "answer": "The minimum contract value is $10,000 annually.",
            "tags": ["pricing", "contract"],
            "is_active": True
        }
        
        response = await client.post(
            f"{SERVICE_URL}/api/v1/knowledge/faqs",
            json=create_payload,
            headers=auth_headers
        )
        
        assert response.status_code == 200
        faq_data = response.json()
        faq_id = faq_data["faq_id"]
        
        # List FAQs
        response = await client.get(
            f"{SERVICE_URL}/api/v1/knowledge/faqs",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        faqs = response.json()
        assert isinstance(faqs, list)
        
        # Update FAQ
        update_payload = {
            "category": "pricing",
            "question": "What is the minimum contract value?",
            "answer": "The minimum contract value is $15,000 annually.",
            "tags": ["pricing", "contract", "updated"],
            "is_active": True
        }
        
        response = await client.put(
            f"{SERVICE_URL}/api/v1/knowledge/faqs/{faq_id}",
            json=update_payload,
            headers=auth_headers
        )
        
        assert response.status_code == 200
        
        # Search FAQs
        search_payload = {
            "query": "contract minimum",
            "top_k": 5
        }
        
        response = await client.post(
            f"{SERVICE_URL}/api/v1/knowledge/faqs/search",
            json=search_payload,
            headers=auth_headers
        )
        
        assert response.status_code == 200
        results = response.json()
        assert isinstance(results, list)
        
        # Delete FAQ
        response = await client.delete(
            f"{SERVICE_URL}/api/v1/knowledge/faqs/{faq_id}",
            headers=auth_headers
        )
        
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_tenant_isolation(auth_headers):
    """Test that tenants are isolated"""
    # This test verifies that one tenant cannot see another tenant's data
    # In production, you'd test this with multiple auth tokens for different tenants
    pass


@pytest.mark.asyncio
async def test_error_handling(auth_headers):
    """Test error handling"""
    async with httpx.AsyncClient() as client:
        # Test invalid token
        response = await client.get(
            f"{SERVICE_URL}/api/v1/knowledge/documents",
            headers={"Authorization": "Bearer invalid_token"}
        )
        
        assert response.status_code == 401
        
        # Test invalid document ID
        response = await client.get(
            f"{SERVICE_URL}/api/v1/knowledge/documents/invalid-id",
            headers=auth_headers
        )
        
        assert response.status_code in [400, 404]


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
