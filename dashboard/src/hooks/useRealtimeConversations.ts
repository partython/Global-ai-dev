'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useWebSocket, WSMessage } from './useWebSocket';

// ─── Types ───────────────────────────────────────────────────────────────────

interface RealtimeMessage {
  id: string;
  sender: 'customer' | 'ai' | 'system';
  content: string;
  timestamp: string;
  conversation_id: string;
}

interface TypingState {
  [conversationId: string]: {
    isTyping: boolean;
    senderType: string;
    timeout?: ReturnType<typeof setTimeout>;
  };
}

interface ConversationEvent {
  type: 'new_message' | 'conversation_updated' | 'conversation_closed' | 'conversation_assigned' | 'typing';
  conversation_id: string;
  data: Record<string, any>;
}

interface UseRealtimeConversationsOptions {
  /** Currently selected conversation ID */
  activeConversationId?: string | null;
  /** Called when a new message arrives */
  onNewMessage?: (message: RealtimeMessage) => void;
  /** Called when a conversation list should be refreshed */
  onConversationUpdate?: (event: ConversationEvent) => void;
  /** Called when typing indicator changes */
  onTypingChange?: (conversationId: string, isTyping: boolean, senderType: string) => void;
}

// ─── Hook ────────────────────────────────────────────────────────────────────

export function useRealtimeConversations({
  activeConversationId,
  onNewMessage,
  onConversationUpdate,
  onTypingChange,
}: UseRealtimeConversationsOptions = {}) {
  const [typingStates, setTypingStates] = useState<TypingState>({});
  const typingTimeoutsRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const handlersRef = useRef({ onNewMessage, onConversationUpdate, onTypingChange });

  useEffect(() => {
    handlersRef.current = { onNewMessage, onConversationUpdate, onTypingChange };
  }, [onNewMessage, onConversationUpdate, onTypingChange]);

  // Handle incoming WebSocket messages
  const handleMessage = useCallback((msg: WSMessage) => {
    switch (msg.type) {
      case 'message': {
        const newMsg: RealtimeMessage = {
          id: msg.data.id || msg.message_id || `ws-${Date.now()}`,
          sender: msg.data.sender_type || msg.sender_type || 'system',
          content: msg.data.content || msg.data.text || '',
          timestamp: msg.data.timestamp || msg.timestamp || new Date().toISOString(),
          conversation_id: msg.data.conversation_id || msg.room?.replace('conversation:', '') || '',
        };

        handlersRef.current.onNewMessage?.(newMsg);
        handlersRef.current.onConversationUpdate?.({
          type: 'new_message',
          conversation_id: newMsg.conversation_id,
          data: msg.data,
        });
        break;
      }

      case 'typing_start': {
        const convId = msg.data.conversation_id || msg.room?.replace('conversation:', '') || '';
        const senderType = msg.data.sender_type || msg.sender_type || 'ai';

        // Clear existing timeout for this conversation
        if (typingTimeoutsRef.current[convId]) {
          clearTimeout(typingTimeoutsRef.current[convId]);
        }

        setTypingStates((prev) => ({
          ...prev,
          [convId]: { isTyping: true, senderType },
        }));
        handlersRef.current.onTypingChange?.(convId, true, senderType);

        // Auto-clear typing after 5 seconds
        typingTimeoutsRef.current[convId] = setTimeout(() => {
          setTypingStates((prev) => ({
            ...prev,
            [convId]: { isTyping: false, senderType },
          }));
          handlersRef.current.onTypingChange?.(convId, false, senderType);
        }, 5000);
        break;
      }

      case 'typing_stop': {
        const convId = msg.data.conversation_id || msg.room?.replace('conversation:', '') || '';
        const senderType = msg.data.sender_type || msg.sender_type || 'ai';

        if (typingTimeoutsRef.current[convId]) {
          clearTimeout(typingTimeoutsRef.current[convId]);
        }

        setTypingStates((prev) => ({
          ...prev,
          [convId]: { isTyping: false, senderType },
        }));
        handlersRef.current.onTypingChange?.(convId, false, senderType);
        break;
      }

      case 'conversation_closed':
      case 'conversation_assigned':
      case 'conversation_transferred':
      case 'conversation_updated': {
        const convId = msg.data.conversation_id || msg.room?.replace('conversation:', '') || '';
        handlersRef.current.onConversationUpdate?.({
          type: msg.type === 'conversation_closed' ? 'conversation_closed'
            : msg.type === 'conversation_assigned' ? 'conversation_assigned'
            : 'conversation_updated',
          conversation_id: convId,
          data: msg.data,
        });
        break;
      }

      case 'message_read': {
        const convId = msg.data.conversation_id || '';
        handlersRef.current.onConversationUpdate?.({
          type: 'conversation_updated',
          conversation_id: convId,
          data: { ...msg.data, read: true },
        });
        break;
      }

      default:
        break;
    }
  }, []);

  // Build WS path — if we have an active conversation, connect to that room
  const wsPath = activeConversationId
    ? `/ws/conversations/${activeConversationId}`
    : `/ws/notifications`;

  const {
    connectionState,
    isConnected,
    send,
    connect,
    disconnect,
  } = useWebSocket({
    path: wsPath,
    onMessage: handleMessage,
  });

  // Send typing indicator
  const sendTyping = useCallback(
    (conversationId: string, isTyping: boolean) => {
      send({
        type: isTyping ? 'typing_start' : 'typing_stop',
        room: `conversation:${conversationId}`,
        data: { conversation_id: conversationId },
      });
    },
    [send]
  );

  // Send a chat message via WebSocket (optimistic)
  const sendMessage = useCallback(
    (conversationId: string, content: string) => {
      return send({
        type: 'message',
        room: `conversation:${conversationId}`,
        data: {
          conversation_id: conversationId,
          content,
          sender_type: 'agent',
        },
      });
    },
    [send]
  );

  // Mark conversation as read
  const markRead = useCallback(
    (conversationId: string) => {
      send({
        type: 'message_read',
        room: `conversation:${conversationId}`,
        data: { conversation_id: conversationId },
      });
    },
    [send]
  );

  // Cleanup typing timeouts on unmount
  useEffect(() => {
    return () => {
      Object.values(typingTimeoutsRef.current).forEach(clearTimeout);
    };
  }, []);

  return {
    connectionState,
    isConnected,
    typingStates,
    sendTyping,
    sendMessage,
    markRead,
    connect,
    disconnect,
  };
}

export default useRealtimeConversations;
