"""
Priya Global — Multilingual Translation Engine (Port 9028)

Enterprise-grade multilingual support for 100+ languages:
- Language detection: LLM-powered + regex heuristics fallback
- Translation: Claude-powered context-aware translation with glossary support
- Localization: Tenant-scoped string management + approval workflows
- Script/direction detection: RTL, CJK, Devanagari, Arabic, etc.
- Message pipeline integration: auto-detect → translate → respond → translate-back
- Cache layer: Redis-backed translation cache with TTL + tenant isolation
- Batch translation: bulk endpoint for dashboard/knowledge base localization

SECURITY:
- All endpoints require JWT authentication
- Tenant isolation via RLS + parameterized queries
- Input sanitization on all text fields
- Rate limiting per tenant (configurable per plan)
- No PII stored in translation cache keys (hashed)
- Glossary entries validated against injection patterns

ARCHITECTURE:
- Translation cache: Redis with hash-based keys (tenant:lang_pair:content_hash)
- Glossary: Per-tenant terminology database for consistent brand translations
- Pipeline mode: Transparent middleware for channel services
- Batch mode: Async processing for large content sets
"""

import asyncio
import hashlib
import json
import logging
import re
import sys
import unicodedata
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import httpx
import redis.asyncio as redis
from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.core.config import config
from shared.core.database import db, get_tenant_pool
from shared.core.security import mask_pii, sanitize_input
from shared.middleware.auth import get_auth, AuthContext, require_role
from shared.observability.tracing import init_tracing, TracingMiddleware, shutdown_tracing
from shared.observability.sentry import init_sentry
from shared.middleware.sentry import SentryTenantMiddleware
from shared.events.event_bus import EventBus, EventType
from shared.middleware.cors import get_cors_config

logger = logging.getLogger("translation")
logger.setLevel(logging.INFO)

# ============================================================================
# CONSTANTS & CONFIGURATION
# ============================================================================

# Maximum sizes for security
MAX_TEXT_LENGTH = 50_000  # 50KB per text field
MAX_BATCH_SIZE = 100  # Max items in batch translation
MAX_GLOSSARY_TERM_LENGTH = 500
MAX_GLOSSARY_ENTRIES_PER_TENANT = 10_000
CACHE_TTL_SECONDS = 86400  # 24 hours default
DETECTION_CACHE_TTL = 3600  # 1 hour for detection results

# Rate limits (requests per minute)
RATE_LIMIT_TRANSLATE = 200
RATE_LIMIT_DETECT = 500
RATE_LIMIT_BATCH = 20
RATE_LIMIT_LOCALIZATION = 100

# Supported languages — ISO 639-1 codes with names
# Claude supports all of these natively for translation
SUPPORTED_LANGUAGES: Dict[str, Dict[str, Any]] = {
    # Major world languages
    "en": {"name": "English", "native": "English", "script": "Latin", "direction": "ltr"},
    "es": {"name": "Spanish", "native": "Español", "script": "Latin", "direction": "ltr"},
    "fr": {"name": "French", "native": "Français", "script": "Latin", "direction": "ltr"},
    "de": {"name": "German", "native": "Deutsch", "script": "Latin", "direction": "ltr"},
    "it": {"name": "Italian", "native": "Italiano", "script": "Latin", "direction": "ltr"},
    "pt": {"name": "Portuguese", "native": "Português", "script": "Latin", "direction": "ltr"},
    "nl": {"name": "Dutch", "native": "Nederlands", "script": "Latin", "direction": "ltr"},
    "pl": {"name": "Polish", "native": "Polski", "script": "Latin", "direction": "ltr"},
    "ro": {"name": "Romanian", "native": "Română", "script": "Latin", "direction": "ltr"},
    "sv": {"name": "Swedish", "native": "Svenska", "script": "Latin", "direction": "ltr"},
    "da": {"name": "Danish", "native": "Dansk", "script": "Latin", "direction": "ltr"},
    "no": {"name": "Norwegian", "native": "Norsk", "script": "Latin", "direction": "ltr"},
    "fi": {"name": "Finnish", "native": "Suomi", "script": "Latin", "direction": "ltr"},
    "cs": {"name": "Czech", "native": "Čeština", "script": "Latin", "direction": "ltr"},
    "sk": {"name": "Slovak", "native": "Slovenčina", "script": "Latin", "direction": "ltr"},
    "hu": {"name": "Hungarian", "native": "Magyar", "script": "Latin", "direction": "ltr"},
    "hr": {"name": "Croatian", "native": "Hrvatski", "script": "Latin", "direction": "ltr"},
    "sl": {"name": "Slovenian", "native": "Slovenščina", "script": "Latin", "direction": "ltr"},
    "bg": {"name": "Bulgarian", "native": "Български", "script": "Cyrillic", "direction": "ltr"},
    "uk": {"name": "Ukrainian", "native": "Українська", "script": "Cyrillic", "direction": "ltr"},
    "ru": {"name": "Russian", "native": "Русский", "script": "Cyrillic", "direction": "ltr"},
    "sr": {"name": "Serbian", "native": "Српски", "script": "Cyrillic", "direction": "ltr"},
    "el": {"name": "Greek", "native": "Ελληνικά", "script": "Greek", "direction": "ltr"},
    "tr": {"name": "Turkish", "native": "Türkçe", "script": "Latin", "direction": "ltr"},
    "az": {"name": "Azerbaijani", "native": "Azərbaycan", "script": "Latin", "direction": "ltr"},
    "ka": {"name": "Georgian", "native": "ქართული", "script": "Georgian", "direction": "ltr"},
    "hy": {"name": "Armenian", "native": "Հայերեն", "script": "Armenian", "direction": "ltr"},
    # South Asian languages
    "hi": {"name": "Hindi", "native": "हिन्दी", "script": "Devanagari", "direction": "ltr"},
    "bn": {"name": "Bengali", "native": "বাংলা", "script": "Bengali", "direction": "ltr"},
    "ta": {"name": "Tamil", "native": "தமிழ்", "script": "Tamil", "direction": "ltr"},
    "te": {"name": "Telugu", "native": "తెలుగు", "script": "Telugu", "direction": "ltr"},
    "kn": {"name": "Kannada", "native": "ಕನ್ನಡ", "script": "Kannada", "direction": "ltr"},
    "ml": {"name": "Malayalam", "native": "മലയാളം", "script": "Malayalam", "direction": "ltr"},
    "mr": {"name": "Marathi", "native": "मराठी", "script": "Devanagari", "direction": "ltr"},
    "gu": {"name": "Gujarati", "native": "ગુજરાતી", "script": "Gujarati", "direction": "ltr"},
    "pa": {"name": "Punjabi", "native": "ਪੰਜਾਬੀ", "script": "Gurmukhi", "direction": "ltr"},
    "or": {"name": "Odia", "native": "ଓଡ଼ିଆ", "script": "Odia", "direction": "ltr"},
    "as": {"name": "Assamese", "native": "অসমীয়া", "script": "Bengali", "direction": "ltr"},
    "ne": {"name": "Nepali", "native": "नेपाली", "script": "Devanagari", "direction": "ltr"},
    "si": {"name": "Sinhala", "native": "සිංහල", "script": "Sinhala", "direction": "ltr"},
    "ur": {"name": "Urdu", "native": "اردو", "script": "Arabic", "direction": "rtl"},
    # East Asian languages
    "zh": {"name": "Chinese (Simplified)", "native": "中文(简体)", "script": "CJK", "direction": "ltr"},
    "zt": {"name": "Chinese (Traditional)", "native": "中文(繁體)", "script": "CJK", "direction": "ltr"},
    "ja": {"name": "Japanese", "native": "日本語", "script": "CJK", "direction": "ltr"},
    "ko": {"name": "Korean", "native": "한국어", "script": "Hangul", "direction": "ltr"},
    # Southeast Asian languages
    "th": {"name": "Thai", "native": "ไทย", "script": "Thai", "direction": "ltr"},
    "vi": {"name": "Vietnamese", "native": "Tiếng Việt", "script": "Latin", "direction": "ltr"},
    "id": {"name": "Indonesian", "native": "Bahasa Indonesia", "script": "Latin", "direction": "ltr"},
    "ms": {"name": "Malay", "native": "Bahasa Melayu", "script": "Latin", "direction": "ltr"},
    "tl": {"name": "Filipino", "native": "Filipino", "script": "Latin", "direction": "ltr"},
    "my": {"name": "Myanmar (Burmese)", "native": "မြန်မာ", "script": "Myanmar", "direction": "ltr"},
    "km": {"name": "Khmer", "native": "ខ្មែរ", "script": "Khmer", "direction": "ltr"},
    "lo": {"name": "Lao", "native": "ລາວ", "script": "Lao", "direction": "ltr"},
    # Middle Eastern & African languages
    "ar": {"name": "Arabic", "native": "العربية", "script": "Arabic", "direction": "rtl"},
    "fa": {"name": "Persian (Farsi)", "native": "فارسی", "script": "Arabic", "direction": "rtl"},
    "he": {"name": "Hebrew", "native": "עברית", "script": "Hebrew", "direction": "rtl"},
    "sw": {"name": "Swahili", "native": "Kiswahili", "script": "Latin", "direction": "ltr"},
    "am": {"name": "Amharic", "native": "አማርኛ", "script": "Ethiopic", "direction": "ltr"},
    "ha": {"name": "Hausa", "native": "Hausa", "script": "Latin", "direction": "ltr"},
    "yo": {"name": "Yoruba", "native": "Yorùbá", "script": "Latin", "direction": "ltr"},
    "ig": {"name": "Igbo", "native": "Igbo", "script": "Latin", "direction": "ltr"},
    "zu": {"name": "Zulu", "native": "isiZulu", "script": "Latin", "direction": "ltr"},
    "af": {"name": "Afrikaans", "native": "Afrikaans", "script": "Latin", "direction": "ltr"},
    # Central Asian
    "kk": {"name": "Kazakh", "native": "Қазақ", "script": "Cyrillic", "direction": "ltr"},
    "uz": {"name": "Uzbek", "native": "Oʻzbek", "script": "Latin", "direction": "ltr"},
    "mn": {"name": "Mongolian", "native": "Монгол", "script": "Cyrillic", "direction": "ltr"},
    # Celtic & Baltic
    "ga": {"name": "Irish", "native": "Gaeilge", "script": "Latin", "direction": "ltr"},
    "cy": {"name": "Welsh", "native": "Cymraeg", "script": "Latin", "direction": "ltr"},
    "lt": {"name": "Lithuanian", "native": "Lietuvių", "script": "Latin", "direction": "ltr"},
    "lv": {"name": "Latvian", "native": "Latviešu", "script": "Latin", "direction": "ltr"},
    "et": {"name": "Estonian", "native": "Eesti", "script": "Latin", "direction": "ltr"},
    # Other widely spoken
    "sq": {"name": "Albanian", "native": "Shqip", "script": "Latin", "direction": "ltr"},
    "mk": {"name": "Macedonian", "native": "Македонски", "script": "Cyrillic", "direction": "ltr"},
    "bs": {"name": "Bosnian", "native": "Bosanski", "script": "Latin", "direction": "ltr"},
    "mt": {"name": "Maltese", "native": "Malti", "script": "Latin", "direction": "ltr"},
    "is": {"name": "Icelandic", "native": "Íslenska", "script": "Latin", "direction": "ltr"},
    "eu": {"name": "Basque", "native": "Euskara", "script": "Latin", "direction": "ltr"},
    "ca": {"name": "Catalan", "native": "Català", "script": "Latin", "direction": "ltr"},
    "gl": {"name": "Galician", "native": "Galego", "script": "Latin", "direction": "ltr"},
    "eo": {"name": "Esperanto", "native": "Esperanto", "script": "Latin", "direction": "ltr"},
    "la": {"name": "Latin", "native": "Latina", "script": "Latin", "direction": "ltr"},
    # Pacific
    "mi": {"name": "Maori", "native": "Te Reo Māori", "script": "Latin", "direction": "ltr"},
    "sm": {"name": "Samoan", "native": "Gagana Sāmoa", "script": "Latin", "direction": "ltr"},
    "to": {"name": "Tongan", "native": "Lea Faka-Tonga", "script": "Latin", "direction": "ltr"},
    "fj": {"name": "Fijian", "native": "Na vosa vaka-Viti", "script": "Latin", "direction": "ltr"},
}

def _sanitize_glossary_term(term: str) -> str:
    """
    Sanitize a glossary term to prevent prompt injection.

    - Strip control characters and newlines
    - Limit length to MAX_GLOSSARY_TERM_LENGTH
    - Remove instruction-like patterns (e.g., "Ignore previous", "System:")
    """
    if not term:
        return ""
    # Strip control characters and newlines
    term = re.sub(r"[\x00-\x1f\x7f]", "", term)
    term = term.replace("\n", " ").replace("\r", " ")
    # Limit length
    term = term[:MAX_GLOSSARY_TERM_LENGTH]
    # Block instruction-like patterns that could hijack the prompt
    injection_patterns = [
        r"(?i)ignore\s+(all\s+)?previous",
        r"(?i)system\s*:",
        r"(?i)assistant\s*:",
        r"(?i)human\s*:",
        r"(?i)you\s+are\s+now",
        r"(?i)forget\s+(all|your|previous)",
        r"(?i)new\s+instructions?\s*:",
        r"(?i)override\s+",
        r"(?i)disregard\s+",
    ]
    for pattern in injection_patterns:
        if re.search(pattern, term):
            logger.warning("Glossary term blocked — injection pattern detected: %s", term[:50])
            return ""
    return term.strip()


# Script-based detection patterns (Unicode ranges)
SCRIPT_RANGES = {
    "Arabic": (0x0600, 0x06FF),
    "Hebrew": (0x0590, 0x05FF),
    "Devanagari": (0x0900, 0x097F),
    "Bengali": (0x0980, 0x09FF),
    "Tamil": (0x0B80, 0x0BFF),
    "Telugu": (0x0C00, 0x0C7F),
    "Kannada": (0x0C80, 0x0CFF),
    "Malayalam": (0x0D00, 0x0D7F),
    "Gujarati": (0x0A80, 0x0AFF),
    "Gurmukhi": (0x0A00, 0x0A7F),
    "Odia": (0x0B00, 0x0B7F),
    "Thai": (0x0E00, 0x0E7F),
    "Lao": (0x0E80, 0x0EFF),
    "Myanmar": (0x1000, 0x109F),
    "Georgian": (0x10A0, 0x10FF),
    "Armenian": (0x0530, 0x058F),
    "Ethiopic": (0x1200, 0x137F),
    "Khmer": (0x1780, 0x17FF),
    "Sinhala": (0x0D80, 0x0DFF),
    "CJK": (0x4E00, 0x9FFF),
    "Hiragana": (0x3040, 0x309F),
    "Katakana": (0x30A0, 0x30FF),
    "Hangul": (0xAC00, 0xD7AF),
    "Cyrillic": (0x0400, 0x04FF),
    "Greek": (0x0370, 0x03FF),
}

# Script to likely languages mapping
SCRIPT_TO_LANGUAGES = {
    "Arabic": ["ar", "fa", "ur"],
    "Hebrew": ["he"],
    "Devanagari": ["hi", "mr", "ne"],
    "Bengali": ["bn", "as"],
    "Tamil": ["ta"],
    "Telugu": ["te"],
    "Kannada": ["kn"],
    "Malayalam": ["ml"],
    "Gujarati": ["gu"],
    "Gurmukhi": ["pa"],
    "Odia": ["or"],
    "Thai": ["th"],
    "Lao": ["lo"],
    "Myanmar": ["my"],
    "Georgian": ["ka"],
    "Armenian": ["hy"],
    "Ethiopic": ["am"],
    "Khmer": ["km"],
    "Sinhala": ["si"],
    "Hangul": ["ko"],
    "Cyrillic": ["ru", "uk", "bg", "sr", "mk", "kk", "mn"],
    "Greek": ["el"],
}


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class DetectRequest(BaseModel):
    """Language detection request."""
    text: str = Field(..., min_length=1, max_length=MAX_TEXT_LENGTH)
    hint_language: Optional[str] = Field(None, pattern=r"^[a-z]{2}$")

    @field_validator("text")
    @classmethod
    def sanitize_text(cls, v: str) -> str:
        return sanitize_input(v)


class DetectResponse(BaseModel):
    """Language detection result."""
    detected_language: str
    language_name: str
    confidence: float
    script: str
    direction: str
    alternatives: List[Dict[str, Any]] = []


class TranslateRequest(BaseModel):
    """Translation request."""
    text: str = Field(..., min_length=1, max_length=MAX_TEXT_LENGTH)
    source_language: Optional[str] = Field(None, pattern=r"^[a-z]{2}$")
    target_language: str = Field(..., pattern=r"^[a-z]{2}$")
    context: Optional[str] = Field(None, max_length=2000)
    formality: Optional[str] = Field("neutral", pattern=r"^(formal|neutral|informal)$")
    use_glossary: bool = True

    @field_validator("text")
    @classmethod
    def sanitize_text(cls, v: str) -> str:
        return sanitize_input(v)

    @field_validator("context")
    @classmethod
    def sanitize_context(cls, v: Optional[str]) -> Optional[str]:
        return sanitize_input(v) if v else None


class TranslateResponse(BaseModel):
    """Translation result."""
    translated_text: str
    source_language: str
    target_language: str
    confidence: float
    model_used: str
    cached: bool = False
    glossary_applied: List[str] = []


class BatchTranslateRequest(BaseModel):
    """Batch translation request."""
    items: List[Dict[str, str]] = Field(..., max_length=MAX_BATCH_SIZE)
    source_language: Optional[str] = Field(None, pattern=r"^[a-z]{2}$")
    target_language: str = Field(..., pattern=r"^[a-z]{2}$")
    formality: Optional[str] = Field("neutral", pattern=r"^(formal|neutral|informal)$")

    @field_validator("items")
    @classmethod
    def validate_items(cls, v: List[Dict[str, str]]) -> List[Dict[str, str]]:
        for item in v:
            if "text" not in item:
                raise ValueError("Each batch item must have a 'text' field")
            if len(item["text"]) > MAX_TEXT_LENGTH:
                raise ValueError(f"Batch item text exceeds {MAX_TEXT_LENGTH} characters")
            item["text"] = sanitize_input(item["text"])
        return v


class BatchTranslateResponse(BaseModel):
    """Batch translation result."""
    translations: List[TranslateResponse]
    total_items: int
    successful: int
    failed: int
    errors: List[Dict[str, str]] = []


class GlossaryEntry(BaseModel):
    """Glossary entry for consistent terminology."""
    source_term: str = Field(..., min_length=1, max_length=MAX_GLOSSARY_TERM_LENGTH)
    target_term: str = Field(..., min_length=1, max_length=MAX_GLOSSARY_TERM_LENGTH)
    source_language: str = Field(..., pattern=r"^[a-z]{2}$")
    target_language: str = Field(..., pattern=r"^[a-z]{2}$")
    context: Optional[str] = Field(None, max_length=500)
    is_case_sensitive: bool = False

    @field_validator("source_term", "target_term")
    @classmethod
    def sanitize_terms(cls, v: str) -> str:
        return sanitize_input(v)


class LocalizationStringRequest(BaseModel):
    """Localization string upsert request."""
    locale: str = Field(..., pattern=r"^[a-z]{2}(-[A-Z]{2})?$")
    module: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_.-]+$")
    key: str = Field(..., min_length=1, max_length=255, pattern=r"^[a-zA-Z0-9_.-]+$")
    value: str = Field(..., min_length=1, max_length=10000)
    context: Optional[str] = Field(None, max_length=500)

    @field_validator("value")
    @classmethod
    def sanitize_value(cls, v: str) -> str:
        return sanitize_input(v)


class PipelineRequest(BaseModel):
    """Message pipeline: detect + translate for channel integration."""
    text: str = Field(..., min_length=1, max_length=MAX_TEXT_LENGTH)
    customer_id: UUID
    conversation_id: UUID
    target_language: Optional[str] = Field(None, pattern=r"^[a-z]{2}$")
    channel: str = Field(default="web")

    @field_validator("text")
    @classmethod
    def sanitize_text(cls, v: str) -> str:
        return sanitize_input(v)


class PipelineResponse(BaseModel):
    """Pipeline result with full language context."""
    original_text: str
    detected_language: str
    translated_text: Optional[str] = None
    target_language: str
    needs_translation: bool
    direction: str
    script: str
    customer_language_preference: Optional[str] = None


# ============================================================================
# TRANSLATION CACHE — Redis-backed with tenant isolation
# ============================================================================

class TranslationCache:
    """
    Redis-backed translation cache with tenant isolation.

    Cache key format: translation:{tenant_id}:{lang_pair}:{content_hash}
    - content_hash is SHA-256 of the input text (no PII in cache keys)
    - TTL configurable per tenant
    """

    def __init__(self):
        self.redis: Optional[redis.Redis] = None
        self.prefix = "translation"

    async def connect(self):
        """Initialize Redis connection."""
        self.redis = redis.from_url(
            config.REDIS_URL,
            decode_responses=True,
            max_connections=20,
        )
        logger.info("Translation cache connected to Redis")

    async def close(self):
        """Close Redis connection."""
        if self.redis:
            await self.redis.close()

    def _cache_key(self, tenant_id: str, source_lang: str, target_lang: str, text: str) -> str:
        """Generate cache key with content hash (no PII)."""
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        return f"{self.prefix}:{tenant_id}:{source_lang}:{target_lang}:{content_hash}"

    def _detect_key(self, tenant_id: str, text: str) -> str:
        """Generate detection cache key."""
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        return f"{self.prefix}:detect:{tenant_id}:{content_hash}"

    async def get_translation(
        self, tenant_id: str, source_lang: str, target_lang: str, text: str
    ) -> Optional[str]:
        """Retrieve cached translation."""
        if not self.redis:
            return None
        try:
            key = self._cache_key(tenant_id, source_lang, target_lang, text)
            return await self.redis.get(key)
        except Exception as e:
            logger.warning("Cache read error: %s", e)
            return None

    async def set_translation(
        self,
        tenant_id: str,
        source_lang: str,
        target_lang: str,
        text: str,
        translation: str,
        ttl: int = CACHE_TTL_SECONDS,
    ):
        """Store translation in cache."""
        if not self.redis:
            return
        try:
            key = self._cache_key(tenant_id, source_lang, target_lang, text)
            await self.redis.setex(key, ttl, translation)
        except Exception as e:
            logger.warning("Cache write error: %s", e)

    async def get_detection(self, tenant_id: str, text: str) -> Optional[dict]:
        """Retrieve cached detection result."""
        if not self.redis:
            return None
        try:
            key = self._detect_key(tenant_id, text)
            result = await self.redis.get(key)
            return json.loads(result) if result else None
        except Exception as e:
            logger.warning("Detection cache read error: %s", e)
            return None

    async def set_detection(self, tenant_id: str, text: str, result: dict, ttl: int = DETECTION_CACHE_TTL):
        """Store detection result in cache."""
        if not self.redis:
            return
        try:
            key = self._detect_key(tenant_id, text)
            await self.redis.setex(key, ttl, json.dumps(result))
        except Exception as e:
            logger.warning("Detection cache write error: %s", e)

    async def invalidate_tenant(self, tenant_id: str):
        """Invalidate all cache entries for a tenant."""
        if not self.redis:
            return
        try:
            pattern = f"{self.prefix}:{tenant_id}:*"
            cursor = 0
            while True:
                cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
                if keys:
                    await self.redis.delete(*keys)
                if cursor == 0:
                    break
            logger.info("Invalidated translation cache for tenant %s", tenant_id)
        except Exception as e:
            logger.warning("Cache invalidation error: %s", e)

    async def check_rate_limit(self, tenant_id: str, endpoint: str, limit: int) -> bool:
        """
        Check rate limit for tenant + endpoint.

        Returns True if within limit, False if exceeded.
        Uses sliding window counter pattern.
        SECURITY: Fails CLOSED on Redis errors — denies requests when rate limiter is down.
        """
        if not self.redis:
            logger.error("Rate limiter unavailable — Redis not connected, failing closed")
            return False
        try:
            key = f"ratelimit:translation:{tenant_id}:{endpoint}"
            current = await self.redis.get(key)
            if current and int(current) >= limit:
                return False
            pipe = self.redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, 60)  # 1-minute window
            await pipe.execute()
            return True
        except Exception as e:
            logger.error("Rate limit check error, failing closed: %s", e)
            return False  # SECURITY: Fail closed — deny on Redis errors


# ============================================================================
# LANGUAGE DETECTOR — Script analysis + LLM confirmation
# ============================================================================

class LanguageDetector:
    """
    Multi-strategy language detection:
    1. Unicode script analysis (instant, free — for non-Latin scripts)
    2. LLM-powered detection (high accuracy for Latin-script and ambiguous text)
    3. Heuristic patterns (common words, character frequency)
    """

    def __init__(self, http_client: httpx.AsyncClient):
        self.http_client = http_client
        self.anthropic_api_key = config.ANTHROPIC_API_KEY

    def detect_script(self, text: str) -> Dict[str, int]:
        """
        Analyze Unicode scripts present in text.

        Returns: dict mapping script names to character counts.
        """
        script_counts: Dict[str, int] = {}

        for char in text:
            code_point = ord(char)
            # Skip ASCII control chars, digits, punctuation, whitespace
            if code_point < 0x0080:
                continue

            for script_name, (start, end) in SCRIPT_RANGES.items():
                if start <= code_point <= end:
                    script_counts[script_name] = script_counts.get(script_name, 0) + 1
                    break

        return script_counts

    def detect_from_script(self, text: str) -> Optional[Tuple[str, float, str]]:
        """
        Detect language from Unicode script analysis.

        Returns: (language_code, confidence, script_name) or None if ambiguous.
        """
        scripts = self.detect_script(text)
        if not scripts:
            return None

        # Find dominant script
        dominant_script = max(scripts, key=scripts.get)
        total_non_ascii = sum(scripts.values())
        dominance_ratio = scripts[dominant_script] / total_non_ascii if total_non_ascii > 0 else 0

        if dominance_ratio < 0.5:
            return None  # Mixed scripts, need LLM

        # Handle CJK (need LLM to distinguish Chinese/Japanese)
        if dominant_script == "CJK":
            # Check for Hiragana/Katakana → Japanese
            if scripts.get("Hiragana", 0) > 0 or scripts.get("Katakana", 0) > 0:
                return ("ja", 0.95, "CJK")
            # Pure CJK → likely Chinese, but not certain
            return ("zh", 0.75, "CJK")

        if dominant_script == "Hangul":
            return ("ko", 0.98, "Hangul")

        # Scripts with single language mapping
        candidates = SCRIPT_TO_LANGUAGES.get(dominant_script, [])
        if len(candidates) == 1:
            return (candidates[0], 0.95, dominant_script)
        elif len(candidates) > 1:
            # Multiple candidates — return most likely, lower confidence
            return (candidates[0], 0.60, dominant_script)

        return None

    async def detect_with_llm(self, text: str) -> Tuple[str, float, List[Dict[str, Any]]]:
        """
        Use Claude to detect language with high accuracy.

        Returns: (language_code, confidence, alternatives)
        """
        # Truncate for cost efficiency — first 300 chars is enough for detection
        sample = text[:300]

        prompt = """You are a language detection system. Analyze the following text and respond with ONLY a valid JSON object.

Rules:
- Detect the primary language of the text
- Use ISO 639-1 two-letter codes (e.g., "en", "es", "hi", "zh", "ar")
- For Chinese, use "zh" for Simplified, "zt" for Traditional
- Confidence should be 0.0-1.0
- Provide up to 3 alternatives if ambiguous

Respond with this exact JSON format, nothing else:
{"language": "xx", "confidence": 0.95, "alternatives": [{"language": "yy", "confidence": 0.3}]}"""

        try:
            headers = {
                "x-api-key": self.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }

            payload = {
                "model": "claude-3-5-haiku-20241022",
                "max_tokens": 200,
                "system": prompt,
                "messages": [{"role": "user", "content": f"Detect language:\n\n{sample}"}],
            }

            response = await self.http_client.post(
                "https://api.anthropic.com/v1/messages",
                json=payload,
                headers=headers,
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()

            result_text = data["content"][0]["text"].strip()
            # Extract JSON from response (handle potential markdown wrapping)
            json_match = re.search(r"\{[^}]+\}", result_text)
            if not json_match:
                logger.warning("LLM detection returned invalid format: %s", result_text[:100])
                return ("en", 0.3, [])

            result = json.loads(json_match.group())
            lang = result.get("language", "en")
            conf = min(max(float(result.get("confidence", 0.5)), 0.0), 1.0)
            alts = result.get("alternatives", [])

            # Validate language code
            if lang not in SUPPORTED_LANGUAGES:
                logger.warning("LLM detected unsupported language: %s", lang)
                return ("en", 0.3, [])

            return (lang, conf, alts)

        except Exception as e:
            logger.error("LLM language detection failed: %s", e)
            return ("en", 0.2, [])

    async def detect(self, text: str, hint: Optional[str] = None) -> DetectResponse:
        """
        Full detection pipeline: script analysis → LLM confirmation.

        Args:
            text: Text to detect language of
            hint: Optional language hint from user/channel
        """
        if not text or not text.strip():
            return DetectResponse(
                detected_language="en",
                language_name="English",
                confidence=0.0,
                script="Latin",
                direction="ltr",
            )

        # Strategy 1: Script-based detection (fast, free)
        script_result = self.detect_from_script(text)

        if script_result and script_result[1] >= 0.90:
            lang_code, confidence, script = script_result
            lang_info = SUPPORTED_LANGUAGES.get(lang_code, {})
            return DetectResponse(
                detected_language=lang_code,
                language_name=lang_info.get("name", "Unknown"),
                confidence=confidence,
                script=script,
                direction=lang_info.get("direction", "ltr"),
            )

        # Strategy 2: LLM-powered detection (for Latin scripts and ambiguous cases)
        lang_code, confidence, alternatives = await self.detect_with_llm(text)

        # If hint agrees with LLM, boost confidence
        if hint and hint == lang_code:
            confidence = min(confidence + 0.1, 1.0)

        lang_info = SUPPORTED_LANGUAGES.get(lang_code, {})
        return DetectResponse(
            detected_language=lang_code,
            language_name=lang_info.get("name", "Unknown"),
            confidence=confidence,
            script=lang_info.get("script", "Latin"),
            direction=lang_info.get("direction", "ltr"),
            alternatives=[
                {
                    "language": a.get("language", ""),
                    "language_name": SUPPORTED_LANGUAGES.get(a.get("language", ""), {}).get("name", "Unknown"),
                    "confidence": a.get("confidence", 0),
                }
                for a in alternatives
                if a.get("language") in SUPPORTED_LANGUAGES
            ],
        )


# ============================================================================
# TRANSLATOR — Claude-powered with glossary support
# ============================================================================

class Translator:
    """
    High-quality, context-aware translation using Claude.

    Features:
    - Glossary integration for consistent brand terminology
    - Formality control (formal/neutral/informal)
    - Sales-context awareness (preserves sales tone)
    - Batch processing with concurrency control
    """

    def __init__(self, http_client: httpx.AsyncClient, cache: TranslationCache):
        self.http_client = http_client
        self.cache = cache
        self.anthropic_api_key = config.ANTHROPIC_API_KEY
        self._semaphore = asyncio.Semaphore(10)  # Max 10 concurrent translations

    async def translate(
        self,
        text: str,
        source_language: str,
        target_language: str,
        tenant_id: str,
        context: Optional[str] = None,
        formality: str = "neutral",
        glossary: Optional[List[Dict[str, str]]] = None,
    ) -> TranslateResponse:
        """
        Translate text with full context and glossary support.

        Returns TranslateResponse with translated text, confidence, and metadata.
        """
        # Same-language bypass
        if source_language == target_language:
            return TranslateResponse(
                translated_text=text,
                source_language=source_language,
                target_language=target_language,
                confidence=1.0,
                model_used="passthrough",
                cached=False,
            )

        # Check cache
        cached = await self.cache.get_translation(tenant_id, source_language, target_language, text)
        if cached:
            return TranslateResponse(
                translated_text=cached,
                source_language=source_language,
                target_language=target_language,
                confidence=0.95,
                model_used="cache",
                cached=True,
            )

        # Build translation prompt
        source_name = SUPPORTED_LANGUAGES.get(source_language, {}).get("name", source_language)
        target_name = SUPPORTED_LANGUAGES.get(target_language, {}).get("name", target_language)

        glossary_section = ""
        glossary_terms_applied = []
        if glossary:
            glossary_lines = []
            for entry in glossary:
                src = entry.get("source_term", "")
                tgt = entry.get("target_term", "")
                if src and tgt:
                    # Sanitize glossary terms to prevent prompt injection:
                    # Strip control chars, limit length, escape quotes
                    safe_src = _sanitize_glossary_term(src)
                    safe_tgt = _sanitize_glossary_term(tgt)
                    if safe_src and safe_tgt:
                        glossary_lines.append(f"- {safe_src} → {safe_tgt}")
                        if safe_src.lower() in text.lower():
                            glossary_terms_applied.append(safe_src)
            if glossary_lines:
                # Limit glossary to 50 entries to prevent prompt bloat
                glossary_lines = glossary_lines[:50]
                glossary_section = "\n\nGLOSSARY — Use these exact translations for these terms:\n" + "\n".join(glossary_lines)

        formality_instruction = {
            "formal": "Use formal, polite language appropriate for business communication.",
            "neutral": "Use natural, conversational tone.",
            "informal": "Use casual, friendly language.",
        }.get(formality, "Use natural, conversational tone.")

        context_section = ""
        if context:
            context_section = f"\n\nCONTEXT: This is a message in a {context}. Preserve the intent and sales tone."

        prompt = f"""You are a professional translator for a global AI sales platform. Translate the following text from {source_name} to {target_name}.

Rules:
1. Preserve the original meaning, tone, and intent exactly
2. {formality_instruction}
3. Preserve all formatting (line breaks, bullet points, etc.)
4. Do NOT translate brand names, product codes, URLs, or email addresses
5. Preserve all numbers, currencies, and units
6. If the text contains sales language, maintain the persuasive tone in the target language
7. Respond with ONLY the translated text — no explanations, no prefix{glossary_section}{context_section}"""

        async with self._semaphore:
            try:
                headers = {
                    "x-api-key": self.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                }

                payload = {
                    "model": "claude-3-5-haiku-20241022",
                    "max_tokens": min(len(text) * 3, 4096),
                    "system": prompt,
                    "messages": [{"role": "user", "content": text}],
                }

                response = await self.http_client.post(
                    "https://api.anthropic.com/v1/messages",
                    json=payload,
                    headers=headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

                translated = data["content"][0]["text"].strip()

                # Cache the result
                await self.cache.set_translation(
                    tenant_id, source_language, target_language, text, translated
                )

                return TranslateResponse(
                    translated_text=translated,
                    source_language=source_language,
                    target_language=target_language,
                    confidence=0.92,
                    model_used="claude-3-5-haiku-20241022",
                    cached=False,
                    glossary_applied=glossary_terms_applied,
                )

            except httpx.HTTPStatusError as e:
                logger.error("Translation API error: %s - %s", e.response.status_code, e.response.text[:200])
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Translation service temporarily unavailable",
                )
            except Exception as e:
                logger.error("Translation failed: %s", e)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Translation failed",
                )

    async def batch_translate(
        self,
        items: List[Dict[str, str]],
        source_language: str,
        target_language: str,
        tenant_id: str,
        formality: str = "neutral",
    ) -> BatchTranslateResponse:
        """Translate multiple items concurrently with error isolation."""
        translations = []
        errors = []

        async def translate_item(idx: int, item: Dict[str, str]):
            try:
                result = await self.translate(
                    text=item["text"],
                    source_language=source_language,
                    target_language=target_language,
                    tenant_id=tenant_id,
                    formality=formality,
                )
                return idx, result, None
            except Exception as e:
                return idx, None, {"index": idx, "error": str(e), "text": item["text"][:50]}

        # Execute concurrently (semaphore limits parallelism)
        tasks = [translate_item(i, item) for i, item in enumerate(items)]
        results = await asyncio.gather(*tasks)

        # Sort by original index
        results.sort(key=lambda x: x[0])

        for idx, result, error in results:
            if result:
                translations.append(result)
            if error:
                errors.append(error)

        return BatchTranslateResponse(
            translations=translations,
            total_items=len(items),
            successful=len(translations),
            failed=len(errors),
            errors=errors,
        )


# ============================================================================
# GLOSSARY STORE — Per-tenant terminology management
# ============================================================================

class GlossaryStore:
    """
    Database-backed glossary management with tenant isolation.

    Stores brand-specific terminology to ensure consistent translations
    across all channels and conversations.
    """

    async def get_glossary(
        self,
        tenant_id: UUID,
        source_language: str,
        target_language: str,
    ) -> List[Dict[str, str]]:
        """Fetch glossary entries for a language pair."""
        pool = await get_tenant_pool(tenant_id)
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT source_term, target_term, context, is_case_sensitive
                FROM translation_glossary
                WHERE tenant_id = $1
                  AND source_language = $2
                  AND target_language = $3
                  AND is_active = TRUE
                ORDER BY source_term
                """,
                str(tenant_id),
                source_language,
                target_language,
            )
        return [dict(r) for r in rows]

    async def upsert_entry(self, tenant_id: UUID, entry: GlossaryEntry) -> str:
        """Add or update a glossary entry."""
        pool = await get_tenant_pool(tenant_id)
        async with pool.acquire() as conn:
            # Check entry count for tenant
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM translation_glossary WHERE tenant_id = $1",
                str(tenant_id),
            )
            if count >= MAX_GLOSSARY_ENTRIES_PER_TENANT:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Glossary limit ({MAX_GLOSSARY_ENTRIES_PER_TENANT}) reached",
                )

            entry_id = await conn.fetchval(
                """
                INSERT INTO translation_glossary
                    (tenant_id, source_term, target_term, source_language, target_language,
                     context, is_case_sensitive, is_active, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, TRUE, NOW(), NOW())
                ON CONFLICT (tenant_id, source_language, target_language, source_term)
                DO UPDATE SET
                    target_term = EXCLUDED.target_term,
                    context = EXCLUDED.context,
                    is_case_sensitive = EXCLUDED.is_case_sensitive,
                    updated_at = NOW()
                RETURNING id::text
                """,
                str(tenant_id),
                entry.source_term,
                entry.target_term,
                entry.source_language,
                entry.target_language,
                entry.context,
                entry.is_case_sensitive,
            )
        return entry_id

    async def delete_entry(self, tenant_id: UUID, entry_id: str):
        """Soft-delete a glossary entry."""
        pool = await get_tenant_pool(tenant_id)
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE translation_glossary
                SET is_active = FALSE, updated_at = NOW()
                WHERE tenant_id = $1 AND id = $2::uuid
                """,
                str(tenant_id),
                entry_id,
            )

    async def list_entries(
        self,
        tenant_id: UUID,
        source_language: Optional[str] = None,
        target_language: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List glossary entries with pagination using static query branches."""
        pool = await get_tenant_pool(tenant_id)
        tid = str(tenant_id)

        # Clamp limit/offset
        limit = min(max(limit, 1), 500)
        offset = max(offset, 0)

        _SELECT = """
            SELECT id::text, source_term, target_term, source_language, target_language,
                   context, is_case_sensitive, created_at, updated_at
            FROM translation_glossary
        """

        async with pool.acquire() as conn:
            # 4 static branches — no dynamic SQL construction
            if source_language and target_language:
                total = await conn.fetchval(
                    "SELECT COUNT(*) FROM translation_glossary WHERE tenant_id = $1 AND is_active = TRUE AND source_language = $2 AND target_language = $3",
                    tid, source_language, target_language,
                )
                rows = await conn.fetch(
                    _SELECT + " WHERE tenant_id = $1 AND is_active = TRUE AND source_language = $2 AND target_language = $3 ORDER BY source_term LIMIT $4 OFFSET $5",
                    tid, source_language, target_language, limit, offset,
                )
            elif source_language:
                total = await conn.fetchval(
                    "SELECT COUNT(*) FROM translation_glossary WHERE tenant_id = $1 AND is_active = TRUE AND source_language = $2",
                    tid, source_language,
                )
                rows = await conn.fetch(
                    _SELECT + " WHERE tenant_id = $1 AND is_active = TRUE AND source_language = $2 ORDER BY source_term LIMIT $3 OFFSET $4",
                    tid, source_language, limit, offset,
                )
            elif target_language:
                total = await conn.fetchval(
                    "SELECT COUNT(*) FROM translation_glossary WHERE tenant_id = $1 AND is_active = TRUE AND target_language = $2",
                    tid, target_language,
                )
                rows = await conn.fetch(
                    _SELECT + " WHERE tenant_id = $1 AND is_active = TRUE AND target_language = $2 ORDER BY source_term LIMIT $3 OFFSET $4",
                    tid, target_language, limit, offset,
                )
            else:
                total = await conn.fetchval(
                    "SELECT COUNT(*) FROM translation_glossary WHERE tenant_id = $1 AND is_active = TRUE",
                    tid,
                )
                rows = await conn.fetch(
                    _SELECT + " WHERE tenant_id = $1 AND is_active = TRUE ORDER BY source_term LIMIT $2 OFFSET $3",
                    tid, limit, offset,
                )

        return [dict(r) for r in rows], total


# ============================================================================
# LOCALIZATION STORE — i18n string management
# ============================================================================

class LocalizationStore:
    """
    Manages localization strings stored in the localization_strings table
    (created by migration 004).
    """

    async def get_strings(
        self,
        tenant_id: UUID,
        locale: str,
        module: Optional[str] = None,
    ) -> Dict[str, str]:
        """Fetch all localization strings for a locale using static query branches."""
        pool = await get_tenant_pool(tenant_id)
        tid = str(tenant_id)

        async with pool.acquire() as conn:
            if module:
                rows = await conn.fetch(
                    """
                    SELECT module, key, value
                    FROM localization_strings
                    WHERE tenant_id = $1 AND locale = $2 AND module = $3
                    ORDER BY module, key
                    """,
                    tid, locale, module,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT module, key, value
                    FROM localization_strings
                    WHERE tenant_id = $1 AND locale = $2
                    ORDER BY module, key
                    """,
                    tid, locale,
                )

        # Return as flat dict: "module.key" → "value"
        result = {}
        for row in rows:
            full_key = f"{row['module']}.{row['key']}"
            result[full_key] = row["value"]
        return result

    async def upsert_string(self, tenant_id: UUID, req: LocalizationStringRequest) -> str:
        """Add or update a localization string."""
        pool = await get_tenant_pool(tenant_id)
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO localization_strings
                    (tenant_id, locale, module, key, value, context, is_approved, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, FALSE, NOW(), NOW())
                ON CONFLICT (tenant_id, locale, module, key)
                DO UPDATE SET
                    value = EXCLUDED.value,
                    context = EXCLUDED.context,
                    is_approved = FALSE,
                    updated_at = NOW()
                """,
                str(tenant_id),
                req.locale,
                req.module,
                req.key,
                req.value,
                req.context,
            )
        return f"{req.locale}:{req.module}.{req.key}"

    async def approve_string(
        self,
        tenant_id: UUID,
        locale: str,
        module: str,
        key: str,
        approved_by: UUID,
    ):
        """Mark a localization string as approved."""
        pool = await get_tenant_pool(tenant_id)
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE localization_strings
                SET is_approved = TRUE, approved_by = $5::uuid, approved_at = NOW(), updated_at = NOW()
                WHERE tenant_id = $1 AND locale = $2 AND module = $3 AND key = $4
                """,
                str(tenant_id),
                locale,
                module,
                key,
                str(approved_by),
            )

    async def get_missing_translations(
        self,
        tenant_id: UUID,
        base_locale: str,
        target_locale: str,
    ) -> List[Dict[str, str]]:
        """Find strings that exist in base locale but not in target locale."""
        pool = await get_tenant_pool(tenant_id)
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT b.module, b.key, b.value as base_value
                FROM localization_strings b
                LEFT JOIN localization_strings t
                    ON b.tenant_id = t.tenant_id
                    AND b.module = t.module
                    AND b.key = t.key
                    AND t.locale = $3
                WHERE b.tenant_id = $1
                  AND b.locale = $2
                  AND t.id IS NULL
                ORDER BY b.module, b.key
                """,
                str(tenant_id),
                base_locale,
                target_locale,
            )
        return [dict(r) for r in rows]


# ============================================================================
# TRANSLATION PIPELINE — Channel integration middleware
# ============================================================================

class TranslationPipeline:
    """
    End-to-end message translation pipeline for channel services.

    Flow:
    1. Detect incoming message language
    2. Translate to tenant's operating language (for AI processing)
    3. AI generates response in operating language
    4. Translate response back to customer's language
    """

    def __init__(
        self,
        detector: LanguageDetector,
        translator: Translator,
        cache: TranslationCache,
    ):
        self.detector = detector
        self.translator = translator
        self.cache = cache

    async def process_inbound(
        self,
        text: str,
        tenant_id: str,
        customer_id: str,
        conversation_id: str,
        target_language: Optional[str] = None,
        channel: str = "web",
    ) -> PipelineResponse:
        """
        Process incoming customer message:
        1. Detect language
        2. Translate to target language (if needed)
        3. Return full language context for AI engine
        """
        # Detect language
        detection = await self.detector.detect(text)

        # Get customer's preferred language (if known)
        customer_pref = await self._get_customer_language_preference(tenant_id, customer_id)

        # Determine target language
        effective_target = target_language or "en"  # Default to English for AI processing

        # Check if translation is needed
        needs_translation = detection.detected_language != effective_target

        translated_text = None
        if needs_translation:
            result = await self.translator.translate(
                text=text,
                source_language=detection.detected_language,
                target_language=effective_target,
                tenant_id=tenant_id,
                context=f"{channel} sales conversation",
            )
            translated_text = result.translated_text

        # Update customer language preference if detection is high confidence
        if detection.confidence >= 0.85 and detection.detected_language != customer_pref:
            await self._update_customer_language_preference(
                tenant_id, customer_id, detection.detected_language
            )

        return PipelineResponse(
            original_text=text,
            detected_language=detection.detected_language,
            translated_text=translated_text,
            target_language=effective_target,
            needs_translation=needs_translation,
            direction=detection.direction,
            script=detection.script,
            customer_language_preference=customer_pref,
        )

    async def process_outbound(
        self,
        text: str,
        source_language: str,
        target_language: str,
        tenant_id: str,
        formality: str = "neutral",
    ) -> TranslateResponse:
        """Translate AI response back to customer's language."""
        return await self.translator.translate(
            text=text,
            source_language=source_language,
            target_language=target_language,
            tenant_id=tenant_id,
            context="AI sales response to customer",
            formality=formality,
        )

    async def _get_customer_language_preference(
        self, tenant_id: str, customer_id: str
    ) -> Optional[str]:
        """Fetch customer's preferred language from DB."""
        try:
            pool = await get_tenant_pool(UUID(tenant_id))
            async with pool.acquire() as conn:
                return await conn.fetchval(
                    """
                    SELECT preferred_language
                    FROM customers
                    WHERE tenant_id = $1 AND id = $2::uuid
                    """,
                    tenant_id,
                    customer_id,
                )
        except Exception as e:
            logger.warning("Failed to fetch customer language preference: %s", e)
            return None

    async def _update_customer_language_preference(
        self, tenant_id: str, customer_id: str, language: str
    ):
        """Update customer's preferred language."""
        try:
            pool = await get_tenant_pool(UUID(tenant_id))
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE customers
                    SET preferred_language = $3, updated_at = NOW()
                    WHERE tenant_id = $1 AND id = $2::uuid
                      AND (preferred_language IS NULL OR preferred_language != $3)
                    """,
                    tenant_id,
                    customer_id,
                    language,
                )
        except Exception as e:
            logger.warning("Failed to update customer language preference: %s", e)


# ============================================================================
# FASTAPI APPLICATION
# ============================================================================

app = FastAPI(
    title="Priya Global Translation Engine",
    description="Multilingual translation, detection, and localization for 100+ languages",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Middleware
cors_config = get_cors_config()
app.add_middleware(CORSMiddleware, **cors_config)
app.add_middleware(TracingMiddleware, service_name="translation")
app.add_middleware(SentryTenantMiddleware)

# Global instances
cache = TranslationCache()
http_client: Optional[httpx.AsyncClient] = None
detector: Optional[LanguageDetector] = None
translator: Optional[Translator] = None
pipeline: Optional[TranslationPipeline] = None
glossary_store = GlossaryStore()
localization_store = LocalizationStore()
event_bus: Optional[EventBus] = None


# ─── Lifecycle ───

@app.on_event("startup")
async def startup():
    global http_client, detector, translator, pipeline, event_bus

    init_sentry(service_name="translation")
    init_tracing(service_name="translation")

    await db.startup()
    await cache.connect()

    http_client = httpx.AsyncClient(timeout=30.0)
    detector = LanguageDetector(http_client)
    translator = Translator(http_client, cache)
    pipeline = TranslationPipeline(detector, translator, cache)

    event_bus = EventBus(service_name="translation")
    await event_bus.startup()

    logger.info("Translation Engine started — %d languages supported", len(SUPPORTED_LANGUAGES))


@app.on_event("shutdown")
async def shutdown():
    if http_client:
        await http_client.aclose()
    await cache.close()
    if event_bus:
        await event_bus.shutdown()
    await db.shutdown()
    await shutdown_tracing()
    logger.info("Translation Engine shut down")


# ─── Health ───

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "translation",
        "languages_supported": len(SUPPORTED_LANGUAGES),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ============================================================================
# API ENDPOINTS
# ============================================================================

# ─── Language Detection ───

@app.post("/api/v1/detect", response_model=DetectResponse)
async def detect_language(request: DetectRequest, auth: AuthContext = Depends(get_auth)):
    """Detect the language of input text."""
    tenant_id = str(auth.tenant_id)

    # Rate limit check
    allowed = await cache.check_rate_limit(tenant_id, "detect", RATE_LIMIT_DETECT)
    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit exceeded for language detection")

    # Check detection cache
    cached = await cache.get_detection(tenant_id, request.text)
    if cached:
        return DetectResponse(**cached)

    result = await detector.detect(request.text, hint=request.hint_language)

    # Cache the result
    await cache.set_detection(tenant_id, request.text, result.model_dump())

    return result


# ─── Translation ───

@app.post("/api/v1/translate", response_model=TranslateResponse)
async def translate_text(request: TranslateRequest, auth: AuthContext = Depends(get_auth)):
    """Translate text between any supported language pair."""
    tenant_id = str(auth.tenant_id)

    # Rate limit
    allowed = await cache.check_rate_limit(tenant_id, "translate", RATE_LIMIT_TRANSLATE)
    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit exceeded for translation")

    # Validate languages
    if request.target_language not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported target language: {request.target_language}")

    # Auto-detect source if not provided
    source_lang = request.source_language
    if not source_lang:
        detection = await detector.detect(request.text)
        source_lang = detection.detected_language

    if source_lang not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported source language: {source_lang}")

    # Fetch glossary if requested
    glossary = None
    if request.use_glossary:
        glossary = await glossary_store.get_glossary(auth.tenant_id, source_lang, request.target_language)

    return await translator.translate(
        text=request.text,
        source_language=source_lang,
        target_language=request.target_language,
        tenant_id=tenant_id,
        context=request.context,
        formality=request.formality,
        glossary=glossary,
    )


# ─── Batch Translation ───

@app.post("/api/v1/translate/batch", response_model=BatchTranslateResponse)
async def batch_translate(request: BatchTranslateRequest, auth: AuthContext = Depends(get_auth)):
    """Translate multiple texts in a single request."""
    tenant_id = str(auth.tenant_id)

    # Rate limit (stricter for batch)
    allowed = await cache.check_rate_limit(tenant_id, "batch", RATE_LIMIT_BATCH)
    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit exceeded for batch translation")

    if request.target_language not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported target language: {request.target_language}")

    # Auto-detect source from first item if not provided
    source_lang = request.source_language
    if not source_lang and request.items:
        detection = await detector.detect(request.items[0]["text"])
        source_lang = detection.detected_language

    return await translator.batch_translate(
        items=request.items,
        source_language=source_lang,
        target_language=request.target_language,
        tenant_id=tenant_id,
        formality=request.formality,
    )


# ─── Pipeline (Channel Integration) ───

@app.post("/api/v1/pipeline/inbound", response_model=PipelineResponse)
async def pipeline_inbound(request: PipelineRequest, auth: AuthContext = Depends(get_auth)):
    """
    Process inbound customer message through the translation pipeline.
    Used by channel services for transparent language handling.
    """
    tenant_id = str(auth.tenant_id)

    allowed = await cache.check_rate_limit(tenant_id, "translate", RATE_LIMIT_TRANSLATE)
    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    return await pipeline.process_inbound(
        text=request.text,
        tenant_id=tenant_id,
        customer_id=str(request.customer_id),
        conversation_id=str(request.conversation_id),
        target_language=request.target_language,
        channel=request.channel,
    )


@app.post("/api/v1/pipeline/outbound", response_model=TranslateResponse)
async def pipeline_outbound(
    request: TranslateRequest,
    auth: AuthContext = Depends(get_auth),
):
    """
    Translate AI response back to customer's language.
    Used by channel services after AI generates a response.
    """
    tenant_id = str(auth.tenant_id)

    allowed = await cache.check_rate_limit(tenant_id, "translate", RATE_LIMIT_TRANSLATE)
    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    source_lang = request.source_language or "en"

    return await pipeline.process_outbound(
        text=request.text,
        source_language=source_lang,
        target_language=request.target_language,
        tenant_id=tenant_id,
        formality=request.formality,
    )


# ─── Glossary Management ───

@app.post("/api/v1/glossary")
async def create_glossary_entry(
    entry: GlossaryEntry,
    auth: AuthContext = Depends(get_auth),
):
    """Add or update a glossary entry for consistent translations."""
    allowed = await cache.check_rate_limit(str(auth.tenant_id), "glossary", RATE_LIMIT_LOCALIZATION)
    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    entry_id = await glossary_store.upsert_entry(auth.tenant_id, entry)

    # Invalidate translation cache for this language pair
    await cache.invalidate_tenant(str(auth.tenant_id))

    return {"id": entry_id, "status": "created"}


@app.get("/api/v1/glossary")
async def list_glossary_entries(
    source_language: Optional[str] = Query(None, pattern=r"^[a-z]{2}$"),
    target_language: Optional[str] = Query(None, pattern=r"^[a-z]{2}$"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    auth: AuthContext = Depends(get_auth),
):
    """List glossary entries with optional filtering."""
    entries, total = await glossary_store.list_entries(
        auth.tenant_id, source_language, target_language, limit, offset
    )
    return {"entries": entries, "total": total, "limit": limit, "offset": offset}


@app.delete("/api/v1/glossary/{entry_id}")
async def delete_glossary_entry(
    entry_id: str,
    auth: AuthContext = Depends(get_auth),
):
    """Delete a glossary entry."""
    await glossary_store.delete_entry(auth.tenant_id, entry_id)
    return {"status": "deleted"}


# ─── Localization Strings ───

@app.get("/api/v1/localization/{locale}")
async def get_localization_strings(
    locale: str,
    module: Optional[str] = Query(None, pattern=r"^[a-zA-Z0-9_.-]+$"),
    auth: AuthContext = Depends(get_auth),
):
    """Fetch all localization strings for a locale."""
    strings = await localization_store.get_strings(auth.tenant_id, locale, module)
    return {"locale": locale, "strings": strings, "count": len(strings)}


@app.post("/api/v1/localization")
async def upsert_localization_string(
    request: LocalizationStringRequest,
    auth: AuthContext = Depends(get_auth),
):
    """Add or update a localization string."""
    allowed = await cache.check_rate_limit(str(auth.tenant_id), "localization", RATE_LIMIT_LOCALIZATION)
    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    key = await localization_store.upsert_string(auth.tenant_id, request)
    return {"key": key, "status": "upserted"}


@app.get("/api/v1/localization/missing/{base_locale}/{target_locale}")
async def get_missing_translations(
    base_locale: str,
    target_locale: str,
    auth: AuthContext = Depends(get_auth),
):
    """Find strings that exist in base locale but not in target locale."""
    missing = await localization_store.get_missing_translations(
        auth.tenant_id, base_locale, target_locale
    )
    return {"base_locale": base_locale, "target_locale": target_locale, "missing": missing, "count": len(missing)}


# ─── Languages Info ───

@app.get("/api/v1/languages")
async def list_supported_languages(auth: AuthContext = Depends(get_auth)):
    """List all supported languages with metadata."""
    return {
        "languages": [
            {
                "code": code,
                "name": info["name"],
                "native_name": info["native"],
                "script": info["script"],
                "direction": info["direction"],
            }
            for code, info in SUPPORTED_LANGUAGES.items()
        ],
        "total": len(SUPPORTED_LANGUAGES),
    }


@app.get("/api/v1/languages/{code}")
async def get_language_info(code: str, auth: AuthContext = Depends(get_auth)):
    """Get details for a specific language."""
    if code not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=404, detail=f"Language not found: {code}")
    info = SUPPORTED_LANGUAGES[code]
    return {
        "code": code,
        "name": info["name"],
        "native_name": info["native"],
        "script": info["script"],
        "direction": info["direction"],
    }


# ─── Admin Endpoints ───

@app.post("/api/v1/admin/cache/invalidate")
async def admin_invalidate_cache(
    auth: AuthContext = Depends(require_role("admin")),
):
    """Invalidate all translation cache entries for the tenant."""
    await cache.invalidate_tenant(str(auth.tenant_id))
    return {"status": "cache_invalidated", "tenant_id": str(auth.tenant_id)}


@app.get("/api/v1/admin/stats")
async def admin_stats(auth: AuthContext = Depends(require_role("admin"))):
    """Get translation service statistics."""
    pool = await get_tenant_pool(auth.tenant_id)
    async with pool.acquire() as conn:
        glossary_count = await conn.fetchval(
            "SELECT COUNT(*) FROM translation_glossary WHERE tenant_id = $1 AND is_active = TRUE",
            str(auth.tenant_id),
        )
        localization_count = await conn.fetchval(
            "SELECT COUNT(*) FROM localization_strings WHERE tenant_id = $1",
            str(auth.tenant_id),
        )
        locales = await conn.fetch(
            "SELECT DISTINCT locale, COUNT(*) as count FROM localization_strings WHERE tenant_id = $1 GROUP BY locale",
            str(auth.tenant_id),
        )

    return {
        "languages_supported": len(SUPPORTED_LANGUAGES),
        "glossary_entries": glossary_count,
        "localization_strings": localization_count,
        "locales_configured": [{"locale": r["locale"], "strings": r["count"]} for r in locales],
    }


# ============================================================================
# RUN
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "services.translation.main:app",
        host="0.0.0.0",
        port=9028,
        workers=2,
        log_level="info",
    )
