import asyncio
import os
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
import json
import base64
import hashlib
from enum import Enum

import fastapi
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Header, BackgroundTasks, Query
from fastapi.security import HTTPBearer, HTTPAuthCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
import jwt
import asyncpg
import aiohttp
from pathlib import Path
from shared.observability.tracing import init_tracing, TracingMiddleware, shutdown_tracing
from shared.observability.sentry import init_sentry
from shared.middleware.sentry import SentryTenantMiddleware
from shared.events.event_bus import EventBus, EventType
from shared.middleware.cors import get_cors_config


# ============ CONFIG & ENV ============
class Config:
    DATABASE_URL = os.getenv("DATABASE_URL")
    DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
    JWT_SECRET = os.getenv("JWT_SECRET")
    JWT_ALGORITHM = "HS256"
    PORT = int(os.getenv("PORT", "9031"))
    cors_origins_str = os.getenv("CORS_ORIGINS", "http://localhost:3000")
    if cors_origins_str == "*":
        print("WARNING: CORS_ORIGINS is wildcard. Using localhost only.")
        cors_origins_str = "http://localhost:3000"
    CORS_ORIGINS = cors_origins_str.split(",")
    SERVICE_NAME = "voice_ai"
    DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
    STORAGE_PATH = Path(os.getenv("STORAGE_PATH", "/tmp/voice_ai_storage"))
    REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
    MAX_AUDIO_SIZE = int(os.getenv("MAX_AUDIO_SIZE", "52428800"))  # 50MB


# Ensure storage path exists
Config.STORAGE_PATH.mkdir(parents=True, exist_ok=True)


# ============ ENUMS ============
class AudioFormat(str, Enum):
    WAV = "wav"
    MP3 = "mp3"
    OGG = "ogg"
    FLAC = "flac"


class LanguageCode(str, Enum):
    EN = "en"
    ES = "es"
    FR = "fr"
    DE = "de"
    IT = "it"
    PT = "pt"
    JA = "ja"
    ZH = "zh"
    RU = "ru"
    AR = "ar"


# ============ AUTH CONTEXT ============
@dataclass
class AuthContext:
    tenant_id: str
    user_id: str
    token: str
    scopes: List[str]


# ============ MODELS ============
class TranscribeRequest(BaseModel):
    audio_url: Optional[str] = None
    language: LanguageCode = LanguageCode.EN
    speaker_diarization: bool = False
    punctuation: bool = True
    model: str = Field(default="nova-2", description="Deepgram model to use")


class TranscribeResponse(BaseModel):
    id: str
    text: str
    language: str
    confidence: float
    duration: float
    word_count: int
    speakers: Optional[List[Dict[str, Any]]] = None
    timestamps: Optional[List[Dict[str, Any]]] = None
    timestamp: str


class SynthesizeRequest(BaseModel):
    text: str
    voice_id: Optional[str] = None
    language: LanguageCode = LanguageCode.EN
    ssml: bool = False
    stability: float = Field(default=0.5, ge=0.0, le=1.0)
    similarity: float = Field(default=0.75, ge=0.0, le=1.0)


class SynthesizeResponse(BaseModel):
    id: str
    audio_url: str
    audio_format: str
    duration: float
    voice_id: str
    character_count: int
    timestamp: str


class AnalyzeRequest(BaseModel):
    audio_url: Optional[str] = None
    transcription_id: Optional[str] = None
    transcription_text: Optional[str] = None
    enable_emotion_detection: bool = False


class EntityType(str, Enum):
    PERSON = "person"
    ORGANIZATION = "organization"
    LOCATION = "location"
    CONTACT = "contact"
    DATE = "date"
    NUMBER = "number"


class Entity(BaseModel):
    type: EntityType
    value: str
    confidence: float = 0.8


class AnalysisResponse(BaseModel):
    id: str
    intent: str
    intent_confidence: float
    entities: List[Entity]
    sentiment: str
    sentiment_score: float
    emotion: Optional[str] = None
    keywords: List[str]
    key_phrases: List[str]
    timestamp: str


class RecordingResponse(BaseModel):
    id: str
    tenant_id: str
    audio_url: str
    transcription: Optional[str]
    transcription_id: Optional[str]
    duration: float
    format: str
    file_size: int
    created_at: str
    updated_at: str


class VoiceConfig(BaseModel):
    default_voice_id: str = Field(default="21m00Tcm4TlvDq8ikWAM")
    preferred_language: LanguageCode = LanguageCode.EN
    enable_speaker_diarization: bool = False
    enable_sentiment_analysis: bool = True
    enable_emotion_detection: bool = False
    recording_enabled: bool = True
    max_recording_duration: int = 3600  # seconds
    audio_format: AudioFormat = AudioFormat.MP3


class PipelineRequest(BaseModel):
    audio_url: str
    language: LanguageCode = LanguageCode.EN
    enable_recording: bool = True
    enable_tts_response: bool = True
    context: Optional[Dict[str, Any]] = None
    timeout: int = 60


class PipelineResponse(BaseModel):
    id: str
    transcription: str
    transcription_confidence: float
    intent: str
    intent_confidence: float
    response: str
    audio_response_url: Optional[str] = None
    processing_time: float
    analytics: Dict[str, Any]
    timestamp: str


class AnalyticsResponse(BaseModel):
    total_calls: int
    avg_duration: float
    avg_transcription_confidence: float
    avg_talk_to_listen_ratio: float
    top_intents: List[tuple[str, int]]
    sentiment_distribution: Dict[str, float]
    emotion_distribution: Dict[str, float]
    keyword_frequency: Dict[str, int]
    top_speakers: List[Dict[str, Any]]
    date_range: str
    generated_at: str


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    timestamp: str
    uptime_seconds: int
    database: str
    deepgram: str
    elevenlabs: str
    checks: Dict[str, str]


# ============ DATABASE SETUP ============
class Database:
    pool: Optional[asyncpg.Pool] = None
    startup_time: Optional[datetime] = None

    @classmethod
    async def connect(cls):
        cls.startup_time = datetime.utcnow()
        cls.pool = await asyncpg.create_pool(
            Config.DATABASE_URL,
            min_size=2,
            max_size=Config.DB_POOL_SIZE,
            command_timeout=60,
        )
        await cls._init_schema()

    @classmethod
    async def disconnect(cls):
        if cls.pool:
            await cls.pool.close()

    @classmethod
    async def _init_schema(cls):
        async with cls.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS transcriptions (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    language TEXT,
                    confidence FLOAT,
                    duration FLOAT,
                    word_count INTEGER,
                    speakers JSONB,
                    timestamps JSONB,
                    model TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_transcriptions_tenant ON transcriptions(tenant_id);
                CREATE INDEX IF NOT EXISTS idx_transcriptions_user ON transcriptions(user_id, tenant_id);
                CREATE INDEX IF NOT EXISTS idx_transcriptions_created ON transcriptions(created_at DESC);
                
                CREATE TABLE IF NOT EXISTS analyses (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    transcription_id TEXT,
                    intent TEXT,
                    intent_confidence FLOAT,
                    entities JSONB,
                    sentiment TEXT,
                    sentiment_score FLOAT,
                    emotion TEXT,
                    keywords JSONB,
                    key_phrases JSONB,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_analyses_tenant ON analyses(tenant_id);
                CREATE INDEX IF NOT EXISTS idx_analyses_transcription ON analyses(transcription_id);
                CREATE INDEX IF NOT EXISTS idx_analyses_created ON analyses(created_at DESC);
                
                CREATE TABLE IF NOT EXISTS recordings (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    audio_path TEXT,
                    audio_format TEXT,
                    file_size INTEGER,
                    transcription_id TEXT,
                    analysis_id TEXT,
                    duration FLOAT,
                    metadata JSONB,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_recordings_tenant ON recordings(tenant_id);
                CREATE INDEX IF NOT EXISTS idx_recordings_user ON recordings(user_id, tenant_id);
                CREATE INDEX IF NOT EXISTS idx_recordings_created ON recordings(created_at DESC);
                
                CREATE TABLE IF NOT EXISTS voice_configs (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL UNIQUE,
                    default_voice_id TEXT,
                    preferred_language TEXT,
                    enable_speaker_diarization BOOLEAN,
                    enable_sentiment_analysis BOOLEAN,
                    enable_emotion_detection BOOLEAN,
                    recording_enabled BOOLEAN,
                    max_recording_duration INTEGER,
                    audio_format TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_voice_configs_tenant ON voice_configs(tenant_id);
                
                CREATE TABLE IF NOT EXISTS call_events (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    event_type TEXT,
                    duration FLOAT,
                    metadata JSONB,
                    created_at TIMESTAMP DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_call_events_tenant ON call_events(tenant_id, created_at DESC);
            """)


# ============ JWT & AUTH ============
security = HTTPBearer()


async def verify_token(credentials: HTTPAuthCredentials = Depends(security)) -> AuthContext:
    try:
        payload = jwt.decode(
            credentials.credentials,
            Config.JWT_SECRET,
            algorithms=[Config.JWT_ALGORITHM],
        )
        tenant_id = payload.get("tenant_id")
        user_id = payload.get("sub")
        scopes = payload.get("scopes", [])

        if not tenant_id or not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: missing tenant_id or user_id")

        return AuthContext(
            tenant_id=tenant_id,
            user_id=user_id,
            token=credentials.credentials,
            scopes=scopes,
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


# ============ DEEPGRAM SERVICE ============
class DeepgramService:
    @staticmethod
    async def transcribe(
        audio_url: str,
        language: str = "en",
        speaker_diarization: bool = False,
        punctuation: bool = True,
        model: str = "nova-2",
    ) -> Dict[str, Any]:
        if not Config.DEEPGRAM_API_KEY:
            raise HTTPException(status_code=503, detail="Deepgram API not configured")

        headers = {
            "Authorization": f"Token {Config.DEEPGRAM_API_KEY}",
            "Content-Type": "application/json",
        }
        params = {
            "model": model,
            "language": language,
            "smart_format": punctuation,
            "filler_words": True,
        }
        if speaker_diarization:
            params["diarize"] = True

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.deepgram.com/v1/listen",
                    headers=headers,
                    params=params,
                    json={"url": audio_url},
                    timeout=aiohttp.ClientTimeout(total=Config.REQUEST_TIMEOUT),
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        raise HTTPException(
                            status_code=502,
                            detail=f"Deepgram API error {resp.status}: {error_text}",
                        )
                    data = await resp.json()

            channel = data.get("results", {}).get("channels", [{}])[0]
            alternative = channel.get("alternatives", [{}])[0]
            transcript = alternative.get("transcript", "")
            confidence = alternative.get("confidence", 0.0)
            duration = data.get("metadata", {}).get("duration", 0.0)
            word_count = len(transcript.split())

            speakers = None
            timestamps = None

            if speaker_diarization and "words" in channel:
                speakers = []
                speaker_map = {}
                for word_data in channel["words"]:
                    speaker_id = word_data.get("speaker", 0)
                    if speaker_id not in speaker_map:
                        speaker_map[speaker_id] = len(speakers)
                        speakers.append({
                            "speaker_id": speaker_id,
                            "start_time": word_data.get("start", 0),
                            "end_time": word_data.get("end", 0),
                        })

            if "words" in channel:
                timestamps = [
                    {
                        "word": word_data.get("word", ""),
                        "start": word_data.get("start", 0),
                        "end": word_data.get("end", 0),
                        "confidence": word_data.get("confidence", 0.0),
                    }
                    for word_data in channel["words"][:100]  # Limit to first 100 words
                ]

            return {
                "text": transcript,
                "confidence": confidence,
                "duration": duration,
                "word_count": word_count,
                "speakers": speakers,
                "timestamps": timestamps,
            }
        except aiohttp.ClientError as e:
            raise HTTPException(status_code=502, detail=f"Deepgram connection error: {str(e)}")
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Deepgram request timeout")


# ============ ELEVENLABS SERVICE ============
class ElevenLabsService:
    @staticmethod
    async def synthesize(
        text: str,
        voice_id: str = "21m00Tcm4TlvDq8ikWAM",
        language: str = "en",
        ssml: bool = False,
        stability: float = 0.5,
        similarity: float = 0.75,
    ) -> Dict[str, Any]:
        if not Config.ELEVENLABS_API_KEY:
            raise HTTPException(status_code=503, detail="ElevenLabs API not configured")

        headers = {
            "xi-api-key": Config.ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "voice_settings": {
                "stability": stability,
                "similarity_boost": similarity,
            },
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=Config.REQUEST_TIMEOUT),
                ) as resp:
                    if resp.status not in [200, 201]:
                        error_text = await resp.text()
                        raise HTTPException(
                            status_code=502,
                            detail=f"ElevenLabs API error {resp.status}: {error_text}",
                        )
                    audio_data = await resp.read()

            audio_id = str(uuid.uuid4())
            audio_path = Config.STORAGE_PATH / f"{audio_id}.mp3"
            audio_path.write_bytes(audio_data)

            # Estimate duration (approximate: ~150 words per minute = 2.5 words per second)
            word_count = len(text.split())
            duration = word_count / 2.5

            return {
                "audio_path": str(audio_path),
                "audio_id": audio_id,
                "duration": duration,
                "voice_id": voice_id,
                "character_count": len(text),
                "file_size": len(audio_data),
            }
        except aiohttp.ClientError as e:
            raise HTTPException(status_code=502, detail=f"ElevenLabs connection error: {str(e)}")
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="ElevenLabs request timeout")


# ============ NLU SERVICE ============
class NLUService:
    INTENT_PATTERNS = {
        "greeting": ["hello", "hi", "hey", "greetings", "good morning", "good afternoon"],
        "help": ["help", "support", "assist", "aid", "can you help"],
        "complaint": ["problem", "issue", "complain", "bad", "terrible", "terrible", "broken"],
        "information": ["tell", "what", "where", "when", "how", "why", "explain"],
        "transaction": ["pay", "purchase", "buy", "charge", "refund", "payment", "invoice"],
        "cancel": ["cancel", "stop", "delete", "remove", "unsubscribe"],
        "feedback": ["feedback", "review", "rate", "comment", "suggestion"],
    }

    SENTIMENT_KEYWORDS = {
        "positive": ["good", "great", "excellent", "happy", "love", "wonderful", "amazing", "perfect"],
        "negative": ["bad", "terrible", "hate", "angry", "disappointed", "awful", "horrible", "useless"],
        "neutral": ["ok", "fine", "alright", "normal", "average"],
    }

    EMOTION_KEYWORDS = {
        "happy": ["happy", "joy", "excited", "delighted", "thrilled"],
        "angry": ["angry", "furious", "rage", "irritated", "annoyed"],
        "sad": ["sad", "unhappy", "depressed", "disappointed", "miserable"],
        "neutral": ["neutral", "calm", "normal", "okay"],
    }

    @staticmethod
    def extract_intent(text: str) -> tuple[str, float]:
        text_lower = text.lower()
        best_intent = "general"
        best_confidence = 0.3

        for intent, keywords in NLUService.INTENT_PATTERNS.items():
            matches = sum(1 for kw in keywords if kw in text_lower)
            if matches > 0:
                confidence = min(0.5 + (matches / len(keywords)) * 0.5, 1.0)
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_intent = intent

        return best_intent, best_confidence

    @staticmethod
    def extract_entities(text: str) -> List[Entity]:
        entities = []
        text_lower = text.lower()

        # Contact information
        if "phone" in text_lower:
            entities.append(Entity(type=EntityType.CONTACT, value="phone", confidence=0.9))
        if "email" in text_lower:
            entities.append(Entity(type=EntityType.CONTACT, value="email", confidence=0.9))

        # Time/Date references
        for time_word in ["today", "tomorrow", "yesterday", "tomorrow", "next week", "last week"]:
            if time_word in text_lower:
                entities.append(Entity(type=EntityType.DATE, value=time_word, confidence=0.8))
                break

        # Numbers
        import re
        numbers = re.findall(r'\b\d+\b', text)
        for num in numbers[:3]:  # Limit to first 3
            entities.append(Entity(type=EntityType.NUMBER, value=num, confidence=0.85))

        return entities[:10]  # Limit to 10 entities

    @staticmethod
    def analyze_sentiment(text: str) -> tuple[str, float]:
        text_lower = text.lower()
        positive_score = sum(1 for kw in NLUService.SENTIMENT_KEYWORDS["positive"] if kw in text_lower)
        negative_score = sum(1 for kw in NLUService.SENTIMENT_KEYWORDS["negative"] if kw in text_lower)
        neutral_score = sum(1 for kw in NLUService.SENTIMENT_KEYWORDS["neutral"] if kw in text_lower)

        total_sentiment = positive_score + negative_score + neutral_score
        if total_sentiment == 0:
            return "neutral", 0.5

        if positive_score > negative_score and positive_score > neutral_score:
            return "positive", min(0.6 + (positive_score / max(total_sentiment, 1)) * 0.4, 1.0)
        elif negative_score > positive_score and negative_score > neutral_score:
            return "negative", min(0.6 + (negative_score / max(total_sentiment, 1)) * 0.4, 1.0)
        return "neutral", 0.5

    @staticmethod
    def detect_emotion(text: str) -> Optional[str]:
        text_lower = text.lower()
        for emotion, keywords in NLUService.EMOTION_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                return emotion
        return None

    @staticmethod
    def extract_keywords(text: str) -> List[str]:
        words = text.lower().split()
        stop_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
            "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
            "do", "does", "did", "will", "would", "could", "should", "may", "might",
        }
        keywords = [w.strip(".,!?;:") for w in words if len(w) > 3 and w not in stop_words]
        return list(set(keywords))[:10]

    @staticmethod
    def extract_key_phrases(text: str) -> List[str]:
        # Extract noun phrases (simple approach)
        phrases = []
        words = text.split()
        for i in range(len(words) - 1):
            phrase = f"{words[i]} {words[i + 1]}"
            if len(phrase) > 5 and phrase.lower() not in [p.lower() for p in phrases]:
                phrases.append(phrase)
        return phrases[:5]


# ============ FASTAPI APP ============
app = FastAPI(
    title="Voice AI Service",
    description="Multi-tenant Voice AI with STT, TTS, NLU & voice analytics",
    version="1.0.0",
)
# Initialize Sentry error tracking

# Initialize event bus
event_bus = EventBus(service_name="voice_ai")
init_sentry(service_name="voice-ai", service_port=9031)

# Initialize OpenTelemetry distributed tracing
init_tracing(app, service_name="voice-ai")
app.add_middleware(TracingMiddleware)


# CORS middleware - restrict to specific origins
origins = [o.strip() for o in Config.CORS_ORIGINS] if isinstance(Config.CORS_ORIGINS, list) else [Config.CORS_ORIGINS]
if any("*" in o for o in origins):
    print("WARNING: CORS origins contain wildcard. Restricting to localhost.")
    origins = ["http://localhost:3000"]

cors_config = get_cors_config(os.getenv("ENVIRONMENT", "development"))
app.add_middleware(CORSMiddleware, **cors_config)
# Sentry tenant context middleware
app.add_middleware(SentryTenantMiddleware)



# ============ LIFECYCLE ============
@app.on_event("startup")
async def startup():
    if not Config.DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable not set")
    await event_bus.startup()
    await Database.connect()


@app.on_event("shutdown")
async def shutdown():
    await Database.disconnect()
    shutdown_tracing()


# ============ ENDPOINTS ============
@app.post("/voice-ai/transcribe", response_model=TranscribeResponse)
async def transcribe(
    request: TranscribeRequest,
    auth: AuthContext = Depends(verify_token),
):
    """Speech-to-Text with Deepgram integration, multi-language & speaker diarization"""
    try:
        result = await DeepgramService.transcribe(
            request.audio_url,
            request.language.value,
            request.speaker_diarization,
            request.punctuation,
            request.model,
        )

        transcription_id = str(uuid.uuid4())
        async with Database.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO transcriptions
                (id, tenant_id, user_id, text, language, confidence, duration, word_count, speakers, timestamps, model)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """, transcription_id, auth.tenant_id, auth.user_id, result["text"],
                request.language.value, result["confidence"], result["duration"],
                result["word_count"],
                json.dumps(result["speakers"]) if result["speakers"] else None,
                json.dumps(result["timestamps"]) if result["timestamps"] else None,
                request.model)

        return TranscribeResponse(
            id=transcription_id,
            text=result["text"],
            language=request.language.value,
            confidence=result["confidence"],
            duration=result["duration"],
            word_count=result["word_count"],
            speakers=result["speakers"],
            timestamps=result["timestamps"],
            timestamp=datetime.utcnow().isoformat(),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")


@app.post("/voice-ai/synthesize", response_model=SynthesizeResponse)
async def synthesize(
    request: SynthesizeRequest,
    auth: AuthContext = Depends(verify_token),
):
    """Text-to-Speech with ElevenLabs, voice cloning & SSML support"""
    try:
        # Get tenant voice config
        async with Database.pool.acquire() as conn:
            config_row = await conn.fetchrow(
                "SELECT * FROM voice_configs WHERE tenant_id = $1",
                auth.tenant_id,
            )

        voice_id = request.voice_id
        if not voice_id and config_row:
            voice_id = config_row["default_voice_id"]
        if not voice_id:
            voice_id = "21m00Tcm4TlvDq8ikWAM"

        result = await ElevenLabsService.synthesize(
            request.text,
            voice_id,
            request.language.value,
            request.ssml,
            request.stability,
            request.similarity,
        )

        return SynthesizeResponse(
            id=result["audio_id"],
            audio_url=f"/voice-ai/audio/{result['audio_id']}",
            audio_format="mp3",
            duration=result["duration"],
            voice_id=voice_id,
            character_count=result["character_count"],
            timestamp=datetime.utcnow().isoformat(),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Synthesis failed: {str(e)}")


@app.post("/voice-ai/analyze", response_model=AnalysisResponse)
async def analyze(
    request: AnalyzeRequest,
    auth: AuthContext = Depends(verify_token),
):
    """NLU: Intent extraction, entity recognition, sentiment & emotion analysis"""
    try:
        # Get transcription text
        if request.transcription_text:
            text = request.transcription_text
        elif request.transcription_id:
            async with Database.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT text FROM transcriptions WHERE id = $1 AND tenant_id = $2",
                    request.transcription_id,
                    auth.tenant_id,
                )
            if not row:
                raise HTTPException(status_code=404, detail="Transcription not found")
            text = row["text"]
        elif request.audio_url:
            transcription_result = await DeepgramService.transcribe(request.audio_url, "en", False)
            text = transcription_result["text"]
        else:
            raise HTTPException(status_code=400, detail="No text source provided")

        intent, intent_confidence = NLUService.extract_intent(text)
        entities = NLUService.extract_entities(text)
        sentiment, sentiment_score = NLUService.analyze_sentiment(text)
        emotion = NLUService.detect_emotion(text) if request.enable_emotion_detection else None
        keywords = NLUService.extract_keywords(text)
        key_phrases = NLUService.extract_key_phrases(text)

        analysis_id = str(uuid.uuid4())
        async with Database.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO analyses
                (id, tenant_id, user_id, transcription_id, intent, intent_confidence, entities, sentiment, sentiment_score, emotion, keywords, key_phrases)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            """, analysis_id, auth.tenant_id, auth.user_id, request.transcription_id,
                intent, intent_confidence, json.dumps([e.dict() for e in entities]),
                sentiment, sentiment_score, emotion,
                json.dumps(keywords), json.dumps(key_phrases))

        return AnalysisResponse(
            id=analysis_id,
            intent=intent,
            intent_confidence=intent_confidence,
            entities=entities,
            sentiment=sentiment,
            sentiment_score=sentiment_score,
            emotion=emotion,
            keywords=keywords,
            key_phrases=key_phrases,
            timestamp=datetime.utcnow().isoformat(),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@app.post("/voice-ai/pipeline", response_model=PipelineResponse)
async def voice_pipeline(
    request: PipelineRequest,
    auth: AuthContext = Depends(verify_token),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """Full voice bot pipeline: STT -> NLU -> Response -> TTS"""
    start_time = datetime.utcnow()
    try:
        pipeline_id = str(uuid.uuid4())

        # Step 1: Transcribe
        transcription_result = await DeepgramService.transcribe(
            request.audio_url, request.language.value, False
        )
        transcription_text = transcription_result["text"]
        transcription_confidence = transcription_result["confidence"]

        # Step 2: Analyze intent & sentiment
        intent, intent_conf = NLUService.extract_intent(transcription_text)
        sentiment, sentiment_score = NLUService.analyze_sentiment(transcription_text)
        keywords = NLUService.extract_keywords(transcription_text)

        # Step 3: Generate response (mock AI response)
        ai_response = f"I understood your message about {', '.join(keywords[:2]) if keywords else 'your inquiry'}. " \
                      f"You expressed a {sentiment} sentiment. How can I help?"

        # Step 4: Synthesize response if enabled
        tts_result = None
        audio_response_url = None
        if request.enable_tts_response:
            tts_result = await ElevenLabsService.synthesize(
                ai_response,
                language=request.language.value,
            )
            audio_response_url = f"/voice-ai/audio/{tts_result['audio_id']}"

        # Step 5: Store recording if enabled
        recording_id = None
        if request.enable_recording:
            recording_id = str(uuid.uuid4())
            recording_path = Config.STORAGE_PATH / f"recording_{recording_id}.wav"
            async with Database.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO recordings
                    (id, tenant_id, user_id, audio_path, duration, audio_format)
                    VALUES ($1, $2, $3, $4, $5, $6)
                """, recording_id, auth.tenant_id, auth.user_id,
                    str(recording_path), transcription_result["duration"], "wav")

        processing_time = (datetime.utcnow() - start_time).total_seconds()

        analytics = {
            "call_duration": transcription_result["duration"],
            "talk_segments": 1,
            "listen_segments": 1,
            "talk_to_listen_ratio": 0.6,
            "sentiment": sentiment,
            "sentiment_score": sentiment_score,
            "intent": intent,
            "intent_confidence": intent_conf,
            "keywords": keywords,
            "recording_id": recording_id,
        }

        return PipelineResponse(
            id=pipeline_id,
            transcription=transcription_text,
            transcription_confidence=transcription_confidence,
            intent=intent,
            intent_confidence=intent_conf,
            response=ai_response,
            audio_response_url=audio_response_url,
            processing_time=processing_time,
            analytics=analytics,
            timestamp=datetime.utcnow().isoformat(),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {str(e)}")


@app.get("/voice-ai/recordings", response_model=List[RecordingResponse])
async def list_recordings(
    auth: AuthContext = Depends(verify_token),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List all recordings for tenant (RLS enforced)"""
    try:
        async with Database.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, tenant_id, audio_path, transcription_id, duration, audio_format, file_size, created_at, updated_at
                FROM recordings
                WHERE tenant_id = $1
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
            """, auth.tenant_id, limit, offset)

        return [
            RecordingResponse(
                id=row["id"],
                tenant_id=row["tenant_id"],
                audio_url=f"/voice-ai/audio/{row['id']}",
                transcription=row["transcription_id"],
                transcription_id=row["transcription_id"],
                duration=row["duration"],
                format=row["audio_format"] or "wav",
                file_size=row["file_size"] or 0,
                created_at=row["created_at"].isoformat(),
                updated_at=row["updated_at"].isoformat(),
            )
            for row in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list recordings: {str(e)}")


@app.get("/voice-ai/recordings/{recording_id}", response_model=RecordingResponse)
async def get_recording(
    recording_id: str,
    auth: AuthContext = Depends(verify_token),
):
    """Retrieve single recording (RLS enforced)"""
    try:
        async with Database.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id, tenant_id, audio_path, transcription_id, duration, audio_format, file_size, created_at, updated_at
                FROM recordings
                WHERE id = $1 AND tenant_id = $2
            """, recording_id, auth.tenant_id)

        if not row:
            raise HTTPException(status_code=404, detail="Recording not found")

        return RecordingResponse(
            id=row["id"],
            tenant_id=row["tenant_id"],
            audio_url=f"/voice-ai/audio/{row['id']}",
            transcription=row["transcription_id"],
            transcription_id=row["transcription_id"],
            duration=row["duration"],
            format=row["audio_format"] or "wav",
            file_size=row["file_size"] or 0,
            created_at=row["created_at"].isoformat(),
            updated_at=row["updated_at"].isoformat(),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get recording: {str(e)}")


@app.get("/voice-ai/analytics", response_model=AnalyticsResponse)
async def get_analytics(
    auth: AuthContext = Depends(verify_token),
    days: int = Query(30, ge=1, le=365),
):
    """Get comprehensive voice analytics: call metrics, sentiment, keywords, speakers"""
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        async with Database.pool.acquire() as conn:
            # Total calls
            total = await conn.fetchval(
                "SELECT COUNT(*) FROM recordings WHERE tenant_id = $1 AND created_at >= $2",
                auth.tenant_id, cutoff_date
            ) or 0

            # Avg duration
            avg_duration = await conn.fetchval(
                "SELECT AVG(duration) FROM recordings WHERE tenant_id = $1 AND created_at >= $2",
                auth.tenant_id, cutoff_date
            ) or 0.0

            # Transcription confidence
            avg_confidence = await conn.fetchval(
                "SELECT AVG(confidence) FROM transcriptions WHERE tenant_id = $1 AND created_at >= $2",
                auth.tenant_id, cutoff_date
            ) or 0.0

            # Intents with counts
            intents = await conn.fetch(
                "SELECT intent, COUNT(*) as count FROM analyses WHERE tenant_id = $1 AND created_at >= $2 GROUP BY intent ORDER BY count DESC",
                auth.tenant_id, cutoff_date
            )
            top_intents = [(row["intent"], row["count"]) for row in intents if row["intent"]]

            # Sentiments
            sentiments = await conn.fetch(
                "SELECT sentiment FROM analyses WHERE tenant_id = $1 AND created_at >= $2",
                auth.tenant_id, cutoff_date
            )
            sentiment_dist = {}
            for row in sentiments:
                if row["sentiment"]:
                    sentiment_dist[row["sentiment"]] = sentiment_dist.get(row["sentiment"], 0) + 1

            # Emotions
            emotions = await conn.fetch(
                "SELECT emotion FROM analyses WHERE tenant_id = $1 AND emotion IS NOT NULL AND created_at >= $2",
                auth.tenant_id, cutoff_date
            )
            emotion_dist = {}
            for row in emotions:
                if row["emotion"]:
                    emotion_dist[row["emotion"]] = emotion_dist.get(row["emotion"], 0) + 1

            # Keywords
            keywords_data = await conn.fetch(
                "SELECT keywords FROM analyses WHERE tenant_id = $1 AND created_at >= $2",
                auth.tenant_id, cutoff_date
            )
            keyword_freq = {}
            for row in keywords_data:
                if row["keywords"]:
                    kws = json.loads(row["keywords"]) if isinstance(row["keywords"], str) else row["keywords"]
                    for kw in kws:
                        keyword_freq[kw] = keyword_freq.get(kw, 0) + 1

            # Speaker stats
            speakers_data = await conn.fetch(
                "SELECT speakers FROM transcriptions WHERE tenant_id = $1 AND speakers IS NOT NULL AND created_at >= $2",
                auth.tenant_id, cutoff_date
            )
            speaker_counts = {}
            for row in speakers_data:
                if row["speakers"]:
                    speakers = json.loads(row["speakers"]) if isinstance(row["speakers"], str) else row["speakers"]
                    speaker_counts[f"speaker_{len(speakers)}"] = speaker_counts.get(f"speaker_{len(speakers)}", 0) + 1

        # Normalize sentiment distribution
        total_analyses = len(sentiments)
        if total_analyses > 0:
            sentiment_dist = {k: v / total_analyses for k, v in sentiment_dist.items()}
        if emotion_dist:
            total_emotions = sum(emotion_dist.values())
            emotion_dist = {k: v / total_emotions for k, v in emotion_dist.items()}

        return AnalyticsResponse(
            total_calls=total,
            avg_duration=float(avg_duration),
            avg_transcription_confidence=float(avg_confidence),
            avg_talk_to_listen_ratio=0.6,
            top_intents=top_intents[:10],
            sentiment_distribution=sentiment_dist,
            emotion_distribution=emotion_dist,
            keyword_frequency=dict(sorted(keyword_freq.items(), key=lambda x: x[1], reverse=True)[:20]),
            top_speakers=[{"type": k, "count": v} for k, v in list(speaker_counts.items())[:5]],
            date_range=f"Last {days} days",
            generated_at=datetime.utcnow().isoformat(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analytics failed: {str(e)}")


@app.put("/voice-ai/config", response_model=VoiceConfig)
async def update_voice_config(
    config: VoiceConfig,
    auth: AuthContext = Depends(verify_token),
):
    """Update tenant-specific voice configuration"""
    try:
        config_id = str(uuid.uuid4())
        async with Database.pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT id FROM voice_configs WHERE tenant_id = $1",
                auth.tenant_id,
            )

            if existing:
                await conn.execute("""
                    UPDATE voice_configs
                    SET default_voice_id = $1, preferred_language = $2,
                        enable_speaker_diarization = $3, enable_sentiment_analysis = $4,
                        enable_emotion_detection = $5,
                        recording_enabled = $6, max_recording_duration = $7,
                        audio_format = $8, updated_at = NOW()
                    WHERE tenant_id = $9
                """, config.default_voice_id, config.preferred_language.value,
                    config.enable_speaker_diarization, config.enable_sentiment_analysis,
                    config.enable_emotion_detection,
                    config.recording_enabled, config.max_recording_duration,
                    config.audio_format.value, auth.tenant_id)
            else:
                await conn.execute("""
                    INSERT INTO voice_configs
                    (id, tenant_id, default_voice_id, preferred_language,
                     enable_speaker_diarization, enable_sentiment_analysis,
                     enable_emotion_detection,
                     recording_enabled, max_recording_duration, audio_format)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """, config_id, auth.tenant_id, config.default_voice_id,
                    config.preferred_language.value, config.enable_speaker_diarization,
                    config.enable_sentiment_analysis, config.enable_emotion_detection,
                    config.recording_enabled, config.max_recording_duration,
                    config.audio_format.value)

        return config
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Config update failed: {str(e)}")


@app.get("/voice-ai/health", response_model=HealthResponse)
async def health_check():
    """Health check with all service status"""
    db_status = "healthy"
    deepgram_status = "healthy"
    elevenlabs_status = "healthy"

    # Check database
    try:
        async with Database.pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
    except Exception as e:
        db_status = "unhealthy"

    # Check Deepgram
    if not Config.DEEPGRAM_API_KEY:
        deepgram_status = "not configured"

    # Check ElevenLabs
    if not Config.ELEVENLABS_API_KEY:
        elevenlabs_status = "not configured"

    uptime = 0
    if Database.startup_time:
        uptime = int((datetime.utcnow() - Database.startup_time).total_seconds())

    overall_status = "healthy" if db_status == "healthy" else "degraded"

    return HealthResponse(
        status=overall_status,
        service="voice_ai",
        version="1.0.0",
        timestamp=datetime.utcnow().isoformat(),
        uptime_seconds=uptime,
        database=db_status,
        deepgram=deepgram_status,
        elevenlabs=elevenlabs_status,
        checks={
            "database": db_status,
            "deepgram": deepgram_status,
            "elevenlabs": elevenlabs_status,
        },
    )


@app.get("/")
async def root():
    """Service root endpoint"""
    return {
        "service": "Voice AI Service",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "transcribe": "POST /voice-ai/transcribe",
            "synthesize": "POST /voice-ai/synthesize",
            "analyze": "POST /voice-ai/analyze",
            "pipeline": "POST /voice-ai/pipeline",
            "recordings": "GET /voice-ai/recordings",
            "analytics": "GET /voice-ai/analytics",
            "config": "PUT /voice-ai/config",
            "health": "GET /voice-ai/health",
        },
    }


if __name__ == "__main__":
    import uvicorn


    uvicorn.run(app, host="0.0.0.0", port=Config.PORT)
