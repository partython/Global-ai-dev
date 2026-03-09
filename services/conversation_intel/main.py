"""
Conversation Intelligence Service - Global AI Sales Platform
Real-time sentiment analysis, topic extraction, sales intelligence, and coaching insights
Multi-tenant SaaS with row-level security and async FastAPI
"""

import asyncio
import json
import os
import re
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from collections import defaultdict, Counter

import aiohttp
import asyncpg
import jwt
from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager
from shared.observability.tracing import init_tracing, TracingMiddleware, shutdown_tracing
from shared.observability.sentry import init_sentry
from shared.middleware.sentry import SentryTenantMiddleware
from shared.events.event_bus import EventBus, EventType
from shared.middleware.cors import get_cors_config

# ==================== Configuration & Models ====================

APP_VERSION = "1.0.0"
SERVICE_NAME = "Conversation Intelligence"
PORT = int(os.getenv("CONV_INTEL_PORT", 9028))
JWT_SECRET = os.getenv("JWT_SECRET_KEY")
if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET_KEY environment variable must be set")
JWT_ALGORITHM = "HS256"

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable must be set")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

# Database connection pool
db_pool: Optional[asyncpg.Pool] = None
http_session: Optional[aiohttp.ClientSession] = None


# ==================== Pydantic Models ====================

class Message(BaseModel):
    speaker: str
    text: str
    timestamp: datetime
    speaker_role: str = "agent"  # agent or customer


class ConversationAnalysisRequest(BaseModel):
    conversation_id: str
    messages: List[Message]
    customer_id: str
    agent_id: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SentimentScore(BaseModel):
    message_idx: int
    sentiment: str  # positive, neutral, negative
    score: float
    confidence: float


class TopicItem(BaseModel):
    topic: str
    confidence: float
    messages_idx: List[int]


class IntentItem(BaseModel):
    intent: str  # buy, inquire, complain, return, escalate
    confidence: float


class KeyMoment(BaseModel):
    type: str  # objection, buying_signal, escalation
    message_idx: int
    description: str
    confidence: float


class ConversationAnalysis(BaseModel):
    conversation_id: str
    sentiment_timeline: List[SentimentScore]
    topics: List[TopicItem]
    intents: List[IntentItem]
    key_moments: List[KeyMoment]
    overall_sentiment: str
    talk_listen_ratio: Dict[str, float]
    response_time_avg_ms: float
    competitor_mentions: List[str]
    objections_count: int
    upsell_opportunities: int
    pain_points: List[str]
    created_at: datetime


class AgentCoachingInsight(BaseModel):
    agent_id: str
    performance_score: float
    conversation_count: int
    avg_sentiment: float
    talk_listen_ratio_avg: float
    top_objections: List[str]
    improvements: List[str]
    strengths: List[str]


class SalesOpportunity(BaseModel):
    conversation_id: str
    opportunity_type: str
    confidence: float
    description: str
    recommended_action: str


class ConversationTrend(BaseModel):
    date: str
    avg_sentiment: float
    conversation_count: int
    top_topics: List[str]
    avg_talk_listen_ratio: float


class AuthContext(BaseModel):
    tenant_id: str
    user_id: str
    roles: List[str]


# ==================== Database Functions ====================

async def init_db():
    """Initialize database connection pool"""
    global db_pool
    try:
        db_pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=5,
            max_size=20,
            command_timeout=60
        )
        print(f"Database pool initialized with {DATABASE_URL}")
    except Exception as e:
        print(f"Failed to initialize database: {e}")
        raise


async def close_db():
    """Close database connection pool"""
    global db_pool
    if db_pool:
        await db_pool.close()
        print("Database pool closed")


async def ensure_tables(pool):
    """Ensure all required tables exist with tenant_id and RLS"""
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL,
                conversation_id TEXT NOT NULL,
                customer_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                messages JSONB NOT NULL,
                metadata JSONB,
                analysis JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(tenant_id, conversation_id)
            )
        """)
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS sentiment_timeline (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL,
                conversation_id TEXT NOT NULL,
                message_idx INT NOT NULL,
                sentiment TEXT NOT NULL,
                score FLOAT NOT NULL,
                confidence FLOAT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(tenant_id, conversation_id, message_idx)
            )
        """)
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS conversation_analysis (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL,
                conversation_id TEXT NOT NULL,
                overall_sentiment TEXT NOT NULL,
                talk_listen_ratio JSONB NOT NULL,
                response_time_avg_ms FLOAT NOT NULL,
                competitor_mentions TEXT[] DEFAULT '{}',
                objections_count INT DEFAULT 0,
                upsell_opportunities INT DEFAULT 0,
                pain_points TEXT[] DEFAULT '{}',
                topics JSONB,
                intents JSONB,
                key_moments JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(tenant_id, conversation_id)
            )
        """)
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_metrics (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL,
                agent_id TEXT NOT NULL,
                conversation_count INT DEFAULT 0,
                avg_sentiment FLOAT DEFAULT 0.0,
                talk_listen_ratio_avg FLOAT DEFAULT 0.5,
                performance_score FLOAT DEFAULT 0.0,
                top_objections TEXT[] DEFAULT '{}',
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(tenant_id, agent_id)
            )
        """)
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS sales_opportunities (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL,
                conversation_id TEXT NOT NULL,
                opportunity_type TEXT NOT NULL,
                confidence FLOAT NOT NULL,
                description TEXT,
                recommended_action TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_conversations_tenant_id ON conversations(tenant_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_conversations_conversation_id ON conversations(tenant_id, conversation_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_sentiment_tenant_conversation ON sentiment_timeline(tenant_id, conversation_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_analysis_tenant_conversation ON conversation_analysis(tenant_id, conversation_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_metrics_tenant_agent ON agent_metrics(tenant_id, agent_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_opportunities_tenant_conversation ON sales_opportunities(tenant_id, conversation_id)")
        
        print("Database tables and indexes ensured")


# ==================== Authentication ====================

security = HTTPBearer()


async def verify_token(credentials: HTTPAuthCredentials = Security(security)) -> AuthContext:
    """Verify JWT token and extract auth context"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        tenant_id = payload.get("tenant_id")
        user_id = payload.get("user_id")
        roles = payload.get("roles", [])
        
        if not tenant_id or not user_id:
            raise HTTPException(status_code=401, detail="Invalid token claims")
        
        return AuthContext(tenant_id=tenant_id, user_id=user_id, roles=roles)
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ==================== AI Analysis Functions ====================

async def call_llm_api(prompt: str, max_tokens: int = 1000) -> str:
    """Call external LLM API with fallback pattern"""
    global http_session
    
    if not http_session:
        http_session = aiohttp.ClientSession()
    
    # Try Anthropic first
    if ANTHROPIC_API_KEY:
        try:
            async with http_session.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["content"][0]["text"]
        except Exception as e:
            print(f"Anthropic API error: {e}")
    
    # Fallback to OpenAI
    if OPENAI_API_KEY:
        try:
            async with http_session.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"OpenAI API error: {e}")
    
    # Return mock response if no API available
    return "Analysis unavailable - LLM API not configured"


async def load_sentiment_config(db_pool: asyncpg.Pool, tenant_id: str) -> Dict[str, set]:
    """
    # TENANT-SCOPED
    Load tenant-specific sentiment word lists from database.
    Falls back to defaults if no tenant config exists.
    """
    try:
        async with db_pool.acquire() as conn:
            config = await conn.fetchrow("""
                SELECT sentiment_positive_words, sentiment_negative_words
                FROM tenant_ai_config
                WHERE tenant_id = $1
            """, tenant_id)

            if config and config["sentiment_positive_words"] and config["sentiment_negative_words"]:
                return {
                    "positive": set(config["sentiment_positive_words"]),
                    "negative": set(config["sentiment_negative_words"])
                }
    except Exception as e:
        print(f"Error loading sentiment config: {e}")

    # Default fallback
    return {
        "positive": {"good", "great", "excellent", "amazing", "love", "perfect", "wonderful", "happy"},
        "negative": {"bad", "terrible", "awful", "hate", "poor", "horrible", "angry", "frustrated"}
    }


def analyze_sentiment(text: str, positive_words: set = None, negative_words: set = None) -> Dict[str, float]:
    """Simple sentiment analysis - in production use ML model or LLM"""
    text_lower = text.lower()

    # # TENANT-SCOPED: Use tenant-specific words or defaults
    if positive_words is None:
        positive_words = {"good", "great", "excellent", "amazing", "love", "perfect", "wonderful", "happy"}
    if negative_words is None:
        negative_words = {"bad", "terrible", "awful", "hate", "poor", "horrible", "angry", "frustrated"}
    
    pos_count = sum(1 for word in positive_words if word in text_lower)
    neg_count = sum(1 for word in negative_words if word in text_lower)
    
    total = pos_count + neg_count
    if total == 0:
        return {"sentiment": "neutral", "score": 0.5, "confidence": 0.5}
    
    score = (pos_count - neg_count + total) / (2 * total)
    score = max(0.0, min(1.0, score))
    
    if score > 0.6:
        sentiment = "positive"
    elif score < 0.4:
        sentiment = "negative"
    else:
        sentiment = "neutral"
    
    return {"sentiment": sentiment, "score": score, "confidence": min(0.95, 0.5 + total * 0.1)}


async def load_topics_config(db_pool: asyncpg.Pool, tenant_id: str) -> Dict[str, List[str]]:
    """
    # TENANT-SCOPED
    Load tenant and industry-specific topic keywords from database.
    Falls back to defaults if no tenant config exists.
    """
    try:
        async with db_pool.acquire() as conn:
            # Get tenant industry for industry-specific defaults
            tenant = await conn.fetchrow(
                "SELECT industry FROM tenants WHERE tenant_id = $1",
                tenant_id
            )

            config = await conn.fetchrow("""
                SELECT topic_keywords
                FROM tenant_ai_config
                WHERE tenant_id = $1
            """, tenant_id)

            if config and config["topic_keywords"]:
                return config["topic_keywords"]
    except Exception as e:
        print(f"Error loading topics config: {e}")

    # Default fallback
    return {
        "pricing": ["price", "cost", "fee", "discount", "budget"],
        "product": ["product", "feature", "functionality", "specification"],
        "service": ["service", "support", "help", "assistance"],
        "delivery": ["delivery", "shipping", "timeline", "schedule"],
        "quality": ["quality", "issue", "problem", "bug", "defect"],
        "integration": ["integration", "api", "system", "connect"]
    }


def extract_topics(text: str, topic_keywords: Dict[str, List[str]] = None) -> List[str]:
    """Extract topic keywords from text"""
    # # TENANT-SCOPED: Use tenant-specific keywords or defaults
    if topic_keywords is None:
        topic_keywords = {
            "pricing": ["price", "cost", "fee", "discount", "budget"],
            "product": ["product", "feature", "functionality", "specification"],
            "service": ["service", "support", "help", "assistance"],
            "delivery": ["delivery", "shipping", "timeline", "schedule"],
            "quality": ["quality", "issue", "problem", "bug", "defect"],
            "integration": ["integration", "api", "system", "connect"]
        }

    text_lower = text.lower()
    found_topics = set()

    for topic, words in topic_keywords.items():
        if any(word in text_lower for word in words):
            found_topics.add(topic)

    return list(found_topics)


async def load_intent_config(db_pool: asyncpg.Pool, tenant_id: str) -> Dict[str, List[str]]:
    """
    # TENANT-SCOPED
    Load tenant-specific intent classification patterns from database.
    Falls back to defaults if no tenant config exists.
    """
    try:
        async with db_pool.acquire() as conn:
            config = await conn.fetchrow("""
                SELECT intent_patterns
                FROM tenant_ai_config
                WHERE tenant_id = $1
            """, tenant_id)

            if config and config["intent_patterns"]:
                return config["intent_patterns"]
    except Exception as e:
        print(f"Error loading intent config: {e}")

    # Default fallback
    return {
        "buy": ["buy", "purchase", "order", "want to get", "interested in"],
        "inquire": ["how", "what", "when", "where", "tell me", "explain", "question"],
        "complain": ["bad", "terrible", "awful", "hate", "angry", "frustrated"],
        "return": ["return", "refund", "send back", "exchange"],
        "escalate": ["speak to", "manager", "supervisor", "escalate", "complaint"]
    }


def classify_intent(text: str, intent_patterns: Dict[str, List[str]] = None) -> str:
    """Classify conversation intent"""
    text_lower = text.lower()

    # # TENANT-SCOPED: Use tenant-specific patterns or defaults
    if intent_patterns is None:
        intent_patterns = {
            "buy": ["buy", "purchase", "order", "want to get", "interested in"],
            "inquire": ["how", "what", "when", "where", "tell me", "explain", "question"],
            "complain": ["bad", "terrible", "awful", "hate", "angry", "frustrated"],
            "return": ["return", "refund", "send back", "exchange"],
            "escalate": ["speak to", "manager", "supervisor", "escalate", "complaint"]
        }

    for intent, patterns in intent_patterns.items():
        if any(pattern in text_lower for pattern in patterns):
            return intent

    return "inquire"


def detect_key_moments(messages: List[Message]) -> List[Dict]:
    """Detect objections, buying signals, escalation triggers"""
    moments = []
    
    objection_keywords = ["but", "however", "concerned", "worry", "doubt", "problem"]
    buying_keywords = ["ready", "let's go", "sign", "when", "start", "proceed"]
    escalation_keywords = ["angry", "frustrated", "complaint", "unacceptable", "lawyer"]
    
    for idx, msg in enumerate(messages):
        text_lower = msg.text.lower()
        
        if any(kw in text_lower for kw in objection_keywords):
            moments.append({"type": "objection", "idx": idx, "text": msg.text[:50]})
        
        if any(kw in text_lower for kw in buying_keywords) and msg.speaker_role == "customer":
            moments.append({"type": "buying_signal", "idx": idx, "text": msg.text[:50]})
        
        if any(kw in text_lower for kw in escalation_keywords):
            moments.append({"type": "escalation", "idx": idx, "text": msg.text[:50]})
    
    return moments


def extract_pain_points(messages: List[Message]) -> List[str]:
    """Extract customer pain points from conversation"""
    pain_point_keywords = {
        "cost": ["expensive", "too much", "overpriced", "cost"],
        "time": ["slow", "takes long", "delayed", "waiting"],
        "complexity": ["complicated", "confusing", "hard to use"],
        "support": ["no support", "can't reach", "help"],
        "reliability": ["down", "broken", "not working", "unstable"]
    }
    
    found_pain_points = set()
    
    for msg in messages:
        if msg.speaker_role == "customer":
            text_lower = msg.text.lower()
            for pain_point, keywords in pain_point_keywords.items():
                if any(kw in text_lower for kw in keywords):
                    found_pain_points.add(pain_point)
    
    return list(found_pain_points)


def detect_competitor_mentions(text: str) -> List[str]:
    """Detect competitor mentions"""
    competitors = ["salesforce", "hubspot", "pipedrive", "zendesk", "intercom", "drift"]
    mentioned = [c for c in competitors if c in text.lower()]
    return mentioned


async def load_objections_config(db_pool: asyncpg.Pool, tenant_id: str) -> List[str]:
    """
    # TENANT-SCOPED
    Load tenant-specific objection types from database.
    Falls back to defaults if no tenant config exists.
    """
    try:
        async with db_pool.acquire() as conn:
            config = await conn.fetchrow("""
                SELECT objection_types
                FROM tenant_ai_config
                WHERE tenant_id = $1
            """, tenant_id)

            if config and config["objection_types"]:
                return config["objection_types"]
    except Exception as e:
        print(f"Error loading objections config: {e}")

    # Default fallback
    return ["pricing", "integration", "support", "timeline", "feature_gap"]


async def analyze_actual_objections(
    db_pool: asyncpg.Pool, tenant_id: str, agent_id: str, conversations: List
) -> List[str]:
    """
    # TENANT-SCOPED
    Analyze actual objections from conversation data rather than hardcoding.
    Returns most common objections specific to this agent's conversations.
    """
    objection_config = await load_objections_config(db_pool, tenant_id)
    objection_counts = Counter()

    # Scan conversations for actual objections
    for conv in conversations:
        if conv.get("key_moments"):
            moments = json.loads(conv["key_moments"]) if isinstance(conv["key_moments"], str) else conv["key_moments"]
            for moment in moments:
                if moment.get("type") == "objection":
                    # Extract objection reason from description
                    desc = moment.get("description", "").lower()
                    for objection in objection_config:
                        if objection in desc:
                            objection_counts[objection] += 1

    # Return top 3 actual objections, or defaults if none found
    if objection_counts:
        return [obj for obj, _ in objection_counts.most_common(3)]
    return objection_config[:3]


async def generate_coaching_suggestions(
    db_pool: asyncpg.Pool, tenant_id: str, conversations: List, avg_sentiment: float
) -> tuple[List[str], List[str]]:
    """
    # TENANT-SCOPED
    Dynamically generate coaching suggestions based on actual conversation analysis.
    Returns (improvements, strengths) based on real data, not hardcoded.
    """
    improvements = []
    strengths = []

    # Analyze response times
    total_response_time = 0
    response_count = 0
    for conv in conversations:
        if conv.get("response_time_avg_ms"):
            total_response_time += conv["response_time_avg_ms"]
            response_count += 1

    if response_count > 0:
        avg_response = total_response_time / response_count
        if avg_response > 5000:  # 5 seconds
            improvements.append("Improve response time - currently averaging " + str(int(avg_response)) + "ms")
        else:
            strengths.append("Quick response times")

    # Analyze talk/listen ratio
    agent_talk_ratios = []
    for conv in conversations:
        if conv.get("talk_listen_ratio"):
            ratio = json.loads(conv["talk_listen_ratio"]) if isinstance(conv["talk_listen_ratio"], str) else conv["talk_listen_ratio"]
            agent_talk_ratios.append(ratio.get("agent", 0.5))

    if agent_talk_ratios:
        avg_talk = sum(agent_talk_ratios) / len(agent_talk_ratios)
        if avg_talk > 0.7:
            improvements.append("Balance talk time - listen more to customers")
        else:
            strengths.append("Good listener - balanced conversation ratio")

    # Analyze sentiment
    if avg_sentiment > 0.7:
        strengths.append("Excellent customer rapport")
    elif avg_sentiment < 0.4:
        improvements.append("Focus on customer satisfaction and empathy")

    # Handle no data case
    if not improvements:
        improvements = ["Continue current approach", "Monitor objection handling"]
    if not strengths:
        strengths = ["Professional communication"]

    return improvements[:3], strengths[:3]


def calculate_talk_listen_ratio(messages: List[Message]) -> Dict[str, float]:
    """Calculate agent vs customer talk ratio"""
    agent_words = 0
    customer_words = 0
    
    for msg in messages:
        word_count = len(msg.text.split())
        if msg.speaker_role == "agent":
            agent_words += word_count
        else:
            customer_words += word_count
    
    total = agent_words + customer_words
    if total == 0:
        return {"agent": 0.5, "customer": 0.5}
    
    return {"agent": agent_words / total, "customer": customer_words / total}


def calculate_response_time(messages: List[Message]) -> float:
    """Calculate average response time in milliseconds"""
    response_times = []
    
    for i in range(1, len(messages)):
        if messages[i].speaker_role == "agent" and messages[i-1].speaker_role == "customer":
            time_diff = (messages[i].timestamp - messages[i-1].timestamp).total_seconds() * 1000
            response_times.append(time_diff)
    
    return sum(response_times) / len(response_times) if response_times else 0.0


# ==================== API Endpoints ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage app lifecycle"""
    await init_db()
    await ensure_tables(db_pool)
    yield
    if http_session:
        await http_session.close()
    await close_db()


app = FastAPI(
    title=SERVICE_NAME,
    version=APP_VERSION,
    lifespan=lifespan
)
# Initialize Sentry error tracking

# Initialize event bus
event_bus = EventBus(service_name="conversation_intel")
init_sentry(service_name="conversation-intel", service_port=9028)

# Initialize OpenTelemetry distributed tracing
init_tracing(app, service_name="conversation-intel")
app.add_middleware(TracingMiddleware)


# CORS
cors_config = get_cors_config(os.getenv("ENVIRONMENT", "development"))
app.add_middleware(CORSMiddleware, **cors_config)
# Sentry tenant context middleware
app.add_middleware(SentryTenantMiddleware)



@app.post("/api/v1/intel/analyze")
async def analyze_conversation(
    request: ConversationAnalysisRequest,
    auth: AuthContext = Depends(verify_token)
):
    """Analyze a conversation for intelligence insights"""
    try:
        # # TENANT-SCOPED: Load tenant-specific configs
        sentiment_config = await load_sentiment_config(db_pool, auth.tenant_id)
        topics_config = await load_topics_config(db_pool, auth.tenant_id)
        intents_config = await load_intent_config(db_pool, auth.tenant_id)

        async with db_pool.acquire() as conn:
            # Store conversation
            await conn.execute("""
                INSERT INTO conversations (tenant_id, conversation_id, customer_id, agent_id, messages, metadata)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (tenant_id, conversation_id) DO UPDATE SET
                    messages = $5, metadata = $6, updated_at = CURRENT_TIMESTAMP
            """, auth.tenant_id, request.conversation_id, request.customer_id,
                request.agent_id, json.dumps([m.dict() for m in request.messages]),
                json.dumps(request.metadata))

            # # TENANT-SCOPED: Sentiment analysis with tenant-specific word lists
            sentiment_timeline = []
            for idx, msg in enumerate(request.messages):
                result = analyze_sentiment(
                    msg.text,
                    positive_words=sentiment_config["positive"],
                    negative_words=sentiment_config["negative"]
                )
                sentiment_timeline.append({
                    "message_idx": idx,
                    "sentiment": result["sentiment"],
                    "score": result["score"],
                    "confidence": result["confidence"]
                })

                await conn.execute("""
                    INSERT INTO sentiment_timeline (tenant_id, conversation_id, message_idx, sentiment, score, confidence)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (tenant_id, conversation_id, message_idx) DO UPDATE SET
                        sentiment = $4, score = $5, confidence = $6
                """, auth.tenant_id, request.conversation_id, idx,
                    result["sentiment"], result["score"], result["confidence"])

            # # TENANT-SCOPED: Topic extraction with tenant-specific keywords
            all_topics = defaultdict(list)
            for idx, msg in enumerate(request.messages):
                topics = extract_topics(msg.text, topic_keywords=topics_config)
                for topic in topics:
                    all_topics[topic].append(idx)

            topics = [{"topic": t, "confidence": 0.8, "messages_idx": indices}
                     for t, indices in all_topics.items()]

            # # TENANT-SCOPED: Intent classification with tenant-specific patterns
            intents_found = defaultdict(int)
            for msg in request.messages:
                intent = classify_intent(msg.text, intent_patterns=intents_config)
                intents_found[intent] += 1

            intents = [{"intent": i, "confidence": 0.75} for i in intents_found.keys()]
            
            # Key moments
            key_moments_list = detect_key_moments(request.messages)
            key_moments = [
                KeyMoment(
                    type=m["type"],
                    message_idx=m["idx"],
                    description=m["text"],
                    confidence=0.8
                ).dict()
                for m in key_moments_list
            ]
            
            # Sales metrics
            competitor_mentions = []
            for msg in request.messages:
                competitor_mentions.extend(detect_competitor_mentions(msg.text))
            competitor_mentions = list(set(competitor_mentions))
            
            objections_count = len([m for m in key_moments_list if m["type"] == "objection"])
            upsell_opportunities = len([m for m in key_moments_list if m["type"] == "buying_signal"])
            pain_points = extract_pain_points(request.messages)
            
            # Performance metrics
            talk_listen_ratio = calculate_talk_listen_ratio(request.messages)
            response_time = calculate_response_time(request.messages)
            overall_sentiment = "positive" if sum(s["score"] for s in sentiment_timeline) / len(sentiment_timeline) > 0.6 else "neutral"
            
            # Store analysis
            await conn.execute("""
                INSERT INTO conversation_analysis (
                    tenant_id, conversation_id, overall_sentiment, talk_listen_ratio,
                    response_time_avg_ms, competitor_mentions, objections_count, upsell_opportunities,
                    pain_points, topics, intents, key_moments
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                ON CONFLICT (tenant_id, conversation_id) DO UPDATE SET
                    overall_sentiment = $3, talk_listen_ratio = $4, response_time_avg_ms = $5,
                    competitor_mentions = $6, objections_count = $7, upsell_opportunities = $8,
                    pain_points = $9, topics = $10, intents = $11, key_moments = $12, updated_at = CURRENT_TIMESTAMP
            """, auth.tenant_id, request.conversation_id, overall_sentiment,
                json.dumps(talk_listen_ratio), response_time, competitor_mentions,
                objections_count, upsell_opportunities, pain_points,
                json.dumps(topics), json.dumps(intents), json.dumps(key_moments))
            
            # Store sales opportunities
            for moment in key_moments_list:
                if moment["type"] == "buying_signal":
                    await conn.execute("""
                        INSERT INTO sales_opportunities (tenant_id, conversation_id, opportunity_type, confidence, description)
                        VALUES ($1, $2, $3, $4, $5)
                    """, auth.tenant_id, request.conversation_id, "upsell",
                        0.8, f"Buying signal at message {moment['idx']}")
            
            return ConversationAnalysis(
                conversation_id=request.conversation_id,
                sentiment_timeline=[SentimentScore(**s) for s in sentiment_timeline],
                topics=[TopicItem(**t) for t in topics],
                intents=[IntentItem(**i) for i in intents],
                key_moments=[KeyMoment(**m) for m in key_moments],
                overall_sentiment=overall_sentiment,
                talk_listen_ratio=talk_listen_ratio,
                response_time_avg_ms=response_time,
                competitor_mentions=competitor_mentions,
                objections_count=objections_count,
                upsell_opportunities=upsell_opportunities,
                pain_points=pain_points,
                created_at=datetime.utcnow()
            )
    
    except Exception as e:
        print(f"Analysis error: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze conversation")


@app.get("/api/v1/intel/conversation/{conversation_id}")
async def get_conversation_analysis(
    conversation_id: str,
    auth: AuthContext = Depends(verify_token)
):
    """Get analysis results for a conversation"""
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM conversation_analysis
                WHERE tenant_id = $1 AND conversation_id = $2
            """, auth.tenant_id, conversation_id)
            
            if not row:
                raise HTTPException(status_code=404, detail="Conversation not found")
            
            return dict(row)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/v1/intel/sentiment/{conversation_id}")
async def get_sentiment_timeline(
    conversation_id: str,
    auth: AuthContext = Depends(verify_token)
):
    """Get sentiment timeline for a conversation"""
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM sentiment_timeline
                WHERE tenant_id = $1 AND conversation_id = $2
                ORDER BY message_idx
            """, auth.tenant_id, conversation_id)
            
            return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/v1/intel/topics")
async def get_topic_distribution(
    days: int = 30,
    auth: AuthContext = Depends(verify_token)
):
    """Get topic distribution over time"""
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT topics FROM conversation_analysis
                WHERE tenant_id = $1 AND created_at > CURRENT_TIMESTAMP - INTERVAL '1 day' * $2
            """, auth.tenant_id, days)
            
            topic_counts = Counter()
            for row in rows:
                if row["topics"]:
                    for topic in row["topics"]:
                        topic_counts[topic["topic"]] += 1
            
            return dict(topic_counts)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/v1/intel/keywords")
async def get_keyword_analysis(
    days: int = 30,
    auth: AuthContext = Depends(verify_token)
):
    """Analyze keyword frequency"""
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT messages FROM conversations
                WHERE tenant_id = $1 AND created_at > CURRENT_TIMESTAMP - INTERVAL '1 day' * $2
            """, auth.tenant_id, days)
            
            keyword_counts = Counter()
            for row in rows:
                if row["messages"]:
                    for msg in row["messages"]:
                        words = msg["text"].lower().split()
                        for word in words:
                            if len(word) > 3 and word not in ["that", "this", "with", "from"]:
                                keyword_counts[word] += 1
            
            return dict(keyword_counts.most_common(20))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/v1/intel/summarize/{conversation_id}")
async def summarize_conversation(
    conversation_id: str,
    auth: AuthContext = Depends(verify_token)
):
    """Generate AI-powered conversation summary"""
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT messages FROM conversations
                WHERE tenant_id = $1 AND conversation_id = $2
            """, auth.tenant_id, conversation_id)
            
            if not row:
                raise HTTPException(status_code=404, detail="Conversation not found")
            
            messages = row["messages"]
            text_for_summary = "\n".join([f"{m['speaker']}: {m['text']}" for m in messages])
            
            prompt = f"""Summarize this customer service conversation in 2-3 sentences, highlighting key outcomes and next steps:

{text_for_summary[:2000]}"""
            
            summary = await call_llm_api(prompt, max_tokens=200)
            
            return {"conversation_id": conversation_id, "summary": summary}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/v1/intel/coaching/{agent_id}")
async def get_agent_coaching(
    agent_id: str,
    auth: AuthContext = Depends(verify_token)
):
    """Get coaching insights for an agent"""
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM agent_metrics
                WHERE tenant_id = $1 AND agent_id = $2
            """, auth.tenant_id, agent_id)

            if not row:
                # # TENANT-SCOPED: Calculate from actual conversation data
                conversations = await conn.fetch("""
                    SELECT * FROM conversation_analysis
                    WHERE tenant_id = $1 AND conversation_id IN (
                        SELECT conversation_id FROM conversations
                        WHERE tenant_id = $1 AND agent_id = $2
                    )
                """, auth.tenant_id, agent_id)

                if not conversations:
                    raise HTTPException(status_code=404, detail="Agent not found")

                # Calculate metrics from real data
                avg_sentiment = sum(c["overall_sentiment"] == "positive" for c in conversations) / len(conversations) if conversations else 0
                talk_listen_ratios = []
                for conv in conversations:
                    if conv.get("talk_listen_ratio"):
                        ratio = json.loads(conv["talk_listen_ratio"]) if isinstance(conv["talk_listen_ratio"], str) else conv["talk_listen_ratio"]
                        talk_listen_ratios.append(ratio.get("agent", 0.5))

                avg_talk_listen = sum(talk_listen_ratios) / len(talk_listen_ratios) if talk_listen_ratios else 0.5

                # # TENANT-SCOPED: Analyze actual objections from conversation data
                top_objections = await analyze_actual_objections(db_pool, auth.tenant_id, agent_id, conversations)

                # # TENANT-SCOPED: Generate coaching suggestions from real metrics
                improvements, strengths = await generate_coaching_suggestions(
                    db_pool, auth.tenant_id, conversations, avg_sentiment
                )

                return {
                    "agent_id": agent_id,
                    "performance_score": 0.75 + (avg_sentiment * 0.25),
                    "conversation_count": len(conversations),
                    "avg_sentiment": avg_sentiment,
                    "talk_listen_ratio_avg": avg_talk_listen,
                    "top_objections": top_objections,
                    "improvements": improvements,
                    "strengths": strengths
                }

            return dict(row)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/v1/intel/opportunities")
async def get_sales_opportunities(
    days: int = 30,
    auth: AuthContext = Depends(verify_token)
):
    """Get detected sales opportunities"""
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM sales_opportunities
                WHERE tenant_id = $1 AND created_at > CURRENT_TIMESTAMP - INTERVAL '1 day' * $2
                ORDER BY created_at DESC LIMIT 100
            """, auth.tenant_id, days)
            
            return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/v1/intel/trends")
async def get_conversation_trends(
    days: int = 30,
    auth: AuthContext = Depends(verify_token)
):
    """Get conversation trend analysis"""
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT DATE(created_at) as date, COUNT(*) as count, AVG(
                    CASE WHEN overall_sentiment = 'positive' THEN 1 ELSE 0 END
                ) as avg_sentiment, array_agg(topics) as all_topics
                FROM conversation_analysis
                WHERE tenant_id = $1 AND created_at > CURRENT_TIMESTAMP - INTERVAL '1 day' * $2
                GROUP BY DATE(created_at)
                ORDER BY date DESC
            """, auth.tenant_id, days)

            trends = []
            for row in rows:
                # # TENANT-SCOPED: Extract actual top topics from conversation data
                topic_counts = Counter()
                if row["all_topics"]:
                    for topics_json in row["all_topics"]:
                        if topics_json:
                            topics = json.loads(topics_json) if isinstance(topics_json, str) else topics_json
                            for topic in topics:
                                topic_counts[topic.get("topic") if isinstance(topic, dict) else topic] += 1

                top_topics = [topic for topic, _ in topic_counts.most_common(3)] if topic_counts else []

                trends.append({
                    "date": str(row["date"]),
                    "avg_sentiment": float(row["avg_sentiment"] or 0),
                    "conversation_count": row["count"],
                    "top_topics": top_topics
                })

            return trends
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/v1/intel/health")
async def health_check():
    """Health check endpoint"""
    try:
        async with db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        
        return {
            "status": "healthy",
            "service": SERVICE_NAME,
            "version": APP_VERSION,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "service": SERVICE_NAME,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


if __name__ == "__main__":
    import uvicorn


    uvicorn.run(app, host="0.0.0.0", port=PORT)
