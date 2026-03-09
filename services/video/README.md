# Video Chat Service

A multi-tenant SaaS video chat microservice built with FastAPI, asyncpg, and WebRTC signaling.

## Features

1. **Video Session Management**
   - Create and manage video rooms
   - Support for scheduled sessions
   - Recording consent tracking
   - Configurable max participants

2. **WebRTC Signaling**
   - STUN/TURN server configuration from environment
   - ICE candidate exchange via WebSocket
   - SDP offer/answer relay between peers

3. **Screen Sharing**
   - Enable/disable screen share signals
   - Broadcast screen share state to all participants

4. **Co-browsing**
   - Shared URL state synchronization
   - DOM state sync for customer support scenarios

5. **Recording**
   - Start/stop recording control
   - Storage management with path tracking
   - File size and duration metadata

6. **Analytics**
   - Session duration tracking
   - Quality metrics collection
   - Drop rate monitoring
   - Aggregated analytics per session and tenant

## API Endpoints

- `POST /video/sessions` - Create a video session
- `GET /video/sessions` - List sessions (with pagination)
- `GET /video/sessions/{id}` - Get session details with participants
- `POST /video/sessions/{id}/join` - Join a session
- `POST /video/sessions/{id}/leave` - Leave a session
- `POST /video/sessions/{id}/record` - Control recording (start/stop)
- `WebSocket /ws/signaling` - WebRTC signaling channel
- `GET /video/analytics` - Get session analytics
- `GET /video/health` - Health check endpoint

## Environment Variables

- `PORT` - Service port (default: 9032)
- `DATABASE_URL` - PostgreSQL connection URL
- `JWT_SECRET` - JWT signing secret
- `STUN_SERVER` - STUN server URL (default: stun:stun.l.google.com:19302)
- `TURN_SERVER` - TURN server URL
- `TURN_USERNAME` - TURN server username
- `TURN_PASSWORD` - TURN server password
- `CORS_ORIGINS` - Comma-separated list of allowed CORS origins

## Authentication

- HTTPBearer token-based authentication
- JWT payload includes: tenant_id, user_id, email
- Tenant RLS enforced on all database queries
- Token verification on all endpoints except health check

## Database Schema

- `video_sessions` - Video session records
- `session_participants` - Session participant tracking
- `recordings` - Recording metadata
- `analytics` - Performance and quality metrics

## WebSocket Signaling Messages

- `auth` - Authenticate WebSocket connection
- `sdp-offer` - Send SDP offer
- `sdp-answer` - Send SDP answer
- `ice-candidate` - Send ICE candidate
- `screen-share-start` - Signal screen share start
- `screen-share-stop` - Signal screen share end
- `cobrowse-url` - Share URL for co-browsing
- `cobrowse-dom` - Share DOM state for co-browsing

## Implementation Details

- Line count: 580 lines
- Fully async with asyncpg connection pooling
- Tenant-level RLS on all data
- No hardcoded secrets (all from os.getenv)
- CORS configurable from environment
- Multi-tenant support with tenant_id isolation
