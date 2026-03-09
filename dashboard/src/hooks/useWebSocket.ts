'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { useAuthStore } from '@/stores/auth';

// ─── Security Constants ──────────────────────────────────────────────────────

/** Maximum inbound message size (10 KB) — drops anything larger */
const MAX_MESSAGE_SIZE = 10 * 1024;

/** Maximum outbound messages per window */
const MAX_SEND_RATE = 10;
const SEND_RATE_WINDOW_MS = 1000;

/**
 * Allowed WebSocket hostnames.
 * The hook will refuse to open a connection to any host not in this list.
 */
const ALLOWED_WS_ORIGINS = [
  'api.priyaai.com',
  'app.priyaai.com',
  'dashboard.priyaai.com',
  'api-staging.priyaai.com',
  'api.priya-global.com',
  'dashboard.priya-global.com',
  'localhost',
  '127.0.0.1',
];

// ─── Types ───────────────────────────────────────────────────────────────────

export type WSEventType =
  | 'connect'
  | 'disconnect'
  | 'reconnect'
  | 'message'
  | 'message_update'
  | 'message_delete'
  | 'message_read'
  | 'typing_start'
  | 'typing_stop'
  | 'presence_update'
  | 'user_online'
  | 'user_offline'
  | 'conversation_assigned'
  | 'conversation_closed'
  | 'conversation_transferred'
  | 'conversation_updated'
  | 'agent_status'
  | 'notification'
  | 'alert'
  | 'system_alert'
  | 'dashboard_update'
  | 'metrics_update'
  | 'ping'
  | 'pong'
  | 'error'
  | 'ack'
  | 'auth'
  | 'auth_ack'
  | 'auth_error';

export interface WSMessage {
  type: WSEventType;
  message_id?: string;
  room?: string;
  data: Record<string, any>;
  sender_id?: string;
  sender_type?: string;
  timestamp?: string;
}

export type WSEventHandler = (message: WSMessage) => void;

export type ConnectionState = 'connecting' | 'connected' | 'disconnected' | 'reconnecting' | 'authenticating';

interface UseWebSocketOptions {
  /** WebSocket URL path (appended to base WS URL) */
  path: string;
  /** Auto-connect on mount (default: true) */
  autoConnect?: boolean;
  /** Max reconnection attempts (default: 10) */
  maxReconnectAttempts?: number;
  /** Base reconnect delay in ms (default: 1000, doubles each attempt) */
  reconnectDelay?: number;
  /** Heartbeat interval in ms (default: 30000) */
  heartbeatInterval?: number;
  /** Event handlers by type */
  onMessage?: WSEventHandler;
  onConnect?: () => void;
  onDisconnect?: (event: CloseEvent) => void;
  onError?: (error: Event) => void;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * Build the WebSocket URL **without** embedding the JWT token.
 * The token is sent as the first message after connection (first-message auth).
 * Returns null if the resolved hostname is not in the allow-list.
 */
function getWSUrl(path: string): string | null {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:9000';
  const wsBase = apiUrl.replace(/^http/, 'ws');
  const fullUrl = `${wsBase}${path}`;

  // Validate hostname against allow-list
  try {
    const parsed = new URL(fullUrl);
    const hostname = parsed.hostname;
    if (!ALLOWED_WS_ORIGINS.includes(hostname)) {
      console.error(`[WS] Blocked connection to untrusted host: ${hostname}`);
      return null;
    }
  } catch {
    console.error(`[WS] Invalid URL: ${fullUrl}`);
    return null;
  }

  return fullUrl;
}

// ─── Hook ────────────────────────────────────────────────────────────────────

export function useWebSocket({
  path,
  autoConnect = true,
  maxReconnectAttempts = 10,
  reconnectDelay = 1000,
  heartbeatInterval = 30000,
  onMessage,
  onConnect,
  onDisconnect,
  onError,
}: UseWebSocketOptions) {
  const { token } = useAuthStore();
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const heartbeatTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const handlersRef = useRef({ onMessage, onConnect, onDisconnect, onError });
  const isAuthenticatedRef = useRef(false);
  const authRejectedRef = useRef(false);

  // Rate-limiter state
  const sendTimestampsRef = useRef<number[]>([]);

  const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected');
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null);

  // Keep handlers ref current without causing reconnects
  useEffect(() => {
    handlersRef.current = { onMessage, onConnect, onDisconnect, onError };
  }, [onMessage, onConnect, onDisconnect, onError]);

  // ── Rate limiter ──────────────────────────────────────────────────────────

  const isRateLimited = useCallback(() => {
    const now = Date.now();
    // Prune old timestamps
    sendTimestampsRef.current = sendTimestampsRef.current.filter(
      (t) => now - t < SEND_RATE_WINDOW_MS
    );
    return sendTimestampsRef.current.length >= MAX_SEND_RATE;
  }, []);

  // ── Heartbeat ─────────────────────────────────────────────────────────────

  const startHeartbeat = useCallback(() => {
    if (heartbeatTimerRef.current) clearInterval(heartbeatTimerRef.current);

    heartbeatTimerRef.current = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'ping', timestamp: new Date().toISOString() }));
      }
    }, heartbeatInterval);
  }, [heartbeatInterval]);

  const stopHeartbeat = useCallback(() => {
    if (heartbeatTimerRef.current) {
      clearInterval(heartbeatTimerRef.current);
      heartbeatTimerRef.current = null;
    }
  }, []);

  // ── Connect ───────────────────────────────────────────────────────────────

  const connect = useCallback(() => {
    if (!token) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    if (authRejectedRef.current) return; // Don't reconnect after auth rejection

    // Clean up existing connection
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
    }

    isAuthenticatedRef.current = false;

    setConnectionState(
      reconnectAttemptsRef.current > 0 ? 'reconnecting' : 'connecting'
    );

    const url = getWSUrl(path);
    if (!url) {
      setConnectionState('disconnected');
      return;
    }

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        // ── SECURITY: First-message auth ──
        // Send token as the very first message instead of embedding in URL.
        // This prevents the JWT from leaking in server access logs, proxy
        // logs, referrer headers, and browser history.
        setConnectionState('authenticating');
        ws.send(JSON.stringify({
          type: 'auth',
          token,
          timestamp: new Date().toISOString(),
        }));
      };

      ws.onmessage = (event) => {
        // ── SECURITY: Message size guard ──
        if (typeof event.data === 'string' && event.data.length > MAX_MESSAGE_SIZE) {
          console.warn(`[WS] Dropped oversized message (${event.data.length} bytes)`);
          return;
        }

        try {
          const message: WSMessage = JSON.parse(event.data);

          // ── Auth flow ─────────────────────────────────────────────────
          if (!isAuthenticatedRef.current) {
            if (message.type === 'auth_ack' || message.type === 'connect') {
              // Server acknowledged auth — we're fully connected
              isAuthenticatedRef.current = true;
              setConnectionState('connected');
              reconnectAttemptsRef.current = 0;
              startHeartbeat();
              handlersRef.current.onConnect?.();
              return;
            }
            if (message.type === 'auth_error' || message.type === 'error') {
              // Server rejected auth — close and don't reconnect
              console.error('[WS] Authentication rejected:', message.data?.reason || 'unknown');
              authRejectedRef.current = true;
              ws.close(1000, 'Auth rejected');
              return;
            }
            // While waiting for auth ack, ignore all other messages
            return;
          }

          // ── Normal message handling ───────────────────────────────────

          // Handle pong silently
          if (message.type === 'pong') return;

          setLastMessage(message);
          handlersRef.current.onMessage?.(message);
        } catch {
          // Non-JSON message, ignore
        }
      };

      ws.onclose = (event) => {
        setConnectionState('disconnected');
        isAuthenticatedRef.current = false;
        stopHeartbeat();
        handlersRef.current.onDisconnect?.(event);

        // ── SECURITY: Don't reconnect on auth rejection (1008) ──
        if (event.code === 1008 || authRejectedRef.current) {
          console.warn('[WS] Connection closed due to policy violation — not reconnecting');
          return;
        }

        // Auto-reconnect unless intentionally closed (code 1000)
        if (event.code !== 1000 && reconnectAttemptsRef.current < maxReconnectAttempts) {
          const delay = reconnectDelay * Math.pow(2, reconnectAttemptsRef.current);
          reconnectAttemptsRef.current += 1;

          reconnectTimerRef.current = setTimeout(() => {
            connect();
          }, Math.min(delay, 30000)); // Cap at 30s
        }
      };

      ws.onerror = (error) => {
        handlersRef.current.onError?.(error);
      };
    } catch {
      setConnectionState('disconnected');
    }
  }, [token, path, maxReconnectAttempts, reconnectDelay, startHeartbeat, stopHeartbeat]);

  // ── Disconnect ──────────────────────────────────────────────────────────

  const disconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    stopHeartbeat();
    reconnectAttemptsRef.current = maxReconnectAttempts; // Prevent auto-reconnect
    isAuthenticatedRef.current = false;

    if (wsRef.current) {
      wsRef.current.close(1000, 'Client disconnect');
      wsRef.current = null;
    }
    setConnectionState('disconnected');
  }, [maxReconnectAttempts, stopHeartbeat]);

  // ── Send (rate-limited + size-checked) ────────────────────────────────

  const send = useCallback((message: Partial<WSMessage>) => {
    if (wsRef.current?.readyState !== WebSocket.OPEN || !isAuthenticatedRef.current) {
      return false;
    }

    // Rate limit check
    if (isRateLimited()) {
      console.warn('[WS] Send rate limited — try again shortly');
      return false;
    }

    const payload = JSON.stringify({
      ...message,
      timestamp: new Date().toISOString(),
    });

    // Size check
    if (payload.length > MAX_MESSAGE_SIZE) {
      console.warn(`[WS] Outbound message too large (${payload.length} bytes)`);
      return false;
    }

    wsRef.current.send(payload);
    sendTimestampsRef.current.push(Date.now());
    return true;
  }, [isRateLimited]);

  // ── Auto-connect on mount ─────────────────────────────────────────────

  useEffect(() => {
    // Reset auth rejection flag when token changes (user re-authenticates)
    authRejectedRef.current = false;

    if (autoConnect && token) {
      connect();
    }

    return () => {
      disconnect();
    };
  }, [autoConnect, token]); // eslint-disable-line react-hooks/exhaustive-deps

  return {
    connectionState,
    lastMessage,
    connect,
    disconnect,
    send,
    isConnected: connectionState === 'connected',
  };
}

export default useWebSocket;
