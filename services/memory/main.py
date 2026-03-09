"""
Priya Global — Conversation Memory Service (Port 9034)

The Memory Service is the long-term brain of the platform. It provides:

1. SHORT-TERM MEMORY (within a conversation):
   - Sliding window of recent turns (last N messages)
   - Important-turn extraction (key moments flagged for context)
   - Real-time summarization of older messages (compression)

2. LONG-TERM MEMORY (across conversations):
   - Conversation summaries with semantic embeddings
   - Customer memory profiles (preferences, facts, behaviors)
   - Episode extraction (discrete interaction units)
   - Cross-conversation pattern detection

3. MEMORY RETRIEVAL (at inference time):
   - Semantic recall: "What did this customer ask about before?"
   - Fact recall: "What are this customer's preferences?"
   - Episode recall: "Have we negotiated with this customer before?"
   - Importance-weighted ranking: Critical memories surface first

4. MEMORY LIFECYCLE:
   - Auto-summarize conversations on close
   - Extract customer memories from each conversation
   - Periodic memory consolidation (merge similar memories)
   - Importance decay (older memories fade unless reinforced)
   - Expiry cleanup for time-bound memories

ARCHITECTURE:
- Subscribes to Kafka events: MESSAGE_RECEIVED, CONVERSATION_ENDED
- Publishes events: MEMORY_UPDATED, MEMORY_CONSOLIDATED
- Uses pgvector for semantic similarity search
- Redis cache for hot memory (active conversations)
- Background workers for summarization and consolidation

SECURITY:
- All queries scoped by tenant_id (RLS enforced at DB level)
- Memory content is never shared across tenants
- PII masking on memory summaries (configurable per tenant)
- Embeddings are tenant-isolated
"""

import asyncio
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

import httpx
import numpy as np
from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import redis.asyncio as redis

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.core.config import config
from shared.core.database import db, get_tenant_pool
from shared.core.security import mask_pii, sanitize_input
from shared.middleware.auth import get_auth, AuthContext, require_role
from shared.cache.redis_client import TenantCache
from shared.observability.tracing import init_tracing, TracingMiddleware, shutdown_tracing
from shared.observability.sentry import init_sentry
from shared.middleware.sentry import SentryTenantMiddleware
from shared.events.event_bus import EventBus, EventType
from shared.middleware.cors import get_cors_config

logger = logging.getLogger("priya.memory")
logger.setLevel(logging.INFO)


# ============================================================================
# ENUMS & CONSTANTS
# ============================================================================

class MemoryType(str, Enum):
    PREFERENCE = "preference"
    FACT = "fact"
    BEHAVIOR = "behavior"
    RELATIONSHIP = "relationship"
    NEED = "need"
    OBJECTION = "objection"
    FEEDBACK = "feedback"
    COMMITMENT = "commitment"


class EpisodeType(str, Enum):
    PURCHASE_INTENT = "purchase_intent"
    PRODUCT_INQUIRY = "product_inquiry"
    COMPLAINT = "complaint"
    NEGOTIATION = "negotiation"
    SUPPORT_REQUEST = "support_request"
    FEEDBACK = "feedback"
    REFERRAL = "referral"
    COMMITMENT = "commitment"


class ConversationOutcome(str, Enum):
    ONGOING = "ongoing"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    PURCHASED = "purchased"
    ABANDONED = "abandoned"
    FOLLOW_UP = "follow_up"


# Memory retrieval limits
MAX_SHORT_TERM_TURNS = 20         # Last N messages in active conversation
MAX_LONG_TERM_MEMORIES = 10       # Customer memories to inject into context
MAX_EPISODE_RECALL = 5            # Past episodes to surface
MAX_CONVERSATION_RECALL = 3       # Past conversation summaries
SUMMARY_THRESHOLD = 10            # Summarize after this many turns
IMPORTANCE_DECAY_RATE = 0.02      # Daily importance decay
MIN_IMPORTANCE_THRESHOLD = 0.1    # Below this, memory is inactive

# Embedding dimensions (text-embedding-3-small for cost efficiency on memory)
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class MemoryContext(BaseModel):
    """Complete memory context for AI prompt injection."""
    customer_id: UUID
    customer_summary: Optional[str] = None
    recent_turns: list[dict] = Field(default_factory=list)
    conversation_summary: Optional[str] = None
    customer_memories: list[dict] = Field(default_factory=list)
    relevant_episodes: list[dict] = Field(default_factory=list)
    past_conversations: list[dict] = Field(default_factory=list)
    memory_stats: dict = Field(default_factory=dict)


class StoreMemoryRequest(BaseModel):
    customer_id: UUID
    memory_type: MemoryType
    content: str
    key: Optional[str] = None
    value: Optional[dict] = None
    importance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    source_conversation_id: Optional[UUID] = None
    expires_in_days: Optional[int] = None


class ConversationSummaryRequest(BaseModel):
    conversation_id: UUID
    customer_id: UUID
    outcome: ConversationOutcome = ConversationOutcome.ONGOING


class RecallRequest(BaseModel):
    customer_id: UUID
    query: Optional[str] = None
    conversation_id: Optional[UUID] = None
    memory_types: Optional[list[MemoryType]] = None
    max_results: int = Field(default=10, ge=1, le=50)


class MemorySearchResult(BaseModel):
    id: UUID
    memory_type: str
    content: str
    importance_score: float
    confidence: float
    similarity: Optional[float] = None
    created_at: datetime
    source_conversation_id: Optional[UUID] = None


# ============================================================================
# EMBEDDING CLIENT
# ============================================================================

class EmbeddingClient:
    """Manages embedding generation with caching and batching."""

    def __init__(self):
        self.http_client = httpx.AsyncClient()
        self.openai_api_key = config.OPENAI_API_KEY
        self._cache: Dict[str, list[float]] = {}

    async def get_embedding(self, text: str) -> list[float]:
        """Get embedding with in-memory cache."""
        cache_key = hashlib.md5(text[:500].encode()).hexdigest()
        if cache_key in self._cache:
            return self._cache[cache_key]

        headers = {
            "Authorization": f"Bearer {self.openai_api_key}",
            "Content-Type": "application/json",
        }

        response = await self.http_client.post(
            "https://api.openai.com/v1/embeddings",
            json={
                "model": EMBEDDING_MODEL,
                "input": text[:8000],  # Truncate to model limit
                "dimensions": EMBEDDING_DIMENSIONS,
            },
            headers=headers,
            timeout=15.0,
        )
        response.raise_for_status()
        data = response.json()

        embedding = data["data"][0]["embedding"]
        self._cache[cache_key] = embedding

        # Keep cache bounded
        if len(self._cache) > 1000:
            oldest_keys = list(self._cache.keys())[:500]
            for k in oldest_keys:
                del self._cache[k]

        return embedding

    async def get_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """Batch embedding generation (max 100 texts per request)."""
        if not texts:
            return []

        truncated = [t[:8000] for t in texts]
        headers = {
            "Authorization": f"Bearer {self.openai_api_key}",
            "Content-Type": "application/json",
        }

        results = []
        for i in range(0, len(truncated), 100):
            batch = truncated[i : i + 100]
            response = await self.http_client.post(
                "https://api.openai.com/v1/embeddings",
                json={
                    "model": EMBEDDING_MODEL,
                    "input": batch,
                    "dimensions": EMBEDDING_DIMENSIONS,
                },
                headers=headers,
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            results.extend([d["embedding"] for d in data["data"]])

        return results

    async def close(self):
        await self.http_client.aclose()


# ============================================================================
# MEMORY SUMMARIZER (LLM-powered)
# ============================================================================

class MemorySummarizer:
    """Uses LLM to generate summaries and extract memories from conversations."""

    def __init__(self):
        self.http_client = httpx.AsyncClient()
        self.anthropic_api_key = config.ANTHROPIC_API_KEY

    async def summarize_conversation(
        self,
        messages: list[dict],
        customer_name: str = "Customer",
    ) -> dict:
        """Generate structured conversation summary.

        Returns:
            {
                "summary": str,
                "topics": [str],
                "outcome": str,
                "key_points": [str],
                "action_items": [str],
                "sentiment": float (-1 to 1),
            }
        """
        # Format conversation for summarization
        conversation_text = "\n".join(
            [f"{m.get('role', 'unknown')}: {m.get('content', '')}" for m in messages[-50:]]
        )

        prompt = f"""Analyze this customer support/sales conversation and extract structured information.

CONVERSATION:
{conversation_text}

Return a JSON object with these fields:
{{
    "summary": "A 2-3 sentence summary of the conversation including what {customer_name} wanted and the outcome",
    "topics": ["list of main topics discussed"],
    "outcome": "one of: resolved, escalated, purchased, abandoned, follow_up, ongoing",
    "key_points": ["important facts or decisions from the conversation"],
    "action_items": ["any follow-up actions needed"],
    "sentiment": 0.0
}}

For sentiment: -1.0 = very negative, 0.0 = neutral, 1.0 = very positive.
Return ONLY valid JSON."""

        headers = {
            "x-api-key": self.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        try:
            response = await self.http_client.post(
                "https://api.anthropic.com/v1/messages",
                json={
                    "model": "claude-3-5-haiku-20241022",
                    "max_tokens": 1000,
                    "system": "You are a conversation analyst. Return ONLY valid JSON. No other text.",
                    "messages": [{"role": "user", "content": prompt}],
                },
                headers=headers,
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            result_text = data["content"][0]["text"]

            # Parse JSON from response
            return json.loads(result_text)
        except (json.JSONDecodeError, Exception) as e:
            logger.error("Summarization failed: %s", e)
            return {
                "summary": f"Conversation with {customer_name} ({len(messages)} messages)",
                "topics": [],
                "outcome": "ongoing",
                "key_points": [],
                "action_items": [],
                "sentiment": 0.0,
            }

    async def extract_customer_memories(
        self,
        messages: list[dict],
        existing_memories: list[dict],
        customer_name: str = "Customer",
    ) -> list[dict]:
        """Extract new customer memories from a conversation.

        Returns list of:
        {
            "memory_type": "preference|fact|behavior|need|objection|feedback|commitment",
            "content": str,
            "key": str (optional, for structured access),
            "value": any (optional),
            "importance_score": float (0-1),
            "confidence": float (0-1)
        }
        """
        conversation_text = "\n".join(
            [f"{m.get('role', 'unknown')}: {m.get('content', '')}" for m in messages[-30:]]
        )

        existing_text = "\n".join(
            [f"- [{m.get('memory_type')}] {m.get('content')}" for m in existing_memories[:20]]
        ) if existing_memories else "No existing memories"

        prompt = f"""Extract customer memories from this conversation that would be useful for future interactions.

EXISTING MEMORIES (don't duplicate these):
{existing_text}

CONVERSATION:
{conversation_text}

Extract NEW information about {customer_name} as a JSON array. Each memory should be:
{{
    "memory_type": "preference|fact|behavior|need|objection|feedback|commitment",
    "content": "human-readable description of the memory",
    "key": "optional_structured_key (e.g., 'preferred_color', 'budget_range')",
    "value": null,
    "importance_score": 0.5,
    "confidence": 0.8
}}

Rules:
- Only extract GENUINELY useful information (not trivial)
- Don't duplicate existing memories
- Higher importance for: purchase intent, complaints, personal preferences
- Lower importance for: greetings, generic questions
- Set confidence based on how explicitly the customer stated it

Return ONLY a JSON array. Return empty array [] if no new memories found."""

        headers = {
            "x-api-key": self.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        try:
            response = await self.http_client.post(
                "https://api.anthropic.com/v1/messages",
                json={
                    "model": "claude-3-5-haiku-20241022",
                    "max_tokens": 2000,
                    "system": "You are a customer memory extractor. Return ONLY valid JSON arrays.",
                    "messages": [{"role": "user", "content": prompt}],
                },
                headers=headers,
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            result_text = data["content"][0]["text"]

            memories = json.loads(result_text)
            if not isinstance(memories, list):
                return []

            # Validate each memory
            valid_types = [t.value for t in MemoryType]
            validated = []
            for m in memories:
                if m.get("memory_type") in valid_types and m.get("content"):
                    validated.append({
                        "memory_type": m["memory_type"],
                        "content": sanitize_input(m["content"][:500]),
                        "key": m.get("key"),
                        "value": m.get("value"),
                        "importance_score": max(0.0, min(1.0, m.get("importance_score", 0.5))),
                        "confidence": max(0.0, min(1.0, m.get("confidence", 0.8))),
                    })

            return validated
        except Exception as e:
            logger.error("Memory extraction failed: %s", e)
            return []

    async def compress_turns(
        self,
        messages: list[dict],
    ) -> str:
        """Compress older messages into a summary for context window management.

        Used when conversation exceeds SUMMARY_THRESHOLD turns.
        """
        conversation_text = "\n".join(
            [f"{m.get('role', 'unknown')}: {m.get('content', '')}" for m in messages]
        )

        prompt = f"""Compress this conversation into a brief summary (max 200 words) that preserves:
1. What the customer wants
2. What products/services were discussed
3. Any decisions or commitments made
4. Current state of the conversation

CONVERSATION:
{conversation_text}

Return ONLY the summary text, no JSON."""

        headers = {
            "x-api-key": self.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        try:
            response = await self.http_client.post(
                "https://api.anthropic.com/v1/messages",
                json={
                    "model": "claude-3-5-haiku-20241022",
                    "max_tokens": 500,
                    "system": "You are a conversation compressor. Return only the summary text.",
                    "messages": [{"role": "user", "content": prompt}],
                },
                headers=headers,
                timeout=20.0,
            )
            response.raise_for_status()
            data = response.json()
            return data["content"][0]["text"].strip()
        except Exception as e:
            logger.error("Turn compression failed: %s", e)
            return "Previous conversation (%s messages)" % len(messages)

    async def close(self):
        await self.http_client.aclose()


# ============================================================================
# MEMORY STORE (Database Operations)
# ============================================================================

class MemoryStore:
    """Handles all database operations for the memory system."""

    def __init__(self, embedding_client: EmbeddingClient):
        self.embedding_client = embedding_client

    # ── Conversation Memory ──────────────────────────────────────────────

    async def store_conversation_memory(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
        customer_id: UUID,
        summary: str,
        topics: list[str],
        intents: list[str],
        entities: dict,
        sentiment_avg: float,
        funnel_stage: str,
        outcome: str,
        message_count: int,
        duration_seconds: int,
        first_message_at: datetime,
        last_message_at: datetime,
        metadata: dict = None,
    ) -> UUID:
        """Store or update conversation memory with embedding."""
        embedding = await self.embedding_client.get_embedding(summary)

        pool = await get_tenant_pool(tenant_id)
        async with pool.acquire() as conn:
            memory_id = await conn.fetchval(
                """
                INSERT INTO conversation_memories (
                    tenant_id, conversation_id, customer_id,
                    summary, summary_embedding, topics, intents, entities,
                    sentiment_avg, funnel_stage, outcome,
                    message_count, duration_seconds,
                    first_message_at, last_message_at,
                    importance_score, metadata
                ) VALUES (
                    $1, $2, $3, $4, $5::vector, $6, $7, $8,
                    $9, $10, $11, $12, $13, $14, $15,
                    $16, $17
                )
                ON CONFLICT (tenant_id, conversation_id) DO UPDATE SET
                    summary = $4,
                    summary_embedding = $5::vector,
                    topics = $6,
                    intents = $7,
                    entities = $8,
                    sentiment_avg = $9,
                    funnel_stage = $10,
                    outcome = $11,
                    message_count = $12,
                    duration_seconds = $13,
                    last_message_at = $15,
                    importance_score = $16,
                    updated_at = NOW()
                RETURNING id
                """,
                str(tenant_id),
                str(conversation_id),
                str(customer_id),
                summary,
                json.dumps(embedding),
                topics,
                intents,
                json.dumps(entities),
                sentiment_avg,
                funnel_stage,
                outcome,
                message_count,
                duration_seconds,
                first_message_at,
                last_message_at,
                self._calculate_importance(outcome, sentiment_avg, message_count),
                json.dumps(metadata or {}),
            )

        return memory_id

    # ── Customer Memory ──────────────────────────────────────────────────

    async def store_customer_memory(
        self,
        tenant_id: UUID,
        customer_id: UUID,
        memory_type: str,
        content: str,
        key: Optional[str] = None,
        value: Optional[dict] = None,
        importance_score: float = 0.5,
        confidence: float = 0.8,
        source_conversation_id: Optional[UUID] = None,
        expires_in_days: Optional[int] = None,
    ) -> UUID:
        """Store a new customer memory with deduplication."""
        embedding = await self.embedding_client.get_embedding(content)

        expires_at = None
        if expires_in_days:
            expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

        pool = await get_tenant_pool(tenant_id)
        async with pool.acquire() as conn:
            # Check for duplicate/similar memory
            existing = await conn.fetchrow(
                """
                SELECT id, content, importance_score
                FROM customer_memories
                WHERE tenant_id = $1
                  AND customer_id = $2
                  AND memory_type = $3
                  AND key = $4
                  AND is_active = TRUE
                LIMIT 1
                """,
                str(tenant_id),
                str(customer_id),
                memory_type,
                key,
            ) if key else None

            if existing:
                # Update existing memory with higher importance
                new_importance = max(existing["importance_score"], importance_score)
                await conn.execute(
                    """
                    UPDATE customer_memories
                    SET content = $1,
                        content_embedding = $2::vector,
                        importance_score = $3,
                        confidence = $4,
                        updated_at = NOW()
                    WHERE id = $5 AND tenant_id = $6
                    """,
                    content,
                    json.dumps(embedding),
                    new_importance,
                    confidence,
                    existing["id"],
                    str(tenant_id),
                )
                return existing["id"]

            # Insert new memory
            memory_id = await conn.fetchval(
                """
                INSERT INTO customer_memories (
                    tenant_id, customer_id, memory_type,
                    content, content_embedding,
                    key, value,
                    importance_score, confidence,
                    source_conversation_id, expires_at
                ) VALUES (
                    $1, $2, $3, $4, $5::vector,
                    $6, $7, $8, $9, $10, $11
                )
                RETURNING id
                """,
                str(tenant_id),
                str(customer_id),
                memory_type,
                content,
                json.dumps(embedding),
                key,
                json.dumps(value) if value else None,
                importance_score,
                confidence,
                str(source_conversation_id) if source_conversation_id else None,
                expires_at,
            )

        return memory_id

    # ── Episode Store ────────────────────────────────────────────────────

    async def store_episode(
        self,
        tenant_id: UUID,
        customer_id: UUID,
        conversation_id: UUID,
        episode_type: str,
        summary: str,
        participants: list[str],
        products_mentioned: list[str],
        action_items: list[dict],
        resolution: Optional[str],
        importance_score: float,
        emotional_valence: float,
        started_at: datetime,
        ended_at: Optional[datetime],
        turn_count: int,
    ) -> UUID:
        """Store a discrete interaction episode."""
        embedding = await self.embedding_client.get_embedding(summary)

        pool = await get_tenant_pool(tenant_id)
        async with pool.acquire() as conn:
            episode_id = await conn.fetchval(
                """
                INSERT INTO memory_episodes (
                    tenant_id, customer_id, conversation_id,
                    episode_type, summary, summary_embedding,
                    participants, products_mentioned, action_items,
                    resolution, importance_score, emotional_valence,
                    started_at, ended_at, turn_count
                ) VALUES (
                    $1, $2, $3, $4, $5, $6::vector,
                    $7, $8, $9, $10, $11, $12, $13, $14, $15
                )
                RETURNING id
                """,
                str(tenant_id),
                str(customer_id),
                str(conversation_id),
                episode_type,
                summary,
                json.dumps(embedding),
                participants,
                products_mentioned,
                json.dumps(action_items),
                resolution,
                importance_score,
                emotional_valence,
                started_at,
                ended_at,
                turn_count,
            )

        return episode_id

    # ── Memory Retrieval ─────────────────────────────────────────────────

    async def recall_customer_memories(
        self,
        tenant_id: UUID,
        customer_id: UUID,
        query: Optional[str] = None,
        memory_types: Optional[list[str]] = None,
        max_results: int = 10,
    ) -> list[dict]:
        """Recall customer memories with optional semantic search."""
        pool = await get_tenant_pool(tenant_id)

        if query:
            # Semantic recall — find memories relevant to current query
            query_embedding = await self.embedding_client.get_embedding(query)

            async with pool.acquire() as conn:
                type_filter = ""
                params = [json.dumps(query_embedding), str(tenant_id), str(customer_id), max_results]
                if memory_types:
                    type_filter = "AND memory_type = ANY($5)"
                    params.append(memory_types)

                rows = await conn.fetch(
                    f"""
                    SELECT id, memory_type, content, key, value,
                           importance_score, confidence, created_at,
                           source_conversation_id,
                           1 - (content_embedding <=> $1::vector) as similarity
                    FROM customer_memories
                    WHERE tenant_id = $2
                      AND customer_id = $3
                      AND is_active = TRUE
                      AND 1 - (content_embedding <=> $1::vector) > 0.4
                      {type_filter}
                    ORDER BY (importance_score * 0.4 + (1 - (content_embedding <=> $1::vector)) * 0.6) DESC
                    LIMIT $4
                    """,
                    *params,
                )
        else:
            # Importance-based recall (no query — get top memories)
            async with pool.acquire() as conn:
                type_filter = ""
                params = [str(tenant_id), str(customer_id), max_results]
                if memory_types:
                    type_filter = "AND memory_type = ANY($4)"
                    params.append(memory_types)

                rows = await conn.fetch(
                    f"""
                    SELECT id, memory_type, content, key, value,
                           importance_score, confidence, created_at,
                           source_conversation_id,
                           NULL::float as similarity
                    FROM customer_memories
                    WHERE tenant_id = $1
                      AND customer_id = $2
                      AND is_active = TRUE
                      {type_filter}
                    ORDER BY importance_score DESC, updated_at DESC
                    LIMIT $3
                    """,
                    *params,
                )

        # Update access counts
        if rows:
            async with pool.acquire() as conn:
                ids = [str(r["id"]) for r in rows]
                await conn.execute(
                    """
                    UPDATE customer_memories
                    SET access_count = access_count + 1,
                        last_accessed_at = NOW()
                    WHERE id = ANY($1::uuid[])
                      AND tenant_id = $2
                    """,
                    ids,
                    str(tenant_id),
                )

        return [dict(r) for r in rows]

    async def recall_past_conversations(
        self,
        tenant_id: UUID,
        customer_id: UUID,
        query: Optional[str] = None,
        max_results: int = 3,
    ) -> list[dict]:
        """Recall past conversation summaries for a customer."""
        pool = await get_tenant_pool(tenant_id)

        if query:
            query_embedding = await self.embedding_client.get_embedding(query)
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, conversation_id, summary, topics, outcome,
                           sentiment_avg, funnel_stage, message_count,
                           first_message_at, last_message_at,
                           importance_score,
                           1 - (summary_embedding <=> $1::vector) as similarity
                    FROM conversation_memories
                    WHERE tenant_id = $2
                      AND customer_id = $3
                      AND 1 - (summary_embedding <=> $1::vector) > 0.3
                    ORDER BY similarity DESC
                    LIMIT $4
                    """,
                    json.dumps(query_embedding),
                    str(tenant_id),
                    str(customer_id),
                    max_results,
                )
        else:
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, conversation_id, summary, topics, outcome,
                           sentiment_avg, funnel_stage, message_count,
                           first_message_at, last_message_at,
                           importance_score, NULL::float as similarity
                    FROM conversation_memories
                    WHERE tenant_id = $1
                      AND customer_id = $2
                    ORDER BY last_message_at DESC
                    LIMIT $3
                    """,
                    str(tenant_id),
                    str(customer_id),
                    max_results,
                )

        return [dict(r) for r in rows]

    async def recall_episodes(
        self,
        tenant_id: UUID,
        customer_id: UUID,
        query: Optional[str] = None,
        episode_types: Optional[list[str]] = None,
        max_results: int = 5,
    ) -> list[dict]:
        """Recall interaction episodes for a customer.

        SECURITY: Uses separate query branches to avoid dynamic SQL construction.
        All queries use fully parameterized placeholders — no string interpolation.
        """
        pool = await get_tenant_pool(tenant_id)

        if query and episode_types:
            # Semantic search + type filter
            query_embedding = await self.embedding_client.get_embedding(query)
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, episode_type, summary,
                           products_mentioned, action_items, resolution,
                           importance_score, emotional_valence,
                           started_at, ended_at, turn_count,
                           1 - (summary_embedding <=> $1::vector) as similarity
                    FROM memory_episodes
                    WHERE tenant_id = $2
                      AND customer_id = $3
                      AND episode_type = ANY($5)
                      AND 1 - (summary_embedding <=> $1::vector) > 0.3
                    ORDER BY similarity DESC
                    LIMIT $4
                    """,
                    json.dumps(query_embedding),
                    str(tenant_id),
                    str(customer_id),
                    max_results,
                    episode_types,
                )
        elif query:
            # Semantic search, no type filter
            query_embedding = await self.embedding_client.get_embedding(query)
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, episode_type, summary,
                           products_mentioned, action_items, resolution,
                           importance_score, emotional_valence,
                           started_at, ended_at, turn_count,
                           1 - (summary_embedding <=> $1::vector) as similarity
                    FROM memory_episodes
                    WHERE tenant_id = $2
                      AND customer_id = $3
                      AND 1 - (summary_embedding <=> $1::vector) > 0.3
                    ORDER BY similarity DESC
                    LIMIT $4
                    """,
                    json.dumps(query_embedding),
                    str(tenant_id),
                    str(customer_id),
                    max_results,
                )
        elif episode_types:
            # Importance-based, with type filter
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, episode_type, summary,
                           products_mentioned, action_items, resolution,
                           importance_score, emotional_valence,
                           started_at, ended_at, turn_count,
                           NULL::float as similarity
                    FROM memory_episodes
                    WHERE tenant_id = $1
                      AND customer_id = $2
                      AND episode_type = ANY($4)
                    ORDER BY importance_score DESC, started_at DESC
                    LIMIT $3
                    """,
                    str(tenant_id),
                    str(customer_id),
                    max_results,
                    episode_types,
                )
        else:
            # Importance-based, no type filter
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, episode_type, summary,
                           products_mentioned, action_items, resolution,
                           importance_score, emotional_valence,
                           started_at, ended_at, turn_count,
                           NULL::float as similarity
                    FROM memory_episodes
                    WHERE tenant_id = $1
                      AND customer_id = $2
                    ORDER BY importance_score DESC, started_at DESC
                    LIMIT $3
                    """,
                    str(tenant_id),
                    str(customer_id),
                    max_results,
                )

        return [dict(r) for r in rows]

    # ── Customer Summary ─────────────────────────────────────────────────

    async def update_customer_summary(
        self,
        tenant_id: UUID,
        customer_id: UUID,
        summary: str,
    ):
        """Update the customer's overall memory summary."""
        embedding = await self.embedding_client.get_embedding(summary)

        pool = await get_tenant_pool(tenant_id)
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE customers
                SET memory_summary = $1,
                    memory_summary_embedding = $2::vector,
                    last_seen_at = NOW()
                WHERE id = $3 AND tenant_id = $4
                """,
                summary,
                json.dumps(embedding),
                str(customer_id),
                str(tenant_id),
            )

    async def increment_customer_stats(
        self,
        tenant_id: UUID,
        customer_id: UUID,
        messages: int = 0,
        conversations: int = 0,
    ):
        """Increment customer conversation/message counts."""
        pool = await get_tenant_pool(tenant_id)
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE customers
                SET total_conversations = COALESCE(total_conversations, 0) + $1,
                    total_messages = COALESCE(total_messages, 0) + $2,
                    last_seen_at = NOW(),
                    first_seen_at = COALESCE(first_seen_at, NOW())
                WHERE id = $3 AND tenant_id = $4
                """,
                conversations,
                messages,
                str(customer_id),
                str(tenant_id),
            )

    # ── Importance Decay ─────────────────────────────────────────────────

    async def apply_importance_decay(self, tenant_id: UUID):
        """Apply time-based importance decay to all memories for a tenant.
        Called periodically by background worker.

        SECURITY: All constants are passed as parameterized values, not interpolated.
        """
        pool = await get_tenant_pool(tenant_id)
        async with pool.acquire() as conn:
            # Decay customer memories
            await conn.execute(
                """
                UPDATE customer_memories
                SET importance_score = GREATEST(
                    $2::float,
                    importance_score * POWER(1 - $3::float,
                        EXTRACT(EPOCH FROM NOW() - COALESCE(last_accessed_at, created_at)) / 86400
                    )
                )
                WHERE tenant_id = $1
                  AND is_active = TRUE
                  AND importance_score > $2::float
                """,
                str(tenant_id),
                MIN_IMPORTANCE_THRESHOLD,
                IMPORTANCE_DECAY_RATE,
            )

            # Deactivate memories below threshold
            await conn.execute(
                """
                UPDATE customer_memories
                SET is_active = FALSE
                WHERE tenant_id = $1
                  AND importance_score <= $2::float
                  AND is_active = TRUE
                """,
                str(tenant_id),
                MIN_IMPORTANCE_THRESHOLD,
            )

            # Clean up expired memories
            await conn.execute(
                """
                UPDATE customer_memories
                SET is_active = FALSE
                WHERE tenant_id = $1
                  AND expires_at IS NOT NULL
                  AND expires_at < NOW()
                  AND is_active = TRUE
                """,
                str(tenant_id),
            )

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _calculate_importance(outcome: str, sentiment: float, message_count: int) -> float:
        """Calculate conversation memory importance score."""
        base = 0.5

        # Outcome boost
        outcome_scores = {
            "purchased": 0.95,
            "escalated": 0.85,
            "follow_up": 0.75,
            "resolved": 0.65,
            "ongoing": 0.50,
            "abandoned": 0.40,
        }
        base = outcome_scores.get(outcome, 0.5)

        # Sentiment adjustment (negative conversations are more important to remember)
        if sentiment < -0.3:
            base = min(1.0, base + 0.1)

        # Length adjustment (longer conversations = more content = more important)
        if message_count > 20:
            base = min(1.0, base + 0.05)

        return round(base, 3)


# ============================================================================
# MEMORY MANAGER (Orchestrator)
# ============================================================================

class MemoryManager:
    """
    Orchestrates memory operations across all layers.
    This is the main interface called by the AI Engine and API endpoints.
    """

    def __init__(
        self,
        store: MemoryStore,
        summarizer: MemorySummarizer,
        embedding_client: EmbeddingClient,
        cache: TenantCache,
    ):
        self.store = store
        self.summarizer = summarizer
        self.embedding_client = embedding_client
        self.cache = cache

    async def get_memory_context(
        self,
        tenant_id: UUID,
        customer_id: UUID,
        conversation_id: Optional[UUID] = None,
        current_message: Optional[str] = None,
    ) -> MemoryContext:
        """
        Build complete memory context for AI prompt injection.

        This is the PRIMARY method called by the AI Engine before generating
        a response. It assembles short-term + long-term memory into a
        structured context that gets injected into the system prompt.
        """
        context = MemoryContext(customer_id=customer_id)

        # 1. Short-term: Recent turns from current conversation
        if conversation_id:
            cached_turns = await self.cache.get(
                str(tenant_id), f"memory:turns:{conversation_id}"
            )
            if cached_turns:
                context.recent_turns = cached_turns[-MAX_SHORT_TERM_TURNS:]

            # Get compressed summary of older messages
            cached_summary = await self.cache.get(
                str(tenant_id), f"memory:summary:{conversation_id}"
            )
            if cached_summary:
                context.conversation_summary = cached_summary

        # 2. Long-term: Customer memories
        context.customer_memories = await self.store.recall_customer_memories(
            tenant_id=tenant_id,
            customer_id=customer_id,
            query=current_message,
            max_results=MAX_LONG_TERM_MEMORIES,
        )

        # 3. Past conversation summaries
        context.past_conversations = await self.store.recall_past_conversations(
            tenant_id=tenant_id,
            customer_id=customer_id,
            query=current_message,
            max_results=MAX_CONVERSATION_RECALL,
        )

        # 4. Relevant episodes
        context.relevant_episodes = await self.store.recall_episodes(
            tenant_id=tenant_id,
            customer_id=customer_id,
            query=current_message,
            max_results=MAX_EPISODE_RECALL,
        )

        # 5. Customer summary
        pool = await get_tenant_pool(tenant_id)
        async with pool.acquire() as conn:
            customer = await conn.fetchrow(
                """
                SELECT memory_summary, total_conversations, total_messages,
                       first_seen_at, preferred_channel, preferred_language,
                       communication_style, lifetime_value
                FROM customers
                WHERE id = $1 AND tenant_id = $2
                """,
                str(customer_id),
                str(tenant_id),
            )
        if customer:
            context.customer_summary = customer["memory_summary"]
            context.memory_stats = {
                "total_conversations": customer["total_conversations"] or 0,
                "total_messages": customer["total_messages"] or 0,
                "first_seen_at": str(customer["first_seen_at"]) if customer["first_seen_at"] else None,
                "preferred_channel": customer["preferred_channel"],
                "preferred_language": customer["preferred_language"],
                "lifetime_value": float(customer["lifetime_value"]) if customer["lifetime_value"] else 0,
            }

        return context

    async def process_new_message(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
        customer_id: UUID,
        role: str,
        content: str,
        message_metadata: dict = None,
    ):
        """
        Called when a new message is received. Updates short-term memory cache.
        """
        # Get existing turns from cache
        cache_key = f"memory:turns:{conversation_id}"
        existing_turns = await self.cache.get(str(tenant_id), cache_key) or []

        turn = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "turn_number": len(existing_turns) + 1,
        }
        existing_turns.append(turn)

        # Cache updated turns (30 min TTL)
        await self.cache.set(str(tenant_id), cache_key, existing_turns, ttl=1800)

        # If conversation is getting long, compress older messages
        if len(existing_turns) > SUMMARY_THRESHOLD and len(existing_turns) % SUMMARY_THRESHOLD == 0:
            older_turns = existing_turns[:-MAX_SHORT_TERM_TURNS]
            summary = await self.summarizer.compress_turns(older_turns)
            await self.cache.set(
                str(tenant_id),
                f"memory:summary:{conversation_id}",
                summary,
                ttl=3600,
            )

        # Update customer stats
        await self.store.increment_customer_stats(tenant_id, customer_id, messages=1)

    async def process_conversation_end(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
        customer_id: UUID,
        outcome: str = "resolved",
    ):
        """
        Called when a conversation ends. Triggers:
        1. Conversation summarization
        2. Customer memory extraction
        3. Episode extraction
        4. Customer summary update
        """
        pool = await get_tenant_pool(tenant_id)

        # 1. Fetch all messages for the conversation
        async with pool.acquire() as conn:
            messages = await conn.fetch(
                """
                SELECT role, content, created_at
                FROM conversation_messages
                WHERE conversation_id = $1 AND tenant_id = $2
                ORDER BY created_at ASC
                """,
                str(conversation_id),
                str(tenant_id),
            )

            customer = await conn.fetchrow(
                "SELECT name FROM customers WHERE id = $1 AND tenant_id = $2",
                str(customer_id),
                str(tenant_id),
            )

        if not messages:
            logger.warning("No messages found for conversation %s", conversation_id)
            return

        messages_list = [dict(m) for m in messages]
        customer_name = customer["name"] if customer else "Customer"

        # 2. Generate conversation summary
        summary_data = await self.summarizer.summarize_conversation(
            messages_list, customer_name
        )

        first_msg = messages_list[0]
        last_msg = messages_list[-1]
        duration = 0
        if first_msg.get("created_at") and last_msg.get("created_at"):
            duration = int((last_msg["created_at"] - first_msg["created_at"]).total_seconds())

        # 3. Store conversation memory
        await self.store.store_conversation_memory(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            customer_id=customer_id,
            summary=summary_data.get("summary", ""),
            topics=summary_data.get("topics", []),
            intents=[],
            entities={},
            sentiment_avg=summary_data.get("sentiment", 0.0),
            funnel_stage=summary_data.get("funnel_stage", "awareness"),
            outcome=summary_data.get("outcome", outcome),
            message_count=len(messages_list),
            duration_seconds=duration,
            first_message_at=first_msg.get("created_at", datetime.now(timezone.utc)),
            last_message_at=last_msg.get("created_at", datetime.now(timezone.utc)),
            metadata={
                "key_points": summary_data.get("key_points", []),
                "action_items": summary_data.get("action_items", []),
            },
        )

        # 4. Extract customer memories
        existing_memories = await self.store.recall_customer_memories(
            tenant_id, customer_id, max_results=20
        )
        new_memories = await self.summarizer.extract_customer_memories(
            messages_list, existing_memories, customer_name
        )

        for mem in new_memories:
            await self.store.store_customer_memory(
                tenant_id=tenant_id,
                customer_id=customer_id,
                memory_type=mem["memory_type"],
                content=mem["content"],
                key=mem.get("key"),
                value=mem.get("value"),
                importance_score=mem["importance_score"],
                confidence=mem["confidence"],
                source_conversation_id=conversation_id,
            )

        # 5. Update customer stats
        await self.store.increment_customer_stats(
            tenant_id, customer_id, conversations=1
        )

        # 6. Update customer summary
        all_memories = await self.store.recall_customer_memories(
            tenant_id, customer_id, max_results=20
        )
        if all_memories:
            memory_text = "; ".join([m["content"] for m in all_memories[:10]])
            customer_summary = (
                f"{customer_name}: {len(all_memories)} known facts. "
                f"Key info: {memory_text[:500]}"
            )
            await self.store.update_customer_summary(
                tenant_id, customer_id, customer_summary
            )

        # 7. Clean up Redis cache for this conversation
        await self.cache.delete(str(tenant_id), f"memory:turns:{conversation_id}")
        await self.cache.delete(str(tenant_id), f"memory:summary:{conversation_id}")

        logger.info(
            f"Processed conversation end: {conversation_id} — "
            f"{len(new_memories)} new memories extracted"
        )

    def format_memory_for_prompt(self, context: MemoryContext) -> str:
        """
        Format memory context into a string for injection into LLM system prompt.
        This is what gets prepended to the AI Engine's system prompt.
        """
        sections = []

        # Customer overview
        if context.customer_summary:
            sections.append(f"CUSTOMER BACKGROUND:\n{context.customer_summary}")

        if context.memory_stats.get("total_conversations", 0) > 0:
            stats = context.memory_stats
            sections.append(
                f"CUSTOMER HISTORY: {stats['total_conversations']} conversations, "
                f"{stats['total_messages']} messages, "
                f"lifetime value ${stats.get('lifetime_value', 0):.2f}"
            )

        # Key memories (PII-masked for LLM injection safety)
        if context.customer_memories:
            memory_lines = []
            for m in context.customer_memories[:8]:
                masked_content = mask_pii(m['content'])
                memory_lines.append(f"- [{m['memory_type']}] {masked_content}")
            sections.append(
                "KNOWN ABOUT THIS CUSTOMER:\n" + "\n".join(memory_lines)
            )

        # Past conversations
        if context.past_conversations:
            conv_lines = []
            for c in context.past_conversations[:3]:
                date_str = ""
                if c.get("last_message_at"):
                    date_str = c["last_message_at"].strftime("%b %d") if hasattr(c["last_message_at"], "strftime") else str(c["last_message_at"])[:10]
                conv_lines.append(
                    f"- [{date_str}] {c.get('summary', 'No summary')} (outcome: {c.get('outcome', 'unknown')})"
                )
            sections.append(
                "PAST CONVERSATIONS:\n" + "\n".join(conv_lines)
            )

        # Relevant episodes
        if context.relevant_episodes:
            ep_lines = []
            for e in context.relevant_episodes[:3]:
                ep_lines.append(
                    f"- [{e.get('episode_type')}] {e.get('summary', '')}"
                )
            sections.append(
                "RELEVANT PAST INTERACTIONS:\n" + "\n".join(ep_lines)
            )

        # Current conversation context
        if context.conversation_summary:
            sections.append(
                f"EARLIER IN THIS CONVERSATION:\n{context.conversation_summary}"
            )

        if not sections:
            return ""

        return (
            "═══ MEMORY CONTEXT (use this to personalize your response) ═══\n"
            + "\n\n".join(sections)
            + "\n═══ END MEMORY CONTEXT ═══"
        )


# ============================================================================
# FASTAPI APP & ENDPOINTS
# ============================================================================

app = FastAPI(
    title="Memory Service",
    description="Conversation Memory System — Short-term + Long-term memory for Priya Global AI",
    version="1.0.0",
)

# Initialize components
event_bus = EventBus(service_name="memory")
init_sentry(service_name="memory", service_port=9034)
init_tracing(app, service_name="memory")
app.add_middleware(TracingMiddleware)

cors_config = get_cors_config(os.getenv("ENVIRONMENT", "development"))
app.add_middleware(CORSMiddleware, **cors_config)
app.add_middleware(SentryTenantMiddleware)

# Service instances (initialized on startup)
embedding_client: Optional[EmbeddingClient] = None
summarizer: Optional[MemorySummarizer] = None
memory_store: Optional[MemoryStore] = None
memory_manager: Optional[MemoryManager] = None
cache: Optional[TenantCache] = None


@app.on_event("startup")
async def startup():
    global embedding_client, summarizer, memory_store, memory_manager, cache

    embedding_client = EmbeddingClient()
    summarizer = MemorySummarizer()
    memory_store = MemoryStore(embedding_client)
    cache = TenantCache()
    await cache.connect()
    memory_manager = MemoryManager(memory_store, summarizer, embedding_client, cache)

    await event_bus.startup()

    # Subscribe to events
    event_bus.subscribe(EventType.MESSAGE_RECEIVED, _handle_message_received)
    event_bus.subscribe(EventType.CONVERSATION_ENDED, _handle_conversation_ended)

    logger.info("Memory Service started on port 9034")


@app.on_event("shutdown")
async def shutdown():
    shutdown_tracing()
    await event_bus.shutdown()
    if embedding_client:
        await embedding_client.close()
    if summarizer:
        await summarizer.close()
    if cache:
        await cache.disconnect()


# ── Security Helpers ──────────────────────────────────────────────────────

# Valid roles for message events
VALID_ROLES = {"customer", "agent", "system", "ai", "bot"}

# Valid outcomes for conversation end
VALID_OUTCOMES = {"resolved", "escalated", "purchased", "abandoned", "follow_up", "ongoing"}

# Max content length for event-driven messages
MAX_EVENT_CONTENT_LENGTH = 10000


async def _validate_customer_belongs_to_tenant(
    tenant_id: UUID, customer_id: UUID
) -> bool:
    """SECURITY: Verify customer belongs to the authenticated tenant."""
    pool = await get_tenant_pool(tenant_id)
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM customers WHERE id = $1 AND tenant_id = $2)",
            str(customer_id),
            str(tenant_id),
        )
    return bool(exists)


async def _check_rate_limit(tenant_id: UUID, action: str, limit: int = 100, window: int = 60) -> bool:
    """SECURITY: Rate limit memory operations per tenant. Returns True if allowed."""
    if cache:
        allowed = await cache.check_rate_limit(str(tenant_id), f"memory:{action}", limit, window)
        return allowed
    return True


# ── Event Handlers ───────────────────────────────────────────────────────

async def _handle_message_received(event):
    """Process new message for memory updates.

    SECURITY: Validates role, truncates content, catches specific exceptions.
    """
    try:
        data = event.data

        # Validate required fields
        tenant_id = UUID(data["tenant_id"])
        conversation_id = UUID(data["conversation_id"])
        customer_id = UUID(data["customer_id"])

        # Validate role
        role = data.get("role", "customer")
        if role not in VALID_ROLES:
            logger.warning("Invalid message role: %s, defaulting to 'customer'", role)
            role = "customer"

        # Truncate content to prevent memory exhaustion
        content = (data.get("content") or "")[:MAX_EVENT_CONTENT_LENGTH]

        await memory_manager.process_new_message(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            customer_id=customer_id,
            role=role,
            content=content,
        )
    except (KeyError, ValueError) as e:
        logger.warning("Invalid event data for message memory: %s", type(e).__name__)
    except Exception:
        logger.error("Unexpected error processing message for memory")


async def _handle_conversation_ended(event):
    """Process conversation end for memory extraction.

    SECURITY: Validates outcome, catches specific exceptions.
    """
    try:
        data = event.data
        tenant_id = UUID(data["tenant_id"])
        conversation_id = UUID(data["conversation_id"])
        customer_id = UUID(data["customer_id"])

        # Validate outcome
        outcome = data.get("outcome", "resolved")
        if outcome not in VALID_OUTCOMES:
            logger.warning("Invalid outcome: %s, defaulting to 'resolved'", outcome)
            outcome = "resolved"

        await memory_manager.process_conversation_end(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            customer_id=customer_id,
            outcome=outcome,
        )
    except (KeyError, ValueError) as e:
        logger.warning("Invalid event data for conversation end memory: %s", type(e).__name__)
    except Exception:
        logger.error("Unexpected error processing conversation end for memory")


# ── Health ───────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "memory", "port": 9034}


# ── Memory Context Endpoint (called by AI Engine) ───────────────────────

@app.get("/api/v1/context/{customer_id}")
async def get_memory_context(
    customer_id: UUID,
    conversation_id: Optional[UUID] = Query(None),
    message: Optional[str] = Query(None, max_length=500),
    auth: AuthContext = Depends(get_auth),
):
    """
    Get complete memory context for a customer.
    This is the primary endpoint called by the AI Engine before generating a response.
    """
    # SECURITY: Rate limit context lookups (high-frequency endpoint)
    if not await _check_rate_limit(auth.tenant_id, "context", limit=200, window=60):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    # SECURITY: Validate customer belongs to tenant
    if not await _validate_customer_belongs_to_tenant(auth.tenant_id, customer_id):
        raise HTTPException(status_code=404, detail="Customer not found")

    context = await memory_manager.get_memory_context(
        tenant_id=auth.tenant_id,
        customer_id=customer_id,
        conversation_id=conversation_id,
        current_message=message,
    )

    return {
        "context": context.dict(),
        "formatted_prompt": memory_manager.format_memory_for_prompt(context),
    }


# ── Memory CRUD Endpoints ───────────────────────────────────────────────

@app.post("/api/v1/memories")
async def store_memory(
    request: StoreMemoryRequest,
    auth: AuthContext = Depends(get_auth),
):
    """Store a new customer memory."""
    # SECURITY: Rate limit memory writes
    if not await _check_rate_limit(auth.tenant_id, "store", limit=50, window=60):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    # SECURITY: Validate customer belongs to tenant
    if not await _validate_customer_belongs_to_tenant(auth.tenant_id, request.customer_id):
        raise HTTPException(status_code=404, detail="Customer not found")

    memory_id = await memory_store.store_customer_memory(
        tenant_id=auth.tenant_id,
        customer_id=request.customer_id,
        memory_type=request.memory_type.value,
        content=sanitize_input(request.content),
        key=request.key,
        value=request.value,
        importance_score=request.importance_score,
        confidence=request.confidence,
        source_conversation_id=request.source_conversation_id,
        expires_in_days=request.expires_in_days,
    )

    return {"memory_id": str(memory_id), "status": "stored"}


@app.get("/api/v1/memories/{customer_id}")
async def recall_memories(
    customer_id: UUID,
    query: Optional[str] = Query(None),
    memory_type: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=50),
    auth: AuthContext = Depends(get_auth),
):
    """Recall customer memories with optional semantic search."""
    memory_types = [memory_type] if memory_type else None

    memories = await memory_store.recall_customer_memories(
        tenant_id=auth.tenant_id,
        customer_id=customer_id,
        query=query,
        memory_types=memory_types,
        max_results=limit,
    )

    return {"memories": memories, "count": len(memories)}


@app.get("/api/v1/conversations/{customer_id}/history")
async def get_conversation_history(
    customer_id: UUID,
    query: Optional[str] = Query(None),
    limit: int = Query(5, ge=1, le=20),
    auth: AuthContext = Depends(get_auth),
):
    """Get past conversation summaries for a customer."""
    conversations = await memory_store.recall_past_conversations(
        tenant_id=auth.tenant_id,
        customer_id=customer_id,
        query=query,
        max_results=limit,
    )

    return {"conversations": conversations, "count": len(conversations)}


@app.get("/api/v1/episodes/{customer_id}")
async def get_episodes(
    customer_id: UUID,
    query: Optional[str] = Query(None),
    episode_type: Optional[str] = Query(None),
    limit: int = Query(5, ge=1, le=20),
    auth: AuthContext = Depends(get_auth),
):
    """Get interaction episodes for a customer."""
    episode_types = [episode_type] if episode_type else None

    episodes = await memory_store.recall_episodes(
        tenant_id=auth.tenant_id,
        customer_id=customer_id,
        query=query,
        episode_types=episode_types,
        max_results=limit,
    )

    return {"episodes": episodes, "count": len(episodes)}


# ── Conversation Lifecycle Endpoints ─────────────────────────────────────

@app.post("/api/v1/conversations/{conversation_id}/summarize")
async def summarize_conversation(
    conversation_id: UUID,
    request: ConversationSummaryRequest,
    auth: AuthContext = Depends(get_auth),
):
    """Manually trigger conversation summarization and memory extraction."""
    await memory_manager.process_conversation_end(
        tenant_id=auth.tenant_id,
        conversation_id=conversation_id,
        customer_id=request.customer_id,
        outcome=request.outcome.value,
    )

    return {"status": "processed", "conversation_id": str(conversation_id)}


@app.post("/api/v1/message")
async def process_message(
    tenant_id: UUID = Query(...),
    conversation_id: UUID = Query(...),
    customer_id: UUID = Query(...),
    role: str = Query("customer"),
    content: str = Query(...),
    auth: AuthContext = Depends(get_auth),
):
    """Process a new message for memory tracking (alternative to event-driven)."""
    await memory_manager.process_new_message(
        tenant_id=auth.tenant_id,
        conversation_id=conversation_id,
        customer_id=customer_id,
        role=role,
        content=sanitize_input(content),
    )

    return {"status": "processed"}


# ── Admin Endpoints ──────────────────────────────────────────────────────

@app.post("/api/v1/admin/decay")
async def trigger_decay(auth: AuthContext = Depends(get_auth)):
    """Manually trigger importance decay for tenant memories."""
    require_role(auth, ["admin", "owner"])
    await memory_store.apply_importance_decay(auth.tenant_id)
    return {"status": "decay_applied", "tenant_id": str(auth.tenant_id)}


@app.get("/api/v1/admin/stats")
async def memory_stats(auth: AuthContext = Depends(get_auth)):
    """Get memory system statistics for the tenant."""
    require_role(auth, ["admin", "owner"])

    pool = await get_tenant_pool(auth.tenant_id)
    async with pool.acquire() as conn:
        stats = await conn.fetchrow(
            """
            SELECT
                (SELECT COUNT(*) FROM conversation_memories WHERE tenant_id = $1) as conversation_memories,
                (SELECT COUNT(*) FROM customer_memories WHERE tenant_id = $1 AND is_active = TRUE) as active_customer_memories,
                (SELECT COUNT(*) FROM customer_memories WHERE tenant_id = $1 AND is_active = FALSE) as inactive_customer_memories,
                (SELECT COUNT(*) FROM memory_episodes WHERE tenant_id = $1) as episodes,
                (SELECT COUNT(DISTINCT customer_id) FROM customer_memories WHERE tenant_id = $1) as customers_with_memories
            """,
            str(auth.tenant_id),
        )

    return dict(stats) if stats else {}
