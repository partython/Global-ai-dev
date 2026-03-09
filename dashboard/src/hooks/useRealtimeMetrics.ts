'use client';

import { useCallback, useState } from 'react';
import { useWebSocket, WSMessage } from './useWebSocket';

// ─── Types ───────────────────────────────────────────────────────────────────

export interface RealtimeMetrics {
  active_conversations: number;
  messages_per_minute: number;
  queue_depth_per_channel: Record<string, number>;
  timestamp: string;
}

interface UseRealtimeMetricsOptions {
  /** Whether to auto-connect (default: true) */
  enabled?: boolean;
  /** Called when new metrics arrive */
  onMetricsUpdate?: (metrics: RealtimeMetrics) => void;
}

// ─── Hook ────────────────────────────────────────────────────────────────────

export function useRealtimeMetrics({
  enabled = true,
  onMetricsUpdate,
}: UseRealtimeMetricsOptions = {}) {
  const [metrics, setMetrics] = useState<RealtimeMetrics | null>(null);

  const handleMessage = useCallback(
    (msg: WSMessage) => {
      if (msg.type === 'metrics_update' || msg.data?.active_conversations !== undefined) {
        const update: RealtimeMetrics = {
          active_conversations: msg.data.active_conversations ?? 0,
          messages_per_minute: msg.data.messages_per_minute ?? 0,
          queue_depth_per_channel: msg.data.queue_depth_per_channel ?? {},
          timestamp: msg.data.timestamp || msg.timestamp || new Date().toISOString(),
        };
        setMetrics(update);
        onMetricsUpdate?.(update);
      }
    },
    [onMetricsUpdate]
  );

  const { connectionState, isConnected } = useWebSocket({
    path: '/analytics/ws/metrics',
    autoConnect: enabled,
    onMessage: handleMessage,
  });

  return {
    metrics,
    connectionState,
    isConnected,
  };
}

export default useRealtimeMetrics;
