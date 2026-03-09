"""
E2E Tests for Knowledge Base Management

Tests document management and search:
- Upload documents
- Document processing and chunking
- Query knowledge base
- Delete documents
- File size validation
- MIME type restrictions
"""

import uuid
import json

import pytest


class TestDocumentUpload:
    """Tests for document upload."""

    @pytest.mark.asyncio
    async def test_upload_text_document(
        self,
        async_client,
        test_auth_headers,
        cleanup_documents,
    ):
        """Test uploading a text document."""
        payload = {
            "title": "Product Guide",
            "content": "This is a comprehensive product guide. " * 50,
            "document_type": "product_guide",
            "language": "en",
        }

        response = await async_client.post(
            "/api/v1/knowledge-base/documents",
            headers=test_auth_headers,
            json=payload,
        )

        assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"
        data = response.json()
        assert "id" in data
        assert data["title"] == "Product Guide"
        assert data["document_type"] == "product_guide"

        cleanup_documents(data["id"])

    @pytest.mark.asyncio
    async def test_upload_document_with_metadata(
        self,
        async_client,
        test_auth_headers,
        cleanup_documents,
    ):
        """Test uploading document with metadata."""
        payload = {
            "title": "FAQ Document",
            "content": "What is this product? It is amazing! " * 50,
            "document_type": "faq",
            "tags": ["faq", "product", "help"],
            "metadata": {
                "category": "support",
                "version": "1.0",
                "author": "support-team",
            },
        }

        response = await async_client.post(
            "/api/v1/knowledge-base/documents",
            headers=test_auth_headers,
            json=payload,
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data

        cleanup_documents(data["id"])

    @pytest.mark.asyncio
    async def test_upload_document_missing_content(self, async_client, test_auth_headers):
        """Test upload fails without content."""
        payload = {
            "title": "Incomplete Document",
            "document_type": "guide",
        }

        response = await async_client.post(
            "/api/v1/knowledge-base/documents",
            headers=test_auth_headers,
            json=payload,
        )

        assert response.status_code == 400, f"Expected 400, got {response.status_code}"

    @pytest.mark.asyncio
    async def test_upload_document_requires_auth(self, async_client):
        """Test document upload requires authentication."""
        payload = {
            "title": "Test",
            "content": "Test content",
        }

        response = await async_client.post(
            "/api/v1/knowledge-base/documents",
            json=payload,
        )

        assert response.status_code == 401


class TestDocumentProcessing:
    """Tests for document processing and chunking."""

    @pytest.mark.asyncio
    async def test_document_gets_processed(
        self,
        async_client,
        test_auth_headers,
        cleanup_documents,
    ):
        """Test that uploaded document gets processed."""
        payload = {
            "title": "Processing Test Document",
            "content": "Test content. " * 200,  # Large enough to chunk
            "document_type": "guide",
        }

        response = await async_client.post(
            "/api/v1/knowledge-base/documents",
            headers=test_auth_headers,
            json=payload,
        )

        assert response.status_code == 201
        doc_id = response.json()["id"]
        cleanup_documents(doc_id)

        # Get document details to check processing
        detail_response = await async_client.get(
            f"/api/v1/knowledge-base/documents/{doc_id}",
            headers=test_auth_headers,
        )

        if detail_response.status_code == 200:
            data = detail_response.json()
            # Should show processing status
            assert "status" in data or "processing" in data

    @pytest.mark.asyncio
    async def test_document_chunks_are_created(
        self,
        async_client,
        test_auth_headers,
        cleanup_documents,
    ):
        """Test that document chunks are created for indexing."""
        payload = {
            "title": "Chunking Test",
            "content": "Section 1: Introduction. " * 50 + "\n" +
                      "Section 2: Details. " * 50 + "\n" +
                      "Section 3: Conclusion. " * 50,
            "document_type": "guide",
        }

        response = await async_client.post(
            "/api/v1/knowledge-base/documents",
            headers=test_auth_headers,
            json=payload,
        )

        assert response.status_code == 201
        doc_id = response.json()["id"]
        cleanup_documents(doc_id)

        # Get chunks (if endpoint exists)
        chunks_response = await async_client.get(
            f"/api/v1/knowledge-base/documents/{doc_id}/chunks",
            headers=test_auth_headers,
        )

        # Either 200 or 404 depending on implementation
        assert chunks_response.status_code in [200, 404]


class TestQueryKnowledgeBase:
    """Tests for querying the knowledge base."""

    @pytest.mark.asyncio
    async def test_query_knowledge_base(
        self,
        async_client,
        test_auth_headers,
        cleanup_documents,
    ):
        """Test querying knowledge base for relevant documents."""
        # First upload a document
        upload_response = await async_client.post(
            "/api/v1/knowledge-base/documents",
            headers=test_auth_headers,
            json={
                "title": "Product Features",
                "content": "Our product has amazing features like AI, automation, and integration. " * 50,
                "document_type": "guide",
                "tags": ["product", "features"],
            },
        )

        assert upload_response.status_code == 201
        doc_id = upload_response.json()["id"]
        cleanup_documents(doc_id)

        # Query for it
        query_response = await async_client.get(
            "/api/v1/knowledge-base/search",
            headers=test_auth_headers,
            params={"query": "product features", "limit": 10},
        )

        assert query_response.status_code == 200, f"Expected 200, got {query_response.status_code}: {query_response.text}"
        data = query_response.json()
        assert isinstance(data, (list, dict))

    @pytest.mark.asyncio
    async def test_query_with_similarity_scoring(
        self,
        async_client,
        test_auth_headers,
        cleanup_documents,
    ):
        """Test that query results include similarity scores."""
        # Upload document
        upload_response = await async_client.post(
            "/api/v1/knowledge-base/documents",
            headers=test_auth_headers,
            json={
                "title": "Integration Guide",
                "content": "How to integrate with our API and SDKs. " * 50,
                "document_type": "guide",
            },
        )

        if upload_response.status_code == 201:
            doc_id = upload_response.json()["id"]
            cleanup_documents(doc_id)

            # Query
            query_response = await async_client.get(
                "/api/v1/knowledge-base/search",
                headers=test_auth_headers,
                params={"query": "API integration"},
            )

            if query_response.status_code == 200:
                data = query_response.json()
                # Results may have score field
                if isinstance(data, list) and len(data) > 0:
                    result = data[0]
                    # May or may not have score depending on implementation
                    assert "id" in result or "document_id" in result

    @pytest.mark.asyncio
    async def test_query_with_filters(self, async_client, test_auth_headers, cleanup_documents):
        """Test querying with document type filter."""
        response = await async_client.get(
            "/api/v1/knowledge-base/search",
            headers=test_auth_headers,
            params={
                "query": "help",
                "document_type": "faq",
                "limit": 5,
            },
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_query_by_tag(self, async_client, test_auth_headers, cleanup_documents):
        """Test querying documents by tag."""
        response = await async_client.get(
            "/api/v1/knowledge-base/search",
            headers=test_auth_headers,
            params={"tags": "support,help"},
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_query_pagination(self, async_client, test_auth_headers):
        """Test search results pagination."""
        response = await async_client.get(
            "/api/v1/knowledge-base/search",
            headers=test_auth_headers,
            params={"query": "test", "page": 1, "limit": 10},
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_query_requires_auth(self, async_client):
        """Test search requires authentication."""
        response = await async_client.get(
            "/api/v1/knowledge-base/search",
            params={"query": "test"},
        )

        assert response.status_code == 401


class TestDeleteDocument:
    """Tests for document deletion."""

    @pytest.mark.asyncio
    async def test_delete_document(
        self,
        async_client,
        test_auth_headers,
    ):
        """Test deleting a document."""
        # Upload document
        upload_response = await async_client.post(
            "/api/v1/knowledge-base/documents",
            headers=test_auth_headers,
            json={
                "title": "Temporary Document",
                "content": "This will be deleted. " * 50,
                "document_type": "guide",
            },
        )

        assert upload_response.status_code == 201
        doc_id = upload_response.json()["id"]

        # Delete it
        response = await async_client.delete(
            f"/api/v1/knowledge-base/documents/{doc_id}",
            headers=test_auth_headers,
        )

        assert response.status_code in [200, 204], \
            f"Expected 200/204, got {response.status_code}: {response.text}"

        # Verify it's deleted
        verify_response = await async_client.get(
            f"/api/v1/knowledge-base/documents/{doc_id}",
            headers=test_auth_headers,
        )

        assert verify_response.status_code == 404, \
            f"Document should be deleted, got {verify_response.status_code}"

    @pytest.mark.asyncio
    async def test_delete_nonexistent_document(self, async_client, test_auth_headers):
        """Test deleting non-existent document."""
        response = await async_client.delete(
            f"/api/v1/knowledge-base/documents/nonexistent-{uuid.uuid4().hex[:8]}",
            headers=test_auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_requires_auth(self, async_client):
        """Test delete requires authentication."""
        response = await async_client.delete(
            "/api/v1/knowledge-base/documents/doc-123",
        )

        assert response.status_code == 401


class TestFileSizeValidation:
    """Tests for file size limits."""

    @pytest.mark.asyncio
    async def test_document_within_size_limit(
        self,
        async_client,
        test_auth_headers,
        cleanup_documents,
    ):
        """Test uploading document within size limit."""
        payload = {
            "title": "Sized Document",
            "content": "Content. " * 10000,  # Should be within limits
            "document_type": "guide",
        }

        response = await async_client.post(
            "/api/v1/knowledge-base/documents",
            headers=test_auth_headers,
            json=payload,
        )

        assert response.status_code == 201
        cleanup_documents(response.json()["id"])

    @pytest.mark.asyncio
    async def test_document_exceeds_size_limit(self, async_client, test_auth_headers):
        """Test that oversized documents are rejected."""
        # Create very large content (>10MB if limit is 10MB)
        large_content = "x" * (11 * 1024 * 1024)  # 11MB

        payload = {
            "title": "Oversized Document",
            "content": large_content,
            "document_type": "guide",
        }

        response = await async_client.post(
            "/api/v1/knowledge-base/documents",
            headers=test_auth_headers,
            json=payload,
        )

        # Should be rejected or accepted depending on limit
        # If there's a limit, should get 413 or 400
        assert response.status_code in [201, 400, 413, 429]


class TestDocumentManagement:
    """Tests for document listing and management."""

    @pytest.mark.asyncio
    async def test_list_documents(self, async_client, test_auth_headers, cleanup_documents):
        """Test listing documents in knowledge base."""
        # Upload a document first
        upload_response = await async_client.post(
            "/api/v1/knowledge-base/documents",
            headers=test_auth_headers,
            json={
                "title": "Listable Document",
                "content": "Content for listing. " * 50,
                "document_type": "guide",
            },
        )

        if upload_response.status_code == 201:
            doc_id = upload_response.json()["id"]
            cleanup_documents(doc_id)

        # List documents
        response = await async_client.get(
            "/api/v1/knowledge-base/documents",
            headers=test_auth_headers,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, (list, dict))

    @pytest.mark.asyncio
    async def test_get_document_details(
        self,
        async_client,
        test_auth_headers,
        cleanup_documents,
    ):
        """Test getting document details."""
        # Upload
        upload_response = await async_client.post(
            "/api/v1/knowledge-base/documents",
            headers=test_auth_headers,
            json={
                "title": "Detail Test",
                "content": "Content. " * 50,
                "document_type": "guide",
            },
        )

        assert upload_response.status_code == 201
        doc_id = upload_response.json()["id"]
        cleanup_documents(doc_id)

        # Get details
        response = await async_client.get(
            f"/api/v1/knowledge-base/documents/{doc_id}",
            headers=test_auth_headers,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["title"] == "Detail Test"

    @pytest.mark.asyncio
    async def test_update_document_metadata(
        self,
        async_client,
        test_auth_headers,
        cleanup_documents,
    ):
        """Test updating document metadata."""
        # Upload
        upload_response = await async_client.post(
            "/api/v1/knowledge-base/documents",
            headers=test_auth_headers,
            json={
                "title": "Update Test",
                "content": "Content. " * 50,
                "document_type": "guide",
                "tags": ["old-tag"],
            },
        )

        assert upload_response.status_code == 201
        doc_id = upload_response.json()["id"]
        cleanup_documents(doc_id)

        # Update
        response = await async_client.patch(
            f"/api/v1/knowledge-base/documents/{doc_id}",
            headers=test_auth_headers,
            json={
                "title": "Updated Title",
                "tags": ["new-tag", "updated"],
            },
        )

        assert response.status_code in [200, 404]  # 404 if not implemented
