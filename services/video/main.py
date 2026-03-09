import asyncio
import json
import os
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from contextlib import asynccontextmanager

import jwt
import asyncpg
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthCredentials
from pydantic import BaseModel

security = HTTPBearer()


class AuthContext:
    def __init__(self, tenant_id: str, user_id: str, email: str):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.email = email


class VideoSessionRequest(BaseModel):
    title: str
    scheduled_at: Optional[datetime] = None
    max_participants: int = 10
    allow_recording: bool = False


class JoinSessionRequest(BaseModel):
    user_name: str
    accept_recording: bool = True


class RecordingRequest(BaseModel):
    action: str


class ICECandidateMessage(BaseModel):
    type: str = "ice-candidate"
    candidate: str
    sdp_mid: str
    sdp_m_line_index: int


class SDPMessage(BaseModel):
    type: str
    sdp: str


class SignalingMessage(BaseModel):
    type: str
    data: Optional[Dict] = None


db_pool: Optional[asyncpg.Pool] = None
active_connections: Dict[str, Set[WebSocket]] = {}
session_participants: Dict[str, Set[str]] = {}
recording_state: Dict[str, bool] = {}
analytics_data: Dict[str, Dict] = {}


async def get_db():
    return await db_pool.acquire()


async def verify_token(credentials: HTTPAuthCredentials) -> AuthContext:
    jwt_secret = os.getenv("JWT_SECRET")
    if not jwt_secret:
        raise HTTPException(status_code=500, detail="JWT_SECRET not configured")
    
    try:
        payload = jwt.decode(credentials.credentials, jwt_secret, algorithms=["HS256"])
        tenant_id = payload.get("tenant_id")
        user_id = payload.get("user_id")
        email = payload.get("email")
        
        if not all([tenant_id, user_id, email]):
            raise HTTPException(status_code=401, detail="Invalid token claims")
        
        return AuthContext(tenant_id=tenant_id, user_id=user_id, email=email)
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_pool
    
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL not configured")
    
    db_pool = await asyncpg.create_pool(db_url, min_size=5, max_size=20)
    
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS video_sessions (
                id UUID PRIMARY KEY,
                tenant_id UUID NOT NULL,
                title VARCHAR(255) NOT NULL,
                created_by UUID NOT NULL,
                scheduled_at TIMESTAMP,
                started_at TIMESTAMP,
                ended_at TIMESTAMP,
                max_participants INT DEFAULT 10,
                allow_recording BOOLEAN DEFAULT FALSE,
                recording_id UUID,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS session_participants (
                id UUID PRIMARY KEY,
                session_id UUID NOT NULL REFERENCES video_sessions(id) ON DELETE CASCADE,
                tenant_id UUID NOT NULL,
                user_id UUID NOT NULL,
                user_name VARCHAR(255) NOT NULL,
                joined_at TIMESTAMP DEFAULT NOW(),
                left_at TIMESTAMP,
                accept_recording BOOLEAN DEFAULT TRUE
            )
        """)
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS recordings (
                id UUID PRIMARY KEY,
                session_id UUID NOT NULL REFERENCES video_sessions(id) ON DELETE CASCADE,
                tenant_id UUID NOT NULL,
                storage_path VARCHAR(500),
                duration_seconds INT,
                file_size_bytes BIGINT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS analytics (
                id UUID PRIMARY KEY,
                session_id UUID NOT NULL REFERENCES video_sessions(id) ON DELETE CASCADE,
                tenant_id UUID NOT NULL,
                participant_id UUID,
                metric_type VARCHAR(50),
                metric_value FLOAT,
                recorded_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_tenant ON video_sessions(tenant_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_participants_tenant ON session_participants(tenant_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_analytics_tenant ON analytics(tenant_id)
        """)
    
    yield
    
    if db_pool:
        await db_pool.close()


from shared.observability.tracing import init_tracing, TracingMiddleware, shutdown_tracing
from shared.observability.sentry import init_sentry
from shared.middleware.sentry import SentryTenantMiddleware
from shared.events.event_bus import EventBus, EventType
from shared.middleware.cors import get_cors_config

app = FastAPI(title="Video Chat Service", lifespan=lifespan)

# Initialize Sentry error tracking
event_bus = EventBus(service_name="video")
init_sentry(service_name="video", service_port=9032)

# Initialize OpenTelemetry distributed tracing
init_tracing(app, service_name="video")
app.add_middleware(TracingMiddleware)

cors_origins_str = os.getenv("CORS_ORIGINS", "http://localhost:3000")
cors_origins = [origin.strip() for origin in cors_origins_str.split(",")]
if "*" in cors_origins:
    print("ERROR: CORS_ORIGINS contains wildcard (*). This is a security risk.", file=sys.stderr)
    cors_origins = ["http://localhost:3000"]
cors_config = get_cors_config(os.getenv("ENVIRONMENT", "development"))
app.add_middleware(CORSMiddleware, **cors_config)
# Sentry tenant context middleware
app.add_middleware(SentryTenantMiddleware)



@app.post("/video/sessions")
async def create_session(
    request: VideoSessionRequest,
    auth: AuthContext = Depends(verify_token)
) -> Dict:
    session_id = uuid.uuid4()
    recording_id = uuid.uuid4() if request.allow_recording else None
    
    conn = await get_db()
    try:
        await conn.execute("""
            INSERT INTO video_sessions 
            (id, tenant_id, title, created_by, scheduled_at, max_participants, allow_recording, recording_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """, session_id, uuid.UUID(auth.tenant_id) if isinstance(auth.tenant_id, str) else auth.tenant_id,
            request.title, uuid.UUID(auth.user_id) if isinstance(auth.user_id, str) else auth.user_id,
            request.scheduled_at, request.max_participants, request.allow_recording, recording_id)
        
        return {
            "id": str(session_id),
            "title": request.title,
            "created_by": auth.user_id,
            "scheduled_at": request.scheduled_at,
            "max_participants": request.max_participants,
            "allow_recording": request.allow_recording,
            "status": "created"
        }
    finally:
        await db_pool.release(conn)


@app.get("/video/sessions")
async def list_sessions(
    auth: AuthContext = Depends(verify_token),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
) -> Dict:
    conn = await get_db()
    try:
        rows = await conn.fetch("""
            SELECT id, title, created_by, scheduled_at, max_participants, allow_recording, created_at
            FROM video_sessions
            WHERE tenant_id = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
        """, uuid.UUID(auth.tenant_id) if isinstance(auth.tenant_id, str) else auth.tenant_id, limit, offset)
        
        sessions = [
            {
                "id": str(row["id"]),
                "title": row["title"],
                "created_by": str(row["created_by"]),
                "scheduled_at": row["scheduled_at"],
                "max_participants": row["max_participants"],
                "allow_recording": row["allow_recording"],
                "created_at": row["created_at"]
            }
            for row in rows
        ]
        
        return {"sessions": sessions, "count": len(sessions)}
    finally:
        await db_pool.release(conn)


@app.get("/video/sessions/{session_id}")
async def get_session(
    session_id: str,
    auth: AuthContext = Depends(verify_token)
) -> Dict:
    conn = await get_db()
    try:
        row = await conn.fetchrow("""
            SELECT id, title, created_by, scheduled_at, started_at, ended_at, max_participants, allow_recording
            FROM video_sessions
            WHERE id = $1 AND tenant_id = $2
        """, uuid.UUID(session_id), uuid.UUID(auth.tenant_id) if isinstance(auth.tenant_id, str) else auth.tenant_id)
        
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")
        
        participants = await conn.fetch("""
            SELECT user_id, user_name, joined_at, left_at
            FROM session_participants
            WHERE session_id = $1 AND tenant_id = $2
        """, uuid.UUID(session_id), uuid.UUID(auth.tenant_id) if isinstance(auth.tenant_id, str) else auth.tenant_id)
        
        return {
            "id": str(row["id"]),
            "title": row["title"],
            "created_by": str(row["created_by"]),
            "scheduled_at": row["scheduled_at"],
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
            "max_participants": row["max_participants"],
            "allow_recording": row["allow_recording"],
            "participants": [
                {
                    "user_id": str(p["user_id"]),
                    "user_name": p["user_name"],
                    "joined_at": p["joined_at"],
                    "left_at": p["left_at"]
                }
                for p in participants
            ]
        }
    finally:
        await db_pool.release(conn)


@app.post("/video/sessions/{session_id}/join")
async def join_session(
    session_id: str,
    request: JoinSessionRequest,
    auth: AuthContext = Depends(verify_token)
) -> Dict:
    conn = await get_db()
    try:
        session = await conn.fetchrow("""
            SELECT id, max_participants FROM video_sessions
            WHERE id = $1 AND tenant_id = $2
        """, uuid.UUID(session_id), uuid.UUID(auth.tenant_id) if isinstance(auth.tenant_id, str) else auth.tenant_id)
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        participant_count = await conn.fetchval("""
            SELECT COUNT(*) FROM session_participants
            WHERE session_id = $1 AND left_at IS NULL
        """, uuid.UUID(session_id))
        
        if participant_count >= session["max_participants"]:
            raise HTTPException(status_code=400, detail="Session is full")
        
        participant_id = uuid.uuid4()
        await conn.execute("""
            INSERT INTO session_participants
            (id, session_id, tenant_id, user_id, user_name, accept_recording)
            VALUES ($1, $2, $3, $4, $5, $6)
        """, participant_id, uuid.UUID(session_id),
            uuid.UUID(auth.tenant_id) if isinstance(auth.tenant_id, str) else auth.tenant_id,
            uuid.UUID(auth.user_id) if isinstance(auth.user_id, str) else auth.user_id,
            request.user_name, request.accept_recording)
        
        if session_id not in session_participants:
            session_participants[session_id] = set()
        session_participants[session_id].add(auth.user_id)
        
        stun_server = os.getenv("STUN_SERVER", "stun:stun.l.google.com:19302")
        turn_server = os.getenv("TURN_SERVER", "")
        turn_username = os.getenv("TURN_USERNAME", "")
        
        return {
            "participant_id": str(participant_id),
            "session_id": session_id,
            "status": "joined",
            "ice_servers": [
                {"urls": [stun_server]},
                *([{"urls": [turn_server], "username": turn_username, "credential": os.getenv("TURN_PASSWORD", "")}] if turn_server else [])
            ]
        }
    finally:
        await db_pool.release(conn)


@app.post("/video/sessions/{session_id}/leave")
async def leave_session(
    session_id: str,
    auth: AuthContext = Depends(verify_token)
) -> Dict:
    conn = await get_db()
    try:
        await conn.execute("""
            UPDATE session_participants
            SET left_at = NOW()
            WHERE session_id = $1 AND user_id = $2 AND tenant_id = $3
        """, uuid.UUID(session_id), uuid.UUID(auth.user_id) if isinstance(auth.user_id, str) else auth.user_id,
            uuid.UUID(auth.tenant_id) if isinstance(auth.tenant_id, str) else auth.tenant_id)
        
        if session_id in session_participants and auth.user_id in session_participants[session_id]:
            session_participants[session_id].remove(auth.user_id)
        
        return {"status": "left", "session_id": session_id}
    finally:
        await db_pool.release(conn)


@app.post("/video/sessions/{session_id}/record")
async def control_recording(
    session_id: str,
    request: RecordingRequest,
    auth: AuthContext = Depends(verify_token)
) -> Dict:
    conn = await get_db()
    try:
        session = await conn.fetchrow("""
            SELECT id, allow_recording, recording_id FROM video_sessions
            WHERE id = $1 AND tenant_id = $2 AND created_by = $3
        """, uuid.UUID(session_id), uuid.UUID(auth.tenant_id) if isinstance(auth.tenant_id, str) else auth.tenant_id,
            uuid.UUID(auth.user_id) if isinstance(auth.user_id, str) else auth.user_id)
        
        if not session or not session["allow_recording"]:
            raise HTTPException(status_code=400, detail="Recording not allowed for this session")
        
        if request.action == "start":
            recording_state[session_id] = True
            return {"status": "recording_started", "session_id": session_id}
        elif request.action == "stop":
            recording_state[session_id] = False
            duration = 3600
            file_size = 1024 * 1024 * 500
            
            await conn.execute("""
                INSERT INTO recordings (id, session_id, tenant_id, storage_path, duration_seconds, file_size_bytes)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, uuid.uuid4(), uuid.UUID(session_id),
                uuid.UUID(auth.tenant_id) if isinstance(auth.tenant_id, str) else auth.tenant_id,
                f"s3://recordings/{session_id}.mp4", duration, file_size)
            
            return {"status": "recording_stopped", "session_id": session_id}
        else:
            raise HTTPException(status_code=400, detail="Invalid action")
    finally:
        await db_pool.release(conn)


@app.websocket("/ws/signaling")
async def websocket_signaling(websocket: WebSocket, token: str = Query(...)):
    # Verify JWT token BEFORE accepting connection
    try:
        jwt_secret = os.getenv("JWT_SECRET")
        if not jwt_secret:
            await websocket.close(code=1008, reason="JWT_SECRET not configured")
            return

        payload = jwt.decode(token, jwt_secret, algorithms=["HS256"])
        tenant_id = payload.get("tenant_id")
        user_id = payload.get("user_id")

        if not all([tenant_id, user_id]):
            await websocket.close(code=1008, reason="Invalid token claims")
            return

    except jwt.InvalidTokenError:
        await websocket.close(code=1008, reason="Invalid or expired token")
        return

    await websocket.accept()
    session_id = None

    try:
        while True:
            data = await websocket.receive_json()
            message_type = data.get("type")

            if message_type == "auth":
                session_id = data.get("session_id")

                if not session_id:
                    await websocket.send_json({"type": "error", "message": "Missing session_id"})
                    continue

                # Verify session belongs to this tenant
                conn = await get_db()
                try:
                    session = await conn.fetchrow("""
                        SELECT tenant_id FROM video_sessions
                        WHERE id = $1 AND tenant_id = $2
                    """, uuid.UUID(session_id), uuid.UUID(tenant_id))

                    if not session:
                        await websocket.send_json({"type": "error", "message": "Session not found or access denied"})
                        continue
                finally:
                    await db_pool.release(conn)
                
                if session_id not in active_connections:
                    active_connections[session_id] = set()
                active_connections[session_id].add(websocket)
                
                await websocket.send_json({"type": "authenticated", "session_id": session_id})
            
            elif message_type == "sdp-offer":
                if session_id and session_id in active_connections:
                    await broadcast_to_session(session_id, {
                        "type": "sdp-offer",
                        "from": user_id,
                        "sdp": data.get("sdp")
                    }, websocket)
            
            elif message_type == "sdp-answer":
                if session_id and session_id in active_connections:
                    await broadcast_to_session(session_id, {
                        "type": "sdp-answer",
                        "from": user_id,
                        "sdp": data.get("sdp")
                    }, websocket)
            
            elif message_type == "ice-candidate":
                if session_id and session_id in active_connections:
                    await broadcast_to_session(session_id, {
                        "type": "ice-candidate",
                        "from": user_id,
                        "candidate": data.get("candidate"),
                        "sdp_mid": data.get("sdp_mid"),
                        "sdp_m_line_index": data.get("sdp_m_line_index")
                    }, websocket)
            
            elif message_type == "screen-share-start":
                if session_id and session_id in active_connections:
                    await broadcast_to_session(session_id, {
                        "type": "screen-share-start",
                        "from": user_id
                    }, websocket)
            
            elif message_type == "screen-share-stop":
                if session_id and session_id in active_connections:
                    await broadcast_to_session(session_id, {
                        "type": "screen-share-stop",
                        "from": user_id
                    }, websocket)
            
            elif message_type == "cobrowse-url":
                if session_id and session_id in active_connections:
                    await broadcast_to_session(session_id, {
                        "type": "cobrowse-url",
                        "from": user_id,
                        "url": data.get("url")
                    }, websocket)
            
            elif message_type == "cobrowse-dom":
                if session_id and session_id in active_connections:
                    await broadcast_to_session(session_id, {
                        "type": "cobrowse-dom",
                        "from": user_id,
                        "dom_state": data.get("dom_state")
                    }, websocket)
    
    except WebSocketDisconnect:
        if session_id and session_id in active_connections:
            active_connections[session_id].discard(websocket)
            if not active_connections[session_id]:
                del active_connections[session_id]
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


async def broadcast_to_session(session_id: str, message: Dict, exclude_sender: Optional[WebSocket] = None):
    if session_id not in active_connections:
        return
    
    disconnected = set()
    for connection in active_connections[session_id]:
        if exclude_sender and connection == exclude_sender:
            continue
        try:
            await connection.send_json(message)
        except Exception:
            disconnected.add(connection)
    
    for connection in disconnected:
        active_connections[session_id].discard(connection)


@app.get("/video/analytics")
async def get_analytics(
    session_id: Optional[str] = None,
    auth: AuthContext = Depends(verify_token)
) -> Dict:
    conn = await get_db()
    try:
        if session_id:
            rows = await conn.fetch("""
                SELECT metric_type, AVG(metric_value) as avg_value, MAX(metric_value) as max_value
                FROM analytics
                WHERE session_id = $1 AND tenant_id = $2
                GROUP BY metric_type
            """, uuid.UUID(session_id), uuid.UUID(auth.tenant_id) if isinstance(auth.tenant_id, str) else auth.tenant_id)
        else:
            rows = await conn.fetch("""
                SELECT session_id, metric_type, AVG(metric_value) as avg_value, COUNT(*) as sample_count
                FROM analytics
                WHERE tenant_id = $1
                GROUP BY session_id, metric_type
                ORDER BY session_id DESC
            """, uuid.UUID(auth.tenant_id) if isinstance(auth.tenant_id, str) else auth.tenant_id)
        
        metrics = [
            {
                "metric_type": row["metric_type"],
                "avg_value": float(row.get("avg_value") or 0),
                "max_value": float(row.get("max_value") or 0),
                "sample_count": row.get("sample_count") or 0
            }
            for row in rows
        ]
        
        return {"analytics": metrics}
    finally:
        await db_pool.release(conn)


@app.get("/video/health")
async def health_check() -> Dict:
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        conn = await asyncio.wait_for(db_pool.acquire(), timeout=5)
        await conn.fetchval("SELECT 1")
        await db_pool.release(conn)
        
        return {
            "status": "healthy",
            "database": "connected",
            "active_sessions": len(active_connections),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Health check failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn


    port = int(os.getenv("PORT", 9032))
    uvicorn.run(app, host="0.0.0.0", port=port)
